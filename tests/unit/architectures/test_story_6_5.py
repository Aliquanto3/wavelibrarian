"""Story 6.5 : Architecture `cag` (préchargement du Corpus dans le cache de prompt)."""

import json
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.cag import Cag
from wavelibrarian.config.resolve import Collecte
from wavelibrarian.config.validate import _verifier_capacites
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import (
    Anchor,
    Block,
    CorpusProfile,
    ParsedCorpus,
    ParsedDocument,
    QuestionInput,
    Usage,
)
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache


class _ProviderPalier512(FakeProvider):
    """Faux provider qui applique `min_cacheable_tokens` : sous 512 tokens, rien n'est lu."""

    def _usage(self, request: LLMRequest, sortie: str) -> Usage:
        usage = super()._usage(request, sortie)
        if len(request.system.split()) < 512:
            return Usage(
                input_tokens=usage.input_tokens + usage.cache_read_tokens,
                output_tokens=usage.output_tokens,
            )
        return usage


def _ctx(tmp_path: Path, provider: FakeProvider, cle: str) -> RunCtx:
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={cle: provider}
    )
    c.parser = "markdown"
    c.provider = provider  # type: ignore[attr-defined]
    return c


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    with _ctx(tmp_path, FakeProvider(), "fake") as c:
        yield c


def _arch(ctx: RunCtx, **params: Any) -> Any:
    return ctx.build("architecture", ComponentSpec(name="cag", params=params))


def _question(texte: str = "Que sait-on de la guilde Orvane ?") -> QuestionInput:
    return QuestionInput(question_id="q-001", text=texte, lang="fr")


def _spans(ctx: RunCtx) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    if not chemin.exists():
        return []
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]


def _llm(ctx: RunCtx, step: str) -> list[dict[str, Any]]:
    return [s for s in _spans(ctx) if s.get("wl.kind") == "llm" and s["wl.step"] == step]


def _construire(ctx: RunCtx, corpus: ParsedCorpus, home: Path, **params: Any) -> Any:
    arch, _ = IndexCache(home).build(ctx, lambda: _arch(ctx, **params), corpus)
    return arch


def _profil(n_tokens: int) -> CorpusProfile:
    return CorpusProfile(
        corpus_id="c",
        fingerprint="f",
        parser="markdown",
        tokenizer="approx",
        n_documents=1,
        n_tokens=n_tokens,
        mean_tokens_per_document=float(n_tokens),
        heading_depth_max=1,
        heading_depth_mean=1.0,
        link_density=0.0,
        table_share=0.0,
        images_per_document=0.0,
        dominant_lang="fr",
        langs={"fr": 1},
        formats={"markdown": 1},
        volatility="low",
    )


def _ancrages(corpus: ParsedCorpus) -> list[str]:
    return [a for d in corpus.documents for a in d.anchors if corpus.anchor_text(a).strip()]


def _petit_corpus() -> ParsedCorpus:
    """Un Document de deux Ancrages, bien sous les 512 tokens de `min_cacheable_tokens`."""
    ancres = {
        a: Anchor(anchor_id=a, doc_id="d", source_path="d.md", heading_path=(a[-1],))
        for a in ("d#h/a", "d#h/b")
    }
    blocs = tuple(Block(text=f"Texte court {a}.", anchor_id=a, kind="text") for a in ancres)
    doc = ParsedDocument(
        doc_id="d", source_path="d.md", format="markdown", lang="fr", blocks=blocs, anchors=ancres
    )
    return ParsedCorpus(corpus_id="petit", fingerprint="fp-petit", documents=(doc,))


def _espion(ctx: RunCtx, vues: list[LLMRequest]) -> None:
    def sortie(req: LLMRequest) -> str:
        vues.append(req)
        return "ok"

    ctx.provider.script("generate", "cag.preload", sortie)  # type: ignore[attr-defined]


def test_enregistrement_et_capacites() -> None:
    assert registry.get("architecture", "cag") is Cag
    assert Cag.capabilities.requires_prompt_cache is True
    assert Cag.capabilities.full_corpus_in_prompt is True
    assert Cag.capabilities.retrieval_method == "cited"


def test_index_ecrit_un_bloc_par_ancrage_et_load_precharge_au_poste_indexing(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _arch(ctx)
    dossier = tmp_path / "idx"
    arch.index(minicorpus, dossier)
    attendus = _ancrages(minicorpus)
    lignes = (dossier / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == len(attendus)  # un Passage par Ancrage
    assert _llm(ctx, "cag.preload") == []  # `index` n'appelle aucun LLM

    vues: list[LLMRequest] = []
    _espion(ctx, vues)
    neuve = _arch(ctx)
    with ctx.scope(post="indexing"):
        neuve.load(dossier)
    assert len(vues) == 1
    req = vues[0]
    assert req.cache_system is True
    assert all(minicorpus.anchor_text(a).strip() in req.system for a in attendus)
    assert all(f"({a})" in req.system for a in attendus)
    spans = _llm(ctx, "cag.preload")
    assert len(spans) == 1 and spans[0]["wl.post"] == "indexing"
    assert spans[0]["wl.usage.cache_write_tokens"] == 0  # le Faux LLM ne facture pas d'écriture


def test_index_construit_ou_servi_par_le_cache_prechargent_de_la_meme_facon(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    vues: list[LLMRequest] = []
    _espion(ctx, vues)
    _construire(ctx, minicorpus, home)  # miss : index puis load
    _construire(ctx, minicorpus, home)  # hit : load seul
    assert len(vues) == 1 and vues[0].cache_system  # le miss précharge
    # le hit précharge aussi : un second appel `cag.preload` part, ici servi par le Cache de
    # réponses de la passerelle (même requête), donc sans seconde sortie scénarisée
    spans = _llm(ctx, "cag.preload")
    assert [s["wl.post"] for s in spans] == ["indexing", "indexing"]
    assert [s["wl.llm_cache_hit"] for s in spans] == [False, True]


def test_seconde_question_lit_le_cache_trace_a_part_et_reponse_cited(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path / "home")
    reps = []
    for _ in range(2):
        with ctx.scope(post="query", question_id="q-001"):
            reps.append(arch.answer(_question()))
    q = [s for s in _llm(ctx, "generate") if s["wl.post"] == "query"]
    assert len(q) == 2
    assert q[1]["wl.usage.cache_read_tokens"] > 0
    # le system lu en cache n'est pas compté comme entrée : champ à part
    assert q[1]["gen_ai.usage.input_tokens"] < q[1]["wl.usage.cache_read_tokens"]
    assert all(r.retrieval_method == "cited" for r in reps)
    assert reps[1].citations  # le Faux LLM cite par défaut au moins un bloc


def test_generator_sans_prompt_cache_refuse_a_la_validation(ctx: RunCtx) -> None:
    erreurs: list[ConfigError] = []
    modeles = ["minicpm5:1b-q4_k_m", "fake-llm-a"]
    col = Collecte(architecture=Cag, producers=modeles, chemin="configurations[0]")
    _verifier_capacites(col, ctx.catalog, set(modeles), erreurs)
    assert len(erreurs) == 1
    assert "prompt_cache: false" in erreurs[0].message and "minicpm5" in erreurs[0].message


def test_inapplicable_au_dela_de_la_fenetre_et_du_palier_sans_appel(ctx: RunCtx) -> None:
    fenetre = _arch(ctx, generator={"name": "llm", "params": {"model": "fake-llm-a"}})
    res = fenetre.check(_profil(120_000))
    assert res.applicable is False
    assert res.reason is not None and "fenêtre" in res.reason and "100000" in res.reason
    assert fenetre.check(_profil(10_000)).applicable is True
    haiku = _arch(ctx, generator={"name": "llm", "params": {"model": "claude-haiku-5-5"}})
    res = haiku.check(_profil(80_000))  # 80 000 x 1,5 = 120 000 tokens estimés
    assert res.applicable is False
    assert res.reason is not None and "palier" in res.reason and "100000" in res.reason
    assert haiku.check(_profil(60_000)).applicable is True
    assert _spans(ctx) == []  # aucun appel, aucune trace


def test_corpus_sous_min_cacheable_tokens_reussit_sans_cache(
    tmp_path: Path,
) -> None:
    petit = _petit_corpus()
    with _ctx(tmp_path, _ProviderPalier512(), "anthropic") as c:
        modele = {"name": "llm", "params": {"model": "claude-haiku-5-5"}}
        arch = _construire(c, petit, tmp_path / "home", generator=modele)
        reps = []
        for _ in range(2):
            with c.scope(post="query", question_id="q-001"):
                reps.append(arch.answer(_question()))
        assert reps[-1].retrieval_method == "cited"
        spans = _llm(c, "cag.preload") + _llm(c, "generate")
        assert len(spans) == 3
        assert all(s["wl.usage.cache_read_tokens"] == 0 for s in spans)
        assert all(s["wl.status"] == "ok" for s in spans)


def test_cache_system_faux_refuse_et_corpus_vide_sans_prechargement(
    ctx: RunCtx, tmp_path: Path
) -> None:
    mauvais = {"name": "llm", "params": {"model": "fake-llm-a", "cache_system": False}}
    with pytest.raises(Exception, match="cache_system"):
        _arch(ctx, generator=mauvais)
    vide = ParsedCorpus(corpus_id="v", fingerprint="fp", documents=())
    _construire(ctx, vide, tmp_path / "home")
    assert _llm(ctx, "cag.preload") == []

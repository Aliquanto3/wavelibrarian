"""Story 6.3 : Architecture `hyde` (recherche par la réponse hypothétique)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.hyde import Hyde
from wavelibrarian.architectures.naive_rag import NaiveRag
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache

PETITS = {"name": "fixed_tokens", "params": {"size": 40, "overlap": 5}}
MARQUEUR = "zorglubien"
REPONSE = '{"answer": "Réponse.", "citations": ["S1"], "abstain": false}'


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.parser = "markdown"
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


def _arch(ctx: RunCtx, nom: str = "hyde", **params: Any) -> Any:
    params.setdefault("embedder", {"name": "fake"})
    params.setdefault("chunker", PETITS)
    return ctx.build("architecture", ComponentSpec(name=nom, params=params))


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def _repondre(arch: Any, ctx: RunCtx) -> Any:
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(_question())


def _spans(ctx: RunCtx) -> list[dict[str, Any]]:
    lignes = (ctx.run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lignes]


def _construire(ctx: RunCtx, corpus: ParsedCorpus, tmp_path: Path, **params: Any) -> Any:
    ctx.provider.script("generate", "generate*", REPONSE)  # type: ignore[attr-defined]
    arch, _ = IndexCache(tmp_path / "home").build(ctx, lambda: _arch(ctx, **params), corpus)
    return arch


def _embed(arch: Any, ctx: RunCtx, *textes: str) -> Any:
    with ctx.scope(post="query"):
        return arch.embedder.embed_queries(list(textes))


def _espionner_vecteur(arch: Any) -> list[Any]:
    """Vecteurs passés au Retriever, un par appel."""
    vus: list[Any] = []
    origine = arch.retriever.retrieve

    def espion(query: str, k: int, index: Any, query_vector: Any = None) -> Any:
        vus.append(query_vector)
        return origine(query, k, index, query_vector=query_vector)

    arch.retriever.retrieve = espion
    return vus


def test_enregistrement_defauts_et_meme_index_que_naive_rag(ctx: RunCtx) -> None:
    assert registry.get("architecture", "hyde") is Hyde
    assert Hyde.capabilities == NaiveRag.capabilities
    h = _arch(ctx)
    assert h.params.mix_question is False and h.params.k == 5
    assert {"k", "mix_question"} <= Hyde.query_params
    # même index que naive_rag : mêmes paramètres d'index
    assert h.index_key() == _arch(ctx, "naive_rag").index_key()
    assert h.embedder_dim() == 64


def test_hyde_appelle_le_role_hyde_au_poste_query_hors_du_span_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path)
    avant = len(_spans(ctx))
    _repondre(arch, ctx)
    nouveaux = _spans(ctx)[avant:]
    hyde = [s for s in nouveaux if s["wl.step"] == "hyde"]
    gen = [s for s in nouveaux if s["wl.step"] == "generate"]
    assert len(hyde) == 1 and len(gen) == 1
    assert hyde[0]["wl.kind"] == "llm" and hyde[0]["wl.post"] == "query"
    assert gen[0]["wl.post"] == "query"
    assert any(s["wl.kind"] == "embed" and s["wl.post"] == "query" for s in nouveaux)


def test_le_vecteur_du_retriever_est_celui_de_la_reponse_hypothetique(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("hyde", "hyde", f"{MARQUEUR} tresor cache")  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path)
    vus = _espionner_vecteur(arch)
    _repondre(arch, ctx)
    attendu = _embed(arch, ctx, f"{MARQUEUR} tresor cache")[0]
    question = _embed(arch, ctx, _question().text)[0]
    assert len(vus) == 1
    np.testing.assert_allclose(vus[0], attendu)
    assert not np.allclose(vus[0], question)


def test_mix_question_moyenne_renormalisee_et_dans_query_params(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("hyde", "hyde", f"{MARQUEUR} tresor cache")  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path, mix_question=True)
    vus = _espionner_vecteur(arch)
    _repondre(arch, ctx)
    hyp = _embed(arch, ctx, f"{MARQUEUR} tresor cache")[0]
    question = _embed(arch, ctx, _question().text)[0]
    somme = hyp + question
    attendu = somme / np.linalg.norm(somme)
    np.testing.assert_allclose(vus[0], attendu, atol=1e-6)
    assert float(np.linalg.norm(vus[0])) == pytest.approx(1.0, abs=1e-6)
    assert "mix_question" in Hyde.query_params
    # mix_question n'entre pas dans la clé d'index : l'index est réutilisé
    assert arch.index_key() == _arch(ctx).index_key()


def test_la_reponse_hypothetique_n_entre_ni_dans_le_contexte_ni_dans_les_citations(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("hyde", "hyde", f"{MARQUEUR} tresor cache")  # type: ignore[attr-defined]
    vues: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        vues.append(req)
        return '{"answer": "Réponse.", "citations": ["S1", "S99"], "abstain": false}'

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    arch, _ = IndexCache(tmp_path / "home").build(ctx, lambda: _arch(ctx), minicorpus)
    rep = _repondre(arch, ctx)
    assert len(vues) == 1
    prompt = vues[0].system + "".join(m.content for m in vues[0].messages)
    assert MARQUEUR not in prompt and MARQUEUR not in json.dumps(vues[0].inputs)
    assert all(MARQUEUR not in s.passage.text for s in rep.retrieved)
    assert rep.citations and rep.invalid_citations == 1  # S99 hors contexte, retirée et comptée
    ancrages = {a for s in rep.retrieved for a in s.passage.anchor_ids}
    assert {c.anchor_id for c in rep.citations} <= ancrages


def test_hypothese_reprenant_les_mots_d_un_passage_donne_le_rang_1(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _construire(ctx, minicorpus, tmp_path)
    with ctx.scope(post="query"):  # recherche par la Question seule
        naif = arch.retriever.retrieve(_question().text, 5, arch._index)
    tete = naif[0].passage.passage_id
    cible = next(p for p in arch._index.passages.values() if p.passage_id != tete)
    ctx.provider.script("hyde", "hyde", cible.text)  # type: ignore[attr-defined]
    rep = _repondre(arch, ctx)
    assert rep.retrieved[0].passage.passage_id == cible.passage_id
    assert rep.retrieved[0].rank == 1


def test_reponse_hypothetique_vide_se_rabat_sur_la_question(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script("hyde", "hyde", "   ")  # type: ignore[attr-defined]
    arch = _construire(ctx, minicorpus, tmp_path, mix_question=True)
    vus = _espionner_vecteur(arch)
    _repondre(arch, ctx)
    np.testing.assert_allclose(vus[0], _embed(arch, ctx, _question().text)[0])


def test_retriever_lexical_refuse(ctx: RunCtx) -> None:
    with pytest.raises(ConfigError):
        _arch(ctx, retriever={"name": "lexical"})

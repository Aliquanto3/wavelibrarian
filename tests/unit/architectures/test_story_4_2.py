"""Story 4.2 : Baselines `no_context`, `long_context`, `bm25_only` et index lexical `bm25`."""

from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.bm25_only import Bm25Only
from wavelibrarian.architectures.long_context import LongContext
from wavelibrarian.architectures.no_context import NoContext
from wavelibrarian.components.chunkers.fixed_tokens import FixedTokenChunker
from wavelibrarian.components.lexical_indexes.bm25 import Bm25Index
from wavelibrarian.components.retrievers.lexical import LexicalRetriever
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import (
    Anchor,
    Block,
    CorpusProfile,
    ParsedCorpus,
    ParsedDocument,
    QuestionInput,
)
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import ArchitectureBase
from wavelibrarian.ports.components import ComponentSpec, LexicalIndex
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


def _arch(ctx: RunCtx, nom: str, **params: Any) -> Any:
    return ctx.build("architecture", ComponentSpec(name=nom, params=params))


def _question(texte: str = "Que sait-on de la guilde Orvane ?") -> QuestionInput:
    return QuestionInput(question_id="q-001", text=texte, lang="fr")


def _espionner(ctx: RunCtx) -> list[LLMRequest]:
    """Enregistre les requêtes `generate` puis rend la sortie par défaut du Faux LLM."""
    from wavelibrarian.llm.providers.fake import default_output

    vues: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        vues.append(req)
        return default_output("generate", req.inputs)

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    return vues


def _repondre(arch: ArchitectureBase, ctx: RunCtx, question: QuestionInput | None = None) -> Any:
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(question or _question())


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


def _corpus_synthetique(n_docs: int, n_ancrages: int, n_mots: int) -> ParsedCorpus:
    docs = []
    for d in range(n_docs):
        doc_id = f"doc{d}"
        ancres = {}
        blocs = []
        for a in range(n_ancrages):
            anchor_id = f"{doc_id}#h/s{a}"
            ancres[anchor_id] = Anchor(
                anchor_id=anchor_id,
                doc_id=doc_id,
                source_path=f"{doc_id}.md",
                heading_path=(f"s{a}",),
            )
            blocs.append(
                Block(
                    text=" ".join(f"mot{d}x{a}x{i}" for i in range(n_mots)),
                    anchor_id=anchor_id,
                    kind="text",
                )
            )
        docs.append(
            ParsedDocument(
                doc_id=doc_id,
                source_path=f"{doc_id}.md",
                format="markdown",
                lang="fr",
                blocks=tuple(blocs),
                anchors=ancres,
            )
        )
    return ParsedCorpus(corpus_id="synth", fingerprint="fp", documents=tuple(docs))


# --- no_context ------------------------------------------------------------------------------


def test_no_context_contexte_vide_et_aucun_fichier_hors_passages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("architecture", "no_context") is NoContext
    vues = _espionner(ctx)
    arch = _arch(ctx, "no_context")
    dossier = tmp_path / "idx"
    arch.index(minicorpus, dossier)
    assert [p.name for p in dossier.iterdir()] == ["passages.jsonl"]
    assert (dossier / "passages.jsonl").read_bytes() == b""
    neuve = _arch(ctx, "no_context")
    neuve.load(dossier)
    rep = _repondre(neuve, ctx)
    assert vues[0].inputs["blocks"] == {}  # le Generator reçoit un Contexte vide
    assert rep.retrieval_method == "none"
    assert rep.retrieved == ()
    assert rep.context_anchor_ids == () and rep.context_texts == ()
    assert rep.abstained is True  # le Faux LLM s'abstient sans contexte


# --- long_context ----------------------------------------------------------------------------


def test_long_context_prompt_complet_system_en_cache_et_citations(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("architecture", "long_context") is LongContext
    assert LongContext.capabilities.full_corpus_in_prompt is True
    vues: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        vues.append(req)
        return '{"answer": "Réponse.", "citations": ["S3", "S1", "S3", "S99"], "abstain": false}'

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    arch = _arch(
        ctx,
        "long_context",
        generator={"name": "llm", "params": {"model": "fake-llm-a", "cache_system": True}},
    )
    dossier = tmp_path / "idx"
    arch.index(minicorpus, dossier)
    neuve = _arch(
        ctx,
        "long_context",
        generator={"name": "llm", "params": {"model": "fake-llm-a", "cache_system": True}},
    )
    neuve.load(dossier)
    rep = _repondre(neuve, ctx)

    attendus = [
        a for d in minicorpus.documents for a in d.anchors if minicorpus.anchor_text(a).strip()
    ]
    requete = vues[0]
    assert requete.cache_system is True
    assert set(requete.inputs["blocks"]) == {f"S{i}" for i in range(1, len(attendus) + 1)}
    assert len(requete.inputs["blocks"]) == len(attendus)
    # un bloc étiqueté par Ancrage, dans l'ordre des Documents
    positions = [requete.system.index(f"[S{i}] ({a})") for i, a in enumerate(attendus, start=1)]
    assert positions == sorted(positions)
    # Réponse `cited` : rang dans l'ordre de première citation, score 1,0
    assert rep.retrieval_method == "cited"
    assert [s.passage.anchor_ids for s in rep.retrieved] == [(attendus[2],), (attendus[0],)]
    assert [s.rank for s in rep.retrieved] == [1, 2]
    assert [s.score for s in rep.retrieved] == [1.0, 1.0]
    assert [c.anchor_id for c in rep.citations] == [attendus[2], attendus[0]]
    assert rep.invalid_citations == 1
    assert rep.context_anchor_ids == tuple(attendus)


def test_long_context_defaut_cache_le_system(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    vues = _espionner(ctx)
    arch = _arch(ctx, "long_context")
    arch.index(minicorpus, tmp_path / "idx")
    arch.load(tmp_path / "idx")
    _repondre(arch, ctx)
    assert vues[0].cache_system is True
    assert "Question :" in vues[0].messages[-1].content
    assert "[S1]" not in vues[0].messages[-1].content  # le Contexte est dans le system


def test_long_context_inapplicable_au_dela_de_la_fenetre(ctx: RunCtx) -> None:
    arch = _arch(ctx, "long_context", generator={"name": "llm", "params": {"model": "fake-llm-a"}})
    res = arch.check(_profil(120_000))
    assert res.applicable is False
    assert res.reason is not None and "fenêtre" in res.reason and "100000" in res.reason
    assert arch.check(_profil(10_000)).applicable is True


def test_long_context_inapplicable_au_dela_du_palier_haiku(ctx: RunCtx) -> None:
    arch = _arch(
        ctx, "long_context", generator={"name": "llm", "params": {"model": "claude-haiku-5-5"}}
    )
    # 80 000 tokens de référence x 1,5 = 120 000 tokens estimés pour Haiku 5.5
    res = arch.check(_profil(80_000))
    assert res.applicable is False
    assert res.reason is not None and "palier" in res.reason and "100000" in res.reason
    assert arch.check(_profil(60_000)).applicable is True  # 90 000 tokens, sous le palier


def test_long_context_tronque_au_dela_de_8000_tokens(ctx: RunCtx, tmp_path: Path) -> None:
    corpus = _corpus_synthetique(n_docs=3, n_ancrages=4, n_mots=1000)  # 12 000 mots
    ctx.provider.script(  # type: ignore[attr-defined]
        "generate", "generate*", '{"answer": "R.", "citations": ["S5"], "abstain": false}'
    )
    arch = _arch(ctx, "long_context", generator={"name": "llm", "params": {"model": "fake-llm-a"}})
    arch.index(corpus, tmp_path / "idx")
    arch.load(tmp_path / "idx")
    rep = _repondre(arch, ctx)
    assert rep.context_truncated is True
    assert len(rep.context_texts) == 1 and rep.context_texts[0].startswith("[S5] (doc1#h/s0)")
    assert len(rep.context_anchor_ids) == 12  # tous les Ancrages fournis restent déclarés


def test_long_context_sous_le_seuil_garde_tous_les_blocs(ctx: RunCtx, tmp_path: Path) -> None:
    corpus = _corpus_synthetique(n_docs=2, n_ancrages=2, n_mots=50)
    arch = _arch(ctx, "long_context", generator={"name": "llm", "params": {"model": "fake-llm-a"}})
    arch.index(corpus, tmp_path / "idx")
    arch.load(tmp_path / "idx")
    rep = _repondre(arch, ctx)
    assert rep.context_truncated is False
    assert len(rep.context_texts) == 4


# --- index lexical bm25 ----------------------------------------------------------------------


def _passages_minicorpus(ctx: RunCtx, corpus: ParsedCorpus) -> list[Any]:
    chunker: FixedTokenChunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    return [p for d in corpus.documents for p in chunker.chunk(d)]


def test_bm25_recherche_ordre_et_sauvegarde(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("lexical_index", "bm25") is Bm25Index
    assert registry.get("retriever", "lexical") is LexicalRetriever
    passages = _passages_minicorpus(ctx, minicorpus)
    index: LexicalIndex = ctx.build("lexical_index", ComponentSpec(name="bm25"))
    index.add(passages)
    res = index.search("guilde Orvane fondation", 5)
    assert 0 < len(res) <= 5
    scores = [s for _, s in res]
    assert scores == sorted(scores, reverse=True)
    par_id = {p.passage_id: p for p in passages}
    assert "orvane" in par_id[res[0][0]].text.lower()

    index.save(tmp_path / "a")
    autre: LexicalIndex = ctx.build("lexical_index", ComponentSpec(name="bm25"))
    autre.load(tmp_path / "a")
    assert autre.search("guilde Orvane fondation", 5) == res

    index.delete([res[0][0]])
    assert res[0][0] not in [i for i, _ in index.search("guilde Orvane fondation", 5)]


def test_bm25_ex_aequo_departages_par_id(ctx: RunCtx) -> None:
    from wavelibrarian.core.types import Passage

    index: LexicalIndex = ctx.build("lexical_index", ComponentSpec(name="bm25"))
    index.add(
        [
            Passage(passage_id=i, doc_id="d", text="alpha beta", anchor_ids=("d#h/a",))
            for i in ("pc", "pa", "pb")
        ]
        + [Passage(passage_id="px", doc_id="d", text="gamma", anchor_ids=("d#h/a",))]
    )
    assert [i for i, _ in index.search("alpha", 5)] == ["pa", "pb", "pc"]
    assert index.search("introuvable", 5) == []


# --- bm25_only -------------------------------------------------------------------------------


def test_bm25_only_cycle_complet(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    assert registry.get("architecture", "bm25_only") is Bm25Only
    assert Bm25Only.query_params == frozenset({"k"})
    arch = _arch(ctx, "bm25_only")
    assert arch.params.k == 5
    dossier = tmp_path / "idx"
    arch.index(minicorpus, dossier)
    lignes = (dossier / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == len(_passages_minicorpus(ctx, minicorpus)) > 0

    neuve = _arch(ctx, "bm25_only")
    neuve.load(dossier)
    rep = _repondre(neuve, ctx)
    assert rep.retrieval_method == "ranked"
    assert 0 < len(rep.retrieved) <= 5
    assert [s.rank for s in rep.retrieved] == list(range(1, len(rep.retrieved) + 1))
    assert [s.score for s in rep.retrieved] == sorted(
        (s.score for s in rep.retrieved), reverse=True
    )
    assert rep.citations and rep.invalid_citations == 0
    assert set(c.anchor_id for c in rep.citations) <= set(rep.context_anchor_ids)
    # même Réponse depuis une troisième instance (chemins cache absent et présent identiques)
    autre = _arch(ctx, "bm25_only")
    autre.load(dossier)
    assert _repondre(autre, ctx) == rep


def test_bm25_only_k_hors_de_la_cle_d_index(ctx: RunCtx) -> None:
    k5 = _arch(ctx, "bm25_only").index_key()
    k3 = _arch(ctx, "bm25_only", k=3).index_key()
    assert k5 == k3
    assert (
        _arch(
            ctx, "bm25_only", chunker={"name": "fixed_tokens", "params": {"size": 100}}
        ).index_key()
        != k5
    )


def test_bm25_only_k_limite_les_passages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _arch(ctx, "bm25_only", k=2)
    arch.index(minicorpus, tmp_path / "idx")
    arch.load(tmp_path / "idx")
    assert len(_repondre(arch, ctx).retrieved) <= 2
    with pytest.raises(ConfigError):
        _arch(ctx, "bm25_only", k=0)


# --- troncature depuis une Architecture (report 4.1) -----------------------------------------


def test_bm25_only_tronque_au_dela_de_8000_tokens(ctx: RunCtx, tmp_path: Path) -> None:
    # Passages de 5 000 mots : 2 passages ≥ 8 000 tokens, un seul est cité.
    corpus = _corpus_synthetique(n_docs=2, n_ancrages=1, n_mots=5000)
    ctx.provider.script(  # type: ignore[attr-defined]
        "generate", "generate*", '{"answer": "R.", "citations": ["S1"], "abstain": false}'
    )
    arch = _arch(
        ctx,
        "bm25_only",
        k=2,
        chunker={"name": "fixed_tokens", "params": {"size": 5000, "overlap": 0}},
        generator={"name": "llm", "params": {"model": "fake-llm-a"}},
    )
    arch.index(corpus, tmp_path / "idx")
    arch.load(tmp_path / "idx")
    rep = _repondre(arch, ctx, _question("mot0x0x1 mot1x0x1"))
    assert len(rep.retrieved) == 2
    assert rep.context_truncated is True
    assert len(rep.context_texts) == 1
    assert len(rep.context_anchor_ids) == 2

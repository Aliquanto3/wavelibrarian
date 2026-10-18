"""Story 6.2 : Retriever `hybrid`, Reranker `fake` et Architecture `hybrid_rag`."""

import json
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.hybrid_rag import HybridRag
from wavelibrarian.components.rerankers.fake import FakeReranker
from wavelibrarian.components.retrievers.hybrid import (
    HybridRetriever,
    fusion_ponderee,
    fusion_rrf,
)
from wavelibrarian.config.resolve import Collecte
from wavelibrarian.config.validate import _verifier_capacites
from wavelibrarian.core.errors import ConfigError, WlError
from wavelibrarian.core.types import (
    ParsedCorpus,
    ParsedDocument,
    Passage,
    QuestionInput,
    ScoredPassage,
)
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import ArchCapabilities, CorpusChange
from wavelibrarian.ports.components import ComponentSpec, SearchIndex
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache

PETITS = {"name": "fixed_tokens", "params": {"size": 40, "overlap": 5}}


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


def _arch(ctx: RunCtx, **params: Any) -> Any:
    params.setdefault("embedder", {"name": "fake"})
    params.setdefault("chunker", PETITS)
    return ctx.build("architecture", ComponentSpec(name="hybrid_rag", params=params))


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def _repondre(arch: Any, ctx: RunCtx) -> Any:
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(_question())


def _passage(i: str, texte: str = "") -> Passage:
    return Passage(passage_id=i, doc_id="d", text=texte or i, anchor_ids=("a",))


def _liste(*ids: str) -> list[ScoredPassage]:
    """Liste classée : scores décroissants 10, 9, ..., rangs 1, 2, ..."""
    return [
        ScoredPassage(passage=_passage(i), score=float(10 - r), rank=r + 1)
        for r, i in enumerate(ids)
    ]


def _spans(ctx: RunCtx) -> list[dict[str, Any]]:
    lignes = (ctx.run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lignes]


# --- fusion ----------------------------------------------------------------------------------


def test_rrf_somme_des_inverses_et_ordre_calcule_a_la_main() -> None:
    dense = _liste("a", "b", "c")
    lexical = _liste("c", "a", "d")
    scores = fusion_rrf([dense, lexical], 60)
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)  # rangs 1 et 2
    assert scores["b"] == pytest.approx(1 / 62)  # dense seul, rang 2
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 61)  # rangs 3 et 1
    assert scores["d"] == pytest.approx(1 / 63)  # lexical seul, rang 3
    # a (0,03252) > c (0,03226) > b (0,01613) > d (0,01587)
    ordre = sorted(scores, key=lambda i: (-scores[i], i))
    assert ordre == ["a", "c", "b", "d"]
    assert fusion_rrf([dense, lexical], 10)["a"] == pytest.approx(1 / 11 + 1 / 12)


def test_ponderee_normalise_min_max_avant_de_combiner() -> None:
    dense = [
        ScoredPassage(passage=_passage("a"), score=0.9, rank=1),
        ScoredPassage(passage=_passage("b"), score=0.5, rank=2),
        ScoredPassage(passage=_passage("c"), score=0.1, rank=3),
    ]
    lexical = [
        ScoredPassage(passage=_passage("c"), score=20.0, rank=1),
        ScoredPassage(passage=_passage("d"), score=10.0, rank=2),
    ]
    # dense normalisé : a 1, b 0,5, c 0 ; lexical normalisé : c 1, d 0
    s = fusion_ponderee(dense, lexical, 0.5)
    assert s == pytest.approx({"a": 0.5, "b": 0.25, "c": 0.5, "d": 0.0})
    s2 = fusion_ponderee(dense, lexical, 0.8)
    assert s2 == pytest.approx({"a": 0.8, "b": 0.4, "c": 0.2, "d": 0.0})
    # liste à scores égaux : 1 pour chacun, pas de division par zéro
    egaux = [ScoredPassage(passage=_passage("x"), score=3.0, rank=1)]
    assert fusion_ponderee(egaux, [], 0.5) == {"x": 0.5}


def test_hybrid_retriever_fusionne_les_deux_listes(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("retriever", "hybrid") is HybridRetriever
    arch = _arch(ctx)
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    arch.load(tmp_path / "i")
    index: SearchIndex = arch._index
    requete = "guilde Orvane"
    with ctx.scope(post="query"):
        dense = ctx.build("retriever", ComponentSpec(name="dense")).retrieve(requete, 50, index)
        lexical = ctx.build("retriever", ComponentSpec(name="lexical")).retrieve(requete, 50, index)
        res = ctx.build("retriever", ComponentSpec(name="hybrid")).retrieve(requete, 6, index)
    attendus = fusion_rrf([dense, lexical], 60)
    ordre = sorted(attendus, key=lambda i: (-attendus[i], i))[:6]
    assert [s.passage.passage_id for s in res] == ordre
    assert [s.rank for s in res] == [1, 2, 3, 4, 5, 6]
    assert [s.score for s in res] == pytest.approx([attendus[i] for i in ordre])
    pond = ctx.build(
        "retriever", ComponentSpec(name="hybrid", params={"fusion": "weighted", "weight_dense": 1})
    )
    with ctx.scope(post="query"):
        seul_dense = pond.retrieve(requete, 5, index)
    assert [s.passage.passage_id for s in seul_dense] == [s.passage.passage_id for s in dense[:5]]


def test_hybrid_retriever_exige_les_deux_index(ctx: RunCtx) -> None:
    retriever = ctx.build("retriever", ComponentSpec(name="hybrid"))
    with pytest.raises(WlError, match="lexical"):
        retriever.retrieve("x", 3, SearchIndex(passages={}))
    with pytest.raises(WlError):
        ctx.build("retriever", ComponentSpec(name="hybrid", params={"fusion": "autre"}))


# --- reranker --------------------------------------------------------------------------------


def test_reranker_fake_recouvrement_et_span_rerank(ctx: RunCtx) -> None:
    assert registry.get("reranker", "fake") is FakeReranker
    reranker = ctx.build("reranker", ComponentSpec(name="fake"))
    candidats = [
        ScoredPassage(passage=_passage("p1", "rien de commun"), score=0.9, rank=1),
        ScoredPassage(passage=_passage("p2", "la guilde Orvane"), score=0.8, rank=2),
        ScoredPassage(passage=_passage("p3", "guilde seule"), score=0.7, rank=3),
        ScoredPassage(passage=_passage("p4", "guilde Orvane hors top_n"), score=0.6, rank=4),
    ]
    with ctx.scope(post="query", question_id="q-001"):
        res = reranker.rerank("guilde Orvane", candidats, 3)
    assert [s.passage.passage_id for s in res] == ["p2", "p3", "p1"]  # p4 hors top_n
    assert [s.rank for s in res] == [1, 2, 3]
    assert [s.score for s in res] == [1.0, 0.5, 0.0]
    rerank = [s for s in _spans(ctx) if _attr(s, "wl.kind") == "rerank"]
    assert len(rerank) == 1
    assert _attr(rerank[0], "wl.step") == "rerank"
    assert _attr(rerank[0], "wl.latency_s") >= 0


def _attr(span: dict[str, Any], cle: str) -> Any:
    return span[cle]


# --- hybrid_rag ------------------------------------------------------------------------------


def test_hybrid_rag_cycle_complet_et_manifeste(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("architecture", "hybrid_rag") is HybridRag
    assert HybridRag.capabilities.requires_hybrid_store is False
    assert HybridRag.capabilities.retrieval_method == "ranked"
    ctx.provider.script(  # type: ignore[attr-defined]
        "generate", "generate*", '{"answer": "Réponse.", "citations": ["S1"], "abstain": false}'
    )
    cache = IndexCache(tmp_path / "home")
    arch, cle = cache.build(ctx, lambda: _arch(ctx), minicorpus)
    dossier = cache.path(cle)
    manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    assert manifeste["embedder_dim"] == 64
    assert (dossier / "vectors").is_dir() and (dossier / "lexical").is_dir()
    rep = _repondre(arch, ctx)
    assert rep.retrieval_method == "ranked"
    assert [s.rank for s in rep.retrieved] == [1, 2, 3, 4, 5]
    index = arch._index  # type: ignore[attr-defined]
    with ctx.scope(post="query"):
        attendu = arch.retriever.retrieve(_question().text, 5, index)  # type: ignore[attr-defined]
    assert [s.passage.passage_id for s in rep.retrieved] == [s.passage.passage_id for s in attendu]
    assert not [s for s in _spans(ctx) if _attr(s, "wl.kind") == "rerank"]  # reranker: null
    assert rep.citations and rep.invalid_citations == 0


@pytest.mark.parametrize(
    "etage",
    [
        {"retriever": {"name": "dense"}},
        {"retriever": {"name": "lexical"}},
        {},
        {"fusion": "weighted", "weight_dense": 0.3},
        {"reranker": {"name": "fake"}, "rerank_top_n": 8},
        {"retriever": {"name": "dense"}, "reranker": {"name": "fake"}},
    ],
)
def test_hybrid_rag_chaque_combinaison_d_etages_est_valide(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, etage: dict[str, Any]
) -> None:
    arch = _arch(ctx, **etage)
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    arch.load(tmp_path / "i")
    rep = _repondre(arch, ctx)
    assert len(rep.retrieved) == 5
    scores = [s.score for s in rep.retrieved]
    assert scores == sorted(scores, reverse=True)
    if "retriever" in etage and etage["retriever"]["name"] == "dense":
        with ctx.scope(post="query"):
            vecteur = arch._index.embedder.embed_queries([_question().text])[0]
        attendu = arch._index.vectors.search(vecteur, 5)
        if "reranker" not in etage:
            assert [s.passage.passage_id for s in rep.retrieved] == [i for i, _ in attendu]


def test_hybrid_rag_etages_de_requete_reutilisent_l_index(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    base = _arch(ctx).index_key()
    for variante in (
        {"k": 3},
        {"fusion": "weighted"},
        {"weight_dense": 0.2},
        {"rrf_k": 10},
        {"reranker": {"name": "fake"}},
        {"rerank_top_n": 7},
        {"retriever": {"name": "lexical"}},
    ):
        assert _arch(ctx, **variante).index_key() == base, variante
    assert _arch(ctx, chunker={"name": "fixed_tokens"}).index_key() != base
    cache = IndexCache(tmp_path / "home")
    _, c1 = cache.build(ctx, lambda: _arch(ctx), minicorpus)
    a2, c2 = cache.build(
        ctx, lambda: _arch(ctx, fusion="weighted", reranker={"name": "fake"}), minicorpus
    )
    assert c1 == c2
    assert len(_repondre(a2, ctx).retrieved) == 5


def test_hybrid_rag_reranker_reclasse_20_candidats_garde_k_et_trace_rerank(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _arch(ctx, reranker={"name": "fake"}, rerank_top_n=20)
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    arch.load(tmp_path / "i")
    avant = len(_spans(ctx))
    rep = _repondre(arch, ctx)
    index = arch._index
    with ctx.scope(post="query"):
        candidats = arch.retriever.retrieve(_question().text, 20, index)
    assert len(candidats) == 20
    mots = set(_question().text.casefold().replace("?", "").split())

    def note(s: ScoredPassage) -> float:
        import re

        m = set(re.findall(r"\w+", s.passage.text.casefold()))
        q = set(re.findall(r"\w+", _question().text.casefold()))
        return len(q & m) / len(q)

    assert mots
    attendu = sorted(enumerate(candidats), key=lambda t: (-note(t[1]), t[0]))[:5]
    assert [s.passage.passage_id for s in rep.retrieved] == [
        c.passage.passage_id for _, c in attendu
    ]
    assert [s.rank for s in rep.retrieved] == [1, 2, 3, 4, 5]
    assert [s.score for s in rep.retrieved] == pytest.approx([note(c) for _, c in attendu])
    nouveaux = _spans(ctx)[avant:]
    rerank = [s for s in nouveaux if _attr(s, "wl.kind") == "rerank"]
    assert len(rerank) == 1
    assert _attr(rerank[0], "wl.latency_s") >= 0
    assert _attr(rerank[0], "wl.candidates") == 20
    assert _attr(rerank[0], "wl.post") == "query"


def test_hybrid_rag_k_superieur_a_rerank_top_n(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    arch = _arch(ctx, reranker={"name": "fake"}, rerank_top_n=2, k=4)
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    arch.load(tmp_path / "i")
    rep = _repondre(arch, ctx)
    ids = [s.passage.passage_id for s in rep.retrieved]
    assert len(ids) == 4 == len(set(ids))
    assert [s.rank for s in rep.retrieved] == [1, 2, 3, 4]


def _modifier(doc: ParsedDocument) -> ParsedDocument:
    blocs = tuple(
        b.model_copy(update={"text": b.text + " Complément inédit sur la guilde."})
        for b in doc.blocks
    )
    return doc.model_copy(update={"blocks": blocs})


def test_hybrid_rag_update_incremental_sur_les_deux_index(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    docs = list(minicorpus.documents)
    supprime, modifie, ajoute_src, garde = docs[0], docs[1], docs[2], docs[3:]
    avant = minicorpus.model_copy(update={"documents": (supprime, modifie, *garde)})
    arch = _arch(ctx)
    with ctx.scope(post="indexing"):
        arch.index(avant, tmp_path / "v1")
    lignes = (tmp_path / "v1" / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    sortants = {
        json.loads(x)["passage_id"] for x in lignes if json.loads(x)["doc_id"] == supprime.doc_id
    }
    assert sortants
    nouveau = _modifier(modifie)
    neuf = ajoute_src.model_copy(update={"doc_id": "doc-neuf"})
    change = CorpusChange(
        added=(neuf,), removed=(supprime.doc_id,), modified=((modifie.doc_id, nouveau),)
    )
    apres = avant.model_copy(update={"documents": (nouveau, *garde, neuf)})

    maj = _arch(ctx)
    appels: list[int] = []
    origine = maj.embedder.embed_passages

    def espion(textes: Any) -> Any:
        appels.append(len(textes))
        return origine(textes)

    maj.embedder.embed_passages = espion
    with ctx.scope(post="update"):
        maj.update(change, apres, tmp_path / "v1", tmp_path / "v2")
    assert sum(appels) == sum(len(maj.chunker.chunk(d)) for d in (neuf, nouveau))

    neuve = _arch(ctx)
    neuve.load(tmp_path / "v2")
    index = neuve._index
    assert {p.doc_id for p in index.passages.values()} == {d.doc_id for d in apres.documents}
    assert not sortants & set(index.passages)
    en_store = {i for i, _ in index.vectors.search(np.ones(64, np.float32), 100_000)}
    assert en_store == set(index.passages)  # index dense à jour
    en_lexical = {i for i, _ in index.lexical.search("guilde Orvane Complément", 100_000)}
    assert en_lexical <= set(index.passages)  # index BM25 à jour
    assert any("Complément" in index.passages[i].text for i in en_lexical)
    rep = _repondre(neuve, ctx)
    assert len(rep.retrieved) == 5
    assert not sortants & {s.passage.passage_id for s in rep.retrieved}


# --- validation (story 1.6) ------------------------------------------------------------------


def test_store_non_hybride_refuse_pour_une_architecture_qui_l_exige_mais_pas_hybrid_rag() -> None:
    class Exigeante:
        capabilities: ClassVar[ArchCapabilities] = ArchCapabilities(requires_hybrid_store=True)

    chemin = "configurations[0].params.store"
    composants = [("vector_store", "numpy_exact", chemin)]
    erreurs: list[ConfigError] = []
    exigeante = Collecte(architecture=Exigeante, composants=composants)
    _verifier_capacites(exigeante, None, set(), erreurs)  # type: ignore[arg-type]
    assert len(erreurs) == 1
    assert "hybride" in erreurs[0].message and "numpy_exact" in erreurs[0].message
    ok: list[ConfigError] = []
    _verifier_capacites(Collecte(architecture=HybridRag, composants=composants), None, set(), ok)  # type: ignore[arg-type]
    assert ok == []

"""Story 6.1 : VectorStore `numpy_exact`, Retriever `dense` et Architecture `naive_rag`."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.naive_rag import NaiveRag
from wavelibrarian.components.retrievers.dense import DenseRetriever
from wavelibrarian.components.vector_stores.numpy_exact import NumpyExactStore
from wavelibrarian.core.errors import WlError
from wavelibrarian.core.types import ParsedCorpus, ParsedDocument, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import CorpusChange
from wavelibrarian.ports.components import ComponentSpec, SearchIndex
from wavelibrarian.ports.gateway import LLMRequest
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache

PETITS = {"name": "fixed_tokens", "params": {"size": 40, "overlap": 5}}


@pytest.fixture
def ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    provider = FakeProvider()
    c = RunCtx.from_profile(
        "test", wl_home=tmp_path / "wl", run_id="r-1", seed=1, providers={"fake": provider}
    )
    c.parser = "markdown"  # parser concret (jamais `auto`) pour la clé d'index
    c.provider = provider  # type: ignore[attr-defined]
    with c:
        yield c


def _arch(ctx: RunCtx, **params: Any) -> Any:
    params.setdefault("embedder", {"name": "fake"})
    params.setdefault("chunker", PETITS)
    return ctx.build("architecture", ComponentSpec(name="naive_rag", params=params))


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def _repondre(arch: Any, ctx: RunCtx) -> Any:
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(_question())


def _unitaires(n: int, dim: int, graine: int = 0) -> Any:
    v = np.random.default_rng(graine).normal(size=(n, dim)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _compteur_embed(arch: Any) -> list[int]:
    """Nombre de textes passés à `embed_passages`, un élément par appel."""
    appels: list[int] = []
    origine = arch.embedder.embed_passages

    def espion(textes: Any) -> Any:
        appels.append(len(textes))
        return origine(textes)

    arch.embedder.embed_passages = espion
    return appels


# --- numpy_exact -----------------------------------------------------------------------------


def test_numpy_exact_ajout_suppression_recherche_et_ordre(ctx: RunCtx) -> None:
    assert registry.get("vector_store", "numpy_exact") is NumpyExactStore
    assert NumpyExactStore.capabilities.hybrid is False
    store = ctx.build("vector_store", ComponentSpec(name="numpy_exact", params={"dim": 8}))
    vecteurs = _unitaires(10, 8)
    ids = [f"p{i}" for i in range(10)]
    store.add(ids, vecteurs)
    store.delete(["p3", "p7"])
    q = vecteurs[0]
    res = store.search(q, 5)
    assert len(res) == 5
    assert res[0][0] == "p0"
    assert [s for _, s in res] == sorted((s for _, s in res), reverse=True)
    assert not {"p3", "p7"} & {i for i, _ in res}
    attendus = sorted(
        ((i, float(v @ q)) for i, v in zip(ids, vecteurs, strict=True) if i not in {"p3", "p7"}),
        key=lambda t: (-t[1], t[0]),
    )[:5]
    assert [i for i, _ in res] == [i for i, _ in attendus]


def test_numpy_exact_ex_aequo_departages_par_id(ctx: RunCtx) -> None:
    store = ctx.build("vector_store", ComponentSpec(name="numpy_exact"))
    store.add(["c", "a", "b"], np.array([[1.0, 0.0]] * 3, dtype=np.float32))
    res = store.search(np.array([1.0, 0.0], dtype=np.float32), 3)
    assert [i for i, _ in res] == ["a", "b", "c"]


def test_numpy_exact_save_load_et_dimension_refusee(ctx: RunCtx, tmp_path: Path) -> None:
    store = ctx.build("vector_store", ComponentSpec(name="numpy_exact", params={"dim": 8}))
    vecteurs = _unitaires(6, 8)
    store.add([f"p{i}" for i in range(6)], vecteurs)
    store.delete(["p1"])
    store.save(tmp_path / "a")
    autre = ctx.build("vector_store", ComponentSpec(name="numpy_exact", params={"dim": 8}))
    autre.load(tmp_path / "a")
    assert autre.search(vecteurs[2], 4) == store.search(vecteurs[2], 4)
    sans_dim = ctx.build("vector_store", ComponentSpec(name="numpy_exact"))
    sans_dim.load(tmp_path / "a")
    assert sans_dim.dim == 8
    with pytest.raises(WlError, match="dimension"):
        store.add(["x"], _unitaires(1, 4))
    with pytest.raises(WlError, match="dimension"):
        store.search(_unitaires(1, 4)[0], 3)
    mauvais = ctx.build("vector_store", ComponentSpec(name="numpy_exact", params={"dim": 4}))
    with pytest.raises(WlError, match="dimension"):
        mauvais.load(tmp_path / "a")
    with pytest.raises(WlError, match="illisible"):
        autre.load(tmp_path / "absent")


def test_numpy_exact_add_remplace_un_id_existant(ctx: RunCtx) -> None:
    store = ctx.build("vector_store", ComponentSpec(name="numpy_exact"))
    store.add(["a", "b"], np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    store.add(["a"], np.array([[0.0, 1.0]], dtype=np.float32))
    assert store.search(np.array([1.0, 0.0], dtype=np.float32), 5) == [("a", 0.0), ("b", 0.0)]
    with pytest.raises(WlError):
        store.add(["z", "z"], np.zeros((2, 2), dtype=np.float32))


# --- dense -----------------------------------------------------------------------------------


def test_dense_appelle_embed_queries_et_classe_de_1_a_k(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("retriever", "dense") is DenseRetriever
    arch = _arch(ctx)
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    arch.load(tmp_path / "i")
    index: SearchIndex = arch._index
    appels: list[list[str]] = []
    origine = index.embedder.embed_queries  # type: ignore[union-attr]

    def espion(textes: Any) -> Any:
        appels.append(list(textes))
        return origine(textes)

    index.embedder.embed_queries = espion  # type: ignore[union-attr,method-assign]
    retriever = ctx.build("retriever", ComponentSpec(name="dense"))
    with ctx.scope(post="query"):
        res = retriever.retrieve("guilde Orvane", 4, index)
    assert appels == [["guilde Orvane"]]
    assert [s.rank for s in res] == [1, 2, 3, 4]
    assert [s.score for s in res] == sorted((s.score for s in res), reverse=True)
    with ctx.scope(post="query"):
        vecteur = origine(["guilde Orvane"])[0]
    res2 = retriever.retrieve("autre texte", 4, index, vecteur)  # `query_vector` fourni
    assert appels == [["guilde Orvane"]]
    assert [s.passage.passage_id for s in res2] == [s.passage.passage_id for s in res]


def test_dense_sans_store_refuse(ctx: RunCtx) -> None:
    retriever = ctx.build("retriever", ComponentSpec(name="dense"))
    with pytest.raises(WlError, match="store"):
        retriever.retrieve("x", 3, SearchIndex(passages={}))


# --- naive_rag -------------------------------------------------------------------------------


def test_naive_rag_cycle_complet_manifeste_et_citations(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert registry.get("architecture", "naive_rag") is NaiveRag
    assert NaiveRag.capabilities.incremental_update is True
    assert NaiveRag.capabilities.retrieval_method == "ranked"
    vues: list[LLMRequest] = []

    def sortie(req: LLMRequest) -> str:
        vues.append(req)
        return '{"answer": "Réponse.", "citations": ["S1", "S99"], "abstain": false}'

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]
    cache = IndexCache(tmp_path / "home")
    arch, cle = cache.build(ctx, lambda: _arch(ctx), minicorpus)
    dossier = cache.path(cle)
    manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    assert manifeste["embedder_dim"] == 64
    assert len((dossier / "passages.jsonl").read_text(encoding="utf-8").splitlines()) >= 5
    rep = _repondre(arch, ctx)
    assert rep.retrieval_method == "ranked"
    assert len(rep.retrieved) == 5
    assert [s.rank for s in rep.retrieved] == [1, 2, 3, 4, 5]
    scores = [s.score for s in rep.retrieved]
    assert scores == sorted(scores, reverse=True)
    blocs = vues[0].inputs["blocks"]
    assert set(blocs) == {f"S{i}" for i in range(1, 6)}
    for s, bloc in zip(rep.retrieved, blocs.values(), strict=True):
        assert s.passage.text in bloc  # le prompt contient le Passage
    assert rep.invalid_citations == 1  # S99 hors des 5 Passages
    assert len(rep.citations) == 1
    attendues = {a for s in rep.retrieved for a in s.passage.anchor_ids}
    assert set(rep.context_anchor_ids) == attendues  # Ancrages des 5 Passages dans le prompt


def test_naive_rag_k_hors_de_la_cle_et_index_reutilise(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert _arch(ctx, k=5).index_key() == _arch(ctx, k=3).index_key()
    assert _arch(ctx, k=5).index_key() != _arch(ctx, chunker={"name": "fixed_tokens"}).index_key()
    cache = IndexCache(tmp_path / "home")
    a1, c1 = cache.build(ctx, lambda: _arch(ctx, k=5), minicorpus)
    a2, c2 = cache.build(ctx, lambda: _arch(ctx, k=3), minicorpus)
    assert c1 == c2
    assert len(_repondre(a1, ctx).retrieved) == 5
    assert len(_repondre(a2, ctx).retrieved) == 3
    # la seconde construction trouve l'index : aucun encodage de Passage
    appels = _compteur_embed(a2)
    cache.build(ctx, lambda: _arch(ctx, k=3), minicorpus)
    assert appels == []


def _modifier(doc: ParsedDocument) -> ParsedDocument:
    blocs = tuple(
        b.model_copy(update={"text": b.text + " Complément inédit sur la guilde."})
        for b in doc.blocks
    )
    return doc.model_copy(update={"blocks": blocs})


def _doc_ids(dossier: Path) -> dict[str, str]:
    lignes = (dossier / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    return {json.loads(x)["passage_id"]: json.loads(x)["doc_id"] for x in lignes}


def test_naive_rag_update_incremental(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    docs = list(minicorpus.documents)
    assert len(docs) >= 4
    supprime, modifie, ajoute_src = docs[0], docs[1], docs[2]
    garde = docs[3:]
    avant = minicorpus.model_copy(update={"documents": (supprime, modifie, *garde)})
    arch = _arch(ctx)
    with ctx.scope(post="indexing"):
        arch.index(avant, tmp_path / "v1")
    anciens = _doc_ids(tmp_path / "v1")

    nouveau = _modifier(modifie)
    neuf = ajoute_src.model_copy(update={"doc_id": "doc-neuf"})
    change = CorpusChange(
        added=(neuf,), removed=(supprime.doc_id,), modified=((modifie.doc_id, nouveau),)
    )
    apres = avant.model_copy(update={"documents": (nouveau, *garde, neuf)})

    maj = _arch(ctx)
    appels = _compteur_embed(maj)
    with ctx.scope(post="update"):
        maj.update(change, apres, tmp_path / "v1", tmp_path / "v2")
    # seuls les Documents ajoutés ou modifiés sont encodés
    assert sum(appels) == sum(len(maj.chunker.chunk(d)) for d in (neuf, nouveau))

    neuve = _arch(ctx)
    neuve.load(tmp_path / "v2")
    passages = neuve._index.passages
    assert {p.doc_id for p in passages.values()} == {d.doc_id for d in apres.documents}
    assert len(passages) == sum(len(maj.chunker.chunk(d)) for d in apres.documents)
    retires = {i for i, d in anciens.items() if d == supprime.doc_id}
    assert retires
    # les Passages du Document supprimé ont quitté le store et passages.jsonl
    assert not retires & set(passages)
    # le Document remplacé ne garde que ses nouveaux Passages
    textes = [p.text for p in passages.values() if p.doc_id == modifie.doc_id]
    assert textes and any("Complément inédit" in x for x in textes)
    en_store = {i for i, _ in neuve._index.vectors.search(np.ones(64, np.float32), 100_000)}
    assert en_store == set(passages)


def test_naive_rag_update_scenario_reel_depuis_le_cache(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    """Scénario réel (le `doc_id` d'un Document modifié change) : index servi par l'IndexCache,
    `update` sur une instance neuve, puis `load` sur une autre et recherche."""
    from wavelibrarian.corpus.scenario import appliquer_fichier

    scenario = Path(__file__).resolve().parents[3] / "corpora/minicorpus/scenario/scenario.yaml"
    change, apres = appliquer_fichier(minicorpus, scenario, parser="markdown")
    assert change.added and change.removed and change.modified
    assert all(ancien != doc.doc_id for ancien, doc in change.modified)
    cache = IndexCache(tmp_path / "home")
    v1: Any
    v1, cle = cache.build(ctx, lambda: _arch(ctx), minicorpus)
    sortants = set(change.removed) | {ancien for ancien, _ in change.modified}
    anciens = {i for i, p in v1._index.passages.items() if p.doc_id in sortants}
    assert anciens

    maj = _arch(ctx)
    appels = _compteur_embed(maj)
    with ctx.scope(post="update"):
        maj.update(change, apres, cache.path(cle), tmp_path / "v2")
    entrants = [*change.added, *(doc for _, doc in change.modified)]
    assert sum(appels) == sum(len(maj.chunker.chunk(d)) for d in entrants)

    v2 = _arch(ctx)
    v2.load(tmp_path / "v2")
    passages = v2._index.passages
    assert {p.doc_id for p in passages.values()} == {d.doc_id for d in apres.documents}
    assert not anciens & set(passages)
    en_store = {i for i, _ in v2._index.vectors.search(np.ones(64, np.float32), 100_000)}
    assert en_store == set(passages)
    rep = _repondre(v2, ctx)
    assert len(rep.retrieved) == 5
    assert not anciens & {s.passage.passage_id for s in rep.retrieved}


def test_numpy_exact_ajout_rate_ne_fixe_pas_la_dimension(ctx: RunCtx, tmp_path: Path) -> None:
    store = ctx.build("vector_store", ComponentSpec(name="numpy_exact"))
    assert store.search(np.ones(3, np.float32), 2) == []  # vide, sans dimension
    with pytest.raises(WlError):
        store.add(["a"], np.zeros((2, 4), dtype=np.float32))  # 1 id pour 2 vecteurs
    assert store.dim == 0
    store.add(["a"], np.array([[1.0, 0.0]], dtype=np.float32))
    assert store.dim == 2
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "ids.json").write_text("{}", encoding="utf-8")
    np.save(tmp_path / "x" / "vectors.npy", np.zeros((0, 2), dtype=np.float32))
    with pytest.raises(WlError, match="illisible"):
        store.load(tmp_path / "x")

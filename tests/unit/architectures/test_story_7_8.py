"""Story 7.8 : Architecture `lightrag` (deux index denses, mise à jour par union de graphes)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from wavelibrarian import registry
from wavelibrarian.architectures._passages import lire_passages
from wavelibrarian.architectures.lightrag import LightRag
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import CorpusChange
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.runner.context import Context as RunCtx


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
    return ctx.build("architecture", ComponentSpec(name="lightrag", params=params))


def _indexer(ctx: RunCtx, corpus: ParsedCorpus, dossier: Path, **params: Any) -> Any:
    arch = _arch(ctx, **params)
    with ctx.scope(post="indexing"):
        arch.index(corpus, dossier)
    return arch


def _spans(ctx: RunCtx, prefixe: str = "") -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    spans = [s for s in map(json.loads, lignes) if s.get("wl.kind") == "llm"]
    return [s for s in spans if s["wl.step"].startswith(prefixe)]


def _json(dossier: Path, nom: str) -> Any:
    return json.loads((dossier / nom).read_text(encoding="utf-8"))


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de la guilde Orvane ?", lang="fr")


def _citer_tout(ctx: RunCtx) -> None:
    def sortie(req: Any) -> str:
        etiquettes = list(req.inputs["blocks"])
        return json.dumps({"answer": "R", "citations": etiquettes, "abstain": False})

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]


def _repondre(ctx: RunCtx, dossier: Path, **params: Any) -> tuple[Any, Any]:
    arch = _arch(ctx, **params)
    arch.load(dossier)
    with ctx.scope(post="query", question_id="q-001"):
        return arch, arch.answer(_question())


@pytest.fixture
def index(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> Path:
    _indexer(ctx, minicorpus, tmp_path / "i")
    return tmp_path / "i"


def _existants(corpus: ParsedCorpus) -> set[str]:
    return {a for d in corpus.documents for a in d.anchors}


def _sans(corpus: ParsedCorpus, doc: Any) -> ParsedCorpus:
    return corpus.model_copy(
        update={"documents": tuple(d for d in corpus.documents if d is not doc)}
    )


# -- enregistrement et indexation ---------------------------------------------------------------


def test_enregistrement_et_capacites(ctx: RunCtx) -> None:
    assert registry.get("architecture", "lightrag") is LightRag
    assert LightRag.capabilities.incremental_update is True
    assert LightRag.capabilities.retrieval_method == "ranked"
    assert _arch(ctx).embedder_dim() == 64
    assert {"k", "k_entities", "k_relations"} == LightRag.query_params


def test_indexation_deux_index_separes_sans_rapport(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path
) -> None:
    passages = lire_passages(index)
    assert passages and all(p.level == 0 for p in passages)  # aucun rapport de communauté
    assert not (index / "communities.json").exists()
    g = _json(index, "graph/graph.json")
    entites, relations = _json(index, "entities.json"), _json(index, "relations.json")
    assert len(entites) == len(g["nodes"]) > 0
    assert len(relations) == len(g["edges"]) > 0
    assert (index / "vectors_entities").is_dir() and (index / "vectors_relations").is_dir()
    arch = _arch(ctx)
    arch.load(index)
    assert len(arch._vec_entites.search(np.ones(64, dtype=np.float32), 10_000)) == len(entites)
    assert len(arch._vec_relations.search(np.ones(64, dtype=np.float32), 10_000)) == len(relations)
    spans = _spans(ctx)
    assert {s["wl.post"] for s in spans} == {"indexing"}
    assert all(s["wl.step"].startswith("graph.extract.") for s in spans)
    assert len(spans) == len(passages)  # un appel par Passage, rien d'autre


def test_indexation_deterministe(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    _indexer(ctx, minicorpus, tmp_path / "a")
    _indexer(ctx, minicorpus, tmp_path / "b")
    for nom in ("passages.jsonl", "entities.json", "relations.json", "graph/graph.json"):
        assert (tmp_path / "a" / nom).read_bytes() == (tmp_path / "b" / nom).read_bytes()


def test_k_hors_de_l_index_key(ctx: RunCtx) -> None:
    a, b = _arch(ctx), _arch(ctx, k=9, k_entities=2, k_relations=7)
    assert a.index_key() == b.index_key()
    assert _arch(ctx, extract_max_tokens=512).index_key() != a.index_key()


# -- requête ------------------------------------------------------------------------------------


def test_requete_deux_niveaux_passages_dedoublonnes(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path
) -> None:
    _citer_tout(ctx)
    avant = len(_spans(ctx))
    arch, rep = _repondre(ctx, index, k=50, k_entities=4, k_relations=4)
    assert not rep.abstained and rep.retrieval_method == "ranked"
    ids = [s.passage.passage_id for s in rep.retrieved]
    assert ids and len(ids) == len(set(ids))
    assert [s.rank for s in rep.retrieved] == list(range(1, len(ids) + 1))
    scores = [s.score for s in rep.retrieved]
    assert scores == sorted(scores, reverse=True)
    # le contexte est exactement l'union des sources du niveau bas et du niveau haut
    g = arch._graphe.graph()
    with ctx.scope(post="query", question_id="q-001"):
        q = np.asarray(arch.embedder.embed_queries([_question().text]), dtype=np.float32)[0]
    bas = {i for n, _ in arch._vec_entites.search(q, 4) for i in g.nodes[n]["passage_ids"]}
    haut = {
        i
        for r, _ in arch._vec_relations.search(q, 4)
        for i in g.edges[arch._relations[r][0], arch._relations[r][1]]["passage_ids"]
    }
    assert set(ids) == bas | haut
    assert rep.citations and {c.anchor_id for c in rep.citations} <= _existants(minicorpus)
    assert [s["wl.step"] for s in _spans(ctx)[avant:]] == ["generate"]  # un seul appel de requête


def test_niveau_haut_apporte_des_passages_absents_du_niveau_bas(ctx: RunCtx, index: Path) -> None:
    _, seul_bas = _repondre(ctx, index, k=50, k_entities=1, k_relations=3)
    arch = _arch(ctx, k=50, k_entities=1, k_relations=3)
    arch.load(index)
    g = arch._graphe.graph()
    with ctx.scope(post="query", question_id="q-001"):
        q = np.asarray(arch.embedder.embed_queries([_question().text]), dtype=np.float32)[0]
    ((n, _),) = arch._vec_entites.search(q, 1)
    haut = {
        i
        for r, _ in arch._vec_relations.search(q, 3)
        for i in g.edges[arch._relations[r][0], arch._relations[r][1]]["passage_ids"]
    }
    bas = set(g.nodes[n]["passage_ids"])
    assert haut - bas  # le niveau haut apporte des Passages que le niveau bas ignore
    assert {s.passage.passage_id for s in seul_bas.retrieved} == bas | haut


def test_k_borne_les_passages(ctx: RunCtx, index: Path) -> None:
    _citer_tout(ctx)
    _, rep = _repondre(ctx, index, k=2, k_entities=10, k_relations=10)
    assert len(rep.retrieved) == 2 and len(rep.context_texts) == 2


def test_graphe_vide_abstention_sans_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script(  # type: ignore[attr-defined]
        "extract_entities", "graph.extract.*", '{"entities": [], "relations": []}'
    )
    _indexer(ctx, minicorpus, tmp_path / "i")
    _, rep = _repondre(ctx, tmp_path / "i")
    assert rep.abstained and rep.citations == () and rep.retrieved == ()
    assert not _spans(ctx, "generate")


def test_fenetre_du_generateur_ecarte_les_blocs_avec_avertissement(
    ctx: RunCtx, index: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _citer_tout(ctx)
    arch = _arch(ctx, k=5)
    arch.load(index)
    arch._fenetre = lambda modele: 1700
    with ctx.scope(post="query", question_id="q-001"), caplog.at_level("WARNING"):
        rep = arch.answer(_question())
    _, entier = _repondre(ctx, index, k=5)
    assert 0 < len(rep.context_texts) < len(entier.context_texts)
    assert "hors de la fenêtre" in caplog.text
    assert len(rep.retrieved) == len(rep.context_texts)


def test_answer_avant_load_leve(ctx: RunCtx) -> None:
    with pytest.raises(RuntimeError):
        _arch(ctx).answer(_question())


# -- mise à jour incrémentale -------------------------------------------------------------------

_FICHIERS = (
    "passages.jsonl",
    "entities.json",
    "relations.json",
    "extractions.json",
    "graph/graph.json",
)


def _comme_index_complet(ctx: RunCtx, apres: ParsedCorpus, v2: Path, tmp_path: Path) -> None:
    _indexer(ctx, apres, tmp_path / "complet")
    for nom in _FICHIERS:
        assert (v2 / nom).read_bytes() == (tmp_path / "complet" / nom).read_bytes(), nom
    _citer_tout(ctx)
    _, a = _repondre(ctx, v2, k=8)
    _, b = _repondre(ctx, tmp_path / "complet", k=8)
    assert [s.passage.passage_id for s in a.retrieved] == [
        s.passage.passage_id for s in b.retrieved
    ]


def test_update_sans_changement_aucun_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    avant = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(), minicorpus, index, tmp_path / "v2")
    assert len(_spans(ctx)) == avant
    for nom in _FICHIERS:
        assert (tmp_path / "v2" / nom).read_bytes() == (index / nom).read_bytes()


def test_update_ajout_unit_le_sous_graphe_sans_toucher_aux_passages_inchanges(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ajoute = minicorpus.documents[0]
    sans = _sans(minicorpus, ajoute)
    _indexer(ctx, sans, tmp_path / "v1")
    avant = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(added=(ajoute,)), minicorpus, tmp_path / "v1", tmp_path / "v2"
        )
    nouveaux = _spans(ctx)[avant:]
    chunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    attendus = {p.passage_id for p in chunker.chunk(ajoute)}
    assert {s["wl.step"] for s in nouveaux} == {f"graph.extract.{i}" for i in attendus}
    assert {s["wl.post"] for s in nouveaux} == {"update"}
    assert len(nouveaux) == len(attendus)  # aucun appel sur un Passage inchangé
    _comme_index_complet(ctx, minicorpus, tmp_path / "v2", tmp_path)


def test_update_suppression_retire_les_passages_sans_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    retire = minicorpus.documents[0]
    sans = _sans(minicorpus, retire)
    avant = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(removed=(retire.doc_id,)), sans, index, tmp_path / "v2")
    assert len(_spans(ctx)) == avant
    apres = lire_passages(tmp_path / "v2")
    assert all(p.doc_id != retire.doc_id for p in apres)
    ids = {p.passage_id for p in apres}
    for n in _json(tmp_path / "v2", "graph/graph.json")["nodes"]:
        assert set(n["passage_ids"]) <= ids
    for e in _json(tmp_path / "v2", "graph/graph.json")["edges"]:
        assert set(e["passage_ids"]) <= ids
    assert not set(retire.anchors) & {a for p in apres for a in p.anchor_ids}
    _comme_index_complet(ctx, sans, tmp_path / "v2", tmp_path)


def test_update_ne_reembarque_que_les_textes_changes(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    arch = _arch(ctx)
    appels: list[int] = []
    vrai = arch.embedder.embed_passages

    def espion(textes: Any) -> Any:
        appels.append(len(textes))
        return vrai(textes)

    arch.embedder.embed_passages = espion
    sans = _sans(minicorpus, minicorpus.documents[0])
    with ctx.scope(post="update"):
        arch.update(
            CorpusChange(removed=(minicorpus.documents[0].doc_id,)), sans, index, tmp_path / "v2"
        )
    total = len(_json(index, "entities.json")) + len(_json(index, "relations.json"))
    changes = 0
    for nom in ("entities.json", "relations.json"):
        avant, apres = _json(index, nom), _json(tmp_path / "v2", nom)
        changes += sum(1 for i, h in apres.items() if avant.get(i) != h)
    assert sum(appels) == changes < total  # exactement les textes changés
    # les index denses ne contiennent plus que ce qui reste dans le graphe
    nv = _arch(ctx)
    nv.load(tmp_path / "v2")
    q = np.ones(64, dtype=np.float32)
    assert {i for i, _ in nv._vec_entites.search(q, 10_000)} == set(nv._graphe.graph().nodes)
    assert {i for i, _ in nv._vec_relations.search(q, 10_000)} == set(nv._relations)


def test_update_document_modifie_nouveau_doc_id_reprend_les_extractions(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    doc = max(minicorpus.documents, key=lambda d: len(d.blocks))
    blocs = list(doc.blocks)
    blocs[-1] = blocs[-1].model_copy(update={"text": blocs[-1].text + " Gorvane Ellis."})
    nouveau = doc.model_copy(update={"doc_id": "e" * 16, "blocks": tuple(blocs)})
    apres = minicorpus.model_copy(
        update={"documents": tuple(nouveau if d is doc else d for d in minicorpus.documents)}
    )
    chunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    anciens_textes = {p.text for p in chunker.chunk(doc)}
    attendus = {p.passage_id for p in chunker.chunk(nouveau) if p.text not in anciens_textes}
    assert 0 < len(attendus) < len(chunker.chunk(nouveau))
    n = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(modified=((doc.doc_id, nouveau),)), apres, index, tmp_path / "v2"
        )
    extraits = {s["wl.step"] for s in _spans(ctx)[n:]}
    assert extraits == {f"graph.extract.{i}" for i in attendus}
    ids = [p.passage_id for p in lire_passages(tmp_path / "v2")]
    assert len(ids) == len(set(ids))  # remplacé, pas dupliqué
    _comme_index_complet(ctx, apres, tmp_path / "v2", tmp_path)


def test_cache_d_extraction_partage_avec_graphrag() -> None:
    from wavelibrarian.architectures import graphrag
    from wavelibrarian.components.graph import cache

    assert graphrag.cle_extraction is cache.cle_extraction
    assert graphrag.extraire_avec_cache is cache.extraire_avec_cache


def _extraction_par_paire(req: Any) -> str:
    """Chaque Passage relie Orvane et Ellis avec une description qui lui est propre."""
    return json.dumps(
        {
            "entities": [
                {"name": "Orvane", "kind": "org", "description": f"guilde vue par {req.step}"},
                {"name": "Ellis", "kind": "person", "description": "membre"},
            ],
            "relations": [
                {
                    "source": "Orvane",
                    "target": "Ellis",
                    "description": f"lien {req.step}",
                    "weight": 0.5,
                }
            ],
        }
    )


def test_toutes_les_descriptions_d_une_paire_sont_encodees(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script(  # type: ignore[attr-defined]
        "extract_entities", "graph.extract.*", _extraction_par_paire
    )
    arch = _arch(ctx)
    textes: list[str] = []
    vrai = arch.embedder.embed_passages

    def espion(lot: Any) -> Any:
        textes.extend(lot)
        return vrai(lot)

    arch.embedder.embed_passages = espion
    with ctx.scope(post="indexing"):
        arch.index(minicorpus, tmp_path / "i")
    etapes = {s["wl.step"] for s in _spans(ctx, "graph.extract.")}
    assert len(etapes) > 1 and len(_json(tmp_path / "i", "relations.json")) == 1
    (relation,) = [t for t in textes if t.startswith("Orvane - Ellis") or "Ellis - " in t]
    assert all(f"lien {e}" in relation for e in etapes)
    (entite,) = [t for t in textes if t.startswith("Orvane :")]
    assert all(f"guilde vue par {e}" in entite for e in etapes)


def test_texte_repete_extrait_une_seule_fois(ctx: RunCtx, tmp_path: Path) -> None:
    from wavelibrarian.components.graph.cache import extraire_avec_cache
    from wavelibrarian.components.graph.extraction import EntityExtractor
    from wavelibrarian.core.types import Passage

    def passage(i: str) -> Passage:
        return Passage(passage_id=i, doc_id="d", text="Orvane recrute Ellis.", anchor_ids=("a",))

    graphe = ctx.build("graph_store", ComponentSpec(name="networkx"))  # type: ignore[attr-defined]
    cache: dict[str, Any] = {}
    with ctx.scope(post="indexing"):
        extraits = extraire_avec_cache(
            EntityExtractor(ctx), graphe, [passage("p1"), passage("p2")], cache
        )
    assert [p.passage_id for p in extraits] == ["p1"] and len(_spans(ctx)) == 1
    noeuds = graphe.graph().nodes(data=True)
    assert noeuds and all({"p1", "p2"} <= set(d["passage_ids"]) for _, d in noeuds)

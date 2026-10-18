"""Story 7.6 : Architecture `graphrag` (extraction, communautés, recherche locale et globale)."""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures._passages import lire_passages
from wavelibrarian.architectures.graphrag import GraphRag
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
    return ctx.build("architecture", ComponentSpec(name="graphrag", params=params))


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


# -- enregistrement et indexation ---------------------------------------------------------------


def test_enregistrement_et_capacites(ctx: RunCtx) -> None:
    assert registry.get("architecture", "graphrag") is GraphRag
    assert GraphRag.capabilities.incremental_update is True
    assert GraphRag.capabilities.retrieval_method == "ranked"
    assert _arch(ctx).embedder_dim() == 64
    assert "search" in GraphRag.query_params


def test_indexation_extraction_communautes_rapports_au_poste_indexing(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path
) -> None:
    passages = lire_passages(index)
    feuilles = [p for p in passages if p.level == 0]
    rapports = [p for p in passages if p.level == 1]
    comms = _json(index, "communities.json")["communities"]
    assert feuilles and rapports and len(rapports) == len(comms)
    assert (index / "graph" / "graph.json").exists() and (index / "vectors").is_dir()
    existants = _existants(minicorpus)
    for r in rapports:
        assert set(r.anchor_ids) <= existants and r.child_ids
    spans = _spans(ctx)
    assert {s["wl.post"] for s in spans} == {"indexing"}
    extraction = [s for s in spans if s["wl.step"].startswith("graph.extract.")]
    rapport = [s for s in spans if s["wl.step"].startswith("graph.report.")]
    assert len(extraction) == len(feuilles) and len(rapport) == len(rapports)
    assert len(spans) == len(extraction) + len(rapport)


def test_indexation_deterministe(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    _indexer(ctx, minicorpus, tmp_path / "a")
    _indexer(ctx, minicorpus, tmp_path / "b")
    for nom in ("passages.jsonl", "communities.json", "entities.json", "graph/graph.json"):
        assert (tmp_path / "a" / nom).read_bytes() == (tmp_path / "b" / nom).read_bytes()


def test_search_hors_de_l_index_key(ctx: RunCtx) -> None:
    a, b = _arch(ctx, search="local"), _arch(ctx, search="global", map_batch=2, k=9)
    assert a.index_key() == b.index_key()
    assert _arch(ctx, min_community_size=2).index_key() != a.index_key()


# -- recherche locale ---------------------------------------------------------------------------


def test_recherche_locale_contexte_et_citations(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path
) -> None:
    _citer_tout(ctx)
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, index, search="local", k=3, k_entities=4, k_reports=2)
    assert not rep.abstained and rep.retrieval_method == "ranked"
    assert any(t.startswith("[S") and "Relations :" in t for t in rep.context_texts)
    retrouves = [s.passage for s in rep.retrieved]
    assert sum(1 for p in retrouves if p.level == 0) == 3  # Passages sources
    assert 1 <= sum(1 for p in retrouves if p.level == 1 and p.child_ids) <= 4
    assert [s.rank for s in rep.retrieved] == list(range(1, len(rep.retrieved) + 1))
    scores = [s.score for s in rep.retrieved]
    assert scores == sorted(scores, reverse=True)
    existants = _existants(minicorpus)
    assert rep.citations and {c.anchor_id for c in rep.citations} <= existants
    assert {a for s in rep.retrieved for a in s.passage.anchor_ids} <= existants
    # un seul appel LLM de requête : generate (pas de map en local)
    assert [s["wl.step"] for s in _spans(ctx)[avant:]] == ["generate"]


def test_recherche_locale_entites_proches_par_embedding(index: Path, ctx: RunCtx) -> None:
    arch = _arch(ctx)
    arch.load(index)
    g = arch._graphe.graph()
    assert g.number_of_nodes() == len(_json(index, "entities.json"))
    cible = sorted(g.nodes)[7]
    texte = f"{g.nodes[cible]['name']} : {g.nodes[cible]['description']}"
    with ctx.scope(post="query", question_id="q-001"):
        q = arch.embedder.embed_queries([texte])[0]
    assert arch._vecteurs.search(q, 3)[0][0] == cible  # la description comme Question


def test_graphe_vide_abstention_sans_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ctx.provider.script(  # type: ignore[attr-defined]
        "extract_entities", "graph.extract.*", '{"entities": [], "relations": []}'
    )
    _indexer(ctx, minicorpus, tmp_path / "i")
    assert not [p for p in lire_passages(tmp_path / "i") if p.level == 1]
    for mode in ("local", "global"):
        _, rep = _repondre(ctx, tmp_path / "i", search=mode)
        assert rep.abstained and rep.citations == ()
    assert not _spans(ctx, "generate") and not _spans(ctx, "graphrag.map")


# -- recherche globale --------------------------------------------------------------------------


def test_recherche_globale_map_puis_reduce(ctx: RunCtx, index: Path) -> None:
    _citer_tout(ctx)
    rapports = [p for p in lire_passages(index) if p.level == 1]
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, index, search="global", map_batch=4)
    spans = _spans(ctx)[avant:]
    n_lots = math.ceil(len(rapports) / 4)
    steps = [s["wl.step"] for s in spans]
    assert steps == [*(f"graphrag.map.{n}" for n in range(1, n_lots + 1)), "generate"]
    assert {s["wl.post"] for s in spans} == {"query"}
    anc_rapports = {a for r in rapports for a in r.anchor_ids}
    assert rep.citations and {c.anchor_id for c in rep.citations} <= anc_rapports
    assert {s.passage.passage_id for s in rep.retrieved} == {r.passage_id for r in rapports}
    assert [s.rank for s in rep.retrieved] == list(range(1, len(rapports) + 1))
    assert len(rep.context_texts) == n_lots


def test_global_et_local_partagent_le_meme_index(ctx: RunCtx, index: Path) -> None:
    avant = (index / "passages.jsonl").read_bytes()
    _repondre(ctx, index, search="global")
    _repondre(ctx, index, search="local")
    assert (index / "passages.jsonl").read_bytes() == avant


def test_global_lots_bornes_et_map_vide(ctx: RunCtx, index: Path) -> None:
    avant = len(_spans(ctx, "graphrag.map"))
    _, rep = _repondre(ctx, index, search="global", map_batch=1, max_map_batches=3)
    assert len(_spans(ctx, "graphrag.map")) - avant == 3 and len(rep.context_texts) == 3
    ctx.provider.script("global_map", "graphrag.map.*", "   ")  # type: ignore[attr-defined]
    avant = len(_spans(ctx, "generate"))
    _, rep = _repondre(ctx, index, search="global")
    assert rep.abstained and len(_spans(ctx, "generate")) == avant  # aucune sortie : pas de reduce


def test_global_map_passage_aux_ancrages_des_rapports(ctx: RunCtx, index: Path) -> None:
    rapports = [p for p in lire_passages(index) if p.level == 1]
    arch = _arch(ctx, search="global")
    arch.load(index)
    lot = rapports[:3]
    with ctx.scope(post="query", question_id="q-001"):
        noeud = arch._map(_question(), 1, lot)
    assert noeud is not None and noeud.level == 1
    assert set(noeud.child_ids) == {r.passage_id for r in lot}
    assert set(noeud.anchor_ids) == {a for r in lot for a in r.anchor_ids}


# -- mise à jour incrémentale -------------------------------------------------------------------


def test_update_sans_changement_aucun_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    avant = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(), minicorpus, index, tmp_path / "v2")
    assert len(_spans(ctx)) == avant
    for nom in ("passages.jsonl", "communities.json", "graph/graph.json"):
        assert (tmp_path / "v2" / nom).read_bytes() == (index / nom).read_bytes()


def test_update_suppression_retire_les_passages_et_regenere_les_rapports_changes(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    retire = minicorpus.documents[0]
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    avant = len(_spans(ctx))
    anciens = lire_passages(index)
    n_rapports = sum(1 for p in anciens if p.level == 1)
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(removed=(retire.doc_id,)), sans, index, tmp_path / "v2")
    nouveaux = _spans(ctx)[avant:]
    assert not [s for s in nouveaux if s["wl.step"].startswith("graph.extract.")]
    regeneres = [s for s in nouveaux if s["wl.step"].startswith("graph.report.")]
    assert {s["wl.post"] for s in nouveaux} == {"update"}
    assert 0 < len(regeneres) < n_rapports  # seules les communautés dont la composition change
    apres = lire_passages(tmp_path / "v2")
    assert all(p.doc_id != retire.doc_id for p in apres if p.level == 0)
    assert not set(retire.anchors) & {a for p in apres for a in p.anchor_ids}
    ids_feuilles = {p.passage_id for p in apres if p.level == 0}
    for n in _json(tmp_path / "v2", "graph/graph.json")["nodes"]:
        assert set(n["passage_ids"]) <= ids_feuilles
    anciens_rapports = {p.passage_id: p for p in anciens if p.level == 1}
    repris = [p for p in apres if p.level == 1 and anciens_rapports.get(p.passage_id) == p]
    assert repris  # les rapports des communautés intactes sont repris tels quels
    _citer_tout(ctx)
    for mode in ("local", "global"):
        _, rep = _repondre(ctx, tmp_path / "v2", search=mode)
        assert {c.anchor_id for c in rep.citations} <= _existants(sans)


def test_update_ajout_n_extrait_que_les_nouveaux_passages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    ajoute = minicorpus.documents[0]
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    _indexer(ctx, sans, tmp_path / "v1")
    avant = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(added=(ajoute,)), minicorpus, tmp_path / "v1", tmp_path / "v2"
        )
    nouveaux = _spans(ctx)[avant:]
    extraits = [s for s in nouveaux if s["wl.step"].startswith("graph.extract.")]
    chunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    assert len(extraits) == len(chunker.chunk(ajoute))
    assert {s["wl.post"] for s in nouveaux} == {"update"}
    ids = {p.passage_id for p in lire_passages(tmp_path / "v2") if p.level == 0}
    assert {p.passage_id for p in chunker.chunk(ajoute)} <= ids
    _citer_tout(ctx)
    _, rep = _repondre(ctx, tmp_path / "v2", search="global")
    assert rep.citations and {c.anchor_id for c in rep.citations} <= _existants(minicorpus)


def test_update_document_modifie_ne_reextrait_pas_les_passages_identiques(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    doc = max(minicorpus.documents, key=lambda d: len(d.blocks))
    blocs = list(doc.blocks)
    blocs[-1] = blocs[-1].model_copy(update={"text": blocs[-1].text + " Gorvane Ellis."})
    nouveau = doc.model_copy(update={"blocks": tuple(blocs)})
    apres = minicorpus.model_copy(
        update={"documents": tuple(nouveau if d is doc else d for d in minicorpus.documents)}
    )
    chunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    avant_p = {p.passage_id: p.text for p in chunker.chunk(doc)}
    apres_p = {p.passage_id: p.text for p in chunker.chunk(nouveau)}
    changes = {i for i, t in apres_p.items() if avant_p.get(i) != t}
    assert changes and len(changes) < len(apres_p)
    n = len(_spans(ctx))
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(modified=((doc.doc_id, nouveau),)), apres, index, tmp_path / "v2"
        )
    extraits = {s["wl.step"] for s in _spans(ctx)[n:] if s["wl.step"].startswith("graph.extract.")}
    assert extraits == {f"graph.extract.{i}" for i in changes}
    ids = [p.passage_id for p in lire_passages(tmp_path / "v2") if p.level == 0]
    assert len(ids) == len(set(ids))  # remplacé, pas dupliqué


def test_update_reembarque_les_seules_entites_changees(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    arch = _arch(ctx)
    appels: list[int] = []
    vrai = arch.embedder.embed_passages

    def espion(textes: Any) -> Any:
        appels.append(len(textes))
        return vrai(textes)

    arch.embedder.embed_passages = espion
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    with ctx.scope(post="update"):
        arch.update(
            CorpusChange(removed=(minicorpus.documents[0].doc_id,)), sans, index, tmp_path / "v2"
        )
    assert sum(appels) < len(_json(index, "entities.json"))


def test_fenetre_du_generateur_ecarte_les_blocs_avec_avertissement(
    ctx: RunCtx, index: Path, caplog: pytest.LogCaptureFixture
) -> None:
    arch = _arch(ctx, search="local", k=5, k_entities=5)
    arch.load(index)
    arch._fenetre = lambda modele: 1700
    _citer_tout(ctx)
    with ctx.scope(post="query", question_id="q-001"), caplog.at_level("WARNING"):
        rep = arch.answer(_question())
    complet = _arch(ctx, search="local", k=5, k_entities=5)
    complet.load(index)
    with ctx.scope(post="query", question_id="q-001"):
        entier = complet.answer(_question())
    assert 0 < len(rep.context_texts) < len(entier.context_texts)
    assert "hors de la fenêtre" in caplog.text
    assert len(rep.retrieved) <= len(rep.context_texts)  # rien d'écarté dans `retrieved`

"""Story 7.2 : Architecture `pageindex` (arbre de sections navigué par `select_nodes`)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.pageindex import PageIndex
from wavelibrarian.core.errors import ConfigError
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
    return ctx.build("architecture", ComponentSpec(name="pageindex", params=params))


def _indexer(ctx: RunCtx, corpus: ParsedCorpus, dossier: Path, **params: Any) -> Any:
    arch = _arch(ctx, **params)
    with ctx.scope(post="indexing"):
        arch.index(corpus, dossier)
    return arch


def _spans(ctx: RunCtx, role: str | None = None) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    spans = list(map(json.loads, lignes))
    prefixe = {
        "summarize": "pageindex.summarize",
        "select_nodes": "pageindex.select",
        "generate": "generate",
    }
    return [s for s in spans if role is None or s["wl.step"].startswith(prefixe[role])]


def _question(texte: str = "Depuis quand Bram Oskelle est-il en poste ?") -> QuestionInput:
    return QuestionInput(question_id="q-001", text=texte, lang="fr")


def _arbres(dossier: Path) -> dict[str, dict[str, Any]]:
    brut = json.loads((dossier / "tree.json").read_text(encoding="utf-8"))
    return {n["node_id"]: n for n in brut["nodes"]}


def _repondre(ctx: RunCtx, dossier: Path, question: QuestionInput | None = None, **p: Any) -> Any:
    arch = _arch(ctx, **p)
    arch.load(dossier)
    with ctx.scope(post="query", question_id="q-001"):
        return arch, arch.answer(question or _question())


def test_enregistrement_et_capacites() -> None:
    assert registry.get("architecture", "pageindex") is PageIndex
    assert PageIndex.capabilities.retrieval_method == "provided"
    assert "max_nodes_read" in PageIndex.query_params


def test_arbre_par_document_hierarchie_resume_et_ancrage(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    noeuds = _arbres(tmp_path / "i")
    docs = {d.doc_id: d for d in minicorpus.documents}
    assert {n["doc_id"] for n in noeuds.values()} == set(docs)  # un arbre par Document
    # un nœud par Ancrage, chacun avec titre, Ancrage existant et résumé
    for doc in minicorpus.documents:
        du_doc = [n for n in noeuds.values() if n["doc_id"] == doc.doc_id]
        assert [n["anchor_id"] for n in du_doc] == list(doc.anchors)
        assert all(n["title"] for n in du_doc)
    avec_texte = [n for n in noeuds.values() if n["text"].strip()]
    assert avec_texte and all(n["summary"] for n in avec_texte)
    # hiérarchie des titres : le parent a un chemin de titres préfixe strict
    hierarchiques = 0
    for n in noeuds.values():
        if n["parent"] is None:
            continue
        p = noeuds[n["parent"]]
        assert n["node_id"] in p["children"] and p["doc_id"] == n["doc_id"]
        chemin_n = docs[n["doc_id"]].anchors[n["anchor_id"]].heading_path
        chemin_p = docs[p["doc_id"]].anchors[p["anchor_id"]].heading_path
        assert chemin_n[: len(chemin_p)] == chemin_p and len(chemin_n) > len(chemin_p)
        hierarchiques += 1
    assert hierarchiques > 0
    # un enfant a un parent déjà ouvert (ordre du Document)
    ordre = list(noeuds)
    assert all(ordre.index(n["parent"]) < ordre.index(i) for i, n in noeuds.items() if n["parent"])


def test_pdf_sans_titre_un_noeud_par_page(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    pdfs = [d for d in minicorpus.documents if d.format == "pdf"]
    if not pdfs:
        pytest.skip("pas de PDF dans ce Mini-corpus ingéré")
    un = minicorpus.model_copy(update={"documents": (pdfs[0],)})
    _indexer(ctx, un, tmp_path / "i")
    noeuds = list(_arbres(tmp_path / "i").values())
    assert [n["anchor_id"] for n in noeuds] == list(pdfs[0].anchors)
    assert all(n["parent"] is None and n["title"].startswith("Page ") for n in noeuds)


def test_summarize_au_poste_indexing_et_load_sans_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    resumes = _spans(ctx, "summarize")
    assert resumes and {s["wl.step"] for s in resumes} == {"pageindex.summarize"}
    assert {s["wl.post"] for s in resumes} == {"indexing"}
    avant = len(_spans(ctx))
    neuve = _arch(ctx)
    neuve.load(tmp_path / "i")
    assert len(_spans(ctx)) == avant  # aucun appel (ni LLM ni embedding) au chargement
    assert set(neuve._noeuds) == set(_arbres(tmp_path / "i"))
    assert [n["summary"] for n in _arbres(tmp_path / "i").values()] == [
        n.summary for n in neuve._noeuds.values()
    ]


def test_navigation_faux_llm_citation_valide_sans_embedding(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, tmp_path / "i")
    existants = {a for d in minicorpus.documents for a in d.anchors}
    assert rep.retrieval_method == "provided" and not rep.abstained
    assert rep.citations and {c.anchor_id for c in rep.citations} <= existants
    assert rep.retrieved and [s.rank for s in rep.retrieved] == list(
        range(1, len(rep.retrieved) + 1)
    )
    assert {a for s in rep.retrieved for a in s.passage.anchor_ids} <= existants
    nouveaux = _spans(ctx)[avant:]
    assert {s["wl.kind"] for s in nouveaux} == {"llm"}  # aucun span d'embedding
    assert [s["wl.step"] for s in nouveaux if s["wl.step"].startswith("pageindex.select")] == [
        "pageindex.select.1"
    ]
    assert {s["wl.post"] for s in nouveaux} == {"query"}


def test_navigation_scenarisee_descend_et_lit_dans_l_ordre(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    noeuds = _arbres(tmp_path / "i")
    parent = next(
        n for n in noeuds.values() if n["children"] and n["parent"] is None and n["text"].strip()
    )
    enfant = noeuds[parent["children"][0]]
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes",
        "pageindex.select.1",
        json.dumps({"node_ids": [parent["node_id"]], "done": False}),
    )
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes",
        "pageindex.select.2",
        json.dumps({"node_ids": [enfant["node_id"]], "done": True}),
    )
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, tmp_path / "i")
    assert [s.passage.anchor_ids[0] for s in rep.retrieved] == [
        parent["anchor_id"],
        enfant["anchor_id"],
    ]
    assert rep.retrieved[0].passage.text == parent["text"]
    etapes = [
        s["wl.step"] for s in _spans(ctx)[avant:] if s["wl.step"].startswith("pageindex.select")
    ]
    assert etapes == ["pageindex.select.1", "pageindex.select.2"]


def test_borne_max_nodes_read_avant_chaque_lecture_et_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    noeuds = _arbres(tmp_path / "i")
    racines = [n for n in noeuds.values() if n["parent"] is None and n["text"].strip()]
    assert len(racines) >= 4
    ids = [n["node_id"] for n in racines]
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes", "pageindex.select.*", json.dumps({"node_ids": ids, "done": False})
    )
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, tmp_path / "i", max_nodes_read=3)
    assert len(rep.retrieved) == 3  # tronqué à la borne, malgré une liste plus longue
    appels = [s for s in _spans(ctx)[avant:] if s["wl.step"].startswith("pageindex.select")]
    assert len(appels) == 1  # borne atteinte : pas de second appel de sélection


def test_borne_limite_aussi_le_max_transmis(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    vus: list[int] = []

    def selection(req: Any) -> str:
        vus.append(int(req.inputs["max"]))
        return json.dumps({"node_ids": [req.inputs["nodes"][0]["id"]], "done": False})

    ctx.provider.script("select_nodes", "pageindex.select.*", selection)  # type: ignore[attr-defined]
    _, rep = _repondre(ctx, tmp_path / "i", max_nodes_read=2)
    assert len(rep.retrieved) <= 2
    assert vus[0] == 2 and all(b < a for a, b in zip(vus, vus[1:], strict=False))


def test_identifiant_inconnu_ignore_journalise_et_abstention(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    reel = next(iter(_arbres(tmp_path / "i")))
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes",
        "pageindex.select.1",
        json.dumps({"node_ids": ["inconnu-1", reel, "inconnu-2"], "done": True}),
    )
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.pageindex"):
        _, rep = _repondre(ctx, tmp_path / "i")
    avertissements = [r.getMessage() for r in caplog.records if "inconnu" in r.getMessage()]
    assert len(avertissements) == 1 and "2 identifiant" in avertissements[0]
    assert len(rep.retrieved) <= 1


def test_aucun_noeud_valide_abstention_sans_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes", "pageindex.select.1", json.dumps({"node_ids": ["x"], "done": True})
    )
    avant = len(_spans(ctx))
    _, vide = _repondre(ctx, tmp_path / "i")
    assert vide.abstained and vide.retrieved == () and vide.citations == ()
    assert vide.retrieval_method == "provided"
    assert not [s for s in _spans(ctx)[avant:] if s["wl.step"] == "generate"]


def test_liste_trop_longue_pour_la_fenetre_refusee(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    arch = _arch(ctx)
    arch.load(tmp_path / "i")
    arch._fenetre = lambda modele: 50
    avant = len(_spans(ctx, "select_nodes"))
    with ctx.scope(post="query", question_id="q-001"), pytest.raises(ConfigError, match="fenêtre"):
        arch.answer(_question())
    assert len(_spans(ctx, "select_nodes")) == avant


def test_section_tronquee_avant_resume(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    arch = _arch(ctx)
    arch._fenetre = lambda modele: 200
    long = "mot " * 5000
    assert len(arch._tronquer(long)) < len(long)
    arch._fenetre = lambda modele: None
    assert arch._tronquer(long) == long


def test_update_incremental_ne_resume_que_les_documents_changes(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    assert PageIndex.capabilities.incremental_update is True
    docs = list(minicorpus.documents)
    retire, garde = docs[0], docs[1:]
    _indexer(ctx, minicorpus, tmp_path / "v1")
    n_v1 = len(_spans(ctx, "summarize"))
    # suppression seule : aucun appel, plus aucun nœud du Document supprimé
    sans = minicorpus.model_copy(update={"documents": tuple(garde)})
    maj = _arch(ctx)
    with ctx.scope(post="update"):
        maj.update(CorpusChange(removed=(retire.doc_id,)), sans, tmp_path / "v1", tmp_path / "v2")
    assert len(_spans(ctx, "summarize")) == n_v1
    arbres = _arbres(tmp_path / "v2")
    assert retire.doc_id not in {n["doc_id"] for n in arbres.values()}
    assert not set(retire.anchors) & {n["anchor_id"] for n in arbres.values()}
    # ajout : seul le Document ajouté est résumé, au poste update
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(added=(retire,)), minicorpus, tmp_path / "v2", tmp_path / "v3"
        )
    nouveaux = _spans(ctx, "summarize")[n_v1:]
    nb_a_resumer = sum(
        1
        for b_id in retire.anchors
        if any(b.anchor_id == b_id and b.text.strip() for b in retire.blocks)
    )
    assert len(nouveaux) == nb_a_resumer and {s["wl.post"] for s in nouveaux} == {"update"}
    assert [n["anchor_id"] for n in _arbres(tmp_path / "v3").values()] == [
        a for d in minicorpus.documents for a in d.anchors
    ]
    neuve = _arch(ctx)
    neuve.load(tmp_path / "v3")
    assert len(neuve._noeuds) == len(_arbres(tmp_path / "v3"))

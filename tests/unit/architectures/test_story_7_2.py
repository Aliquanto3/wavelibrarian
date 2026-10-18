"""Story 7.2 : Architecture `pageindex` (arbre de sections navigué par `select_nodes`)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.pageindex import _SYSTEM_RESUME, PageIndex
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Anchor, Block, ParsedCorpus, ParsedDocument, QuestionInput
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
    arch._fenetre = lambda modele: 400
    tok = ctx.tokenizer_for(arch._summary_model)
    reserve = 128 + tok.count(_SYSTEM_RESUME)
    long = "mot " * 5000
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.pageindex"):
        coupe = arch._tronquer(long)
    assert 0 < tok.count(coupe) <= 400 - reserve < tok.count(long)
    assert long.startswith(coupe)
    assert any("tronquée avant résumé" in r.getMessage() for r in caplog.records)
    caplog.clear()
    court = "mot " * 10
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.pageindex"):
        assert arch._tronquer(court) == court
    assert not caplog.records
    arch._fenetre = lambda modele: None
    assert arch._tronquer(long) == long
    # fenêtre plus petite que la réserve : refus explicite, pas un résumé d'un caractère
    arch._fenetre = lambda modele: reserve
    with pytest.raises(ConfigError, match="summary_max_tokens"):
        arch._tronquer(long)


def _pdf(n_pages: int, mots_par_page: int = 20, doc_id: str = "d" * 16) -> ParsedDocument:
    ancres = {
        f"{doc_id}#p{i}": Anchor(
            anchor_id=f"{doc_id}#p{i}", doc_id=doc_id, source_path="long.pdf", page=i
        )
        for i in range(1, n_pages + 1)
    }
    blocs = tuple(
        Block(text=f"Page {i} : " + "contenu " * mots_par_page, anchor_id=a, kind="text")
        for i, a in enumerate(ancres, start=1)
    )
    return ParsedDocument(
        doc_id=doc_id, source_path="long.pdf", format="pdf", lang="fr", blocks=blocs, anchors=ancres
    )


def _taille_requete(ctx: RunCtx, req: Any) -> int:
    """Tokens de la requête telle qu'envoyée (system, messages, sortie réservée)."""
    tok = ctx.tokenizer_for(req.model_id)
    texte = "\n".join([req.system, *(m.content for m in req.messages)])
    return int(tok.count(texte)) + int(req.max_tokens)


def test_selection_paginee_pour_un_pdf_a_beaucoup_de_pages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    corpus = minicorpus.model_copy(update={"documents": (_pdf(150),)})
    _indexer(ctx, corpus, tmp_path / "i")
    racines = [n["node_id"] for n in _arbres(tmp_path / "i").values() if n["parent"] is None]
    assert len(racines) == 150
    fenetre = 1500
    vus: list[list[str]] = []
    tailles: list[int] = []
    cible = racines[-1]

    def selection(req: Any) -> str:
        ids = [n["id"] for n in req.inputs["nodes"]]
        vus.append(ids)
        tailles.append(_taille_requete(ctx, req))
        return json.dumps({"node_ids": [cible] if cible in ids else [], "done": cible in ids})

    ctx.provider.script("select_nodes", "pageindex.select.*", selection)  # type: ignore[attr-defined]
    arch = _arch(ctx, generator={"name": "llm", "params": {"max_tokens": 64}})
    arch.load(tmp_path / "i")
    arch._fenetre = lambda modele: fenetre
    avant = len(_spans(ctx))
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(_question())
    assert len(vus) >= 3  # liste découpée en plusieurs lots
    assert [i for lot in vus for i in lot] == racines  # tous présentés, dans l'ordre, une fois
    assert max(tailles) <= fenetre
    etapes = [s["wl.step"] for s in _spans(ctx)[avant:] if s["wl.step"].startswith("pageindex.s")]
    assert etapes == [f"pageindex.select.{i}" for i in range(1, len(vus) + 1)]
    assert [s.passage.anchor_ids[0] for s in rep.retrieved] == [
        corpus.documents[0].doc_id + "#p150"
    ]


def test_contexte_borne_par_la_fenetre_du_generateur(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    corpus = minicorpus.model_copy(update={"documents": (_pdf(8, mots_par_page=200),)})
    _indexer(ctx, corpus, tmp_path / "i")
    racines = [n["node_id"] for n in _arbres(tmp_path / "i").values()]
    ctx.provider.script(  # type: ignore[attr-defined]
        "select_nodes", "pageindex.select.*", json.dumps({"node_ids": racines, "done": True})
    )
    envoyes: list[int] = []

    def generation(req: Any) -> str:
        envoyes.append(_taille_requete(ctx, req))
        return json.dumps({"answer": "x", "citations": ["S1"], "abstain": False})

    ctx.provider.script("generate", "generate", generation)  # type: ignore[attr-defined]
    arch: Any = None
    for fenetre, unique in ((1500, False), (500, True)):
        envoyes.clear()
        caplog.clear()
        arch = _arch(ctx, generator={"name": "llm", "params": {"max_tokens": 64}})
        arch.load(tmp_path / "i")
        arch._fenetre = lambda modele, f=fenetre: f
        with (
            caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.pageindex"),
            ctx.scope(post="query", question_id="q-001"),
        ):
            rep = arch.answer(_question())
        assert envoyes and envoyes[0] <= fenetre  # la requête envoyée tient dans la fenêtre
        lus = [s.passage.anchor_ids[0] for s in rep.retrieved]
        ordre = list(corpus.documents[0].anchors)
        if not unique:  # sections écartées depuis la dernière lue
            assert 1 < len(lus) < 8 and lus == ordre[: len(lus)]
            assert any("écartée" in r.getMessage() for r in caplog.records)
        else:  # une seule section, tronquée
            assert lus == ordre[:1]
            texte = rep.retrieved[0].passage.text
            assert texte and corpus.documents[0].blocks[0].text.startswith(texte)
            assert len(texte) < len(corpus.documents[0].blocks[0].text)
            assert any("tronquée avant génération" in r.getMessage() for r in caplog.records)
    arch._fenetre = lambda modele: 64 + 200
    # fenêtre sans place pour le contexte : refus explicite avant tout appel `generate`
    with pytest.raises(ConfigError, match="generator"):
        arch._borner_contexte(_question(), [arch._passage(next(iter(arch._noeuds.values())))])


def test_update_scenario_reel_document_modifie(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    from wavelibrarian.corpus.scenario import appliquer_fichier

    scenario = Path(__file__).resolve().parents[3] / "corpora/minicorpus/scenario/scenario.yaml"
    change, apres = appliquer_fichier(minicorpus, scenario, parser="markdown")
    assert change.modified and all(ancien != doc.doc_id for ancien, doc in change.modified)
    _indexer(ctx, minicorpus, tmp_path / "v1")
    v1 = _arbres(tmp_path / "v1")
    n_v1 = len(_spans(ctx, "summarize"))
    with ctx.scope(post="update"):
        _arch(ctx).update(change, apres, tmp_path / "v1", tmp_path / "v2")
    entrants = [*change.added, *(doc for _, doc in change.modified)]
    attendus = sum(
        1
        for d in entrants
        for a in d.anchors
        if any(b.anchor_id == a and b.text.strip() for b in d.blocks)
    )
    nouveaux = _spans(ctx, "summarize")[n_v1:]
    assert len(nouveaux) == attendus and {s["wl.post"] for s in nouveaux} == {"update"}
    v2 = _arbres(tmp_path / "v2")
    sortants = set(change.removed) | {ancien for ancien, _ in change.modified}
    assert not sortants & {n["doc_id"] for n in v2.values()}
    assert [n["anchor_id"] for n in v2.values()] == [a for d in apres.documents for a in d.anchors]
    # les nœuds des Documents inchangés sont repris tels quels (résumés compris)
    inchanges = {d.doc_id for d in apres.documents} - {d.doc_id for d in entrants}
    assert inchanges
    for i, n in v2.items():
        if n["doc_id"] in inchanges:
            assert v1[i] == n
    neuve = _arch(ctx)
    neuve.load(tmp_path / "v2")
    with ctx.scope(post="query", question_id="q-001"):
        neuve.answer(_question())


def test_update_reconstruit_un_document_absent_de_l_ancien_index(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    docs = minicorpus.documents
    _indexer(ctx, minicorpus.model_copy(update={"documents": docs[1:]}), tmp_path / "v1")
    with (
        caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.pageindex"),
        ctx.scope(post="update"),
    ):
        _arch(ctx).update(CorpusChange(), minicorpus, tmp_path / "v1", tmp_path / "v2")
    assert docs[0].doc_id in {n["doc_id"] for n in _arbres(tmp_path / "v2").values()}
    assert any("ancien index, reconstruit" in r.getMessage() for r in caplog.records)


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

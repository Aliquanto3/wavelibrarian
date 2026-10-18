"""Story 7.3 : Architecture `llm_wiki` (corpus compilé en pages, fidélité, copie au runner)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures.llm_wiki import LlmWiki
from wavelibrarian.core.types import ParsedCorpus, QuestionInput
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.architecture import CorpusChange
from wavelibrarian.ports.components import ComponentSpec
from wavelibrarian.report.wiki import section_fidelite, taux_fidelite
from wavelibrarian.runner.context import Context as RunCtx
from wavelibrarian.runner.index_cache import IndexCache


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
    return ctx.build("architecture", ComponentSpec(name="llm_wiki", params=params))


def _indexer(ctx: RunCtx, corpus: ParsedCorpus, dossier: Path, **params: Any) -> Any:
    arch = _arch(ctx, **params)
    with ctx.scope(post="indexing"):
        arch.index(corpus, dossier)
    return arch


def _spans(ctx: RunCtx, prefixe: str | None = None) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    spans = list(map(json.loads, lignes))
    return [s for s in spans if prefixe is None or s["wl.step"].startswith(prefixe)]


def _json(dossier: Path, nom: str) -> Any:
    return json.loads((dossier / nom).read_text(encoding="utf-8"))


def _question() -> QuestionInput:
    return QuestionInput(
        question_id="q-001", text="Depuis quand Bram Oskelle est-il en poste ?", lang="fr"
    )


def _repondre(ctx: RunCtx, dossier: Path, **p: Any) -> Any:
    arch = _arch(ctx, **p)
    arch.load(dossier)
    with ctx.scope(post="query", question_id="q-001"):
        return arch, arch.answer(_question())


def test_enregistrement_et_capacites() -> None:
    assert registry.get("architecture", "llm_wiki") is LlmWiki
    assert LlmWiki.capabilities.retrieval_method == "provided"
    assert LlmWiki.capabilities.incremental_update is True
    assert LlmWiki.query_params == frozenset({"k"})


def test_pages_de_level_1_aux_ancrages_filtres_au_poste_indexing(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    def sortie(req: Any) -> str:
        bloc = req.inputs["documents"][0]["blocks"][0]
        page = {"title": "P", "body": bloc["text"], "anchor_ids": [bloc["anchor_id"], "nope#1"]}
        return json.dumps({"pages": [page]})

    ctx.provider.script("wiki_compile", "wiki.compile", sortie)  # type: ignore[attr-defined]
    _indexer(ctx, minicorpus, tmp_path / "i")
    existants = {a for d in minicorpus.documents for a in d.anchors}
    lignes = (tmp_path / "i/passages.jsonl").read_text(encoding="utf-8").splitlines()
    passages = [json.loads(ligne) for ligne in lignes]
    assert len(passages) == len(minicorpus.documents)
    assert all(p["level"] == 1 and len(p["anchor_ids"]) == 1 for p in passages)
    assert {a for p in passages for a in p["anchor_ids"]} <= existants
    compiles = _spans(ctx, "wiki.compile")
    assert compiles and {s["wl.post"] for s in compiles} == {"indexing"}


def test_page_sans_ancrage_valide_ecartee_et_comptee(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx.provider.script(  # type: ignore[attr-defined]
        "wiki_compile",
        "wiki.compile",
        json.dumps({"pages": [{"title": "X", "body": "b", "anchor_ids": ["nope#1"]}]}),
    )
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.llm_wiki"):
        _indexer(ctx, minicorpus, tmp_path / "i")
    assert (tmp_path / "i/passages.jsonl").read_text(encoding="utf-8") == ""
    assert _json(tmp_path / "i", "wiki.json")["discarded_pages"] == len(minicorpus.documents)
    assert any("écartée(s) faute d'Ancrage valide" in r.getMessage() for r in caplog.records)
    assert _json(tmp_path / "i", "wiki_fidelity.json")["pages"] == []


def test_reponse_par_index_lexical_et_citation_aux_ancrages_des_pages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    avant = len(_spans(ctx))
    _, rep = _repondre(ctx, tmp_path / "i")
    existants = {a for d in minicorpus.documents for a in d.anchors}
    assert rep.retrieval_method == "provided" and not rep.abstained
    assert rep.citations and {c.anchor_id for c in rep.citations} <= existants
    assert rep.retrieved and all(s.passage.level == 1 for s in rep.retrieved)
    nouveaux = _spans(ctx)[avant:]
    assert {s["wl.kind"] for s in nouveaux} == {"llm"}  # aucun embedding
    assert [s["wl.step"] for s in nouveaux] == ["generate"]
    pages_anchors = {a for s in rep.retrieved for a in s.passage.anchor_ids}
    assert {c.anchor_id for c in rep.citations} <= pages_anchors


def test_question_sans_page_trouvee_abstention_sans_generate(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    _indexer(ctx, minicorpus, tmp_path / "i")
    arch = _arch(ctx)
    arch.load(tmp_path / "i")
    avant = len(_spans(ctx))
    with ctx.scope(post="query", question_id="q-001"):
        rep = arch.answer(QuestionInput(question_id="q-001", text="zzzqqq xxyyww", lang="fr"))
    assert rep.abstained and not rep.retrieved
    assert len(_spans(ctx)) == avant


def test_fidelite_echantillon_deterministe_et_fichier_ecrit(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    n = len(minicorpus.documents)
    assert n > 2
    _indexer(ctx, minicorpus, tmp_path / "a", fidelity_sample=2)
    _indexer(ctx, minicorpus, tmp_path / "b", fidelity_sample=2)
    a, b = _json(tmp_path / "a", "wiki_fidelity.json"), _json(tmp_path / "b", "wiki_fidelity.json")
    assert a == b and len(a["pages"]) == 2 and a["fidelity_sample"] == 2
    assert a["claims"] == sum(p["claims"] for p in a["pages"]) > 0
    assert a["supported"] == sum(p["supported"] for p in a["pages"])
    assert all(set(p) >= {"passage_id", "claims", "supported", "anchor_ids"} for p in a["pages"])
    assert len(_spans(ctx, "wiki.fidelity")) == 4
    # défaut : fidelity_sample = 5 (borné par le nombre de pages)
    _indexer(ctx, minicorpus, tmp_path / "c")
    assert len(_json(tmp_path / "c", "wiki_fidelity.json")["pages"]) == min(5, n)


def test_fidelite_depend_de_la_graine(minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    tirages = set()
    for graine in range(1, 7):
        provider = FakeProvider()
        with RunCtx.from_profile(
            "test",
            wl_home=tmp_path / f"wl{graine}",
            run_id="r-1",
            seed=graine,
            providers={"fake": provider},
        ) as c:
            c.parser = "markdown"
            _indexer(c, minicorpus, tmp_path / f"i{graine}", fidelity_sample=1)
            tirages.add(_json(tmp_path / f"i{graine}", "wiki_fidelity.json")["pages"][0]["title"])
    assert len(tirages) > 1


def test_fidelite_mesure_le_faux_llm_sur_le_texte_des_ancrages(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    vus: list[dict[str, Any]] = []

    def espion(req: Any) -> str:
        vus.append(req.inputs)
        return json.dumps({"claims": 4, "supported": 3})

    ctx.provider.script("wiki_fidelity", "wiki.fidelity", espion)  # type: ignore[attr-defined]
    _indexer(ctx, minicorpus, tmp_path / "i", fidelity_sample=2)
    textes: dict[str, str] = {}
    for d in minicorpus.documents:
        for b in d.blocks:
            deja = textes.get(b.anchor_id)
            textes[b.anchor_id] = b.text if deja is None else deja + "\n\n" + b.text
    assert len(vus) == 2
    pages = _json(tmp_path / "i", "wiki_fidelity.json")["pages"]
    for entree, page in zip(vus, pages, strict=True):
        assert entree["sources"] == [textes[a] for a in page["anchor_ids"]]
    assert _json(tmp_path / "i", "wiki_fidelity.json")["supported"] == 6


def test_update_ne_recompile_que_les_documents_changes_et_remesure(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    docs = list(minicorpus.documents)
    retire, garde = docs[0], docs[1:]
    _indexer(ctx, minicorpus, tmp_path / "v1")
    n_compile = len(_spans(ctx, "wiki.compile"))
    n_fidelite = len(_spans(ctx, "wiki.fidelity"))
    sans = minicorpus.model_copy(update={"documents": tuple(garde)})
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(removed=(retire.doc_id,)), sans, tmp_path / "v1", tmp_path / "v2"
        )
    assert len(_spans(ctx, "wiki.compile")) == n_compile  # suppression seule : rien à compiler
    nouveaux = _spans(ctx, "wiki.fidelity")[n_fidelite:]
    assert nouveaux and {s["wl.post"] for s in nouveaux} == {"update"}  # fidélité remesurée
    wiki = _json(tmp_path / "v2", "wiki.json")
    assert retire.doc_id not in {p["source_doc_id"] for p in wiki["pages"]}
    lignes = (tmp_path / "v2/passages.jsonl").read_text(encoding="utf-8").splitlines()
    dans_passages = {a for ligne in lignes for a in json.loads(ligne)["anchor_ids"]}
    assert not set(retire.anchors) & dans_passages
    assert not set(retire.anchors) & {
        a for p in _json(tmp_path / "v2", "wiki_fidelity.json")["pages"] for a in p["anchor_ids"]
    }
    # ajout : seul le Document ajouté est compilé, au poste update
    avant = len(_spans(ctx, "wiki.compile"))
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(added=(retire,)), minicorpus, tmp_path / "v2", tmp_path / "v3"
        )
    ajoutes = _spans(ctx, "wiki.compile")[avant:]
    assert len(ajoutes) == 1 and ajoutes[0]["wl.post"] == "update"
    neuve = _arch(ctx)
    neuve.load(tmp_path / "v3")
    with ctx.scope(post="query", question_id="q-001"):
        neuve.answer(_question())


def test_update_scenario_reel_document_modifie(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    from wavelibrarian.corpus.scenario import appliquer_fichier

    scenario = Path(__file__).resolve().parents[3] / "corpora/minicorpus/scenario/scenario.yaml"
    change, apres = appliquer_fichier(minicorpus, scenario, parser="markdown")
    assert change.modified
    _indexer(ctx, minicorpus, tmp_path / "v1")
    n = len(_spans(ctx, "wiki.compile"))
    with ctx.scope(post="update"):
        _arch(ctx).update(change, apres, tmp_path / "v1", tmp_path / "v2")
    entrants = len(change.added) + len(change.modified)
    assert len(_spans(ctx, "wiki.compile")) - n == entrants
    sortants = set(change.removed) | {ancien for ancien, _ in change.modified}
    wiki = _json(tmp_path / "v2", "wiki.json")
    assert not sortants & {p["source_doc_id"] for p in wiki["pages"]}
    existants = {a for d in apres.documents for a in d.anchors}
    assert {a for p in wiki["pages"] for a in p["anchor_ids"]} <= existants


def test_update_retire_les_pages_qui_citent_un_document_supprime(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    """Une page du Document B qui cite un Ancrage du Document A supprimé perd cet Ancrage ;
    si c'était le seul, la page est écartée (aucune page ne référence le Document supprimé)."""
    a, b = minicorpus.documents[0], minicorpus.documents[1]
    ancre_a = next(iter(a.anchors))
    ancre_b = next(iter(b.anchors))

    def sortie(req: Any) -> str:
        doc = req.inputs["documents"][0]
        if doc["source_path"] != b.source_path:
            return json.dumps({"pages": []})
        pages = [
            {"title": "melange", "body": "x", "anchor_ids": [ancre_a, ancre_b]},
            {"title": "seul-a", "body": "y", "anchor_ids": [ancre_a]},
        ]
        return json.dumps({"pages": pages})

    ctx.provider.script("wiki_compile", "wiki.compile", sortie)  # type: ignore[attr-defined]
    _indexer(ctx, minicorpus, tmp_path / "v1")
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(removed=(a.doc_id,)), sans, tmp_path / "v1", tmp_path / "v2")
    pages = _json(tmp_path / "v2", "wiki.json")["pages"]
    assert [p["title"] for p in pages] == ["melange"]
    assert pages[0]["anchor_ids"] == [ancre_b]


def test_compilation_decoupee_en_lots_dans_la_fenetre(
    ctx: RunCtx, minicorpus: ParsedCorpus
) -> None:
    arch = _arch(ctx)
    doc = max(minicorpus.documents, key=lambda d: len(d.blocks))
    assert len([b for b in doc.blocks if b.text.strip()]) > 1
    arch._fenetre = lambda modele: 1300
    lots = arch._lots_de_blocks(doc)
    assert len(lots) > 1
    tokenizer = ctx.tokenizer_for(arch._compile_model)
    for lot in lots:
        assert tokenizer.count(json.dumps(lot, ensure_ascii=False)) < 1300
    assert [b["anchor_id"] for lot in lots for b in lot] == [
        b.anchor_id for b in doc.blocks if b.text.strip()
    ]


def test_fidelite_tient_dans_la_fenetre_avec_avertissement(
    ctx: RunCtx, caplog: pytest.LogCaptureFixture
) -> None:
    arch = _arch(ctx)
    arch._fenetre = lambda modele: 300
    sources = ["alpha " * 40, "beta " * 40, "gamma " * 40]
    with caplog.at_level(logging.WARNING, logger="wavelibrarian.architectures.llm_wiki"):
        page, gardees = arch._tenir("page courte", sources)
    tokenizer = ctx.tokenizer_for(arch._fidelity_model)
    assert 0 < len(gardees) < 3 and gardees == sources[: len(gardees)]
    assert tokenizer.count(page) + sum(tokenizer.count(s) for s in gardees) < 300
    assert any("avant fidélité" in r.getMessage() for r in caplog.records)


def test_copie_generique_au_runner_et_taux_dans_le_rapport(
    ctx: RunCtx, minicorpus: ParsedCorpus
) -> None:
    ctx.config_id = "wiki-1"
    spec = ComponentSpec(name="llm_wiki", params={})

    def fabrique() -> Any:
        return ctx.build("architecture", spec)

    cache = IndexCache(ctx.wl_home)
    _, cle = cache.build(ctx, fabrique, minicorpus)
    source = _json(cache.path(cle), "wiki_fidelity.json")
    assert _json(ctx.run_dir, "wiki_fidelity.json") == {"wiki-1": source}
    # chemin « cache présent » identique, et une seconde Configuration s'ajoute
    ctx.config_id = "wiki-2"
    cache.build(ctx, fabrique, minicorpus)
    assert set(_json(ctx.run_dir, "wiki_fidelity.json")) == {"wiki-1", "wiki-2"}
    taux = taux_fidelite(ctx.run_dir)
    assert taux["wiki-1"] == source["supported"] / source["claims"]
    assert "wiki-1" in section_fidelite(ctx.run_dir)


def test_architecture_sans_fidelite_ne_copie_rien_et_rapport_vide(
    ctx: RunCtx, minicorpus: ParsedCorpus
) -> None:
    ctx.config_id = "bm25"
    spec = ComponentSpec(name="bm25_only", params={})
    IndexCache(ctx.wl_home).build(ctx, lambda: ctx.build("architecture", spec), minicorpus)
    assert not (ctx.run_dir / "wiki_fidelity.json").exists()
    assert taux_fidelite(ctx.run_dir) == {} and section_fidelite(ctx.run_dir) == ""


def test_taux_sans_affirmation_est_none(tmp_path: Path) -> None:
    (tmp_path / "wiki_fidelity.json").write_text(
        json.dumps({"c": {"claims": 0, "supported": 0, "pages": []}}), encoding="utf-8"
    )
    assert taux_fidelite(tmp_path) == {"c": None}
    assert "n/a" in section_fidelite(tmp_path)


# -- revue de la story 7.3 ----------------------------------------------------------------------


def test_juge_de_fidelite_par_defaut_d_une_autre_famille(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    """AD-14 : l'auteur des pages ne juge pas ses pages ; défaut = premier Juge du réservoir
    d'une autre Famille que `compile_model`."""
    for compile_model in ("fake-llm-a", "fake-llm-c"):
        arch = _arch(ctx, compile_model=compile_model)
        familles = {ctx.catalog.get(m).family for m in (compile_model, arch._fidelity_model)}
        assert len(familles) == 2
    # profil de test : réservoir [fake-llm-c, fake-llm-b, fake-llm-a]
    assert _arch(ctx, compile_model="fake-llm-c")._fidelity_model == "fake-llm-b"
    _indexer(ctx, minicorpus, tmp_path / "i", compile_model="fake-llm-a")
    modeles = {s["gen_ai.request.model"] for s in _spans(ctx, "wiki.fidelity")}
    assert modeles == {"fake-llm-c"}


def test_juge_de_fidelite_de_la_meme_famille_refuse(ctx: RunCtx) -> None:
    from wavelibrarian.core.errors import ConfigError

    with pytest.raises(ConfigError, match="Famille"):
        _arch(ctx, compile_model="fake-llm-a", fidelity_model="fake-llm-a")
    assert _arch(ctx, compile_model="fake-llm-a", fidelity_model="fake-llm-b")


def test_graine_dans_la_cle_un_hit_de_cache_ne_sert_pas_l_echantillon_d_une_autre_graine(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    spec = ComponentSpec(name="llm_wiki", params={"fidelity_sample": 1})

    def fabrique() -> Any:
        return ctx.build("architecture", spec)

    cache = IndexCache(ctx.wl_home)
    cles, tirages = set(), {}
    for graine in range(1, 7):
        ctx.seed = graine
        _, cle = cache.build(ctx, fabrique, minicorpus)
        cles.add(cle)
        tirages[graine] = _json(cache.path(cle), "wiki_fidelity.json")["pages"][0]["passage_id"]
        # même tirage qu'un index neuf de cette graine
        _indexer(ctx, minicorpus, tmp_path / f"n{graine}", fidelity_sample=1)
        neuf = _json(tmp_path / f"n{graine}", "wiki_fidelity.json")["pages"][0]["passage_id"]
        assert tirages[graine] == neuf
    assert len(cles) == 6 and len(set(tirages.values())) > 1
    # sans échantillon, la graine n'invalide pas l'index
    sans = ComponentSpec(name="llm_wiki", params={"fidelity_sample": 0})
    ctx.seed = 1
    _, c1 = cache.build(ctx, lambda: ctx.build("architecture", sans), minicorpus)
    ctx.seed = 2
    _, c2 = cache.build(ctx, lambda: ctx.build("architecture", sans), minicorpus)
    assert c1 == c2


def test_page_ne_garde_que_les_ancrages_de_son_document_source(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path
) -> None:
    a, b = minicorpus.documents[0], minicorpus.documents[1]
    ancre_a, ancre_b = next(iter(a.anchors)), next(iter(b.anchors))

    def sortie(req: Any) -> str:
        if req.inputs["documents"][0]["source_path"] != b.source_path:
            return json.dumps({"pages": []})
        pages = [
            {"title": "mixte", "body": "x", "anchor_ids": [ancre_a, ancre_b]},
            {"title": "autre", "body": "y", "anchor_ids": [ancre_a]},
        ]
        return json.dumps({"pages": pages})

    ctx.provider.script("wiki_compile", "wiki.compile", sortie)  # type: ignore[attr-defined]
    _indexer(ctx, minicorpus, tmp_path / "i")
    wiki = _json(tmp_path / "i", "wiki.json")
    assert [(p["title"], p["anchor_ids"]) for p in wiki["pages"]] == [("mixte", [ancre_b])]
    assert wiki["discarded_pages"] == 1

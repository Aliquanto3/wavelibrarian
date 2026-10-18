"""Story 7.5 : GraphStore `networkx`, extracteur d'entités, communautés et rapports."""

import json
from pathlib import Path
from typing import Any

import networkx as nx
import pytest

from wavelibrarian import registry
from wavelibrarian.components.graph.communities import detect_communities, louvain_seed
from wavelibrarian.components.graph.extraction import EntityExtractor
from wavelibrarian.components.graph.reports import CommunityReporter
from wavelibrarian.components.graph_stores.networkx_store import NetworkxGraphStore
from wavelibrarian.core.errors import ConfigError, NonConformantOutput
from wavelibrarian.core.types import ParsedCorpus, Passage
from wavelibrarian.llm.providers.fake import FakeProvider
from wavelibrarian.ports.components import ComponentSpec
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


@pytest.fixture
def passages(ctx: RunCtx, minicorpus: ParsedCorpus) -> list[Passage]:
    chunker = ctx.build("chunker", ComponentSpec(name="fixed_tokens"))
    return [p for doc in minicorpus.documents for p in chunker.chunk(doc)]


def _store(ctx: RunCtx) -> Any:
    return ctx.build("graph_store", ComponentSpec(name="networkx"))


def _spans(ctx: RunCtx, role: str) -> list[dict[str, Any]]:
    chemin = ctx.run_dir / "traces.jsonl"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    return [s for s in map(json.loads, lignes) if s["wl.step"].startswith(role)]


def _egal(a: nx.Graph, b: nx.Graph) -> bool:
    return dict(a.nodes(data=True)) == dict(b.nodes(data=True)) and {
        frozenset((u, v)): d for u, v, d in a.edges(data=True)
    } == {frozenset((u, v)): d for u, v, d in b.edges(data=True)}


# -- GraphStore ---------------------------------------------------------------------------------


def test_enregistrement() -> None:
    assert registry.get("graph_store", "networkx") is NetworkxGraphStore


def test_remove_passages_retire_les_orphelins(ctx: RunCtx) -> None:
    s = _store(ctx)
    s.upsert_entity("a", "Alpha", "entity", "premier", ["p1"])
    s.upsert_entity("b", "Beta", "entity", "second", ["p1", "p2"])
    s.upsert_entity("c", "Gamma", "entity", "troisieme", ["p2"])
    s.upsert_relation("a", "b", "lie", 1.0, ["p1"])
    s.upsert_relation("b", "c", "lie aussi", 1.0, ["p2"])
    s.remove_passages(["p1"])
    g = s.graph()
    assert sorted(g.nodes) == ["b", "c"]  # `a` n'a plus de Passage
    assert not g.has_edge("a", "b")
    assert g.has_edge("b", "c")
    assert g.nodes["b"]["passage_ids"] == ["p2"]
    s.remove_passages(["p2"])
    assert s.graph().number_of_nodes() == 0


def test_relation_retiree_sans_passage_mais_entites_gardees(ctx: RunCtx) -> None:
    s = _store(ctx)
    s.upsert_entity("a", "Alpha", "entity", "", ["p1", "p3"])
    s.upsert_entity("b", "Beta", "entity", "", ["p1", "p3"])
    s.upsert_relation("a", "b", "lie", 1.0, ["p1"])
    s.remove_passages(["p1"])
    assert s.graph().number_of_edges() == 0
    assert sorted(s.graph().nodes) == ["a", "b"]


def test_save_puis_load_redonnent_le_meme_graphe(ctx: RunCtx, tmp_path: Path) -> None:
    s = _store(ctx)
    s.upsert_entity("a", "Alpha", "personne", "premier", ["p1"])
    s.upsert_entity("b", "Béta", "lieu", "second", ["p2", "p1"])
    s.upsert_relation("a", "b", "lie", 0.5, ["p1"])
    s.save(tmp_path / "g")
    t = _store(ctx)
    t.load(tmp_path / "g")
    assert _egal(s.graph(), t.graph())
    t.save(tmp_path / "g2")  # sérialisation stable
    assert (tmp_path / "g" / "graph.json").read_bytes() == (
        tmp_path / "g2" / "graph.json"
    ).read_bytes()


def test_load_d_un_graphe_illisible_leve_une_erreur(ctx: RunCtx, tmp_path: Path) -> None:
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "graph.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(Exception, match="illisible"):
        _store(ctx).load(tmp_path / "g")


def test_fusion_par_slug_casse_et_accents(ctx: RunCtx) -> None:
    s = _store(ctx)
    s.upsert_entity("Éric Müller", "Éric Müller", "personne", "court", ["p1"])
    s.upsert_entity("eric muller", "eric muller", "personne", "description plus longue", ["p2"])
    s.upsert_entity("ERIC MULLER", "ERIC MULLER", "personne", "", ["p3"])
    g = s.graph()
    assert list(g.nodes) == ["eric-muller"]
    n = g.nodes["eric-muller"]
    assert n["passage_ids"] == ["p1", "p2", "p3"]
    assert n["description"] == "description plus longue"
    assert n["name"] == "Éric Müller"  # ex æquo de mentions : la forme accentuée


def test_fusion_independante_de_l_ordre(ctx: RunCtx) -> None:
    mentions = [("Éric", "x", "p1"), ("eric", "longue", "p2"), ("ERIC", "", "p3")]
    a, b = _store(ctx), _store(ctx)
    for n, d, p in mentions:
        a.upsert_entity(n, n, "k", d, [p])
    for n, d, p in reversed(mentions):
        b.upsert_entity(n, n, "k", d, [p])
    assert _egal(a.graph(), b.graph())


def test_relation_fusionnee_et_boucle_ignoree(ctx: RunCtx) -> None:
    s = _store(ctx)
    s.upsert_relation("Alpha", "Béta", "r1", 0.4, ["p1"])
    s.upsert_relation("beta", "alpha", "r plus longue", 0.9, ["p2"])
    s.upsert_relation("alpha", "ALPHA", "boucle", 1.0, ["p3"])
    g = s.graph()
    assert g.number_of_edges() == 1
    e = g.edges["alpha", "beta"]
    assert e["weight"] == 0.9
    assert e["description"] == "r plus longue"
    assert e["passage_ids"] == ["p1", "p2"]
    assert g.nodes["alpha"]["passage_ids"] == ["p1", "p2"]  # extrémité créée par la relation


def test_entite_sans_identifiant_exploitable_refusee(ctx: RunCtx) -> None:
    with pytest.raises(Exception, match="identifiant"):
        _store(ctx).upsert_entity("!!!", "???", "k", "", ["p"])


# -- Extraction ---------------------------------------------------------------------------------


def test_extraction_rattache_aux_passage_id(ctx: RunCtx, passages: list[Passage]) -> None:
    trois = passages[:3]
    store = _store(ctx)
    with ctx.scope(post="indexing"):
        resultats = EntityExtractor(ctx).extract_into(store, trois)
    assert [r.passage_id for r in resultats] == [p.passage_id for p in trois]
    g = store.graph()
    ids_trois = {p.passage_id for p in trois}
    assert g.number_of_nodes() > 0
    for _, n in g.nodes(data=True):
        assert n["passage_ids"] and set(n["passage_ids"]) <= ids_trois
    for _, _, e in g.edges(data=True):
        assert e["passage_ids"] and set(e["passage_ids"]) <= ids_trois
    # chaque entité extraite d'un Passage porte ce Passage
    for r in resultats:
        for eid, *_ in r.entities:
            assert r.passage_id in g.nodes[eid]["passage_ids"]
    spans = _spans(ctx, "graph.extract.")
    assert len(spans) == 3
    assert {s["wl.step"] for s in spans} == {f"graph.extract.{p.passage_id}" for p in trois}


def test_extraction_scenarisee_fusionne_par_slug(ctx: RunCtx, passages: list[Passage]) -> None:
    ctx.provider.script(  # type: ignore[attr-defined]
        "extract_entities",
        f"graph.extract.{passages[0].passage_id}",
        json.dumps(
            {
                "entities": [
                    {"name": "Éric", "kind": "personne", "description": "d1"},
                    {"name": "eric", "kind": "personne", "description": "doublon"},
                    {"name": "Lyon", "kind": "lieu", "description": "d2"},
                ],
                "relations": [
                    {"source": "ÉRIC", "target": "Lyon", "description": "habite", "weight": 1.0},
                    {"source": "Éric", "target": "eric", "description": "boucle", "weight": 1.0},
                ],
            }
        ),
    )
    store = _store(ctx)
    with ctx.scope(post="indexing"):
        (x,) = EntityExtractor(ctx).extract_into(store, passages[:1])
    assert [e[0] for e in x.entities] == ["eric", "lyon"]
    # dans un Passage, mêmes règles que le store : forme accentuée, description la plus longue
    assert x.entities[0][1:] == ("Éric", "personne", "doublon")
    assert len(x.relations) == 1
    assert store.graph().has_edge("eric", "lyon")


def test_sortie_non_conforme_reessayee_une_fois_puis_erreur(
    ctx: RunCtx, passages: list[Passage]
) -> None:
    ctx.provider.script("extract_entities", "graph.extract.*", "pas du json")  # type: ignore[attr-defined]
    with ctx.scope(post="indexing"), pytest.raises(NonConformantOutput):
        EntityExtractor(ctx).extract_passage(passages[0])
    assert len(_spans(ctx, "graph.extract.")) == 2  # un appel, un nouvel essai


def test_extraction_fenetre_trop_petite_erreur(ctx: RunCtx, passages: list[Passage]) -> None:
    modele = EntityExtractor(ctx).model_id
    with ctx.scope(post="indexing"), pytest.raises(ConfigError):
        EntityExtractor(ctx, max_tokens=10**9).extract_passage(passages[0])
    assert modele


def test_extraction_tronque_avec_avertissement(
    ctx: RunCtx, passages: list[Passage], caplog: pytest.LogCaptureFixture
) -> None:
    modele = EntityExtractor(ctx).model_id
    fenetre = ctx.catalog.get(modele).context_window
    if fenetre is None:
        pytest.skip("pas de fenêtre au Catalogue")
    long = passages[0].model_copy(update={"text": "mot " * (fenetre + 100)})
    with ctx.scope(post="indexing"), caplog.at_level("WARNING"):
        EntityExtractor(ctx).extract_passage(long)
    assert "tronqué" in caplog.text


# -- Communautés et rapports --------------------------------------------------------------------


def _graphe(ctx: RunCtx, passages: list[Passage]) -> Any:
    store = _store(ctx)
    with ctx.scope(post="indexing"):
        EntityExtractor(ctx).extract_into(store, passages)
    return store


def test_communautes_deterministes(ctx: RunCtx, passages: list[Passage]) -> None:
    g = _graphe(ctx, passages[:12]).graph()
    graine = louvain_seed(ctx.seed)
    a = detect_communities(g, graine)
    b = detect_communities(g, graine)
    assert a == b
    membres = [m for c in a for m in c.members]
    assert sorted(membres) == sorted(g.nodes)  # partition
    cles = [(-len(c.members), c.community_id) for c in a]
    assert cles == sorted(cles)  # taille décroissante, ex æquo par id


def test_communautes_independantes_de_l_ordre_d_insertion() -> None:
    aretes = [("a", "b"), ("b", "c"), ("a", "c"), ("d", "e"), ("e", "f"), ("d", "f"), ("c", "d")]
    g1: nx.Graph = nx.Graph()
    g2: nx.Graph = nx.Graph()
    for u, v in aretes:
        g1.add_edge(u, v, weight=1.0)
    for u, v in reversed(aretes):
        g2.add_edge(v, u, weight=1.0)
    assert detect_communities(g1, 7) == detect_communities(g2, 7)
    membres = sorted(c.members for c in detect_communities(g1, 7))
    assert membres == [("a", "b", "c"), ("d", "e", "f")]


def test_graine_derivee_de_l_experience() -> None:
    assert louvain_seed(1) == louvain_seed(1)
    assert louvain_seed(1) != louvain_seed(2)


def test_graphe_vide_aucune_communaute() -> None:
    assert detect_communities(nx.Graph(), 1) == []


def test_ids_de_communaute_selon_la_composition() -> None:
    g: nx.Graph = nx.Graph()
    g.add_edge("a", "b", weight=1.0)
    g.add_node("z")
    c = detect_communities(g, 3)
    assert {x.members for x in c} == {("a", "b"), ("z",)}
    assert detect_communities(g, 3, min_size=2)[0].members == ("a", "b")
    assert len(detect_communities(g, 3, min_size=2)) == 1


def test_rapports_passages_de_niveau_1_aux_ancrages_unis(
    ctx: RunCtx, passages: list[Passage]
) -> None:
    sources = passages[:12]
    store = _graphe(ctx, sources)
    g = store.graph()
    communautes = detect_communities(g, louvain_seed(ctx.seed))
    par_id = {p.passage_id: p for p in passages}
    with ctx.scope(post="indexing"):
        rapports = CommunityReporter(ctx).reports(g, communautes, par_id)
    assert rapports and len(rapports) <= len(communautes)
    for r in rapports:
        assert r.level == 1 and r.text
        assert r.child_ids and all(c in par_id for c in r.child_ids)
        union = {a for c in r.child_ids for a in par_id[c].anchor_ids}
        assert set(r.anchor_ids) == union
        docs = {par_id[c].doc_id for c in r.child_ids}
        assert r.doc_id == (next(iter(docs)) if len(docs) == 1 else None)
    assert len({r.passage_id for r in rapports}) == len(rapports)
    spans = _spans(ctx, "graph.report.")
    assert len(spans) == len(rapports)


def test_rapports_identiques_sur_deux_executions(ctx: RunCtx, passages: list[Passage]) -> None:
    g = _graphe(ctx, passages[:12]).graph()
    par_id = {p.passage_id: p for p in passages}
    communautes = detect_communities(g, louvain_seed(ctx.seed))
    with ctx.scope(post="indexing"):
        r1 = CommunityReporter(ctx).reports(g, communautes, par_id)
        r2 = CommunityReporter(ctx).reports(
            g, detect_communities(g, louvain_seed(ctx.seed)), par_id
        )
    assert r1 == r2


def test_rapport_ecarte_sans_passage_source_ou_vide(ctx: RunCtx, passages: list[Passage]) -> None:
    g = _graphe(ctx, passages[:3]).graph()
    communautes = detect_communities(g, 1)
    with ctx.scope(post="indexing"):
        assert CommunityReporter(ctx).reports(g, communautes, {}) == []  # aucun Passage connu
        ctx.provider.script("community_report", "graph.report.*", "   ")  # type: ignore[attr-defined]
        par_id = {p.passage_id: p for p in passages}
        assert CommunityReporter(ctx).reports(g, communautes, par_id) == []


def test_contexte_du_rapport_borne_a_la_fenetre(
    ctx: RunCtx, passages: list[Passage], caplog: pytest.LogCaptureFixture
) -> None:
    modele = CommunityReporter(ctx).model_id
    fenetre = ctx.catalog.get(modele).context_window
    if fenetre is None:
        pytest.skip("pas de fenêtre au Catalogue")
    g = nx.Graph()
    g.add_node(
        "a",
        name="A",
        kind="k",
        description="mot " * (fenetre + 100),
        passage_ids=[passages[0].passage_id],
    )
    c = detect_communities(g, 1)
    with ctx.scope(post="indexing"), caplog.at_level("WARNING"):
        r = CommunityReporter(ctx).reports(g, c, {passages[0].passage_id: passages[0]})
    assert len(r) == 1
    assert "tronqué" in caplog.text


# -- Revue ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("relation_d_abord", [True, False])
def test_kind_et_nom_extraits_l_emportent_sur_la_relation(
    ctx: RunCtx, relation_d_abord: bool
) -> None:
    s = _store(ctx)
    ops = [
        lambda: s.upsert_relation("eric", "Paris", "vit", 0.5, ["p1"]),
        lambda: s.upsert_entity("Éric", "Éric", "personne", "desc", ["p2"]),
    ]
    for op in ops if relation_d_abord else reversed(ops):
        op()
    n = s.graph().nodes["eric"]
    assert (n["kind"], n["name"]) == ("personne", "Éric")
    assert s.graph().nodes["paris"]["kind"] == "entity"


def test_nom_canonique_le_plus_frequent(ctx: RunCtx) -> None:
    mentions = [("eric", "p1"), ("Éric", "p2"), ("eric", "p3")]
    for ordre in (mentions, list(reversed(mentions))):
        s = _store(ctx)
        for nom, p in ordre:
            s.upsert_entity(nom, nom, "personne", "", [p])
        assert s.graph().nodes["eric"]["name"] == "eric"


def test_slug_entite_apostrophes_et_ligatures() -> None:
    from wavelibrarian.core.ids import slug, slug_entite

    assert slug_entite("L’Oréal") == slug_entite("L'Oréal") == "l-oreal"
    assert slug_entite("Œuvre et Æther") == "oeuvre-et-aether"
    assert slug("Œuvre") == "uvre"  # `slug` des Ancrages inchangé (Jeux gelés)


def test_save_load_garde_les_noms(ctx: RunCtx, tmp_path: Path) -> None:
    s = _store(ctx)
    s.upsert_entity("L’Oréal", "L’Oréal", "org", "", ["p1"])
    s.upsert_relation("L'Oréal", "Paris", "siège", 1.0, ["p1"])
    s.save(tmp_path / "g")
    t = _store(ctx)
    t.load(tmp_path / "g")
    assert _egal(s.graph(), t.graph())
    assert t.graph().nodes["l-oreal"]["name"] == "L’Oréal"


def test_borner_reserve_le_schema(ctx: RunCtx) -> None:
    from wavelibrarian.components.graph._texte import SURCOUT_SCHEMA, borner, reserve_schema
    from wavelibrarian.llm.roles import ExtractEntitiesOutput

    modele = EntityExtractor(ctx).model_id
    fenetre = ctx.catalog.get(modele).context_window
    if fenetre is None:
        pytest.skip("pas de fenêtre au Catalogue")
    reserve = reserve_schema(ctx, modele, ExtractEntitiesOutput)
    assert reserve > SURCOUT_SCHEMA
    sortie = fenetre - 128 - 10  # tient sans réserve, plus avec
    assert borner(ctx, modele, "", "x", sortie, "t") == "x"
    with pytest.raises(ConfigError):
        borner(ctx, modele, "", "x", sortie, "t", reserve=reserve)


def test_sources_absentes_signalees(
    ctx: RunCtx, passages: list[Passage], caplog: pytest.LogCaptureFixture
) -> None:
    g = nx.Graph()
    g.add_node(
        "a", name="A", kind="k", description="", passage_ids=["inconnu", passages[0].passage_id]
    )
    (c,) = detect_communities(g, 1)
    with caplog.at_level("WARNING"):
        sources = CommunityReporter(ctx).sources(g, c, {passages[0].passage_id: passages[0]})
    assert sources == [passages[0]]
    assert "inconnu" in caplog.text


def test_communautes_identiques_entre_processus() -> None:
    import os
    import subprocess
    import sys

    script = (
        "import random, networkx as nx\n"
        "from wavelibrarian.components.graph.communities import detect_communities\n"
        "r = random.Random(3); g = nx.Graph()\n"
        "noms = [f'e{i}' for i in range(40)]\n"
        "for _ in range(120):\n"
        "    a, b = r.sample(noms, 2); g.add_edge(a, b, weight=r.random())\n"
        "print([c.community_id for c in detect_communities(g, 42)])\n"
    )
    sorties = set()
    for graine in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": graine}
        res = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
        )
        sorties.add(res.stdout)
    assert len(sorties) == 1

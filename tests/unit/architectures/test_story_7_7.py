"""Story 7.7 : Architecture `lazy_graphrag` (zéro appel LLM à l'indexation)."""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from wavelibrarian import registry
from wavelibrarian.architectures import graphrag as _graphrag  # noqa: F401  (enregistre graphrag)
from wavelibrarian.architectures._passages import lire_passages
from wavelibrarian.architectures.lazy_graphrag import LazyGraphRag, _mots
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
    return ctx.build("architecture", ComponentSpec(name="lazy_graphrag", params=params))


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


def _interdire_llm(ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tout appel au provider lève : prouve l'absence d'appel sans dépendre de la Trace."""

    def interdit(*_: Any, **__: Any) -> Any:
        raise AssertionError("appel LLM interdit")

    monkeypatch.setattr(ctx.provider, "complete", interdit)  # type: ignore[attr-defined]


def _question() -> QuestionInput:
    return QuestionInput(question_id="q-001", text="Que sait-on de Port Ysel ?", lang="fr")


def _citer_tout(ctx: RunCtx) -> None:
    def sortie(req: Any) -> str:
        etiquettes = list(req.inputs["blocks"])
        return json.dumps({"answer": "R", "citations": etiquettes, "abstain": False})

    ctx.provider.script("generate", "generate*", sortie)  # type: ignore[attr-defined]


def _repondre(ctx: RunCtx, dossier: Path, question: QuestionInput | None = None, **p: Any) -> Any:
    arch = _arch(ctx, **p)
    arch.load(dossier)
    with ctx.scope(post="query", question_id="q-001"):
        return arch.answer(question or _question())


@pytest.fixture
def index(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> Path:
    _indexer(ctx, minicorpus, tmp_path / "i")
    return tmp_path / "i"


def _existants(corpus: ParsedCorpus) -> set[str]:
    return {a for d in corpus.documents for a in d.anchors}


def _json(dossier: Path, nom: str) -> Any:
    return json.loads((dossier / nom).read_text(encoding="utf-8"))


_FICHIERS = ("passages.jsonl", "communities.json", "graph/graph.json")


# -- enregistrement et indexation ---------------------------------------------------------------


def test_enregistrement_et_capacites(ctx: RunCtx) -> None:
    assert registry.get("architecture", "lazy_graphrag") is LazyGraphRag
    assert registry.get("architecture", "graphrag") is not LazyGraphRag
    assert LazyGraphRag.capabilities.incremental_update is True
    assert LazyGraphRag.capabilities.retrieval_method == "ranked"
    assert _arch(ctx).embedder_dim() is None
    assert "relevance_budget" in LazyGraphRag.query_params
    assert _arch(ctx).p.relevance_budget == 20


def test_relevance_budget_hors_de_l_index_key(ctx: RunCtx) -> None:
    a = _arch(ctx, relevance_budget=3)
    assert a.index_key() == _arch(ctx, relevance_budget=50, k=9, grade_batch=2).index_key()
    assert _arch(ctx, min_community_size=2).index_key() != a.index_key()


def test_indexation_sans_aucun_appel_llm(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _interdire_llm(ctx, monkeypatch)
    index = tmp_path / "i"
    _indexer(ctx, minicorpus, index)
    assert _spans(ctx) == []
    g = _json(index, "graph/graph.json")
    assert g["nodes"] and g["edges"]
    assert all(n["kind"] == "concept" for n in g["nodes"])
    feuilles = lire_passages(index)
    assert feuilles and all(p.level == 0 for p in feuilles)
    ids = {p.passage_id for p in feuilles}
    assert all(set(n["passage_ids"]) <= ids for n in g["nodes"])
    membres = [m for c in _json(index, "communities.json")["communities"] for m in c["members"]]
    assert sorted(membres) == sorted(n["id"] for n in g["nodes"])  # partition des concepts


def test_cooccurrence_dans_un_meme_passage(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    g = arch._graphe.graph()
    for a, b, d in g.edges(data=True):
        commun = set(g.nodes[a]["passage_ids"]) & set(g.nodes[b]["passage_ids"])
        assert d["passage_ids"] and set(d["passage_ids"]) <= commun


def test_indexation_deterministe(ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path) -> None:
    _indexer(ctx, minicorpus, tmp_path / "a")
    _indexer(ctx, minicorpus, tmp_path / "b")
    for nom in _FICHIERS:
        assert (tmp_path / "a" / nom).read_bytes() == (tmp_path / "b" / nom).read_bytes()


# -- requête ------------------------------------------------------------------------------------


def test_requete_classe_les_communautes_note_puis_genere(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path
) -> None:
    _citer_tout(ctx)
    rep = _repondre(ctx, index)
    assert not rep.abstained and rep.retrieval_method == "ranked"
    spans = _spans(ctx)
    steps = [s["wl.step"] for s in spans]
    assert steps[-1] == "generate" and len(steps) > 1
    assert all(s.startswith("lazygraphrag.grade.") for s in steps[:-1])
    assert {s["wl.post"] for s in spans} == {"query"}
    assert rep.citations and {c.anchor_id for c in rep.citations} <= _existants(minicorpus)
    assert [s.rank for s in rep.retrieved] == list(range(1, len(rep.retrieved) + 1))
    scores = [s.score for s in rep.retrieved]
    assert scores == sorted(scores, reverse=True) and all(s > 0 for s in scores)
    assert len(rep.retrieved) <= 5


def test_la_communaute_qui_touche_la_question_passe_en_premier(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    candidats = arch._candidats(_question())
    assert candidats and "port-ysel" in candidats[0].text.casefold()
    autre = QuestionInput(question_id="q-001", text="Quel temps fait-il ?", lang="fr")
    assert arch._candidats(autre) == []


def test_premier_mot_de_la_question_compte(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx)
    arch.load(index)
    seul = arch._candidats(QuestionInput(question_id="q", text="Brumeval ?", lang="fr"))
    assert seul and "brumeval" in seul[0].text.casefold()


def test_relevance_budget_borne_les_passages_notes(ctx: RunCtx, index: Path) -> None:
    _citer_tout(ctx)
    pris: list[int] = []
    arch = _arch(ctx, relevance_budget=3, grade_batch=2)
    arch.load(index)
    vrai = arch._appeler

    def espion(question: Any, n: int, lot: Any) -> Any:
        pris.append(len(lot))
        return vrai(question, n, lot)

    arch._appeler = espion
    with ctx.scope(post="query", question_id="q-001"):
        arch.answer(_question())
    assert pris == [2, 1]  # 3 Passages au plus : un lot de 2, puis le reste du budget
    assert len(_spans(ctx, "lazygraphrag.grade.")) == 2


def test_budget_par_defaut_20_et_lots_de_5(ctx: RunCtx, index: Path) -> None:
    _citer_tout(ctx)
    arch = _arch(ctx)
    arch.load(index)
    n_cand = len(arch._candidats(_question()))
    assert 0 < n_cand <= 20
    _repondre(ctx, index)
    assert len(_spans(ctx, "lazygraphrag.grade.")) == math.ceil(n_cand / 5)


def test_scores_tous_nuls_abstention_sans_generate(ctx: RunCtx, index: Path) -> None:
    def zeros(req: Any) -> str:
        return json.dumps({"scores": [0.0] * len(req.inputs["passages"])})

    ctx.provider.script("grade_relevance", "lazygraphrag.grade.*", zeros)  # type: ignore[attr-defined]
    rep = _repondre(ctx, index)
    assert rep.abstained and rep.citations == ()
    assert _spans(ctx, "lazygraphrag.grade.") and not _spans(ctx, "generate")


def test_seuil_de_pertinence(ctx: RunCtx, index: Path) -> None:
    _citer_tout(ctx)

    def demi(req: Any) -> str:
        return json.dumps({"scores": [0.5] * len(req.inputs["passages"])})

    ctx.provider.script("grade_relevance", "lazygraphrag.grade.*", demi)  # type: ignore[attr-defined]
    rep = _repondre(ctx, index, relevance_threshold=0.5)  # note strictement au-dessus du seuil
    assert rep.abstained and not _spans(ctx, "generate")
    rep = _repondre(ctx, index, relevance_threshold=0.4, k=2)
    assert not rep.abstained and len(rep.retrieved) == 2


def test_question_sans_concept_abstention_sans_appel(ctx: RunCtx, index: Path) -> None:
    autre = QuestionInput(question_id="q-001", text="Quel temps fait-il ?", lang="fr")
    rep = _repondre(ctx, index, autre)
    assert rep.abstained and _spans(ctx) == []


def test_fenetre_de_notation_reduit_le_lot(ctx: RunCtx, index: Path) -> None:
    arch = _arch(ctx, grade_batch=5)
    arch.load(index)
    fenetre = ctx.catalog.get(arch._grade_model).context_window
    if fenetre is None:
        pytest.skip("modèle sans fenêtre déclarée")
    gros = arch._candidats(_question())[0].model_copy(update={"text": "mot " * fenetre})
    assert len(arch._lot(_question(), [gros, gros, gros], 3)) == 1  # un Passage seul reste


# -- mise à jour incrémentale -------------------------------------------------------------------


def test_update_ajout_egale_l_index_complet_sans_appel(
    ctx: RunCtx, minicorpus: ParsedCorpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ajoute = minicorpus.documents[0]
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    _indexer(ctx, sans, tmp_path / "v1")
    _indexer(ctx, minicorpus, tmp_path / "complet")
    _interdire_llm(ctx, monkeypatch)
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(added=(ajoute,)), minicorpus, tmp_path / "v1", tmp_path / "v2"
        )
    assert _spans(ctx) == []
    for nom in _FICHIERS:
        assert (tmp_path / "v2" / nom).read_bytes() == (tmp_path / "complet" / nom).read_bytes()


def test_update_suppression_egale_l_index_complet(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    retire = minicorpus.documents[0]
    sans = minicorpus.model_copy(update={"documents": minicorpus.documents[1:]})
    _indexer(ctx, sans, tmp_path / "complet")
    with ctx.scope(post="update"):
        _arch(ctx).update(CorpusChange(removed=(retire.doc_id,)), sans, index, tmp_path / "v2")
    assert _spans(ctx) == []
    for nom in _FICHIERS:
        assert (tmp_path / "v2" / nom).read_bytes() == (tmp_path / "complet" / nom).read_bytes()
    apres = lire_passages(tmp_path / "v2")
    assert not set(retire.anchors) & {a for p in apres for a in p.anchor_ids}


def test_update_document_modifie_remplace_sans_dupliquer(
    ctx: RunCtx, minicorpus: ParsedCorpus, index: Path, tmp_path: Path
) -> None:
    doc = max(minicorpus.documents, key=lambda d: len(d.blocks))
    blocs = list(doc.blocks)
    blocs[-1] = blocs[-1].model_copy(update={"text": blocs[-1].text + " Gorvane Ellis."})
    nouveau = doc.model_copy(update={"blocks": tuple(blocs)})
    apres = minicorpus.model_copy(
        update={"documents": tuple(nouveau if d is doc else d for d in minicorpus.documents)}
    )
    _indexer(ctx, apres, tmp_path / "complet")
    with ctx.scope(post="update"):
        _arch(ctx).update(
            CorpusChange(modified=((doc.doc_id, nouveau),)), apres, index, tmp_path / "v2"
        )
    for nom in _FICHIERS:
        assert (tmp_path / "v2" / nom).read_bytes() == (tmp_path / "complet" / nom).read_bytes()
    _citer_tout(ctx)
    rep = _repondre(ctx, tmp_path / "v2")
    assert not rep.abstained and rep.citations
    assert {c.anchor_id for c in rep.citations} <= _existants(apres)


# -- revue : Decider, seuil par défaut, mots outils ---------------------------------------------


def test_notation_par_le_decider_avec_son_step(ctx: RunCtx, index: Path) -> None:
    assert "decider" in LazyGraphRag.query_params
    arch = _arch(ctx, decider={"name": "llm", "params": {"max_tokens": 64}})
    assert arch.decider.max_tokens == 64 and arch._grade_max_tokens == 64
    arch.load(index)
    pris: list[str] = []
    vrai = arch.decider.grade

    def espion(question: Any, passages: Any, loop: int = 0, *, step: Any = None) -> Any:
        pris.append(step)
        return vrai(question, passages, loop, step=step)

    arch.decider.grade = espion
    _citer_tout(ctx)
    with ctx.scope(post="query", question_id="q-001"):
        arch.answer(_question())
    assert pris and pris == [f"lazygraphrag.grade.{i}" for i in range(1, len(pris) + 1)]
    assert [s["wl.step"] for s in _spans(ctx, "lazygraphrag.grade.")] == pris


def test_seuil_par_defaut_ecarte_les_notes_quasi_nulles(ctx: RunCtx, index: Path) -> None:
    assert _arch(ctx).p.relevance_threshold == 0.1

    def faibles(req: Any) -> str:
        return json.dumps({"scores": [0.05] * len(req.inputs["passages"])})

    ctx.provider.script("grade_relevance", "lazygraphrag.grade.*", faibles)  # type: ignore[attr-defined]
    rep = _repondre(ctx, index)
    assert rep.abstained and not _spans(ctx, "generate")


def test_mots_outils_ne_rattachent_rien() -> None:
    assert _mots("que") == frozenset() and _mots("le") == frozenset()
    assert _mots("pourquoi port ysel") == {"port", "ysel"}
    assert _mots("port-ysel") == {"port", "ysel"}


def test_le_provider_interdit_leve_bien_a_la_requete(
    ctx: RunCtx, index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrôle de la doublure : sans cela, les tests « sans appel » ne prouveraient rien."""
    _interdire_llm(ctx, monkeypatch)
    with pytest.raises(Exception, match="appel LLM interdit"):
        _repondre(ctx, index)

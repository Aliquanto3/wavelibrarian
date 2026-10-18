"""Story 4.9, AC 1 : rappel@5, MRR et nDCG@5 contre des valeurs calculées à la main."""

import math

from wavelibrarian.core.types import Passage, ScoredPassage
from wavelibrarian.scoring.retrieval import est_pertinent, retrieval_metrics


def _sp(i: int, *anchors: str) -> ScoredPassage:
    passage = Passage(passage_id=f"p{i}", doc_id="d", text=f"t{i}", anchor_ids=anchors)
    return ScoredPassage(passage=passage, score=1.0 / i, rank=i)


# Deux Ancrages de référence (A1, A2) ; les rangs 2 et 4 en recouvrent chacun un.
CLASSES = [_sp(1, "d#x"), _sp(2, "d#a1"), _sp(3, "d#y"), _sp(4, "d#a2", "d#z"), _sp(5, "d#w")]
REFERENCE = {"d#a1", "d#a2"}


def test_valeurs_calculees_a_la_main() -> None:
    m = retrieval_metrics(CLASSES, REFERENCE, "ranked")
    assert m.method == "ranked" and m.k == 5
    assert m.recall == 1.0  # A1 et A2 recouverts dans les 5 premiers
    assert m.mrr == 0.5  # premier pertinent au rang 2
    dcg = 1 / math.log2(3) + 1 / math.log2(5)  # rangs 2 et 4
    ideal = 1 + 1 / math.log2(3)  # deux pertinents aux rangs 1 et 2
    assert m.ndcg is not None and abs(m.ndcg - dcg / ideal) < 1e-12
    assert round(m.ndcg, 4) == 0.6509


def test_pertinence_par_recouvrement_quel_que_soit_le_decoupage() -> None:
    gros = Passage(passage_id="g", doc_id="d", text="g", anchor_ids=("d#a1", "d#a2"))
    assert est_pertinent(gros, REFERENCE)
    m = retrieval_metrics([ScoredPassage(passage=gros, score=1.0, rank=1)], REFERENCE, "ranked")
    assert (m.recall, m.mrr) == (1.0, 1.0)
    assert m.ndcg is not None and abs(m.ndcg - 1 / (1 + 1 / math.log2(3))) < 1e-12  # idéal : 2


def test_rappel_partiel_et_k() -> None:
    m = retrieval_metrics(CLASSES, REFERENCE, "ranked", k=3)
    assert m.recall == 0.5 and m.mrr == 0.5 and m.k == 3
    vide = retrieval_metrics([_sp(1, "d#x")], REFERENCE, "ranked")
    assert (vide.recall, vide.mrr, vide.ndcg) == (0.0, 0.0, 0.0)


def test_le_rang_ordonne_la_liste() -> None:
    melange = [CLASSES[3], CLASSES[1], CLASSES[0], CLASSES[2], CLASSES[4]]
    assert retrieval_metrics(melange, REFERENCE, "ranked") == retrieval_metrics(
        CLASSES, REFERENCE, "ranked"
    )


def test_methodes_reportees_et_none_sans_metrique() -> None:
    for methode in ("provided", "cited"):
        m = retrieval_metrics(CLASSES, REFERENCE, methode)
        assert m.method == methode and m.mrr == 0.5
    n = retrieval_metrics(CLASSES, REFERENCE, "none")
    assert n.method == "none" and (n.recall, n.mrr, n.ndcg) == (None, None, None)


def test_question_sans_ancrage_de_reference_sans_metrique() -> None:
    m = retrieval_metrics(CLASSES, set(), "ranked")
    assert m.method == "ranked" and m.recall is None

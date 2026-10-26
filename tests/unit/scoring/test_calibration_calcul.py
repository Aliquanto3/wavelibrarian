"""Calcul de la calibration d'un Juge (story 5.2) : kappa juge-humain, instabilité, exclusion."""

import pytest

from wavelibrarian.core.types import VerdictValue
from wavelibrarian.scoring.calibration import (
    Annotations,
    FicheCritere,
    Passe,
    decider_exclusion,
    doublement_annotees,
    fiches_du_juge,
    kappa_inter_annotateurs,
)


def _annotations() -> Annotations:
    # anael : a1 oui, a2 oui, a3 non, a4 non ; bruno : a1 oui, a2 non (correctness)
    return Annotations(
        {
            ("anael", "a1", "correctness"): "yes",
            ("anael", "a2", "correctness"): "yes",
            ("anael", "a3", "correctness"): "no",
            ("anael", "a4", "correctness"): "no",
            ("bruno", "a1", "correctness"): "yes",
            ("bruno", "a2", "correctness"): "no",
        }
    )


def test_kappa_juge_humain_instabilite_et_items_a_la_main() -> None:
    # Passe 0 du Juge : a1 oui, a2 oui, a3 non, a4 oui. Humains par annotateur : 6 paires,
    # humain [1,1,0,0,1,0] contre juge [1,1,0,1,1,1] : p_o = 4/6, p_e = 0,5 -> kappa = 1/3.
    verdicts: dict[Passe, VerdictValue] = {
        ("a1", "correctness", 0): "yes",
        ("a1", "correctness", 1): "yes",
        ("a2", "correctness", 0): "yes",
        ("a2", "correctness", 1): "no",  # instable
        ("a3", "correctness", 0): "no",
        ("a3", "correctness", 1): "no",
        ("a4", "correctness", 0): "yes",
        ("a4", "correctness", 1): "yes",
    }
    fiches = fiches_du_juge(verdicts, _annotations(), {"a1", "a2", "a3", "a4"})
    assert set(fiches) == {"correctness"}
    f = fiches["correctness"]
    assert f.kappa == pytest.approx(1 / 3, abs=1e-12)
    assert f.instability == 0.25
    assert f.n_items == 6


def test_reponse_hors_perimetre_ou_sans_passe_zero_n_entre_pas() -> None:
    verdicts: dict[Passe, VerdictValue] = {
        ("a1", "correctness", 0): "yes",
        ("a2", "correctness", 1): "yes",
    }
    f = fiches_du_juge(verdicts, _annotations(), {"a1", "a2"})["correctness"]
    assert f.n_items == 2  # a1 : anael et bruno ; a2 n'a pas de passe 0
    assert f.instability is None  # aucune Réponse notée à deux passes


def test_kappa_indefini_si_une_seule_classe() -> None:
    annotations = Annotations({("anael", "a1", "correctness"): "yes"})
    f = fiches_du_juge({("a1", "correctness", 0): "yes"}, annotations, {"a1"})["correctness"]
    assert f.kappa is None and f.n_items == 1


def test_kappa_inter_annotateurs_sur_les_doublement_annotees() -> None:
    # Communes : a1 (oui/oui) et a2 (oui/non) : p_o = 0,5, p_e = 0,5 -> kappa 0.
    (paire,) = kappa_inter_annotateurs(_annotations())
    assert paire["annotators"] == ["anael", "bruno"]
    assert paire["criteria"]["correctness"] == {
        "kappa": 0.0,
        "n_items": 2,
        "na_agreements": 0,
        "na_disagreements": 0,
    }
    assert doublement_annotees(_annotations()) == {"a1", "a2"}


def test_exclusion_sous_le_seuil_et_kappa_indefini_signale() -> None:
    fiches = {
        "correctness": FicheCritere(kappa=0.4, instability=0.0, n_items=10),
        "completeness": FicheCritere(kappa=None, instability=None, n_items=3),
    }
    exclu, raison, signales = decider_exclusion(fiches, 0.6)
    assert exclu is True
    assert raison == "kappa 0,40 sous le seuil 0,60 sur correctness"
    assert len(signales) == 1 and "completeness" in signales[0]
    exclu, raison, signales = decider_exclusion({"completeness": fiches["completeness"]}, 0.6)
    assert exclu is False and raison is None and len(signales) == 1
    assert decider_exclusion({"correctness": FicheCritere(0.6, 0.0, 4)}, 0.6)[0] is False


def test_kappa_hors_na_et_comptes_na_a_part() -> None:
    """Story 9.3 : le kappa ne porte que sur les paires yes/no ; les `na` sont comptés à part."""
    annotations = Annotations(
        {
            ("anael", "a1", "faithfulness"): "yes",
            ("anael", "a2", "faithfulness"): "no",
            ("anael", "a3", "faithfulness"): "na",  # accord na
            ("anael", "a4", "faithfulness"): "na",  # désaccord : le Juge dit yes
            ("anael", "a5", "faithfulness"): "yes",  # désaccord : le Juge dit na
        }
    )
    verdicts: dict[Passe, VerdictValue] = {
        ("a1", "faithfulness", 0): "yes",
        ("a2", "faithfulness", 0): "no",
        ("a3", "faithfulness", 0): "na",
        ("a4", "faithfulness", 0): "yes",
        ("a5", "faithfulness", 0): "na",
    }
    f = fiches_du_juge(verdicts, annotations, {"a1", "a2", "a3", "a4", "a5"})["faithfulness"]
    assert f.kappa == 1.0  # a1 et a2 seulement : accord parfait sur deux classes
    assert (f.n_items, f.na_agreements, f.na_disagreements) == (2, 1, 2)
    assert f.en_json() == {
        "kappa": 1.0,
        "instability": None,
        "n_items": 2,
        "na_agreements": 1,
        "na_disagreements": 2,
    }


def test_instabilite_compte_un_passage_na_vers_yes() -> None:
    annotations = Annotations(
        {("anael", "a1", "faithfulness"): "yes", ("anael", "a2", "faithfulness"): "na"}
    )
    verdicts: dict[Passe, VerdictValue] = {
        ("a1", "faithfulness", 0): "na",
        ("a1", "faithfulness", 1): "yes",  # instable
        ("a2", "faithfulness", 0): "na",
        ("a2", "faithfulness", 1): "na",  # stable
    }
    f = fiches_du_juge(verdicts, annotations, {"a1", "a2"})["faithfulness"]
    assert f.instability == 0.5
    assert f.kappa is None and f.n_items == 0  # aucune paire yes/no
    assert (f.na_agreements, f.na_disagreements) == (1, 1)


def test_kappa_inter_annotateurs_hors_na() -> None:
    annotations = Annotations(
        {
            ("anael", "a1", "faithfulness"): "yes",
            ("anael", "a2", "faithfulness"): "no",
            ("anael", "a3", "faithfulness"): "na",
            ("anael", "a4", "faithfulness"): "na",
            ("bruno", "a1", "faithfulness"): "yes",
            ("bruno", "a2", "faithfulness"): "no",
            ("bruno", "a3", "faithfulness"): "na",
            ("bruno", "a4", "faithfulness"): "no",
        }
    )
    (paire,) = kappa_inter_annotateurs(annotations)
    assert paire["criteria"]["faithfulness"] == {
        "kappa": 1.0,
        "n_items": 2,
        "na_agreements": 1,
        "na_disagreements": 1,
    }

"""Calcul de la calibration d'un Juge (story 5.2) : kappa juge-humain, instabilité, exclusion."""

import pytest

from wavelibrarian.scoring.calibration import (
    Annotations,
    FicheCritere,
    decider_exclusion,
    doublement_annotees,
    fiches_du_juge,
    kappa_inter_annotateurs,
)


def _annotations() -> Annotations:
    # anael : a1 oui, a2 oui, a3 non, a4 non ; bruno : a1 oui, a2 non (correctness)
    return Annotations(
        {
            ("anael", "a1", "correctness"): True,
            ("anael", "a2", "correctness"): True,
            ("anael", "a3", "correctness"): False,
            ("anael", "a4", "correctness"): False,
            ("bruno", "a1", "correctness"): True,
            ("bruno", "a2", "correctness"): False,
        }
    )


def test_kappa_juge_humain_instabilite_et_items_a_la_main() -> None:
    # Passe 0 du Juge : a1 oui, a2 oui, a3 non, a4 oui. Humains par annotateur : 6 paires,
    # humain [1,1,0,0,1,0] contre juge [1,1,0,1,1,1] : p_o = 4/6, p_e = 0,5 -> kappa = 1/3.
    verdicts = {
        ("a1", "correctness", 0): True,
        ("a1", "correctness", 1): True,
        ("a2", "correctness", 0): True,
        ("a2", "correctness", 1): False,  # instable
        ("a3", "correctness", 0): False,
        ("a3", "correctness", 1): False,
        ("a4", "correctness", 0): True,
        ("a4", "correctness", 1): True,
    }
    fiches = fiches_du_juge(verdicts, _annotations(), {"a1", "a2", "a3", "a4"})
    assert set(fiches) == {"correctness"}
    f = fiches["correctness"]
    assert f.kappa == pytest.approx(1 / 3, abs=1e-12)
    assert f.instability == 0.25
    assert f.n_items == 6


def test_reponse_hors_perimetre_ou_sans_passe_zero_n_entre_pas() -> None:
    verdicts = {("a1", "correctness", 0): True, ("a2", "correctness", 1): True}
    f = fiches_du_juge(verdicts, _annotations(), {"a1", "a2"})["correctness"]
    assert f.n_items == 2  # a1 : anael et bruno ; a2 n'a pas de passe 0
    assert f.instability is None  # aucune Réponse notée à deux passes


def test_kappa_indefini_si_une_seule_classe() -> None:
    annotations = Annotations({("anael", "a1", "correctness"): True})
    f = fiches_du_juge({("a1", "correctness", 0): True}, annotations, {"a1"})["correctness"]
    assert f.kappa is None and f.n_items == 1


def test_kappa_inter_annotateurs_sur_les_doublement_annotees() -> None:
    # Communes : a1 (oui/oui) et a2 (oui/non) : p_o = 0,5, p_e = 0,5 -> kappa 0.
    (paire,) = kappa_inter_annotateurs(_annotations())
    assert paire["annotators"] == ["anael", "bruno"]
    assert paire["criteria"]["correctness"] == {"kappa": 0.0, "n_items": 2}
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

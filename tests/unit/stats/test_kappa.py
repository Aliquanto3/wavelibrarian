"""Tests du kappa de Cohen (story 5.1)."""

import pytest

from wavelibrarian.stats.kappa import cohen_kappa


def _vecteurs(oo: int, on: int, no: int, nn: int) -> tuple[list[bool], list[bool]]:
    a = [True] * (oo + on) + [False] * (no + nn)
    b = [True] * oo + [False] * on + [True] * no + [False] * nn
    return a, b


def test_table_connue() -> None:
    a, b = _vecteurs(20, 5, 10, 15)
    # p_o = 35/50 = 0,7 ; p_e = (25*30 + 25*20)/2500 = 0,5 ; kappa = 0,2/0,5
    assert cohen_kappa(a, b) == pytest.approx(0.4, abs=1e-12)


def test_vecteurs_identiques() -> None:
    v = [True, False, False, True, True]
    assert cohen_kappa(v, list(v)) == 1.0


def test_classe_unique_indefini() -> None:
    assert cohen_kappa([True] * 4, [True] * 4) is None
    assert cohen_kappa([False] * 4, [False] * 4) is None
    assert cohen_kappa([], []) is None


def test_desaccord_total() -> None:
    assert cohen_kappa([True, False], [False, True]) == -1.0


def test_longueurs_differentes() -> None:
    with pytest.raises(ValueError, match="longueurs"):
        cohen_kappa([True], [True, False])


def test_evaluateur_constant_face_a_mixte() -> None:
    # p_o = 2/4 ; p_e = (4*2 + 0*2)/16 = 0,5 ; kappa = 0
    assert cohen_kappa([True] * 4, [True, True, False, False]) == 0.0


def test_deux_classes_constantes_opposees() -> None:
    # p_o = 0 ; p_e = (n*0 + 0*n)/n² = 0 ; kappa = 0
    assert cohen_kappa([True] * 3, [False] * 3) == 0.0


def test_un_seul_item() -> None:
    assert cohen_kappa([True], [True]) is None

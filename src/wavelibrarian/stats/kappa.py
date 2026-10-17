"""Kappa de Cohen binaire (fonction pure, AD-22)."""

from collections.abc import Sequence


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Kappa de Cohen de deux vecteurs binaires de même longueur.

    `None` quand il est indéfini : vecteurs vides, ou accord attendu égal à 1
    (les deux évaluateurs n'emploient qu'une seule et même classe).
    Longueurs différentes : `ValueError`.
    """
    if len(a) != len(b):
        raise ValueError(f"longueurs différentes : {len(a)} et {len(b)}")
    n = len(a)
    if n == 0:
        return None
    oo = sum(1 for x, y in zip(a, b, strict=True) if x and y)
    on = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    no = sum(1 for x, y in zip(a, b, strict=True) if not x and y)
    nn = n - oo - on - no
    p_o = (oo + nn) / n
    p_e = ((oo + on) * (oo + no) + (no + nn) * (on + nn)) / (n * n)
    if p_e == 1.0:
        return None
    return (p_o - p_e) / (1.0 - p_e)

"""Front de Pareto (fonction pure, AD-20, AD-22)."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    config_id: str
    qualite: float
    cout: float


def domine(p: Point, q: Point) -> bool:
    """`p` domine `q` : au moins aussi bon partout, strictement meilleur sur un axe."""
    return (
        p.qualite >= q.qualite and p.cout <= q.cout and (p.qualite > q.qualite or p.cout < q.cout)
    )


def front_pareto(points: Iterable[Point]) -> list[Point]:
    """Points non dominés (Qualité maximisée, coût minimisé).

    Deux points identiques ne se dominent pas : les deux restent. Ordre
    déterministe : coût croissant, Qualité décroissante, puis `config_id`.
    """
    pts = list(points)
    front = [p for p in pts if not any(domine(q, p) for q in pts)]
    return sorted(front, key=lambda p: (p.cout, -p.qualite, p.config_id))

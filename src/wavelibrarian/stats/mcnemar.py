"""Test de McNemar exact (fonction pure, AD-22)."""

from collections.abc import Mapping
from dataclasses import dataclass

from scipy.stats import binomtest

from wavelibrarian.stats.appariement import questions_communes


@dataclass(frozen=True)
class ResultatMcNemar:
    """b : A oui et B non ; c : A non et B oui."""

    b: int
    c: int
    p_value: float
    n_common: int


def mcnemar_exact(b: int, c: int) -> float:
    """P-valeur bilatérale exacte sur les paires discordantes ; 1 si b = c = 0."""
    if b < 0 or c < 0:
        raise ValueError("b et c doivent être positifs")
    n = b + c
    if n == 0:
        return 1.0
    return float(binomtest(min(b, c), n, 0.5).pvalue)


def compare(a: Mapping[str, bool], b: Mapping[str, bool]) -> ResultatMcNemar | None:
    """McNemar exact sur les seules Questions communes ; `n_common` renvoyé.

    `None` quand aucune Question n'est commune : une p-valeur de 1 sans
    donnée ferait conclure à tort à une « Qualité égale ». Les valeurs sont
    des verdicts booléens ; l'appelant décide en amont du sort d'une Réponse
    absente (exclue, ou comptée fausse explicitement).
    """
    communes = questions_communes(a, b)
    if not communes:
        return None
    disc_b = sum(1 for q in communes if a[q] and not b[q])
    disc_c = sum(1 for q in communes if not a[q] and b[q])
    return ResultatMcNemar(disc_b, disc_c, mcnemar_exact(disc_b, disc_c), len(communes))

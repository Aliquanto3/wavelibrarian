"""Bootstrap percentile et bootstrap apparié (fonctions pures, AD-20, AD-22).

L'aléa vient d'un `numpy.random.Generator` créé ici à partir de la graine.
Les rééchantillons sont tirés d'un seul bloc `rng.integers(0, n, (B, n))`,
comme le fait `scipy.stats.bootstrap`, donc l'IC percentile coïncide avec
celui de scipy pour le même générateur.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from wavelibrarian.stats.appariement import questions_communes

N_RESAMPLES = 2000
CONFIDENCE = 0.95


@dataclass(frozen=True)
class Intervalle:
    mean: float
    low: float
    high: float
    n: int


@dataclass(frozen=True)
class DifferenceAppariee:
    """Différence moyenne a - b sur les Questions communes."""

    diff: float
    low: float
    high: float
    p_value: float
    n_common: int


def _valider(n_resamples: int, confidence: float) -> None:
    if n_resamples < 1:
        raise ValueError("n_resamples doit être au moins 1")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence doit être dans ]0, 1[")


def _percentiles(stats: np.ndarray, confidence: float) -> tuple[float, float]:
    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(stats, [alpha * 100.0, (1.0 - alpha) * 100.0])
    return float(low), float(high)


def bootstrap_ci(
    values: Sequence[float | bool],
    *,
    seed: int,
    n_resamples: int = N_RESAMPLES,
    confidence: float = CONFIDENCE,
) -> Intervalle | None:
    """IC percentile de la moyenne ; `None` si `values` est vide."""
    _valider(n_resamples, confidence)
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_resamples, x.size))
    low, high = _percentiles(x[idx].mean(axis=1), confidence)
    return Intervalle(float(x.mean()), low, high, int(x.size))


def paired_bootstrap(
    a: Sequence[float | bool],
    b: Sequence[float | bool],
    *,
    seed: int,
    n_resamples: int = N_RESAMPLES,
    confidence: float = CONFIDENCE,
) -> DifferenceAppariee | None:
    """Bootstrap apparié de la différence moyenne a - b.

    Les paires sont rééchantillonnées ensemble. P-valeur bilatérale :
    2 * min(part des différences rééchantillonnées <= 0, part >= 0), avec
    correction (+1)/(B+1) pour ne jamais renvoyer 0, plafonnée à 1.
    `None` si les vecteurs sont vides ; longueurs différentes : `ValueError`.
    """
    _valider(n_resamples, confidence)
    if len(a) != len(b):
        raise ValueError(f"longueurs différentes : {len(a)} et {len(b)}")
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    if d.size == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(n_resamples, d.size))
    means = d[idx].mean(axis=1)
    low, high = _percentiles(means, confidence)
    le = (int(np.sum(means <= 0.0)) + 1) / (n_resamples + 1)
    ge = (int(np.sum(means >= 0.0)) + 1) / (n_resamples + 1)
    p = min(1.0, 2.0 * min(le, ge))
    return DifferenceAppariee(float(d.mean()), low, high, p, int(d.size))


def compare_continu(
    a: Mapping[str, float],
    b: Mapping[str, float],
    *,
    seed: int,
    n_resamples: int = N_RESAMPLES,
    confidence: float = CONFIDENCE,
) -> DifferenceAppariee | None:
    """Bootstrap apparié sur les seules Questions communes ; `n_common` renvoyé.

    `None` quand aucune Question n'est commune.
    """
    communes = questions_communes(a, b)
    return paired_bootstrap(
        [a[q] for q in communes],
        [b[q] for q in communes],
        seed=seed,
        n_resamples=n_resamples,
        confidence=confidence,
    )

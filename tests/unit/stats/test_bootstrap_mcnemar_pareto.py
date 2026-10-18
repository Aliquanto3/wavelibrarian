"""Tests de la story 4.10 : bootstrap, McNemar, Pareto."""

import numpy as np
import pytest
from scipy import stats

from wavelibrarian.core.ids import sha16
from wavelibrarian.stats.bootstrap import (
    bootstrap_ci,
    compare_continu,
    graine_derivee,
    paired_bootstrap,
)
from wavelibrarian.stats.mcnemar import compare, mcnemar_exact
from wavelibrarian.stats.pareto import Point, front_pareto

VEC = [True] * 70 + [False] * 30


def test_ic_identique_a_scipy():
    ic = bootstrap_ci(VEC, seed=42, n_resamples=2000)
    ref = stats.bootstrap(
        (np.array(VEC, dtype=float),),
        np.mean,
        n_resamples=2000,
        confidence_level=0.95,
        method="percentile",
        rng=np.random.default_rng(42),
        vectorized=True,
    )
    assert ic is not None
    assert ic.low == pytest.approx(ref.confidence_interval.low, abs=1e-9)
    assert ic.high == pytest.approx(ref.confidence_interval.high, abs=1e-9)
    assert ic.mean == pytest.approx(0.7)


def test_meme_graine_meme_ic_et_vide():
    assert bootstrap_ci(VEC, seed=42, n_resamples=300) == bootstrap_ci(
        VEC, seed=42, n_resamples=300
    )
    assert bootstrap_ci(VEC, seed=1, n_resamples=300) != bootstrap_ci(VEC, seed=2, n_resamples=300)
    assert bootstrap_ci([], seed=1) is None
    with pytest.raises(ValueError):
        bootstrap_ci(VEC, seed=1, n_resamples=0)


def test_bootstrap_apparie_donnees_connues():
    a = [1.0 + 0.1 * (i % 3) for i in range(40)]
    b = [x - 0.5 for x in a]
    r = paired_bootstrap(a, b, seed=7, n_resamples=500)
    assert r is not None
    assert r.diff == pytest.approx(0.5)
    assert r.low == pytest.approx(0.5)
    assert r.high == pytest.approx(0.5)
    assert r.p_value == pytest.approx(2 / 501)
    assert r.n_common == 40
    nul = paired_bootstrap([0.2, 0.8, 0.5, 0.1], [0.8, 0.2, 0.1, 0.5], seed=7, n_resamples=500)
    assert nul is not None
    assert nul.diff == pytest.approx(0.0)
    assert nul.p_value == 1.0
    assert paired_bootstrap(a, b, seed=7, n_resamples=500) == r
    assert paired_bootstrap([], [], seed=1) is None
    with pytest.raises(ValueError):
        paired_bootstrap([1.0], [1.0, 2.0], seed=1)


def test_mcnemar_exact():
    assert mcnemar_exact(12, 3) == pytest.approx(stats.binomtest(3, 15, 0.5).pvalue)
    assert mcnemar_exact(3, 12) == mcnemar_exact(12, 3)
    assert mcnemar_exact(0, 0) == 1.0
    with pytest.raises(ValueError):
        mcnemar_exact(-1, 2)


def test_compare_questions_communes():
    a = {"q1": True, "q2": True, "q3": False, "q4": True}
    b = {"q2": False, "q3": True, "q4": True, "q5": False}
    r = compare(a, b)
    assert r is not None
    assert r.n_common == 3
    assert (r.b, r.c) == (1, 1)
    assert r.p_value == 1.0
    d = compare_continu({"q1": 1.0, "q2": 0.5}, {"q2": 0.25, "q9": 3.0}, seed=1, n_resamples=50)
    assert d is not None
    assert d.n_common == 1
    assert d.diff == pytest.approx(0.25)
    assert compare_continu({"q1": 1.0}, {"q2": 1.0}, seed=1) is None
    assert compare({"q1": True}, {"q2": True}) is None


def test_pareto_domine_et_egalite():
    pts = [
        Point("b", 0.8, 5.0),
        Point("a", 0.8, 5.0),  # ex aequo avec b : les deux restent
        Point("c", 0.6, 2.0),
        Point("d", 0.5, 6.0),  # domine
        Point("e", 0.9, 9.0),
    ]
    assert [p.config_id for p in front_pareto(pts)] == ["c", "a", "b", "e"]
    assert [p.config_id for p in front_pareto(reversed(pts))] == ["c", "a", "b", "e"]
    assert front_pareto([]) == []


def test_bootstrap_apparie_ic_scipy_et_p_analytique():
    # IC apparié = IC percentile de scipy sur les différences (vecteur non constant).
    rng = np.random.default_rng(3)
    a = rng.normal(0.6, 0.2, 60).tolist()
    b = rng.normal(0.5, 0.2, 60).tolist()
    r = paired_bootstrap(a, b, seed=11, n_resamples=2000)
    ref = stats.bootstrap(
        (np.array(a) - np.array(b),),
        np.mean,
        n_resamples=2000,
        method="percentile",
        rng=np.random.default_rng(11),
        vectorized=True,
    )
    assert r is not None
    assert r.low == pytest.approx(ref.confidence_interval.low, abs=1e-9)
    assert r.high == pytest.approx(ref.confidence_interval.high, abs=1e-9)
    # d = [1, 1, -1] : moyenne rééchantillonnée <= 0 ssi au moins deux -1,
    # probabilité 7/27, donc p bilatérale théorique 14/27.
    m = paired_bootstrap([1.0, 1.0, 0.0], [0.0, 0.0, 1.0], seed=5, n_resamples=40000)
    assert m is not None
    assert m.p_value == pytest.approx(14 / 27, abs=0.015)


def test_graine_derivee_et_valeurs_non_finies():
    assert graine_derivee(42, "cfg", "dev") == int(sha16("42", "cfg", "dev"), 16)
    assert graine_derivee(42, "cfg", "dev") != graine_derivee(42, "cfg", "test")
    with pytest.raises(ValueError):
        bootstrap_ci([0.5, float("nan")], seed=1)
    with pytest.raises(ValueError):
        paired_bootstrap([0.5, 1.0], [float("inf"), 0.0], seed=1)
    with pytest.raises(ValueError):
        front_pareto([Point("a", float("nan"), 1.0)])

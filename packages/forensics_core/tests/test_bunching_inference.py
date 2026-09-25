"""Tests for forensics_core.bunching.inference: bootstrap, placebo and permutation tests.

Synthetic data only (HARD RULE 3), fixed seeds throughout so that every assertion about a
p-value or an interval is deterministic.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from forensics_core.bunching.density import bunching_estimator
from forensics_core.bunching.inference import (
    BootstrapResult,
    bootstrap_bunching,
    permutation_test,
    placebo_test,
)

THRESHOLD = 100.0
SIGMA = 0.35
WINDOW = {
    "bin_width": 1.0,
    "exclude_below": 2.0,
    "exclude_above": 2.0,
    "lo": 60.0,
    "hi": 160.0,
    "poly_degree": 7,
}
PLACEBOS = [85.0, 90.0, 95.0, 105.0, 110.0, 115.0]


def lognormal_with_bunching(seed: int, n: int = 200_000, n_moved: int = 2_000) -> np.ndarray:
    """Lognormal density with ``n_moved`` units moved from just above to just below 100."""
    rng = np.random.default_rng(seed)
    x = rng.lognormal(np.log(THRESHOLD), SIGMA, size=n)
    pool = np.flatnonzero((x >= THRESHOLD) & (x < THRESHOLD + 2.0))
    chosen = rng.choice(pool, size=n_moved, replace=False)
    x[chosen] = rng.uniform(THRESHOLD - 1.0, THRESHOLD, size=n_moved)
    return x


def smooth_lognormal(seed: int, n: int = 200_000) -> np.ndarray:
    return np.random.default_rng(seed).lognormal(np.log(THRESHOLD), SIGMA, size=n)


def estimator(x: np.ndarray):
    return bunching_estimator(x, THRESHOLD, bunching_side="below", **WINDOW)


def factory(threshold: float):
    def _estimate(x: np.ndarray):
        return bunching_estimator(x, threshold, bunching_side="below", **WINDOW)

    return _estimate


# -------------------------------------------------------------------------- bootstrap


def test_residual_bootstrap_covers_the_injected_mass():
    injected = 2_000
    x = lognormal_with_bunching(seed=20260903, n_moved=injected)
    boot = bootstrap_bunching(x, estimator, n_boot=199, seed=11, method="residual")

    assert isinstance(boot, BootstrapResult)
    assert boot.draws.shape == (199,)
    assert boot.n_boot == 199
    assert boot.method == "residual"
    assert boot.se > 0.0
    assert boot.ci_low < boot.point < boot.ci_high
    assert boot.covers(injected)
    assert not boot.covers(0.0)
    assert boot.point == pytest.approx(estimator(x).excess_mass, rel=1e-12)


def test_pairs_bootstrap_covers_the_injected_mass():
    injected = 600
    x = lognormal_with_bunching(seed=11, n=40_000, n_moved=injected)
    boot = bootstrap_bunching(x, estimator, n_boot=99, seed=3, method="pairs")

    assert boot.method == "pairs"
    assert boot.draws.shape == (99,)
    assert boot.se > 0.0
    assert boot.covers(injected)
    assert not boot.covers(0.0)


def test_bootstrap_ci_covers_zero_when_there_is_no_bunching():
    x = smooth_lognormal(seed=1)
    boot = bootstrap_bunching(x, estimator, n_boot=199, seed=11, method="residual")
    assert boot.covers(0.0)


def test_bootstrap_is_reproducible_and_seed_sensitive():
    x = lognormal_with_bunching(seed=5, n=40_000, n_moved=600)
    a = bootstrap_bunching(x, estimator, n_boot=99, seed=42)
    b = bootstrap_bunching(x, estimator, n_boot=99, seed=42)
    c = bootstrap_bunching(x, estimator, n_boot=99, seed=43)
    np.testing.assert_array_equal(a.draws, b.draws)
    assert not np.array_equal(a.draws, c.draws)


def test_bootstrap_supports_other_statistics():
    x = lognormal_with_bunching(seed=5, n=40_000, n_moved=600)
    normalized = bootstrap_bunching(x, estimator, n_boot=99, seed=1, statistic="normalized_excess")
    assert normalized.point == pytest.approx(estimator(x).normalized_excess, rel=1e-12)
    custom = bootstrap_bunching(
        x, estimator, n_boot=99, seed=1, statistic=lambda r: r.excess_mass - r.missing_mass
    )
    assert custom.point == pytest.approx(
        estimator(x).excess_mass - estimator(x).missing_mass, rel=1e-12
    )


def test_bootstrap_result_is_jsonable():
    x = lognormal_with_bunching(seed=5, n=20_000, n_moved=300)
    boot = bootstrap_bunching(x, estimator, n_boot=25, seed=1)
    payload = boot.to_dict()
    assert json.loads(json.dumps(payload))["n_boot"] == 25
    assert boot.to_test_result().pvalue is None
    assert boot.to_test_result().details["bootstrap_method"] == "residual"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_boot": 1}, "n_boot"),
        ({"alpha": 0.0}, "alpha"),
        ({"alpha": 1.5}, "alpha"),
        ({"method": "jackknife"}, "method"),
        ({"statistic": "excess"}, "statistic"),
    ],
)
def test_bootstrap_rejects_bad_arguments(kwargs, match):
    x = lognormal_with_bunching(seed=5, n=20_000, n_moved=300)
    call = {"n_boot": 25, "seed": 1, **kwargs}
    with pytest.raises(ValueError, match=match):
        bootstrap_bunching(x, estimator, **call)


def test_bootstrap_rejects_a_non_bunching_estimator():
    x = lognormal_with_bunching(seed=5, n=20_000, n_moved=300)
    with pytest.raises(ValueError, match="BunchingResult"):
        bootstrap_bunching(x, lambda a: float(a.mean()), n_boot=25, seed=1)


# ----------------------------------------------------------------------------- placebo


def test_placebo_test_singles_out_the_real_threshold():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000)
    result = placebo_test(x, THRESHOLD, factory, PLACEBOS)

    assert result.method == "bunching_placebo"
    assert result.details["alternative"] == "greater"
    assert result.details["n_placebo"] == len(PLACEBOS)
    assert result.pvalue == 0.0
    assert result.statistic > 0.5
    # the placebos see essentially nothing
    assert np.max(np.abs(result.details["placebo_values"])) < 0.15
    assert result.statistic > 10.0 * np.max(np.abs(result.details["placebo_values"]))


def test_placebo_add_one_never_returns_zero():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000)
    result = placebo_test(x, THRESHOLD, factory, PLACEBOS, add_one=True)
    assert result.pvalue == pytest.approx(1.0 / (1.0 + len(PLACEBOS)))
    assert result.details["add_one"] is True


def test_placebo_test_is_unremarkable_on_a_smooth_density():
    x = smooth_lognormal(seed=20260903)
    result = placebo_test(x, THRESHOLD, factory, PLACEBOS)
    assert result.pvalue >= 1.0 / len(PLACEBOS)
    assert abs(result.statistic) < 0.15


def test_placebo_test_counts_the_dropped_values():
    x = lognormal_with_bunching(seed=5, n=40_000, n_moved=600)
    result = placebo_test(np.concatenate([x, [np.nan]]), THRESHOLD, factory, PLACEBOS)
    assert result.details["n_dropped"] == 1
    assert result.n == x.size


@pytest.mark.parametrize(
    ("threshold", "placebos", "match"),
    [
        (np.nan, PLACEBOS, "threshold"),
        (THRESHOLD, [], "must not be empty"),
        (THRESHOLD, [THRESHOLD, 90.0], "must not contain the real threshold"),
        (THRESHOLD, [np.nan], "finite"),
    ],
)
def test_placebo_rejects_bad_arguments(threshold, placebos, match):
    x = lognormal_with_bunching(seed=5, n=20_000, n_moved=300)
    with pytest.raises(ValueError, match=match):
        placebo_test(x, threshold, factory, placebos)


# ------------------------------------------------------------------------ permutation


def test_permutation_test_detects_a_mean_shift():
    rng = np.random.default_rng(5)
    x = np.concatenate([rng.normal(0.0, 1.0, 200), rng.normal(0.8, 1.0, 200)])
    groups = np.array(["a"] * 200 + ["b"] * 200)
    result = permutation_test(x, groups, np.mean, n_perm=499, seed=1)

    assert result.method == "permutation_group_difference"
    assert result.details["alternative"] == "two-sided"
    assert result.pvalue < 0.01
    assert result.statistic == pytest.approx(np.mean(x[:200]) - np.mean(x[200:]))
    assert result.details["group_sizes"] == {"a": 200, "b": 200}
    assert set(result.details["per_group_statistic"]) == {"a", "b"}


def test_permutation_test_finds_nothing_under_the_null():
    rng = np.random.default_rng(5)
    x = rng.normal(0.0, 1.0, 400)
    groups = np.array(["a"] * 200 + ["b"] * 200)
    result = permutation_test(x, groups, np.mean, n_perm=499, seed=1)
    assert result.pvalue > 0.2


def test_permutation_test_uses_the_range_for_three_groups():
    rng = np.random.default_rng(5)
    x = np.concatenate(
        [rng.normal(0.0, 1.0, 200), rng.normal(0.8, 1.0, 200), rng.normal(-0.8, 1.0, 200)]
    )
    groups = np.array(["a"] * 200 + ["b"] * 200 + ["c"] * 200)
    result = permutation_test(x, groups, np.mean, n_perm=499, seed=1)

    assert result.details["alternative"] == "greater"
    per_group = result.details["per_group_statistic"]
    assert result.statistic == pytest.approx(max(per_group.values()) - min(per_group.values()))
    assert result.pvalue < 0.01


def test_permutation_test_works_with_any_scalar_statistic():
    rng = np.random.default_rng(6)
    x = np.concatenate([rng.normal(0.0, 1.0, 300), rng.normal(0.0, 3.0, 300)])
    groups = np.array([0] * 300 + [1] * 300)
    result = permutation_test(x, groups, lambda v: float(np.var(v)), n_perm=499, seed=2)
    assert result.pvalue < 0.01


def test_permutation_test_is_reproducible():
    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 1.0, 200)
    groups = np.array(["a"] * 100 + ["b"] * 100)
    a = permutation_test(x, groups, np.mean, n_perm=199, seed=3)
    b = permutation_test(x, groups, np.mean, n_perm=199, seed=3)
    c = permutation_test(x, groups, np.mean, n_perm=199, seed=4)
    assert a.pvalue == b.pvalue
    assert a.details["permutation_sd"] == b.details["permutation_sd"]
    assert a.details["permutation_sd"] != c.details["permutation_sd"]


def test_permutation_test_never_returns_a_zero_pvalue():
    x = np.concatenate([np.zeros(50), np.ones(50)])
    groups = np.array(["a"] * 50 + ["b"] * 50)
    result = permutation_test(x, groups, np.mean, n_perm=99, seed=1)
    assert result.pvalue == pytest.approx(1.0 / 100.0)


def test_permutation_test_drops_nonfinite_values():
    x = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0])
    groups = np.array(["a", "a", "a", "b", "b", "b"])
    result = permutation_test(x, groups, np.mean, n_perm=49, seed=1)
    assert result.n == 5
    assert result.details["n_dropped"] == 1
    assert result.details["group_sizes"] == {"a": 2, "b": 3}


@pytest.mark.parametrize(
    ("x", "groups", "n_perm", "match"),
    [
        ([1.0, 2.0, 3.0], ["a", "b"], 99, "same length"),
        ([1.0, 2.0, 3.0], ["a", "a", "a"], 99, "at least two distinct groups"),
        ([1.0, 2.0, 3.0], ["a", "a", "b"], 0, "n_perm"),
        ([np.nan, np.nan], ["a", "b"], 99, "no finite values"),
    ],
)
def test_permutation_test_rejects_bad_arguments(x, groups, n_perm, match):
    with pytest.raises(ValueError, match=match):
        permutation_test(x, groups, np.mean, n_perm=n_perm, seed=1)


def test_permutation_test_requires_a_callable_statistic():
    with pytest.raises(ValueError, match="statistic must be callable"):
        permutation_test([1.0, 2.0], ["a", "b"], "mean", n_perm=9, seed=1)  # type: ignore[arg-type]

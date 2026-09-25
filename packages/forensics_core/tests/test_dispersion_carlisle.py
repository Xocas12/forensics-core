"""Tests for forensics_core.dispersion.carlisle.

Synthetic data only: every "trial" here is drawn from a seeded numpy Generator inside the
test, with obviously artificial values (HARD RULE 3). Nothing resembles a real trial and
nothing is read from disk or the network.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from forensics_core.dispersion import (
    CarlisleResult,
    balance_pvalues,
    carlisle_test,
    combine_pvalues,
)

# --------------------------------------------------------------------------------------
# helpers


def _summarise(groups: list[np.ndarray]) -> tuple[list[float], list[float], list[int]]:
    """Means / SDs / sizes, i.e. exactly what a published baseline table reports."""
    return (
        [float(g.mean()) for g in groups],
        [float(g.std(ddof=1)) for g in groups],
        [int(g.size) for g in groups],
    )


def _honest_trial(
    seed: int, n_variables: int = 30, n_groups: int = 3, n_per_group: int = 20
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A genuinely randomised synthetic baseline table: every group is drawn from N(50, 10)."""
    rng = np.random.default_rng(seed)
    means = np.empty((n_variables, n_groups))
    sds = np.empty((n_variables, n_groups))
    for i in range(n_variables):
        for j in range(n_groups):
            draw = rng.normal(50.0, 10.0, size=n_per_group)
            means[i, j] = draw.mean()
            sds[i, j] = draw.std(ddof=1)
    return means, sds, np.full(n_groups, n_per_group)


# --------------------------------------------------------------------------------------
# balance_pvalues


def test_balance_pvalues_matches_f_oneway_on_the_underlying_data() -> None:
    rng = np.random.default_rng(4242)
    groups = [rng.normal(10.0, 3.0, 25), rng.normal(10.0, 3.0, 30), rng.normal(11.0, 3.0, 20)]
    means, sds, ns = _summarise(groups)
    assert balance_pvalues(means, sds, ns) == pytest.approx(
        float(stats.f_oneway(*groups).pvalue), rel=1e-12
    )


def test_balance_pvalues_two_groups_equals_the_pooled_t_test() -> None:
    rng = np.random.default_rng(99)
    groups = [rng.normal(0.0, 1.0, 18), rng.normal(0.4, 1.0, 22)]
    means, sds, ns = _summarise(groups)
    assert balance_pvalues(means, sds, ns) == pytest.approx(
        float(stats.ttest_ind(groups[0], groups[1], equal_var=True).pvalue), rel=1e-12
    )


def test_balance_pvalues_hand_computed() -> None:
    # means 1, 2, 3; sds all 1; ns all 10.
    # grand mean 2, SSB = 10*(1+0+1) = 20 on 2 df; SSW = 9*1*3 = 27 on 27 df; F = 10/1 = 10.
    p = balance_pvalues([1.0, 2.0, 3.0], [1.0, 1.0, 1.0], [10, 10, 10])
    assert p == pytest.approx(float(stats.f.sf(10.0, 2, 27)))


def test_balance_pvalues_is_one_for_perfectly_equal_means() -> None:
    assert balance_pvalues([5.0, 5.0, 5.0], [2.0, 2.0, 2.0], [10, 10, 10]) == 1.0
    # degenerate reported data: zero SDs everywhere
    assert balance_pvalues([5.0, 5.0], [0.0, 0.0], [10, 10]) == 1.0
    assert balance_pvalues([5.0, 6.0], [0.0, 0.0], [10, 10]) == 0.0


def test_balance_pvalues_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="same length"):
        balance_pvalues([1.0, 2.0], [1.0], [10, 10])
    with pytest.raises(ValueError, match="at least 2 groups"):
        balance_pvalues([1.0], [1.0], [10])
    with pytest.raises(ValueError, match="finite"):
        balance_pvalues([1.0, np.nan], [1.0, 1.0], [10, 10])
    with pytest.raises(ValueError, match="non-negative"):
        balance_pvalues([1.0, 2.0], [1.0, -1.0], [10, 10])
    with pytest.raises(ValueError, match="whole numbers"):
        balance_pvalues([1.0, 2.0], [1.0, 1.0], [10, 10.5])
    with pytest.raises(ValueError, match="at least 2 observations"):
        balance_pvalues([1.0, 2.0], [1.0, 1.0], [10, 1])


# --------------------------------------------------------------------------------------
# combine_pvalues


def test_combine_pvalues_stouffer_hand_computed() -> None:
    res = combine_pvalues([0.5, 0.5, 0.5])
    assert res.statistic == pytest.approx(0.0)
    assert res.pvalue == pytest.approx(0.5)
    assert res.details["alternative"] == "greater"

    # four p-values of 0.975: z_i = Phi^-1(0.025) = -1.959964, z = 4*z_i/2 = 2*z_i.
    res = combine_pvalues([0.975] * 4)
    assert res.statistic == pytest.approx(-2.0 * float(stats.norm.ppf(0.025)))
    assert res.pvalue == pytest.approx(float(stats.norm.sf(res.statistic)))
    assert res.pvalue < 1e-4
    assert res.n == 4


def test_combine_pvalues_sign_convention() -> None:
    """Large statistic = too balanced; p-values near 0 push the statistic negative."""
    too_balanced = combine_pvalues([0.9, 0.95, 0.99, 0.92, 0.97])
    too_different = combine_pvalues([0.1, 0.05, 0.01, 0.08, 0.03])
    assert too_balanced.statistic > 0
    assert too_balanced.pvalue < 0.01
    assert too_different.statistic < 0
    assert too_different.pvalue > 0.99
    assert too_balanced.statistic == pytest.approx(-too_different.statistic, rel=0.35)


def test_combine_pvalues_fisher_uses_the_complements() -> None:
    p = [0.9, 0.95, 0.99, 0.92, 0.97]
    res = combine_pvalues(p, "fisher")
    expected = -2.0 * float(np.sum(np.log1p(-np.asarray(p))))
    assert res.statistic == pytest.approx(expected)
    assert res.pvalue == pytest.approx(float(stats.chi2.sf(expected, 2 * len(p))))
    assert res.pvalue < 0.01
    assert res.details["df"] == 10
    # the conventional lower-tail Fisher statistic is kept for reference
    assert res.details["fisher_lower_tail_statistic"] == pytest.approx(
        float(stats.combine_pvalues(p, method="fisher").statistic)
    )


def test_combine_pvalues_is_calibrated_under_uniform_pvalues() -> None:
    rng = np.random.default_rng(2026)
    for method in ("stouffer", "fisher"):
        combined = [combine_pvalues(rng.uniform(size=25), method).pvalue for _ in range(500)]
        assert np.mean(combined) == pytest.approx(0.5, abs=0.05)
        assert np.mean(np.asarray(combined) < 0.05) == pytest.approx(0.05, abs=0.035)


def test_combine_pvalues_clips_and_reports_it() -> None:
    res = combine_pvalues([1.0, 1.0, 1.0])
    assert res.details["n_clipped"] == 3
    assert np.isfinite(res.statistic)
    assert res.statistic == pytest.approx(np.sqrt(3) * float(stats.norm.ppf(1 - 1e-12)))
    assert combine_pvalues([0.4, 0.6]).details["n_clipped"] == 0


def test_combine_pvalues_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="at least one p-value"):
        combine_pvalues([])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        combine_pvalues([0.5, 1.5])
    with pytest.raises(ValueError, match="finite"):
        combine_pvalues([0.5, np.nan])
    with pytest.raises(ValueError, match="clip"):
        combine_pvalues([0.5, 0.5], clip=0.0)
    with pytest.raises(ValueError, match="stouffer"):
        combine_pvalues([0.5, 0.5], "lancaster")  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# carlisle_test


def test_carlisle_does_not_reject_a_genuinely_randomised_table() -> None:
    means, sds, ns = _honest_trial(seed=11)
    res = carlisle_test(means, sds, ns)

    assert isinstance(res, CarlisleResult)
    assert res.per_variable.shape == (30,)
    assert np.all((res.per_variable >= 0) & (res.per_variable <= 1))
    assert res.combined.pvalue > 0.05
    assert res.ks_uniformity.pvalue > 0.05
    assert res.combined.details["mean_pvalue"] == pytest.approx(0.5, abs=0.2)
    assert res.combined.details["n_variables"] == 30
    assert res.combined.details["n_groups"] == 3
    assert res.combined.details["n_dropped"] == 0
    assert res.to_dict()["combined"]["method"] == "combine_pvalues_stouffer"


def test_carlisle_does_not_reject_across_many_honest_tables() -> None:
    """Calibration rather than a single lucky seed: the false-positive rate must be small."""
    rejects = [carlisle_test(*_honest_trial(seed)).combined.pvalue < 0.05 for seed in range(40)]
    assert sum(rejects) <= 4


def test_carlisle_detects_identical_means_with_small_sds() -> None:
    """The textbook fabrication: every group mean identical, so every p-value is exactly 1."""
    means = np.full((30, 3), 50.0)
    sds = np.full((30, 3), 10.0)
    res = carlisle_test(means, sds, np.full(3, 20))

    assert np.all(res.per_variable == 1.0)
    assert res.combined.statistic > 30
    assert res.combined.pvalue < 1e-12
    assert res.ks_uniformity.pvalue < 1e-12
    assert res.combined.details["n_clipped"] == 30  # the statistic is a clip-bounded floor
    assert res.combined.details["share_pvalue_above_0p9"] == 1.0


def test_carlisle_detects_realistically_too_balanced_groups() -> None:
    """Means jittered at 5% of the standard error: p-values pile near 1 without touching it."""
    rng = np.random.default_rng(7)
    standard_error = 10.0 / np.sqrt(20)
    means = 50.0 + rng.normal(scale=0.05 * standard_error, size=(30, 3))
    sds = np.full((30, 3), 10.0)
    res = carlisle_test(means, sds, np.full(3, 20))

    assert res.per_variable.min() > 0.9
    assert res.combined.details["n_clipped"] == 0
    assert res.combined.statistic > 5
    assert res.combined.pvalue < 1e-10
    assert res.ks_uniformity.statistic > 0.8
    assert res.ks_uniformity.pvalue < 1e-10


def test_carlisle_fisher_agrees_with_stouffer_on_direction() -> None:
    rng = np.random.default_rng(7)
    means = 50.0 + rng.normal(scale=0.05 * 10.0 / np.sqrt(20), size=(30, 3))
    sds = np.full((30, 3), 10.0)
    fabricated = carlisle_test(means, sds, np.full(3, 20), method="fisher")
    honest = carlisle_test(*_honest_trial(seed=11), method="fisher")
    assert fabricated.combined.method == "combine_pvalues_fisher"
    assert fabricated.combined.pvalue < 1e-10
    assert honest.combined.pvalue > 0.05
    assert fabricated.combined.statistic > honest.combined.statistic


def test_carlisle_per_variable_matches_balance_pvalues_row_by_row() -> None:
    means, sds, ns = _honest_trial(seed=3, n_variables=5)
    res = carlisle_test(means, sds, ns)
    for i in range(5):
        assert res.per_variable[i] == pytest.approx(balance_pvalues(means[i], sds[i], ns))


def test_carlisle_accepts_a_full_ns_matrix_and_a_single_variable() -> None:
    means, sds, ns = _honest_trial(seed=5, n_variables=4)
    full = np.tile(ns, (4, 1))
    assert carlisle_test(means, sds, full).per_variable == pytest.approx(
        carlisle_test(means, sds, ns).per_variable
    )
    one = carlisle_test(means[0], sds[0], ns)
    assert one.per_variable.shape == (1,)
    assert one.per_variable[0] == pytest.approx(balance_pvalues(means[0], sds[0], ns))


def test_carlisle_drops_variables_with_non_finite_summary_statistics() -> None:
    means, sds, ns = _honest_trial(seed=13, n_variables=10)
    means = means.copy()
    means[2, 1] = np.nan
    sds = sds.copy()
    sds[7, 0] = np.inf
    res = carlisle_test(means, sds, ns)
    assert res.per_variable.size == 8
    assert res.combined.details["n_dropped"] == 2
    assert res.combined.n == 8


def test_carlisle_rejects_bad_input() -> None:
    means, sds, ns = _honest_trial(seed=17, n_variables=4)
    with pytest.raises(ValueError, match="same shape as means"):
        carlisle_test(means, sds[:2], ns)
    with pytest.raises(ValueError, match="ns must have shape"):
        carlisle_test(means, sds, np.full(2, 20))
    with pytest.raises(ValueError, match="at least 2 groups"):
        carlisle_test(means[:, :1], sds[:, :1], ns[:1])
    with pytest.raises(ValueError, match="non-finite"):
        carlisle_test(np.full((3, 3), np.nan), np.ones((3, 3)), np.full(3, 20))
    with pytest.raises(ValueError, match="stouffer"):
        carlisle_test(means, sds, ns, method="tippett")  # type: ignore[arg-type]

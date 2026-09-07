"""Tests for forensics_core.dispersion.underdispersion.

Synthetic data only: everything is generated in the test from a seeded Generator or written
out by hand (HARD RULE 3). No network, no file I/O.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from forensics_core.dispersion import (
    dispersion_index,
    implied_variance_floor,
    residual_underdispersion,
    rolling_variance_floor,
    smoothness_ratio,
    too_smooth_test,
    variance_floor_test,
)

# --------------------------------------------------------------------------------------
# helpers


def _ar1(n: int, rho: float, scale: float, rng: np.random.Generator) -> np.ndarray:
    """Synthetic AR(1) path: smooth deviations, the shape a fabricated series tends to have."""
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = rho * e[i - 1] + rng.normal(scale=scale)
    return e


# --------------------------------------------------------------------------------------
# dispersion_index


def test_dispersion_index_hand_computed() -> None:
    # x = [2,4,4,4,5,5,7,9]: mean 5, sum of squared deviations 32.
    x = [2, 4, 4, 4, 5, 5, 7, 9]
    assert dispersion_index(x) == pytest.approx((32 / 7) / 5)
    assert dispersion_index(x, ddof=0) == pytest.approx((32 / 8) / 5)


def test_dispersion_index_detects_under_and_over_dispersion(rng: np.random.Generator) -> None:
    poisson = rng.poisson(20.0, size=5000).astype(float)
    binomial = rng.binomial(40, 0.5, size=5000).astype(float)  # variance = 0.5 * mean
    assert dispersion_index(poisson) == pytest.approx(1.0, abs=0.06)
    assert dispersion_index(binomial) == pytest.approx(0.5, abs=0.04)


def test_dispersion_index_drops_nonfinite() -> None:
    assert dispersion_index([2, 4, np.nan, 4, 4, 5, 5, 7, 9, np.inf]) == pytest.approx((32 / 7) / 5)


def test_dispersion_index_rejects_zero_mean_and_short_input() -> None:
    with pytest.raises(ValueError, match="mean exactly zero"):
        dispersion_index([-1.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="more than ddof"):
        dispersion_index([3.0])


# --------------------------------------------------------------------------------------
# variance_floor_test


def test_variance_floor_statistic_matches_hand_computation() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])  # s2 = 2.5 with ddof=1
    res = variance_floor_test(x, floor_variance=10.0)
    assert res.details["s2"] == pytest.approx(2.5)
    assert res.statistic == pytest.approx(4 * 2.5 / 10.0)
    assert res.pvalue == pytest.approx(float(stats.chi2.cdf(1.0, 4)))
    # "floor" is the key fixed by INTERFACES.md; "floor_variance" is the alias.
    assert res.details["floor"] == 10.0
    assert res.details["floor_variance"] == 10.0
    assert res.details["ratio"] == pytest.approx(0.25)
    assert res.details["df"] == 4
    assert res.details["ddof"] == 1
    assert res.details["alternative"] == "less"
    assert res.details["n_dropped"] == 0
    assert res.n == 5
    assert res.method == "variance_floor_chi2"
    assert res.to_dict()["method"] == "variance_floor_chi2"


def test_variance_floor_contract_details_keys_are_present() -> None:
    """INTERFACES.md fixes details: s2, floor, ratio -- downstream code indexes those names."""
    res = variance_floor_test([1.0, 2.0, 3.0, 4.0, 5.0], 10.0)
    assert {"s2", "floor", "ratio"} <= set(res.details)
    assert res.details["floor"] == res.details["floor_variance"]
    # ...and they survive the wrappers that re-emit them.
    resid = residual_underdispersion([1.0, 2.0, 3.0, 4.0, 5.0], np.zeros(5), 10.0)
    assert resid.details["floor"] == 10.0
    table = rolling_variance_floor([1.0, 2.0, 3.0, 4.0, 5.0], 10.0, window=4)
    assert table["s2"].notna().all()


def test_variance_floor_rejects_at_a_tenth_of_the_floor_and_not_at_twice(
    rng: np.random.Generator,
) -> None:
    floor = 4.0
    thin = rng.normal(scale=np.sqrt(0.1 * floor), size=80)
    fat = rng.normal(scale=np.sqrt(2.0 * floor), size=80)
    thin_res = variance_floor_test(thin, floor)
    fat_res = variance_floor_test(fat, floor)
    assert thin_res.pvalue < 1e-6
    assert thin_res.details["ratio"] == pytest.approx(0.1, rel=0.4)
    assert fat_res.pvalue > 0.5
    assert fat_res.details["ratio"] > 1.0


def test_variance_floor_pvalue_is_uniform_at_the_floor(rng: np.random.Generator) -> None:
    # calibration: exactly at the floor the lower-tail p-value must be ~U(0,1).
    floor = 2.25
    pvals = [variance_floor_test(rng.normal(scale=1.5, size=40), floor).pvalue for _ in range(400)]
    assert np.mean(pvals) == pytest.approx(0.5, abs=0.06)
    assert np.mean(np.asarray(pvals) < 0.05) == pytest.approx(0.05, abs=0.04)


def test_variance_floor_is_calibrated_with_a_fitted_trend_removed(
    rng: np.random.Generator,
) -> None:
    """ddof = 1 + k is the surviving branch: two parameters fitted, so df = n - 2.

    Residuals from an OLS line have variance ``sigma^2 (n - 2) / n``, so the *only* ddof that
    both centres the p-value and keeps the reference distribution right is 2. This is the
    calibration the rejected ``ddof = 0`` branch failed (it referred a chi2(n-1) numerator to
    chi2(n) and rejected at 0.071 for a nominal 0.05).
    """
    n = 25
    t = np.arange(float(n))
    design = np.column_stack([np.ones(n), t - t.mean()])
    sigma2 = 4.0
    pvals = []
    for _ in range(400):
        y = 3.0 - 0.7 * t + rng.normal(scale=np.sqrt(sigma2), size=n)
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        pvals.append(residual_underdispersion(y, design @ coef, sigma2, ddof=2).pvalue)
    pvals = np.asarray(pvals)
    assert pvals.mean() == pytest.approx(0.5, abs=0.06)
    assert (pvals < 0.05).mean() == pytest.approx(0.05, abs=0.035)


def test_variance_floor_counts_dropped_values() -> None:
    res = variance_floor_test([1.0, 2.0, np.nan, 3.0, 4.0, 5.0, np.inf], 10.0)
    assert res.n == 5
    assert res.details["n_dropped"] == 2


def test_variance_floor_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="floor_variance"):
        variance_floor_test([1.0, 2.0, 3.0], 0.0)
    with pytest.raises(ValueError, match="floor_variance"):
        variance_floor_test([1.0, 2.0, 3.0], -1.0)
    with pytest.raises(ValueError, match="floor_variance"):
        variance_floor_test([1.0, 2.0, 3.0], np.nan)
    with pytest.raises(ValueError, match="ddof must be"):
        variance_floor_test([1.0, 2.0, 3.0], 1.0, ddof=-1)
    with pytest.raises(ValueError, match="ddof must be >= 1"):
        variance_floor_test([1.0, 2.0, 3.0], 1.0, ddof=0)
    with pytest.raises(ValueError, match="at least ddof"):
        variance_floor_test([1.0], 1.0)
    with pytest.raises(ValueError, match="must be 1-D"):
        variance_floor_test(np.ones((3, 3)), 1.0)


# --------------------------------------------------------------------------------------
# implied_variance_floor


def test_implied_variance_floor_is_exactly_beta_squared_times_variance() -> None:
    proxy = [1.0, 2.0, 3.0, 4.0]  # sample variance 5/3
    assert implied_variance_floor(proxy, 3.0) == 15.0  # 9 * 5/3, exact in binary floating point
    assert implied_variance_floor(proxy, -3.0) == 15.0  # sign of the response is irrelevant


def test_implied_variance_floor_matches_numpy_var_exactly(rng: np.random.Generator) -> None:
    proxy = rng.normal(100.0, 15.0, size=64)
    beta = 2.5
    assert implied_variance_floor(proxy, beta) == beta**2 * np.var(proxy, ddof=1)
    assert implied_variance_floor(proxy, beta, ddof=0) == beta**2 * np.var(proxy, ddof=0)


def test_implied_variance_floor_recovers_an_injected_response(rng: np.random.Generator) -> None:
    # y = beta * proxy + independent noise: Var(y) must sit above the floor, and a smoothed
    # y (the fabrication) must sit below it.
    proxy = rng.normal(0.0, 2.0, size=300)
    beta = 1.5
    y = beta * proxy + rng.normal(0.0, 1.0, size=300)
    floor = implied_variance_floor(proxy, beta)
    assert np.var(y, ddof=1) > floor
    assert variance_floor_test(y, floor).pvalue > 0.05
    smoothed = 0.2 * y  # the reporter shaved the swings off
    assert variance_floor_test(smoothed, floor).pvalue < 1e-9


def test_implied_variance_floor_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="elasticity"):
        implied_variance_floor([1.0, 2.0], np.nan)
    with pytest.raises(ValueError, match="more than ddof"):
        implied_variance_floor([1.0], 2.0)


# --------------------------------------------------------------------------------------
# residual_underdispersion


def test_residual_underdispersion_flags_a_flattened_residual(rng: np.random.Generator) -> None:
    t = np.arange(60.0)
    fitted = 100.0 + 2.0 * t
    floor = 9.0
    honest = fitted + rng.normal(scale=np.sqrt(floor) * 1.2, size=60)
    faked = fitted + rng.normal(scale=np.sqrt(floor) * 0.2, size=60)
    assert residual_underdispersion(honest, fitted, floor).pvalue > 0.05
    faked_res = residual_underdispersion(faked, fitted, floor)
    assert faked_res.pvalue < 1e-8
    assert faked_res.method == "residual_underdispersion"
    assert faked_res.details["ratio"] < 0.1
    assert faked_res.details["mean_residual"] == pytest.approx(np.mean(faked - fitted))


def test_residual_underdispersion_matches_the_test_on_precomputed_residuals(
    rng: np.random.Generator,
) -> None:
    series = rng.normal(size=30)
    fitted = rng.normal(size=30)
    direct = variance_floor_test(series - fitted, 1.0, ddof=2)
    via = residual_underdispersion(series, fitted, 1.0, ddof=2)
    assert via.statistic == pytest.approx(direct.statistic)
    assert via.pvalue == pytest.approx(direct.pvalue)


def test_residual_underdispersion_drops_pairwise_and_validates_length() -> None:
    series = [1.0, 2.0, np.nan, 4.0, 5.0, 6.0]
    fitted = [0.0, 0.0, 0.0, np.inf, 0.0, 0.0]
    res = residual_underdispersion(series, fitted, 1.0)
    assert res.n == 4
    assert res.details["n_dropped"] == 2
    with pytest.raises(ValueError, match="same length"):
        residual_underdispersion([1.0, 2.0, 3.0], [1.0, 2.0], 1.0)


# --------------------------------------------------------------------------------------
# smoothness_ratio


def test_smoothness_ratio_hand_computed() -> None:
    # [1,2,3,4]: MSSD = (1+1+1)/3 = 1, s2 = 5/3, ratio = 0.6.
    assert smoothness_ratio([1.0, 2.0, 3.0, 4.0]) == pytest.approx(0.6)
    # alternating series: MSSD = (4+4+4)/3 = 4, s2 = 4/3, ratio = 3.
    assert smoothness_ratio([1.0, -1.0, 1.0, -1.0]) == pytest.approx(3.0)


def test_smoothness_ratio_is_two_for_iid_noise(rng: np.random.Generator) -> None:
    assert smoothness_ratio(rng.normal(size=20_000)) == pytest.approx(2.0, abs=0.05)


def test_smoothness_ratio_is_scale_and_shift_invariant(rng: np.random.Generator) -> None:
    x = rng.normal(size=200)
    assert smoothness_ratio(7.5 * x + 1000.0) == pytest.approx(smoothness_ratio(x))


def test_smoothness_ratio_falls_with_serial_correlation(rng: np.random.Generator) -> None:
    smooth = _ar1(4000, rho=0.95, scale=1.0, rng=rng)
    # eta = 2(1 - rho) to first order: rho = 0.95 -> about 0.1.
    assert smoothness_ratio(smooth) == pytest.approx(2 * (1 - 0.95), abs=0.05)


def test_smoothness_ratio_rejects_degenerate_input() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        smoothness_ratio([1.0, 2.0])
    with pytest.raises(ValueError, match="constant series"):
        smoothness_ratio([4.0, 4.0, 4.0, 4.0])


def test_smoothness_ratio_rejects_variation_below_machine_precision() -> None:
    """Constant "to within floating-point precision" is relative, not absolute.

    Values of order 1e6 are represented to about 1e-10, so a spread of 1e-9 around 1e6 is
    rounding error; computing a ratio from it would report noise as a finding.
    """
    base = 1e6
    with pytest.raises(ValueError, match="constant series"):
        smoothness_ratio([base, base + 1e-9, base, base - 1e-9, base])
    # the same *absolute* spread around 1 is perfectly real data and is not rejected
    assert smoothness_ratio([1.0, 1.0 + 1e-9, 1.0, 1.0 - 1e-9, 1.0]) == pytest.approx(2.0)


# --------------------------------------------------------------------------------------
# too_smooth_test


def test_too_smooth_diff_flags_a_smoothly_accelerating_series(rng: np.random.Generator) -> None:
    """detrend='diff': the fabricated path's *changes* drift; the honest one's do not."""
    t = np.arange(120.0)
    honest = 5.0 + 0.3 * t + rng.normal(scale=2.0, size=120)
    faked = 5.0 + 0.3 * t + 0.02 * t**2 + rng.normal(scale=0.05, size=120)

    honest_res = too_smooth_test(honest, detrend="diff", seed=11)
    faked_res = too_smooth_test(faked, detrend="diff", seed=11)

    # Differencing "trend + iid noise" gives an MA(1) with rho1 = -1/2, hence eta near 3.
    assert honest_res.statistic == pytest.approx(3.0, abs=0.4)
    assert honest_res.pvalue > 0.10
    assert faked_res.statistic < 0.2
    assert faked_res.pvalue == pytest.approx(1 / 1000)
    assert faked_res.details["alternative"] == "less"
    assert faked_res.details["null_mean"] == pytest.approx(2.0, abs=0.1)
    assert faked_res.n == 120
    assert faked_res.details["n_analysed"] == 119


def test_too_smooth_linear_flags_correlated_deviations_around_a_trend(
    rng: np.random.Generator,
) -> None:
    t = np.arange(150.0)
    honest = 10.0 + 0.5 * t + rng.normal(scale=1.0, size=150)
    faked = 10.0 + 0.5 * t + _ar1(150, rho=0.92, scale=0.4, rng=rng)
    assert too_smooth_test(honest, detrend="linear", seed=3).pvalue > 0.10
    faked_res = too_smooth_test(faked, detrend="linear", seed=3)
    assert faked_res.pvalue < 0.01
    assert faked_res.statistic < 1.0
    assert faked_res.details["implied_lag1_autocorr"] > 0.5


def test_too_smooth_none_flags_a_trend_with_tiny_noise(rng: np.random.Generator) -> None:
    """detrend='none' analyses levels, so any trend is "too smooth" -- see the docstring."""
    t = np.arange(120.0)
    trend_plus_tiny_noise = 5.0 + 0.3 * t + rng.normal(scale=0.01, size=120)
    stationary = rng.normal(scale=3.0, size=120)
    assert too_smooth_test(trend_plus_tiny_noise, detrend="none", seed=5).pvalue < 0.01
    assert too_smooth_test(stationary, detrend="none", seed=5).pvalue > 0.10


def test_too_smooth_is_calibrated_under_the_null(rng: np.random.Generator) -> None:
    pvals = [
        too_smooth_test(rng.normal(size=50), detrend="none", n_perm=199, seed=i).pvalue
        for i in range(200)
    ]
    assert np.mean(pvals) == pytest.approx(0.5, abs=0.08)
    assert np.mean(np.asarray(pvals) < 0.05) < 0.12


def test_too_smooth_is_deterministic_given_a_seed(rng: np.random.Generator) -> None:
    x = _ar1(80, rho=0.8, scale=1.0, rng=rng)
    first = too_smooth_test(x, detrend="none", seed=99)
    second = too_smooth_test(x, detrend="none", seed=99)
    assert first.pvalue == second.pvalue
    assert first.statistic == second.statistic
    assert first.details["null_mean"] == second.details["null_mean"]


def test_too_smooth_seed_changes_the_null_but_not_the_statistic(rng: np.random.Generator) -> None:
    """A different seed must actually redraw the permutation null.

    The observed statistic is seed-free by construction, so only the null can catch an
    implementation that ignored ``seed``.
    """
    x = _ar1(80, rho=0.8, scale=1.0, rng=rng)
    a = too_smooth_test(x, detrend="none", n_perm=499, seed=99)
    b = too_smooth_test(x, detrend="none", n_perm=499, seed=100)
    assert a.statistic == b.statistic
    assert a.details["null_mean"] != b.details["null_mean"]
    assert a.details["null_q05"] != b.details["null_q05"]


def test_too_smooth_statistic_equals_smoothness_ratio_of_the_analysed_values(
    rng: np.random.Generator,
) -> None:
    x = rng.normal(size=60)
    assert too_smooth_test(x, detrend="none", n_perm=9, seed=1).statistic == pytest.approx(
        smoothness_ratio(x)
    )
    assert too_smooth_test(x, detrend="diff", n_perm=9, seed=1).statistic == pytest.approx(
        smoothness_ratio(np.diff(x))
    )


def test_too_smooth_reports_what_it_analysed(rng: np.random.Generator) -> None:
    x = rng.normal(size=40)
    assert too_smooth_test(x, detrend="none", n_perm=9, seed=1).details["analysed"] == "levels"
    assert (
        too_smooth_test(x, detrend="diff", n_perm=9, seed=1).details["analysed"]
        == "first differences"
    )
    assert (
        too_smooth_test(x, detrend="linear", n_perm=9, seed=1).details["analysed"]
        == "linear-trend residuals"
    )


@pytest.mark.parametrize("intercept", [0.0, 100.0, 12345.678])
@pytest.mark.parametrize("slope", [1.0, 0.3, 7.0])
def test_too_smooth_linear_refuses_an_exactly_linear_series(slope: float, intercept: float) -> None:
    """The detrended residuals of an exact line are rounding error, not data.

    Without a *relative* tolerance the residual standard deviation (here 1e-16 to 1e-12,
    depending on the arithmetic) is happily fed to the ratio and a p-value near 0.001 comes
    back out of pure floating-point noise -- arbitrary, and different for each intercept.
    """
    x = intercept + slope * np.arange(40.0)
    with pytest.raises(ValueError, match="constant series"):
        too_smooth_test(x, detrend="linear", seed=4)
    # detrend="none" analyses the levels, which are genuinely spread out: no error, and the
    # perfectly monotone path is flagged as too smooth (that is what "none" is for).
    res = too_smooth_test(x, detrend="none", seed=4)
    assert res.statistic < 0.02
    assert res.pvalue == pytest.approx(1 / 1000)


def test_too_smooth_relative_guard_does_not_fire_on_genuinely_small_noise(
    rng: np.random.Generator,
) -> None:
    """The guard is at machine precision, so real (even tiny) noise still gets tested."""
    x = 12345.678 + 7.0 * np.arange(40.0) + rng.normal(scale=1e-6, size=40)
    res = too_smooth_test(x, detrend="linear", n_perm=199, seed=4)
    assert res.pvalue > 0.05  # iid deviations around the line: nothing to flag
    assert res.statistic == pytest.approx(2.0, abs=0.7)


def test_too_smooth_rejects_bad_input() -> None:
    x = np.arange(10.0) + np.sin(np.arange(10.0))
    with pytest.raises(ValueError, match="detrend must be one of"):
        too_smooth_test(x, detrend="quadratic")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="n_perm must be >= 2"):
        too_smooth_test(x, n_perm=0)
    with pytest.raises(ValueError, match="n_perm must be >= 2"):
        too_smooth_test(x, n_perm=1)
    with pytest.raises(ValueError, match="at least 3 analysable"):
        too_smooth_test([1.0, 2.0, 4.0], detrend="diff")
    with pytest.raises(ValueError, match="constant series"):
        too_smooth_test([1.0, 2.0, 3.0, 4.0, 5.0], detrend="diff")


def test_too_smooth_n_perm_two_is_usable_and_warning_free() -> None:
    """The smallest accepted null still has a finite spread -- no numpy RuntimeWarning."""
    x = np.array([1.0, 5.0, 2.0, 9.0, 3.0, 7.0, 4.0, 8.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        res = too_smooth_test(x, detrend="none", n_perm=2, seed=0)
    assert np.isfinite(res.details["null_sd"])
    assert res.pvalue in (1 / 3, 2 / 3, 1.0)


# --------------------------------------------------------------------------------------
# rolling_variance_floor


def test_rolling_variance_floor_isolates_the_flat_stretch(rng: np.random.Generator) -> None:
    floor = 1.0
    series = rng.normal(scale=2.0, size=60)
    series[20:35] = rng.normal(scale=0.05, size=15)  # a fabricated stretch
    table = rolling_variance_floor(series, floor, window=10)

    assert list(table.columns) == [
        "start",
        "end",
        "n",
        "s2",
        "statistic",
        "pvalue",
        "flag",
        "n_dropped",
    ]
    assert len(table) == 60 - 10 + 1
    assert isinstance(table, pd.DataFrame)

    starts = table["start"].to_numpy()
    ends = table["end"].to_numpy()
    flags = table["flag"].to_numpy()
    inside = (starts >= 20) & (ends <= 34)  # window entirely within the fabricated stretch
    outside = (ends < 20) | (starts > 34)  # window entirely outside it
    assert flags[inside].all()
    assert not flags[outside].any()
    assert table.loc[table["start"] == 25, "pvalue"].to_numpy()[0] < 1e-8
    assert table.loc[table["start"] == 0, "pvalue"].to_numpy()[0] > 0.05


def test_rolling_variance_floor_rows_match_the_single_window_test(
    rng: np.random.Generator,
) -> None:
    series = rng.normal(size=25)
    table = rolling_variance_floor(series, 1.0, window=8)
    row = table.iloc[3]
    direct = variance_floor_test(series[3:11], 1.0)
    assert row["s2"] == pytest.approx(direct.details["s2"])
    assert row["statistic"] == pytest.approx(direct.statistic)
    assert row["pvalue"] == pytest.approx(direct.pvalue)
    assert row["start"] == 3
    assert row["end"] == 10
    assert row["n"] == 8


def test_rolling_variance_floor_rejects_bad_window(rng: np.random.Generator) -> None:
    series = rng.normal(size=10)
    with pytest.raises(ValueError, match="window must be greater than ddof"):
        rolling_variance_floor(series, 1.0, window=1)
    with pytest.raises(ValueError, match="exceeds the number of finite observations"):
        rolling_variance_floor(series, 1.0, window=11)
    with pytest.raises(ValueError, match="alpha"):
        rolling_variance_floor(series, 1.0, window=5, alpha=0.0)

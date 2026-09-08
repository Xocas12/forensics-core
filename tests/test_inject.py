"""Tests for forensics_core.inject.

All data here is synthetic and generated in this file (HARD RULE 3): honest binomial
numerators, a lognormal running variable, a flat level series and a trend-plus-noise
series. Nothing touches the network or the filesystem, and nothing is written anywhere:
the injectors work in memory and so do these tests.

The four properties the card fixes are tested per injector: no-op at effect size zero,
monotone in its effect size under the matching estimator, preserving the totals its
docstring claims, reproducible from its seed. A fifth test per injector runs a deliberately
mis-specified estimator and checks it still recovers a reduced but nonzero effect, which is
the only outside check that the injector is not the estimator run backwards.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from forensics_core.bunching.density import bunching_estimator
from forensics_core.digits.integer_pct import integer_excess
from forensics_core.dispersion.underdispersion import smoothness_ratio, variance_floor_test
from forensics_core.inject import (
    InjectionRecord,
    inject_bunching,
    inject_padding,
    inject_rounding,
    inject_smoothing,
)

THRESHOLD = 100.0
WINDOW = 2.0
# the matching analysis for a window=2 injection: one bin of width 2 on each side, so the
# dominated-side pool is one bin's worth of units and a recovered b is comparable with mass
BUNCHING_ESTIMATOR_KW = {
    "bin_width": WINDOW,
    "exclude_below": WINDOW,
    "exclude_above": WINDOW,
    "lo": 60.0,
    "hi": 160.0,
    "bunching_side": "above",
}


def clean_binomial_numerators(seed: int, n: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    """Honest numerators and denominators; denominators are multiples of 100.

    With ``d = 100 k`` an integer percentage occurs exactly when ``k`` divides the
    numerator, so the units that are already on an integer can be counted exactly, with no
    floating-point edge cases, in the mechanism test below.
    """
    rng = np.random.default_rng(seed)
    d = 100.0 * rng.integers(3, 21, size=n)
    p = rng.uniform(0.3, 0.7, size=n)
    v = rng.binomial(d.astype(np.int64), p).astype(float)
    return v, d


def already_integer_units(v: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Positions whose percentage is already exactly an integer (``d`` a multiple of 100)."""
    k = d / 100.0
    return np.flatnonzero(v % k == 0)


def lognormal_running_variable(seed: int, n: int = 20_000) -> np.ndarray:
    """Smooth lognormal density centred on the threshold: no bunching to begin with."""
    return np.random.default_rng(seed).lognormal(np.log(THRESHOLD), 0.35, size=n)


def flat_level_series(seed: int, n: int = 40) -> np.ndarray:
    return 50.0 + np.random.default_rng(seed).normal(0.0, 2.0, size=n)


def trend_plus_noise(seed: int, n: int = 200) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 + 0.03 * np.arange(n, dtype=float) + rng.normal(0.0, 5.0, size=n)


def local_trend(v: np.ndarray) -> np.ndarray:
    """The three-point average inject_smoothing shrinks towards (its documented trend)."""
    t = np.empty_like(v)
    t[1:-1] = (v[:-2] + v[1:-1] + v[2:]) / 3.0
    t[0] = (v[0] + v[1]) / 2.0
    t[-1] = (v[-2] + v[-1]) / 2.0
    return t


def log_ols_inflation(series: np.ndarray, block: np.ndarray, pre: np.ndarray) -> float:
    """Estimate a multiplicative inflation from outside the block.

    Fits level plus linear trend on the clean positions ``pre``, extrapolates over
    ``block`` and averages the log ratio; for a multiplicative padding of magnitude m this
    recovers about ``log(1 + m)`` times the block's mean ramp factor. Deliberately naive:
    it knows nothing about the taper, which is what makes it the mis-specified estimator.
    """
    design = np.column_stack([np.ones(pre.size), pre - pre.mean()])
    coef, *_ = np.linalg.lstsq(design, np.log(series[pre]), rcond=None)
    pred = np.column_stack([np.ones(block.size), block - pre.mean()]) @ coef
    return float(np.mean(np.log(series[block]) - pred))


# ----------------------------------------------------------------------------- rounding


def test_rounding_noop_at_zero_fraction():
    v, d = clean_binomial_numerators(1)
    out, rec = inject_rounding(v, d, fraction=0.0, seed=7)
    assert out is not v
    np.testing.assert_array_equal(out, v)
    assert rec.mechanism == "rounding"
    assert rec.effect_size == 0.0
    assert rec.indices.size == 0
    assert rec.seed == 7


def test_rounding_snaps_selected_units_to_exact_integer_percentages():
    v, d = clean_binomial_numerators(2)
    out, rec = inject_rounding(v, d, fraction=1.0, seed=3)
    pct_before = 100.0 * v / d
    pct_after = 100.0 * out / d
    # totals: the sample keeps its size, and every denominator is untouched
    assert out.size == v.size
    # every unit now sits exactly on an integer percentage ...
    assert np.all(np.abs(pct_after - np.round(pct_after)) <= 1e-8)
    # ... no unit moved by more than half a percentage point ...
    assert np.all(np.abs(pct_after - pct_before) <= 0.5 + 1e-9)
    # ... units left untouched were exactly the ones already on an integer, and the record
    # lists precisely the positions where the value changed
    already = already_integer_units(v, d)
    np.testing.assert_array_equal(out[already], v[already])
    np.testing.assert_array_equal(rec.indices, np.flatnonzero(out != v))
    assert rec.indices.size == v.size - already.size
    assert rec.effect_size == 1.0


def test_rounding_monotone_under_integer_excess():
    v, d = clean_binomial_numerators(3)
    excesses = []
    for fraction in (0.0, 0.3, 0.6):
        out, _ = inject_rounding(v, d, fraction=fraction, seed=11)
        res = integer_excess(100.0 * out / d, d, n_mc=200, seed=123)
        excesses.append(res.excess)
    assert excesses[1] > excesses[0]
    assert excesses[2] > excesses[1]


def test_rounding_mispecified_estimator_recovers_reduced_nonzero_effect():
    v, d = clean_binomial_numerators(4)
    out, _ = inject_rounding(v, d, fraction=0.4, seed=5)
    pct = 100.0 * out / d
    # the estimator the injector never saw: a fifth of the tolerance band, and a
    # min_denominator that drops two thirds of the sample. The excess survives, reduced,
    # not zeroed.
    tight = integer_excess(pct, d, tolerance=0.005, min_denominator=1500, n_mc=200, seed=9)
    full = integer_excess(pct, d, n_mc=200, seed=9)
    assert tight.excess > 0
    assert tight.test.pvalue < 0.01
    assert tight.excess < full.excess


def test_rounding_reproducible_from_seed():
    v, d = clean_binomial_numerators(6)
    out_a, rec_a = inject_rounding(v, d, fraction=0.4, seed=101)
    out_b, rec_b = inject_rounding(v, d, fraction=0.4, seed=101)
    np.testing.assert_array_equal(out_a, out_b)
    assert rec_a == rec_b
    out_c, _ = inject_rounding(v, d, fraction=0.4, seed=102)
    assert not np.array_equal(out_a, out_c)


# ------------------------------------------------------------------------------ bunching


def test_bunching_noop_at_zero_mass():
    v = lognormal_running_variable(7)
    out, rec = inject_bunching(v, threshold=THRESHOLD, mass=0.0, window=WINDOW, seed=7)
    assert out is not v
    np.testing.assert_array_equal(out, v)
    assert rec.mechanism == "bunching"
    assert rec.effect_size == 0.0
    assert rec.indices.size == 0


def test_bunching_moves_dominated_side_just_past_threshold():
    v = lognormal_running_variable(8)
    mass = 0.4
    out, rec = inject_bunching(
        v, threshold=THRESHOLD, mass=mass, window=WINDOW, side="above", seed=9
    )
    pool = np.flatnonzero((v >= THRESHOLD - WINDOW) & (v < THRESHOLD))
    n_moved = round(mass * pool.size)
    # totals: the sample keeps its size, the movers are relocated, not recreated
    assert out.size == v.size
    assert rec.indices.size == n_moved
    assert np.all(np.isin(rec.indices, pool))
    # origins came from the dominated side, destinations sit just past the threshold
    assert np.all(v[rec.indices] < THRESHOLD)
    assert np.all(out[rec.indices] >= THRESHOLD)
    assert np.all(out[rec.indices] < THRESHOLD + WINDOW)
    # nothing outside the band moved
    band = (v >= THRESHOLD - WINDOW) & (v < THRESHOLD + WINDOW)
    np.testing.assert_array_equal(out[~band], v[~band])


def test_bunching_units_exactly_at_threshold_count_as_above():
    v = lognormal_running_variable(10, n=5000)
    at_threshold = np.arange(100, 110)
    v[at_threshold] = THRESHOLD
    out_above, _ = inject_bunching(
        v, threshold=THRESHOLD, mass=1.0, window=WINDOW, side="above", seed=11
    )
    # side="above": a value exactly at the threshold is already past it, not in the pool
    np.testing.assert_array_equal(out_above[at_threshold], v[at_threshold])
    out_below, rec_below = inject_bunching(
        v, threshold=THRESHOLD, mass=1.0, window=WINDOW, side="below", seed=11
    )
    # side="below": the threshold values sit on the dominated side and are moved below it
    assert np.all(np.isin(at_threshold, rec_below.indices))
    assert np.all(out_below[at_threshold] < THRESHOLD)


def test_bunching_monotone_under_bunching_estimator():
    v = lognormal_running_variable(12)
    b = []
    for mass in (0.0, 0.25, 0.5, 0.75, 1.0):
        out, _ = inject_bunching(
            v, threshold=THRESHOLD, mass=mass, window=WINDOW, side="above", seed=13
        )
        res = bunching_estimator(out, THRESHOLD, poly_degree=7, **BUNCHING_ESTIMATOR_KW)
        b.append(res.normalized_excess)
    assert b[1] > b[0]
    assert b[2] > b[1]
    assert b[3] > b[2]
    assert b[4] > b[3]


def test_bunching_effect_size_is_recovered_as_normalized_excess():
    # with the matching binning (one bin of width `window` on each side) the injected mass
    # and the recovered normalized_excess are the same number, to within the fit error
    v = lognormal_running_variable(14)
    for mass in (0.3, 0.6):
        out, _ = inject_bunching(
            v, threshold=THRESHOLD, mass=mass, window=WINDOW, side="above", seed=15
        )
        res = bunching_estimator(out, THRESHOLD, poly_degree=7, **BUNCHING_ESTIMATOR_KW)
        assert abs(res.normalized_excess - mass) <= 0.3 * mass
        # the hole on the dominated side matches the pile: mass is conserved in the window
        assert res.imbalance <= 0.15 * res.excess_mass


def test_bunching_misspecified_estimator_still_recovers_the_effect():
    """The anti-circularity property: the injector placed the mass without using any
    polynomial, so an estimator with the WRONG counterfactual degree still finds it.

    Note what this does not assert. A degree-2 counterfactual cannot track the lognormal's
    curvature, and the resulting bias does not have a predictable sign: under-fitting near the
    threshold pushes the counterfactual DOWN and so inflates the estimated excess. Measured
    here, the misspecified fit recovers more than the well-specified one, not less. That is a
    fact about the estimator worth carrying into the power atlas (WO-100), not a defect in the
    injector, and asserting the opposite direction would be asserting something untrue.
    """
    v = lognormal_running_variable(16)
    out, _ = inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=WINDOW, side="above", seed=17)
    fit7 = bunching_estimator(out, THRESHOLD, poly_degree=7, **BUNCHING_ESTIMATOR_KW)
    fit2 = bunching_estimator(out, THRESHOLD, poly_degree=2, **BUNCHING_ESTIMATOR_KW)
    # the effect survives misspecification, which is the property that matters
    assert fit2.normalized_excess > 0.1
    assert fit7.normalized_excess > 0.1
    # and misspecification moves the estimate materially, in either direction
    assert abs(fit2.normalized_excess - fit7.normalized_excess) > 0.01


def test_bunching_reproducible_from_seed():
    v = lognormal_running_variable(18)
    out_a, rec_a = inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=WINDOW, seed=201)
    out_b, rec_b = inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=WINDOW, seed=201)
    np.testing.assert_array_equal(out_a, out_b)
    assert rec_a == rec_b
    out_c, _ = inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=WINDOW, seed=202)
    assert not np.array_equal(out_a, out_c)


# ------------------------------------------------------------------------------- padding


def test_padding_noop_at_zero_magnitude():
    v = flat_level_series(19)
    block = np.arange(20, 36)
    for mode in ("multiplicative", "additive"):
        out, rec = inject_padding(v, years=block, magnitude=0.0, mode=mode, seed=7)
        assert out is not v
        np.testing.assert_array_equal(out, v)
        assert rec.mechanism == "padding"
        assert rec.effect_size == 0.0
        assert rec.indices.size == 0


def test_padding_leaves_outside_block_untouched_and_applies_exact_factors():
    v = flat_level_series(20)
    block = np.arange(20, 36)
    out, rec = inject_padding(v, years=block, magnitude=0.3, mode="multiplicative", seed=7)
    outside = np.setdiff1d(np.arange(v.size), block)
    np.testing.assert_array_equal(out[outside], v[outside])
    np.testing.assert_allclose(out[block], v[block] * 1.3, rtol=1e-15)
    np.testing.assert_array_equal(rec.indices, block)
    out_add, _ = inject_padding(v, years=block, magnitude=5.0, mode="additive", seed=7)
    np.testing.assert_allclose(out_add[block], v[block] + 5.0, rtol=1e-15)


def test_padding_taper_ramps_the_onset():
    v = flat_level_series(21)
    block = np.arange(20, 36)
    taper = 4
    out, rec = inject_padding(
        v, years=block, magnitude=0.5, mode="multiplicative", taper=taper, seed=7
    )
    expected = 1.0 + 0.5 * np.minimum(np.arange(block.size), taper) / taper
    np.testing.assert_allclose(out[block], v[block] * expected, rtol=1e-15)
    # the first tapered year carries factor 1, changes nothing, and is not in the record
    assert out[block[0]] == v[block[0]]
    assert block[0] not in rec.indices
    # the last year of the block always carries the full magnitude
    np.testing.assert_allclose(out[block[-1]], v[block[-1]] * 1.5, rtol=1e-15)
    # outside the block nothing moved
    outside = np.setdiff1d(np.arange(v.size), block)
    np.testing.assert_array_equal(out[outside], v[outside])


def test_padding_requires_a_contiguous_in_range_block():
    v = flat_level_series(22)
    with pytest.raises(ValueError, match="contiguous"):
        inject_padding(v, years=[20, 22, 23], magnitude=0.3)
    with pytest.raises(ValueError, match="distinct"):
        inject_padding(v, years=[20, 20, 21], magnitude=0.3)
    with pytest.raises(ValueError, match="outside"):
        inject_padding(v, years=[35, 40], magnitude=0.3)
    with pytest.raises(ValueError, match="integer"):
        inject_padding(v, years=[20.5, 21.5], magnitude=0.3)


def test_padding_monotone_under_block_to_rest_ratio():
    v = flat_level_series(23)
    block = np.arange(20, 36)
    rest = np.arange(0, 20)
    ratios = []
    for magnitude in (0.0, 0.1, 0.3, 0.6):
        out, _ = inject_padding(v, years=block, magnitude=magnitude, seed=7)
        ratios.append(float(np.mean(out[block]) / np.mean(out[rest])))
    assert ratios[1] > ratios[0]
    assert ratios[2] > ratios[1]
    assert ratios[3] > ratios[2]


def test_padding_misspecified_estimator_recovers_reduced_nonzero_effect():
    # the taper exists so that a naive estimator does not find the full magnitude: it must
    # still find something. The estimator below knows nothing about the taper.
    v = flat_level_series(24)
    block = np.arange(20, 36)
    pre = np.arange(0, 20)
    out_untapered, _ = inject_padding(v, years=block, magnitude=0.5, seed=7)
    out_tapered, _ = inject_padding(v, years=block, magnitude=0.5, taper=4, seed=7)
    est_untapered = log_ols_inflation(out_untapered, block, pre)
    est_tapered = log_ols_inflation(out_tapered, block, pre)
    # the untapered block is recovered at about its full log magnitude ...
    assert abs(est_untapered - np.log(1.5)) < 0.05
    # ... the tapered one at a reduced but clearly nonzero share of it
    assert 0.0 < est_tapered < est_untapered
    assert est_tapered > 0.5 * np.log(1.5)


def test_padding_is_deterministic_across_seeds():
    v = flat_level_series(25)
    block = np.arange(20, 36)
    out_a, rec_a = inject_padding(v, years=block, magnitude=0.3, taper=3, seed=301)
    out_b, rec_b = inject_padding(v, years=block, magnitude=0.3, taper=3, seed=302)
    np.testing.assert_array_equal(out_a, out_b)
    assert rec_a == rec_b
    assert rec_a.seed == 301 and rec_b.seed == 302


# ------------------------------------------------------------------------------ smoothing


def test_smoothing_noop_at_retain_one():
    v = trend_plus_noise(26)
    out, rec = inject_smoothing(v, retain=1.0, seed=7)
    assert out is not v
    np.testing.assert_array_equal(out, v)  # bit-exact, not merely close
    assert rec.mechanism == "smoothing"
    assert rec.effect_size == 1.0
    assert rec.indices.size == 0


def test_smoothing_scales_deviation_variance_by_retain():
    v = trend_plus_noise(27)
    trend = local_trend(v)
    dev_var = float(np.var(v - trend, ddof=1))
    for retain in (0.75, 0.5, 0.25, 0.0):
        out, _ = inject_smoothing(v, retain=retain, seed=7)
        got = float(np.var(out - trend, ddof=1))
        assert got == pytest.approx(retain * dev_var, rel=1e-10)
    # retain=0 replaces the series with the local trend itself
    out0, _ = inject_smoothing(v, retain=0.0, seed=7)
    np.testing.assert_allclose(out0, trend, rtol=1e-12)


def test_smoothing_monotone_under_variance_floor_and_smoothness():
    v = trend_plus_noise(28)
    floor = float(np.var(v, ddof=1))
    ratios = []
    for retain in (1.0, 0.75, 0.5, 0.25, 0.0):
        out, _ = inject_smoothing(v, retain=retain, seed=7)
        res = variance_floor_test(out, floor)
        ratios.append(res.details["ratio"])
    assert ratios[1] < ratios[0]
    assert ratios[2] < ratios[1]
    assert ratios[3] < ratios[2]
    assert ratios[4] < ratios[3]
    # the shape of the noise smooths with it: the von Neumann ratio falls
    out_light, _ = inject_smoothing(v, retain=1.0, seed=7)
    out_mid, _ = inject_smoothing(v, retain=0.5, seed=7)
    out_heavy, _ = inject_smoothing(v, retain=0.05, seed=7)
    assert smoothness_ratio(out_heavy) < smoothness_ratio(out_mid) < smoothness_ratio(out_light)


def test_smoothing_mispecified_estimator_recovers_reduced_nonzero_effect():
    # the injector scales deviations about a three-point average; an estimator handed the
    # total variance as its floor instead sees a reduction diluted by the trend the
    # injector leaves in place -- reduced, but far from zero
    v = trend_plus_noise(29)
    out, _ = inject_smoothing(v, retain=0.4, seed=7)
    res = variance_floor_test(out, float(np.var(v, ddof=1)))
    injected_reduction = 1.0 - 0.4
    recovered_reduction = 1.0 - res.details["ratio"]
    assert recovered_reduction > 0.0
    assert recovered_reduction < injected_reduction


def test_smoothing_reproducible_from_seed():
    v = trend_plus_noise(30)
    out_a, rec_a = inject_smoothing(v, retain=0.4, seed=401)
    out_b, rec_b = inject_smoothing(v, retain=0.4, seed=401)
    np.testing.assert_array_equal(out_a, out_b)
    assert rec_a == rec_b


# --------------------------------------------------------------------------- discipline


def test_injectors_never_mutate_their_input():
    v, d = clean_binomial_numerators(31)
    v0, d0 = v.copy(), d.copy()
    series = lognormal_running_variable(32)
    s0 = series.copy()
    level = flat_level_series(33)
    l0 = level.copy()
    path = trend_plus_noise(34)
    p0 = path.copy()
    inject_rounding(v, d, fraction=0.5, seed=1)
    inject_bunching(series, threshold=THRESHOLD, mass=0.5, window=WINDOW, seed=1)
    inject_padding(level, years=np.arange(10, 20), magnitude=0.5, seed=1)
    inject_smoothing(path, retain=0.5, seed=1)
    np.testing.assert_array_equal(v, v0)
    np.testing.assert_array_equal(d, d0)
    np.testing.assert_array_equal(series, s0)
    np.testing.assert_array_equal(level, l0)
    np.testing.assert_array_equal(path, p0)


def test_records_carry_mechanism_effect_size_indices_and_seed():
    v, d = clean_binomial_numerators(35)
    _, rec_r = inject_rounding(v, d, fraction=0.5, seed=501)
    series = lognormal_running_variable(36)
    _, rec_b = inject_bunching(series, threshold=THRESHOLD, mass=0.5, window=WINDOW, seed=502)
    level = flat_level_series(37)
    _, rec_p = inject_padding(level, years=np.arange(10, 20), magnitude=0.4, seed=503)
    path = trend_plus_noise(38)
    _, rec_s = inject_smoothing(path, retain=0.5, seed=504)
    for rec, mechanism, effect, seed in (
        (rec_r, "rounding", 0.5, 501),
        (rec_b, "bunching", 0.5, 502),
        (rec_p, "padding", 0.4, 503),
        (rec_s, "smoothing", 0.5, 504),
    ):
        assert isinstance(rec, InjectionRecord)
        assert rec.mechanism == mechanism
        assert rec.effect_size == effect
        assert rec.indices.dtype == np.int64
        assert rec.seed == seed
        payload = rec.to_dict()
        assert json.loads(json.dumps(payload)) == payload  # plain python, serialisable


def test_injectors_reject_out_of_range_effect_sizes_and_bad_geometry():
    v, d = clean_binomial_numerators(39)
    with pytest.raises(ValueError, match="fraction"):
        inject_rounding(v, d, fraction=-0.1)
    with pytest.raises(ValueError, match="fraction"):
        inject_rounding(v, d, fraction=1.1)
    with pytest.raises(ValueError, match="same length"):
        inject_rounding(v, d[:-1], fraction=0.5)
    with pytest.raises(ValueError, match="positive"):
        inject_rounding(v, d * 0.0, fraction=0.5)
    with pytest.raises(ValueError, match="mass"):
        inject_bunching(v, threshold=THRESHOLD, mass=1.5, window=WINDOW)
    with pytest.raises(ValueError, match="window"):
        inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=0.0)
    with pytest.raises(ValueError, match="side"):
        inject_bunching(v, threshold=THRESHOLD, mass=0.5, window=WINDOW, side="left")
    with pytest.raises(ValueError, match="no units on the dominated side"):
        inject_bunching(v, threshold=-1.0, mass=0.5, window=WINDOW)
    with pytest.raises(ValueError, match="magnitude"):
        inject_padding(v, years=np.arange(10, 20), magnitude=-0.5)
    with pytest.raises(ValueError, match="mode"):
        inject_padding(v, years=np.arange(10, 20), magnitude=0.5, mode="geometric")
    with pytest.raises(ValueError, match="taper"):
        inject_padding(v, years=np.arange(10, 20), magnitude=0.5, taper=-1)
    with pytest.raises(ValueError, match="retain"):
        inject_smoothing(v, retain=1.5)
    with pytest.raises(ValueError, match="at least 3"):
        inject_smoothing(v[:2], retain=0.5)
    with pytest.raises(ValueError, match="finite"):
        inject_bunching(np.array([1.0, np.nan, 3.0]), threshold=THRESHOLD, mass=0.5, window=1.0)

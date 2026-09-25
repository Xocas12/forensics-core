"""Tests for forensics_core.bunching.density.

All data here is synthetic (HARD RULE 3): either a hand-built count vector whose bunching
estimate can be computed on paper, or a lognormal draw into which a known number of units is
moved across a threshold. Nothing touches the network or the filesystem.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from forensics_core.bunching.density import BunchingResult, bin_around, bunching_estimator

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


def sample_from_counts(centres: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Units placed exactly on the given bin centres, so binning reproduces ``counts``."""
    return np.repeat(np.asarray(centres, dtype=float), np.asarray(counts, dtype=int))


def lognormal_with_bunching(
    seed: int,
    n: int = 200_000,
    n_moved: int = 2_000,
    side: str = "below",
) -> np.ndarray:
    """Smooth lognormal density with ``n_moved`` units moved across ``THRESHOLD``.

    Movers are taken from the bin pair on one side of the threshold and dropped into the bin
    immediately on the other side, so the true excess mass is exactly ``n_moved`` and the
    true missing mass is exactly ``n_moved`` as well (mass is conserved inside the excluded
    window). Obviously artificial: a real running variable is never generated this way.
    """
    rng = np.random.default_rng(seed)
    x = rng.lognormal(np.log(THRESHOLD), SIGMA, size=n)
    if side == "below":
        pool = np.flatnonzero((x >= THRESHOLD) & (x < THRESHOLD + 2.0))
        target_lo, target_hi = THRESHOLD - 1.0, THRESHOLD
    else:
        pool = np.flatnonzero((x >= THRESHOLD - 2.0) & (x < THRESHOLD))
        target_lo, target_hi = THRESHOLD, THRESHOLD + 1.0
    if pool.size < n_moved:
        raise AssertionError("synthetic sample too small to move the requested mass")
    chosen = rng.choice(pool, size=n_moved, replace=False)
    x[chosen] = rng.uniform(target_lo, target_hi, size=n_moved)
    return x


def smooth_lognormal(seed: int, n: int = 200_000) -> np.ndarray:
    return np.random.default_rng(seed).lognormal(np.log(THRESHOLD), SIGMA, size=n)


# --------------------------------------------------------------------------- bin_around


def test_bin_around_matches_a_hand_computed_grid():
    centres, counts = bin_around([0.3, 1.2, 1.7], threshold=1.0, bin_width=0.5)
    # data range [0.3, 1.7] expanded to whole bins around the edge 1.0 -> [0.0, 2.0)
    np.testing.assert_allclose(centres, [0.25, 0.75, 1.25, 1.75])
    np.testing.assert_allclose(counts, [1.0, 0.0, 1.0, 1.0])


def test_bin_around_puts_the_threshold_on_an_edge():
    x = smooth_lognormal(seed=1, n=5_000)
    centres, _ = bin_around(x, threshold=THRESHOLD, bin_width=0.7)
    offsets = (centres - THRESHOLD) / 0.7 - 0.5
    np.testing.assert_allclose(offsets, np.round(offsets), atol=1e-9)
    assert not np.any(np.isclose(centres, THRESHOLD))


def test_bin_around_value_on_the_threshold_counts_as_above():
    centres, counts = bin_around(
        [99.5, 100.0, 100.5], threshold=100.0, bin_width=1.0, lo=99.0, hi=101.0
    )
    np.testing.assert_allclose(centres, [99.5, 100.5])
    np.testing.assert_allclose(counts, [1.0, 2.0])


def test_bin_around_expands_the_upper_edge_so_the_maximum_is_inside():
    centres, counts = bin_around([0.0, 2.0], threshold=0.0, bin_width=1.0)
    np.testing.assert_allclose(centres, [0.5, 1.5, 2.5])
    np.testing.assert_allclose(counts, [1.0, 0.0, 1.0])
    assert counts.sum() == 2.0


def test_bin_around_snaps_user_ranges_onto_the_grid():
    # lo snaps down, hi snaps up, threshold stays an edge
    centres, counts = bin_around(
        [0.1, 0.9], threshold=0.0, bin_width=0.25, lo=-0.3, hi=1.1, weights=None
    )
    np.testing.assert_allclose(centres[0], -0.375)
    np.testing.assert_allclose(centres[-1], 1.125)
    assert counts.sum() == 2.0


def test_bin_around_uses_weights_as_counts():
    x = np.array([0.25, 0.25, 1.25])
    w = np.array([2.0, 3.0, 10.0])
    centres, counts = bin_around(x, threshold=0.0, bin_width=1.0, lo=0.0, hi=2.0, weights=w)
    np.testing.assert_allclose(centres, [0.5, 1.5])
    np.testing.assert_allclose(counts, [5.0, 10.0])


def test_bin_around_drops_nonfinite_values():
    x = np.array([0.5, np.nan, 1.5, np.inf, -np.inf])
    _, counts = bin_around(x, threshold=0.0, bin_width=1.0, lo=0.0, hi=2.0)
    np.testing.assert_allclose(counts, [1.0, 1.0])


def test_bin_around_excludes_values_outside_the_range():
    _, counts = bin_around([0.5, 5.0, -5.0], threshold=0.0, bin_width=1.0, lo=0.0, hi=1.0)
    np.testing.assert_allclose(counts, [1.0])


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"bin_width": 0.0}, "bin_width"),
        ({"bin_width": -1.0}, "bin_width"),
        ({"bin_width": np.nan}, "bin_width"),
        ({"threshold": np.nan, "bin_width": 1.0}, "threshold"),
        ({"bin_width": 1.0, "lo": 5.0, "hi": 1.0}, "empty binning range"),
        ({"bin_width": 1e-12, "lo": 0.0, "hi": 1.0}, "bins"),
    ],
)
def test_bin_around_rejects_bad_arguments(kwargs, match):
    call = {"threshold": 0.0, **kwargs}
    with pytest.raises(ValueError, match=match):
        bin_around([0.5, 1.5], **call)


def test_bin_around_rejects_bad_weights():
    with pytest.raises(ValueError, match="same length"):
        bin_around([0.5, 1.5], 0.0, 1.0, weights=[1.0])
    with pytest.raises(ValueError, match="non-negative"):
        bin_around([0.5, 1.5], 0.0, 1.0, weights=[1.0, -1.0])
    with pytest.raises(ValueError, match="finite"):
        bin_around([0.5, 1.5], 0.0, 1.0, weights=[1.0, np.nan])


def test_bin_around_rejects_an_all_nonfinite_sample():
    with pytest.raises(ValueError, match="no finite values"):
        bin_around([np.nan, np.inf], 0.0, 1.0)


# ------------------------------------------------------------------- exact hand fit


def test_bunching_estimator_is_exact_on_a_linear_density():
    """Counts are exactly linear outside the window, with a spike of exactly 50 units.

    Bin j spans [j, j+1) with centre j+0.5, counts_j = 100 + 2j for j = 0..39. Fifty units
    are moved from bin 20 (just above the threshold 20.0) into bin 19 (just below it). A
    degree-1 counterfactual fitted on the 38 untouched bins is exact, so the counterfactual
    is 138 in bin 19 and 140 in bin 20 and, on paper,

        B = (138 + 50) - 138 = 50,  M = 140 - (140 - 50) = 50,  b = 50 / ((138 + 140)/2).
    """
    centres = np.arange(40) + 0.5
    counts = 100 + 2 * np.arange(40)
    counts[19] += 50
    counts[20] -= 50
    x = sample_from_counts(centres, counts)

    result = bunching_estimator(
        x,
        20.0,
        bin_width=1.0,
        exclude_below=1.0,
        exclude_above=1.0,
        poly_degree=1,
        lo=0.0,
        hi=40.0,
    )

    np.testing.assert_allclose(result.counts, counts)
    np.testing.assert_allclose(result.counterfactual[result.excluded_mask], [138.0, 140.0])
    assert result.excess_mass == pytest.approx(50.0, abs=1e-8)
    assert result.missing_mass == pytest.approx(50.0, abs=1e-8)
    assert result.normalized_excess == pytest.approx(50.0 / 139.0, rel=1e-10)
    assert result.imbalance == pytest.approx(0.0, abs=1e-8)
    # the polynomial is the counterfactual, not the fitted value: it ignores the spike
    assert result.counterfactual[19] < result.counts[19]
    # coefficients live in the z basis: counts = 99 + 2*centre = 139 + 2*z, z = centre - 20
    np.testing.assert_allclose(result.coefficients, [139.0, 2.0], atol=1e-8)
    assert result.excluded_mask.sum() == 2
    assert result.settings["n_excluded_below"] == 1
    assert result.settings["n_excluded_above"] == 1
    assert result.settings["n_in_window"] == pytest.approx(counts[19] + counts[20])


def test_bunching_estimator_excluded_window_rounds_down_to_whole_bins():
    x = sample_from_counts(np.arange(40) + 0.5, np.full(40, 10))
    result = bunching_estimator(
        x,
        20.0,
        bin_width=1.0,
        exclude_below=2.9,
        exclude_above=1.5,
        poly_degree=1,
        lo=0.0,
        hi=40.0,
    )
    assert result.settings["n_excluded_below"] == 2
    assert result.settings["n_excluded_above"] == 1
    np.testing.assert_allclose(result.centres[result.excluded_mask], [18.5, 19.5, 20.5])


# ------------------------------------------------------------- injected-mass recovery


def test_bunching_estimator_recovers_the_injected_mass():
    injected = 2_000
    x = lognormal_with_bunching(seed=20260903, n_moved=injected)
    result = bunching_estimator(x, THRESHOLD, **WINDOW)

    assert result.excess_mass == pytest.approx(injected, rel=0.10)
    assert result.missing_mass == pytest.approx(injected, rel=0.10)
    assert result.imbalance < 0.10 * injected
    # b is B expressed in bins' worth of counterfactual observations
    assert result.normalized_excess == pytest.approx(
        result.excess_mass / result.settings["mean_counterfactual_excluded"], rel=1e-12
    )
    assert result.normalized_excess > 0.5
    assert result.settings["n"] == x.size
    assert result.settings["n_dropped"] == 0
    assert result.settings["converged"] is True


def test_bunching_estimator_finds_nothing_in_a_smooth_density():
    injected = 2_000
    clean = smooth_lognormal(seed=20260903)
    result = bunching_estimator(clean, THRESHOLD, **WINDOW)
    assert abs(result.normalized_excess) < 0.15
    assert abs(result.excess_mass) < 0.25 * injected

    spiked = bunching_estimator(
        lognormal_with_bunching(20260903, n_moved=injected), THRESHOLD, **WINDOW
    )
    assert spiked.normalized_excess > 5.0 * abs(result.normalized_excess)


def test_bunching_side_above_recovers_a_spike_above_the_threshold():
    injected = 2_000
    x = lognormal_with_bunching(seed=7, n_moved=injected, side="above")
    result = bunching_estimator(x, THRESHOLD, bunching_side="above", **WINDOW)
    assert result.excess_mass == pytest.approx(injected, rel=0.12)
    assert result.missing_mass == pytest.approx(injected, rel=0.12)
    # measuring on the wrong side turns the pile-up into a hole
    flipped = bunching_estimator(x, THRESHOLD, bunching_side="below", **WINDOW)
    assert flipped.excess_mass == pytest.approx(-result.missing_mass, rel=1e-10)


def test_integration_constraint_balances_excess_and_missing_mass():
    injected = 2_000
    x = lognormal_with_bunching(seed=20260903, n_moved=injected)
    constrained = bunching_estimator(x, THRESHOLD, integration_constraint=True, **WINDOW)

    assert constrained.settings["converged"] is True
    assert 1 <= constrained.settings["n_iter"] <= 50
    assert constrained.settings["shift_factor"] > 1.0
    assert constrained.imbalance < 0.05 * constrained.excess_mass
    assert constrained.excess_mass == pytest.approx(injected, rel=0.15)
    assert constrained.missing_mass == pytest.approx(injected, rel=0.15)


def test_integration_constraint_is_a_no_op_flag_when_disabled():
    x = lognormal_with_bunching(seed=3, n_moved=1_500)
    plain = bunching_estimator(x, THRESHOLD, **WINDOW)
    assert plain.settings["n_iter"] == 0
    assert plain.settings["shift_factor"] == 1.0


def test_weights_scale_the_excess_mass_but_not_the_normalized_excess():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000)
    plain = bunching_estimator(x, THRESHOLD, **WINDOW)
    doubled = bunching_estimator(x, THRESHOLD, weights=np.full(x.size, 2.0), **WINDOW)

    assert doubled.excess_mass == pytest.approx(2.0 * plain.excess_mass, rel=1e-10)
    assert doubled.missing_mass == pytest.approx(2.0 * plain.missing_mass, rel=1e-10)
    assert doubled.normalized_excess == pytest.approx(plain.normalized_excess, rel=1e-10)
    assert doubled.settings["weighted"] is True
    assert doubled.settings["effective_n"] == pytest.approx(float(x.size))


def test_weights_reproduce_a_duplicated_sample():
    """Weighting a unit by 2 must equal listing it twice."""
    x = lognormal_with_bunching(seed=11, n=40_000, n_moved=500)
    heavy = np.arange(x.size) % 2 == 0
    weights = np.where(heavy, 2.0, 1.0)
    duplicated = np.concatenate([x, x[heavy]])

    weighted = bunching_estimator(x, THRESHOLD, weights=weights, **WINDOW)
    stacked = bunching_estimator(duplicated, THRESHOLD, **WINDOW)
    assert weighted.excess_mass == pytest.approx(stacked.excess_mass, rel=1e-10)
    assert weighted.normalized_excess == pytest.approx(stacked.normalized_excess, rel=1e-10)


def test_nonfinite_values_are_dropped_and_counted():
    x = lognormal_with_bunching(seed=5, n=40_000, n_moved=500)
    dirty = np.concatenate([x, [np.nan, np.inf, -np.inf]])
    result = bunching_estimator(dirty, THRESHOLD, **WINDOW)
    assert result.settings["n_dropped"] == 3
    assert result.settings["n"] == x.size


# ------------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"poly_degree": -1}, "poly_degree"),
        ({"exclude_below": 0.0, "exclude_above": 0.0}, "excluded window is empty"),
        ({"exclude_below": -1.0}, "exclude_below"),
        ({"exclude_above": np.nan}, "exclude_above"),
        ({"lo": 101.0, "hi": 160.0}, "beyond the binned range"),
        ({"lo": 96.0, "hi": 104.0, "poly_degree": 7}, "at least 8 bins"),
        ({"bunching_side": "sideways"}, "bunching_side"),
        ({"max_iter": 0}, "max_iter"),
        ({"tol": 0.0}, "tol"),
    ],
)
def test_bunching_estimator_rejects_bad_arguments(override, match):
    x = smooth_lognormal(seed=2, n=20_000)
    kwargs = {**WINDOW, **override}
    with pytest.raises(ValueError, match=match):
        bunching_estimator(x, THRESHOLD, **kwargs)


def test_bunching_estimator_rejects_an_empty_range():
    x = smooth_lognormal(seed=2, n=5_000)
    with pytest.raises(ValueError, match="no observation falls inside"):
        bunching_estimator(
            x,
            THRESHOLD,
            bin_width=1.0,
            exclude_below=1.0,
            exclude_above=1.0,
            poly_degree=1,
            lo=1000.0,
            hi=1100.0,
        )


def test_bunching_estimator_rejects_non_numeric_input():
    with pytest.raises(ValueError, match="numeric"):
        bunching_estimator(
            np.array(["a", "b"]),
            THRESHOLD,
            bin_width=1.0,
            exclude_below=1.0,
            exclude_above=1.0,
            poly_degree=1,
        )


# ----------------------------------------------------------------------- result type


def test_result_is_jsonable_and_carries_the_contract_fields():
    x = lognormal_with_bunching(seed=13, n=40_000, n_moved=500)
    result = bunching_estimator(x, THRESHOLD, **WINDOW)
    assert isinstance(result, BunchingResult)
    payload = result.to_dict()
    assert json.loads(json.dumps(payload))["threshold"] == THRESHOLD
    for key in (
        "centres",
        "counts",
        "counterfactual",
        "excluded_mask",
        "excess_mass",
        "missing_mass",
        "normalized_excess",
        "coefficients",
        "threshold",
        "settings",
    ):
        assert key in payload
    assert result.details is result.settings

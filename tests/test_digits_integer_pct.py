"""Tests for forensics_core.digits.integer_pct.

Synthetic data only (HARD RULE 3). The central pair of tests is the calibration check the
Kobak-Shpilkin-Pshenichnikov (2016) design demands: honest units drawn from the same
binomial noise the null assumes must NOT be flagged, and units whose numerators were set to
hit a round percentage must be flagged hard.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.digits.integer_pct import (
    IntegerExcessResult,
    integer_excess,
    integer_excess_by_group,
    percentage,
    percentage_histogram,
)


def _honest_units(seed: int, n: int = 1_500):
    """Denominators in 500..3000 with binomial numerators: the null is true by construction."""
    rng = np.random.default_rng(seed)
    den = rng.integers(500, 3_001, n)
    share = rng.uniform(0.30, 0.70, n)
    num = rng.binomial(den, share)
    return num, den


def _plant_round_percentages(num, den, seed: int, fraction: float = 0.05):
    """Replace a fraction of numerators with round(d * k / 100) for a random integer k."""
    rng = np.random.default_rng(seed)
    n = num.size
    idx = rng.choice(n, size=round(fraction * n), replace=False)
    k = rng.integers(30, 71, idx.size)
    planted = num.copy()
    planted[idx] = np.round(den[idx] * k / 100.0)
    return planted, idx


# ------------------------------------------------------------------------------ percentage


def test_percentage_hand_values_and_undefined_cases():
    out = percentage([50, 1, 3, 7, 2], [200, 0, 4, -10, np.nan])
    assert out[0] == pytest.approx(25.0)
    assert out[2] == pytest.approx(75.0)
    assert np.isnan(out[[1, 3, 4]]).all()


def test_percentage_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        percentage([1, 2, 3], [10, 20])


# ------------------------------------------------------------------------------- histogram


def test_histogram_puts_integers_at_bin_centres():
    centres, counts = percentage_histogram([49.96, 49.94, 50.0, 50.049, 0.0, 100.0])
    assert centres.size == 1_001
    assert centres[0] == pytest.approx(0.0)
    assert centres[-1] == pytest.approx(100.0)
    assert centres[500] == pytest.approx(50.0)
    # edges at k * 0.1 - 0.05, so [49.95, 50.05) is the bin centred on 50
    assert counts[500] == 3  # 49.96, 50.0, 50.049
    assert counts[499] == 1  # 49.94 falls in the bin centred on 49.9
    assert counts.sum() == 6


def test_histogram_weights_and_out_of_range_values():
    centres, counts = percentage_histogram(
        [10.0, 10.0, 200.0, -5.0, np.nan], weights=[2.0, 3.0, 9.0, 9.0, 9.0]
    )
    assert counts[100] == pytest.approx(5.0)
    assert counts.sum() == pytest.approx(5.0)  # out-of-range and nan contribute nothing
    assert centres[100] == pytest.approx(10.0)


def test_histogram_bin_width_must_divide_one():
    with pytest.raises(ValueError, match="must divide 1"):
        percentage_histogram([1.0, 2.0], bin_width=0.3)
    with pytest.raises(ValueError, match="positive finite"):
        percentage_histogram([1.0, 2.0], bin_width=0.0)
    with pytest.raises(ValueError, match="not an integer multiple"):
        percentage_histogram([1.0, 2.0], lo=0.05)
    with pytest.raises(ValueError, match="lo < hi"):
        percentage_histogram([1.0, 2.0], lo=50.0, hi=50.0)


def test_histogram_at_unit_bin_width_counts_every_value():
    centres, counts = percentage_histogram(np.linspace(0.0, 100.0, 101), bin_width=1.0)
    assert centres.size == 101
    assert counts.tolist() == [1] * 101


# -------------------------------------------------------------------------- the null holds


def test_honest_binomial_units_show_no_significant_excess():
    num, den = _honest_units(seed=7)
    result = integer_excess(percentage(num, den), den, n_mc=100, seed=11)
    assert isinstance(result, IntegerExcessResult)
    assert result.test.method == "integer_percentage_excess"
    assert result.test.details["alternative"] == "greater"
    assert result.test.pvalue > 0.05
    assert result.test.details["mc_pvalue"] > 0.05
    assert abs(result.test.statistic) < 2.5
    assert abs(result.excess) < 3 * result.expected_sd
    # roughly a tenth of the units land within +-0.05 of an integer by chance
    assert 0.05 < result.expected_mean / result.test.n < 0.15


def test_the_null_is_calibrated_across_seeds():
    """Honest samples must not be flagged as a rule, not merely for one lucky seed."""
    pvalues = []
    for seed in range(101, 111):
        num, den = _honest_units(seed=seed, n=600)
        pvalues.append(integer_excess(percentage(num, den), den, n_mc=60, seed=seed).test.pvalue)
    assert sum(p < 0.05 for p in pvalues) <= 1
    assert min(pvalues) > 1e-3
    assert 0.2 < float(np.mean(pvalues)) < 0.8


def test_planted_round_percentages_are_detected():
    num, den = _honest_units(seed=7)
    planted, idx = _plant_round_percentages(num, den, seed=13)
    result = integer_excess(percentage(planted, den), den, n_mc=100, seed=11)
    assert result.test.pvalue < 1e-3
    assert result.test.statistic > 4.0
    assert result.test.details["mc_pvalue"] == pytest.approx(1.0 / 101.0)
    # the excess recovers most of the planted units (some would have been near an
    # integer anyway, and the null absorbs those)
    assert result.excess > 0.5 * idx.size
    assert result.test.details["neighbour_excess"] > 0.5 * idx.size


def test_per_integer_excess_localises_the_planted_integers():
    num, den = _honest_units(seed=3)
    rng = np.random.default_rng(5)
    idx = rng.choice(num.size, size=200, replace=False)
    planted = num.copy()
    planted[idx] = np.round(den[idx] * 0.60)  # everyone at exactly 60%
    result = integer_excess(percentage(planted, den), den, n_mc=100, seed=2)
    assert result.per_integer.shape == (101,)
    assert result.per_integer.sum() == pytest.approx(result.excess)
    assert int(np.argmax(result.per_integer)) == 60
    assert result.per_integer[60] > 150
    # a planted unit misses the +-0.05 window only when round(0.6 d) / d strays that far,
    # which needs a small denominator, so nearly all 200 land in the bin centred on 60
    assert result.test.details["observed_per_integer"][60] >= 190


def test_small_units_are_excluded_and_counted():
    num, den = _honest_units(seed=7, n=800)
    small_den = np.full(200, 50)
    small_num = np.round(small_den * 0.5).astype(int)  # every one of them lands on 50%
    all_num = np.concatenate([num, small_num])
    all_den = np.concatenate([den, small_den])
    result = integer_excess(percentage(all_num, all_den), all_den, n_mc=50, seed=1)
    assert result.n_excluded_small == 200
    assert result.test.n == 800
    assert result.test.pvalue > 0.05  # the planted small units never entered the test
    # Lowering the threshold lets them in. The binomial null is not fooled by them - with
    # d = 50 every possible percentage is a multiple of 2, so the null draws sit on integers
    # just as the data do - but the model-free neighbour comparison IS fooled, which is why
    # min_denominator exists.
    permissive = integer_excess(
        percentage(all_num, all_den), all_den, min_denominator=10, n_mc=50, seed=1
    )
    assert permissive.n_excluded_small == 0
    assert permissive.test.n == 1_000
    assert permissive.test.pvalue > 0.05
    assert permissive.test.details["neighbour_excess"] > 150
    assert result.test.details["neighbour_excess"] < 50


def test_nonfinite_values_are_dropped_and_counted():
    num, den = _honest_units(seed=21, n=300)
    pct = percentage(num, den).astype(float)
    pct[:10] = np.nan
    result = integer_excess(pct, den, n_mc=25, seed=1)
    assert result.test.details["n_dropped"] == 10
    assert result.test.n == 290


def test_results_are_reproducible_and_seed_sensitive():
    num, den = _honest_units(seed=7, n=600)
    pct = percentage(num, den)
    first = integer_excess(pct, den, n_mc=50, seed=123)
    again = integer_excess(pct, den, n_mc=50, seed=123)
    other = integer_excess(pct, den, n_mc=50, seed=124)
    assert first.expected_mean == again.expected_mean
    assert first.test.statistic == again.test.statistic
    assert first.observed == other.observed  # the observed count does not depend on the seed
    assert first.expected_mean != other.expected_mean


def test_weighted_run_reports_effective_n():
    num, den = _honest_units(seed=7, n=400)
    pct = percentage(num, den)
    weights = den.astype(float)  # weight by unit size, the usual electoral choice
    result = integer_excess(pct, den, n_mc=50, seed=9, weights=weights)
    assert result.test.n == 400
    assert 0 < result.test.details["effective_n"] < 400
    assert result.test.details["weighted_pvalue_is_approximate"] is True
    assert result.observed == pytest.approx(weights[np.abs(pct - np.round(pct)) <= 0.05].sum())


def test_neighbour_bins_are_truncated_at_the_half_integer():
    num, den = _honest_units(seed=7, n=300)
    result = integer_excess(percentage(num, den), den, n_mc=25, seed=1)
    # offsets +-0.1 .. +-0.4 fit inside the unit interval; +-0.5 does not
    assert result.test.details["neighbour_bins_used"] == 8
    assert result.settings["neighbour_bins"] == 5


def test_invalid_arguments_raise():
    num, den = _honest_units(seed=7, n=100)
    pct = percentage(num, den)
    with pytest.raises(ValueError, match="same length"):
        integer_excess(pct[:50], den, n_mc=5)
    with pytest.raises(ValueError, match="tolerance"):
        integer_excess(pct, den, tolerance=0.6, n_mc=5)
    with pytest.raises(ValueError, match="n_mc"):
        integer_excess(pct, den, n_mc=0)
    with pytest.raises(ValueError, match="neighbour_bins"):
        integer_excess(pct, den, neighbour_bins=-1, n_mc=5)
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        integer_excess(np.append(pct[:-1], 150.0), den, n_mc=5)
    with pytest.raises(ValueError, match="integer-valued"):
        integer_excess(pct, den.astype(float) + 0.5, n_mc=5)
    with pytest.raises(ValueError, match="no unit survives"):
        integer_excess(pct, np.full(100, 10), n_mc=5)


def test_result_is_serialisable():
    num, den = _honest_units(seed=7, n=200)
    as_dict = integer_excess(percentage(num, den), den, n_mc=20, seed=1).to_dict()
    assert isinstance(as_dict["per_integer"], list)
    assert len(as_dict["per_integer"]) == 101
    assert as_dict["test"]["method"] == "integer_percentage_excess"
    assert "Kobak" in as_dict["test"]["details"]["citation"]


# ---------------------------------------------------------------------------- by group


def test_by_group_isolates_the_contaminated_group():
    num_a, den_a = _honest_units(seed=41, n=900)
    num_b, den_b = _honest_units(seed=42, n=900)
    num_b, idx = _plant_round_percentages(num_b, den_b, seed=43, fraction=0.08)
    num = np.concatenate([num_a, num_b])
    den = np.concatenate([den_a, den_b])
    groups = np.array(["clean"] * 900 + ["stuffed"] * 900)

    table = integer_excess_by_group(percentage(num, den), den, groups, n_mc=100, seed=17)
    assert isinstance(table, pd.DataFrame)
    assert table["group"].tolist() == ["clean", "stuffed"]  # first-appearance order
    assert set(table.columns) >= {
        "group",
        "n",
        "observed",
        "expected_mean",
        "expected_sd",
        "excess",
        "z",
        "pvalue",
        "mc_pvalue",
        "n_excluded_small",
    }
    clean = table.set_index("group").loc["clean"]
    stuffed = table.set_index("group").loc["stuffed"]
    assert clean["pvalue"] > 0.05
    assert stuffed["pvalue"] < 1e-4
    assert stuffed["z"] > clean["z"] + 3
    assert stuffed["excess"] > 0.5 * idx.size
    assert clean["n"] == 900 and stuffed["n"] == 900


def test_by_group_is_reproducible():
    num, den = _honest_units(seed=7, n=400)
    groups = np.where(np.arange(400) < 200, "a", "b")
    pct = percentage(num, den)
    first = integer_excess_by_group(pct, den, groups, n_mc=25, seed=5)
    again = integer_excess_by_group(pct, den, groups, n_mc=25, seed=5)
    pd.testing.assert_frame_equal(first, again)


def test_by_group_survives_a_group_with_no_usable_unit():
    num, den = _honest_units(seed=7, n=300)
    num = np.concatenate([num, np.full(20, 5)])
    den = np.concatenate([den, np.full(20, 10)])  # all below min_denominator
    groups = np.array(["big"] * 300 + ["tiny"] * 20)
    table = integer_excess_by_group(percentage(num, den), den, groups, n_mc=20, seed=3)
    tiny = table.set_index("group").loc["tiny"]
    assert tiny["n"] == 0
    assert np.isnan(tiny["z"])
    assert tiny["n_excluded_small"] == 20


def test_by_group_length_mismatch_raises():
    num, den = _honest_units(seed=7, n=50)
    with pytest.raises(ValueError, match="same length"):
        integer_excess_by_group(percentage(num, den), den, np.array(["a", "b"]), n_mc=5)

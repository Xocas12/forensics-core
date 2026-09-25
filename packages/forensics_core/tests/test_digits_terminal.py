"""Tests for forensics_core.digits.terminal.

Synthetic data only (HARD RULE 3): small hand-built vectors whose chi-square value can be
worked out on paper, plus generated uniform samples with fixed seeds.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from forensics_core.digits.terminal import (
    terminal_digit_pair_test,
    terminal_digit_test,
    terminal_digits,
)

# ------------------------------------------------------------------------- digit extraction


def test_terminal_digits_hand_cases():
    assert terminal_digits([123, 4560, 7.0]).tolist() == [3, 0, 7]
    assert terminal_digits([123, 4560, 7.0], k=2).tolist() == [23, 60, 7]
    assert terminal_digits([123456], k=3).tolist() == [456]


def test_terminal_digits_use_the_magnitude():
    assert terminal_digits([-123], k=2).tolist() == [23]


def test_terminal_digits_drop_nonfinite_but_reject_fractions():
    assert terminal_digits([11.0, np.nan, 23.0, np.inf]).tolist() == [1, 3]
    with pytest.raises(ValueError, match="integer-valued"):
        terminal_digits([10.0, 1.5])
    # the tolerance is 1e-9, so float noise is accepted and real fractions are not
    assert terminal_digits([10.0 + 1e-12]).tolist() == [0]
    with pytest.raises(ValueError, match="integer-valued"):
        terminal_digits([10.0 + 1e-6])


def test_terminal_digits_reject_unrepresentable_magnitudes():
    with pytest.raises(ValueError, match=r"2\*\*53"):
        terminal_digits([2.0**53])


@pytest.mark.parametrize("bad_k", [0, -1, 10])
def test_k_out_of_range_raises(bad_k):
    with pytest.raises(ValueError, match="k must be"):
        terminal_digits([10, 20], k=bad_k)


def test_non_integer_k_raises():
    with pytest.raises(ValueError, match="k must be an integer"):
        terminal_digits([10, 20], k=1.0)


# ------------------------------------------------------------------------- uniformity test


def test_chi_square_matches_a_hand_computed_value():
    # ten values ending in 0 and ten ending in 1: expected 2 per cell,
    # chi2 = 2 * (10 - 2)^2 / 2 + 8 * (0 - 2)^2 / 2 = 64 + 16 = 80
    x = [10 * i for i in range(1, 11)] + [10 * i + 1 for i in range(1, 11)]
    result = terminal_digit_test(x)
    assert result.method == "terminal_digit_1_chi2"
    assert result.statistic == pytest.approx(80.0)
    assert result.n == 20
    assert result.details["df"] == 9
    assert result.pvalue == pytest.approx(stats.chi2.sf(80.0, 9))
    assert result.details["max_abs_dev"] == pytest.approx(0.4)
    assert result.details["max_excess_cell"] in (0, 1)
    assert result.details["observed"].tolist() == [10, 10, 0, 0, 0, 0, 0, 0, 0, 0]
    assert result.details["alternative"] == "greater"


def test_uniform_last_digits_are_not_rejected():
    x = np.random.default_rng(4242).integers(1_000, 100_000, 20_000).astype(float)
    result = terminal_digit_test(x)
    assert result.pvalue > 0.05
    assert result.details["max_abs_dev"] < 0.02


def test_planted_round_number_preference_is_detected():
    """A fifth of the counts nudged to a multiple of 10 must show up in cell 0."""
    rng = np.random.default_rng(7)
    x = rng.integers(1_000, 100_000, 5_000).astype(float)
    rounded = rng.random(5_000) < 0.2
    x[rounded] = np.round(x[rounded] / 10.0) * 10.0
    result = terminal_digit_test(x)
    assert result.pvalue < 1e-10
    assert result.details["max_excess_cell"] == 0
    assert result.details["observed_prop"][0] > 0.25


def test_two_digit_test_has_ninety_nine_degrees_of_freedom():
    x = np.random.default_rng(11).integers(10_000, 1_000_000, 30_000).astype(float)
    result = terminal_digit_test(x, k=2)
    assert result.method == "terminal_digit_2_chi2"
    assert result.details["df"] == 99
    assert result.pvalue > 0.01


def test_weights_scale_the_statistic_by_the_effective_sample_size():
    weighted = terminal_digit_test([10, 11], weights=[1.0, 3.0])
    replicated = terminal_digit_test([10, 11, 11, 11])
    assert weighted.details["observed"].tolist() == [1.0, 3.0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert weighted.details["observed_prop"] == pytest.approx(replicated.details["observed_prop"])
    # Kish effective n = (1 + 3)^2 / (1 + 9) = 1.6, against 4 for the replicated sample
    assert weighted.details["effective_n"] == pytest.approx(1.6)
    assert replicated.statistic == pytest.approx(21.0)
    assert weighted.statistic == pytest.approx(8.4)
    assert weighted.n == 2
    assert weighted.details["weighted_pvalue_is_approximate"] is True


def test_uniformity_test_rejects_bad_input():
    with pytest.raises(ValueError, match="same length"):
        terminal_digit_test([10, 20], weights=[1.0])
    with pytest.raises(ValueError, match="no finite values"):
        terminal_digit_test([np.nan, np.inf])
    with pytest.raises(ValueError, match="integer-valued"):
        terminal_digit_test([10.0, 20.5])


# ------------------------------------------------------------------------------ pair test


def test_pair_test_on_a_degenerate_sample_is_hand_computable():
    # every value ends in 11: one cell holds everything, so
    # chi2 = n * [(1 - 0.01)^2 / 0.01 + 99 * (0.01)^2 / 0.01] = 99 n
    x = np.arange(100) * 100 + 11
    result = terminal_digit_pair_test(x)
    assert result.method == "terminal_digit_pair_chi2"
    assert result.statistic == pytest.approx(99.0 * 100)
    assert result.details["df"] == 99
    assert result.pvalue < 1e-20

    excess = result.details["adjacent_pair_excess"]
    assert excess["repeated"]["observed_prop"] == pytest.approx(1.0)
    assert excess["repeated"]["expected_prop"] == pytest.approx(0.10)
    assert excess["repeated"]["excess"] == pytest.approx(0.90)
    assert excess["adjacent"]["observed_prop"] == pytest.approx(0.0)
    assert excess["adjacent"]["expected_prop"] == pytest.approx(0.18)
    assert excess["adjacent"]["excess"] == pytest.approx(-0.18)
    assert excess["repeated"]["cells"] == [0, 11, 22, 33, 44, 55, 66, 77, 88, 99]
    assert len(excess["adjacent"]["cells"]) == 18


def test_pair_test_accepts_uniform_last_two_digits():
    x = np.random.default_rng(2024).integers(10_000, 1_000_000, 20_000).astype(float)
    result = terminal_digit_pair_test(x)
    assert result.pvalue > 0.05
    excess = result.details["adjacent_pair_excess"]
    assert excess["repeated"]["pvalue"] > 0.05
    assert excess["adjacent"]["pvalue"] > 0.05
    assert abs(excess["repeated"]["excess"]) < 0.02


def test_pair_test_recovers_the_beber_scacco_fingerprint():
    """Too few repeats, too many adjacent pairs: the human-generation signature."""
    rng = np.random.default_rng(31)
    n = 6_000
    base = rng.integers(100, 10_000, n) * 100
    tens = rng.integers(0, 10, n)
    units = tens.copy()
    # a third of the units get an adjacent digit, and repeats are pushed away
    adjacent = rng.random(n) < 0.35
    units[adjacent] = (tens[adjacent] + 1) % 10
    repeat_free = ~adjacent
    units[repeat_free] = (tens[repeat_free] + rng.integers(2, 9, repeat_free.sum())) % 10
    x = (base + 10 * tens + units).astype(float)

    result = terminal_digit_pair_test(x)
    excess = result.details["adjacent_pair_excess"]
    assert result.pvalue < 1e-10
    assert excess["adjacent"]["excess"] > 0.1
    assert excess["adjacent"]["z"] > 5
    assert excess["repeated"]["excess"] < -0.05
    assert excess["repeated"]["z"] < -5
    assert "Beber" in result.details["citation"]


def test_pair_test_weights_are_honoured():
    x = np.arange(100) * 100 + 11
    w = np.full(100, 4.0)
    weighted = terminal_digit_pair_test(x, weights=w)
    assert weighted.details["effective_n"] == pytest.approx(100.0)
    assert weighted.statistic == pytest.approx(terminal_digit_pair_test(x).statistic)
    assert weighted.details["observed"].sum() == pytest.approx(400.0)


def test_pair_test_rejects_non_integer_input():
    with pytest.raises(ValueError, match="integer-valued"):
        terminal_digit_pair_test([1010.0, 2020.25])


def test_results_are_serialisable():
    x = np.random.default_rng(1).integers(1_000, 100_000, 500).astype(float)
    as_dict = terminal_digit_test(x).to_dict()
    assert isinstance(as_dict["details"]["observed"], list)
    assert as_dict["method"] == "terminal_digit_1_chi2"
    pair = terminal_digit_pair_test(x).to_dict()
    assert isinstance(pair["details"]["adjacent_pair_excess"]["repeated"]["z"], float)

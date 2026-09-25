"""Tests for forensics_core.digits.benford.

All data is synthetic and generated here (HARD RULE 3). Reference numbers are either closed
form (log10(2), the second-digit table published in Nigrini 2012 ch. 3) or computed in the
test with an independent loop, never by calling the function under test.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from forensics_core.digits.benford import (
    MAD_BANDS,
    MAD_LABELS,
    BenfordResult,
    DigitTable,
    _kuiper_pvalue,
    _mad_conformity,
    benford_expected,
    benford_test,
    digit_frequencies,
    digit_support,
    leading_digits,
)

POSITIONS = ("first", "second", "first_two")


# --------------------------------------------------------------------------- expectations


@pytest.mark.parametrize("position", POSITIONS)
def test_expected_probabilities_sum_to_one(position):
    expected = benford_expected(position)
    assert expected.shape == digit_support(position).shape
    assert np.all(expected > 0)
    assert expected.sum() == pytest.approx(1.0, abs=1e-12)


def test_first_digit_matches_closed_form():
    expected = benford_expected("first")
    assert expected[0] == pytest.approx(math.log10(2.0))
    assert expected[8] == pytest.approx(math.log10(10.0 / 9.0))
    # monotone decreasing, the whole point of the law
    assert np.all(np.diff(expected) < 0)


def test_first_two_marginalises_to_first_and_second():
    first_two = benford_expected("first_two").reshape(9, 10)
    assert first_two.sum(axis=1) == pytest.approx(benford_expected("first"), abs=1e-12)
    assert first_two.sum(axis=0) == pytest.approx(benford_expected("second"), abs=1e-12)


def test_second_digit_matches_published_table():
    # Nigrini (2012), Benford's Law, Wiley, ch. 3: second-digit probabilities.
    published = [0.11968, 0.11389, 0.10882, 0.10433, 0.10031, 0.09668, 0.09337, 0.09035, 0.08757]
    assert benford_expected("second")[:9] == pytest.approx(published, abs=5e-6)


def test_supports():
    assert digit_support("first").tolist() == list(range(1, 10))
    assert digit_support("second").tolist() == list(range(10))
    assert digit_support("first_two").tolist() == list(range(10, 100))


@pytest.mark.parametrize("bad", ["third", "FIRST", "", None])
def test_unknown_position_raises(bad):
    with pytest.raises(ValueError, match="position must be one of"):
        benford_expected(bad)


# ------------------------------------------------------------------------- digit extraction


def test_leading_digits_handles_floats_across_magnitudes():
    x = [0.000123, 123.0, 1.0, 9.99, 8.7, 1000.0, 0.001, 999999999.0]
    assert leading_digits(x, "first").tolist() == [1, 1, 1, 9, 8, 1, 1, 9]
    assert leading_digits(x, "first_two").tolist() == [12, 12, 10, 99, 87, 10, 10, 99]


def test_leading_digits_excludes_nonpositive_and_nonfinite():
    x = [1.5, 0.0, -3.7, np.nan, np.inf, -np.inf, 4.2]
    assert leading_digits(x).tolist() == [1, 4]


def test_second_digit_requires_two_significant_digits():
    # 300.0 and 0.0007 carry a single significant digit: their "second digit" is padding.
    x = [0.000123, 3.05, 300.0, 0.0007, 8.7]
    assert leading_digits(x, "second").tolist() == [2, 0, 7]
    # opting out reads the placeholder zeros instead
    assert leading_digits(x, "second", require_two_significant_digits=False).tolist() == [
        2,
        0,
        0,
        0,
        7,
    ]


def test_float_noise_does_not_manufacture_a_second_digit():
    noisy = 3 * 0.1  # 0.30000000000000004
    assert noisy != 0.3
    assert leading_digits([noisy], "second").size == 0
    assert leading_digits([noisy], "first").tolist() == [3]


def test_leading_digits_exact_powers_of_ten():
    x = np.power(10.0, np.arange(-8, 9))
    assert leading_digits(x, "first").tolist() == [1] * x.size
    assert leading_digits(x, "first_two").tolist() == [10] * x.size


def test_leading_digits_rejects_bad_input():
    with pytest.raises(ValueError, match="1-D"):
        leading_digits(np.ones((2, 3)))
    with pytest.raises(ValueError, match="boolean"):
        leading_digits(np.array([True, False]))


# ------------------------------------------------------------------------------ frequencies


def _exact_benford_sample(position: str, scale: int = 100_000) -> np.ndarray:
    """Values whose digits reproduce the Benford proportions to within rounding."""
    support = digit_support(position)
    counts = np.round(benford_expected(position) * scale).astype(int)
    if position == "first":
        values = support + 0.5
    elif position == "first_two":
        values = support / 10.0 + 0.05
    else:  # second: 1.d5 has first digit 1 and second digit d
        values = 1.0 + support / 10.0 + 0.05
    return np.repeat(values, counts)


def test_digit_frequencies_counts_and_proportions():
    x = [1.1, 1.2, 2.3, 9.9]
    table = digit_frequencies(x, "first")
    assert isinstance(table, DigitTable)
    assert table.observed.tolist() == [2, 1, 0, 0, 0, 0, 0, 0, 1]
    assert table.n == 4
    assert table.effective_n == 4.0
    assert table.observed_prop.sum() == pytest.approx(1.0)
    assert table.expected.sum() == pytest.approx(4.0)
    assert table.expected[0] == pytest.approx(4 * math.log10(2.0))
    assert table.n_dropped == 0


def test_digit_frequencies_reports_dropped_values():
    table = digit_frequencies([1.1, -2.0, np.nan, 3.0])
    assert table.n == 2
    assert table.n_dropped == 2


def test_weights_reproduce_replication_and_kish_n():
    x = [1.1, 2.2, 3.3]
    weighted = digit_frequencies(x, "first", weights=[1.0, 2.0, 3.0])
    replicated = digit_frequencies([1.1, 2.2, 2.2, 3.3, 3.3, 3.3], "first")
    assert weighted.observed.tolist() == [1.0, 2.0, 3.0, 0, 0, 0, 0, 0, 0]
    assert weighted.observed_prop == pytest.approx(replicated.observed_prop)
    assert weighted.n == 3  # n stays the unweighted count
    assert weighted.effective_n == pytest.approx(36.0 / 14.0)  # (1+2+3)^2 / (1+4+9)


def test_constant_weights_leave_the_effective_n_at_n():
    x = 10 ** np.random.default_rng(11).uniform(0, 4, 500)
    table = digit_frequencies(x, "first", weights=np.full(500, 2.0))
    assert table.effective_n == pytest.approx(500.0)
    assert table.observed_prop == pytest.approx(digit_frequencies(x, "first").observed_prop)


def test_frequencies_reject_bad_weights_and_empty_samples():
    with pytest.raises(ValueError, match="same length"):
        digit_frequencies([1.0, 2.0], weights=[1.0])
    with pytest.raises(ValueError, match="non-negative"):
        digit_frequencies([1.0, 2.0], weights=[1.0, -1.0])
    with pytest.raises(ValueError, match="no usable values"):
        digit_frequencies([0.0, -1.0, np.nan])
    with pytest.raises(ValueError, match="must not all be zero"):
        digit_frequencies([1.0, 2.0], weights=[0.0, 0.0])
    # weight mass sits entirely on values that digit extraction excluded
    with pytest.raises(ValueError, match="zero weight"):
        digit_frequencies([1.0, -1.0], weights=[0.0, 5.0])


# ------------------------------------------------------------------------------- the tests


def test_conforming_sample_is_not_rejected():
    x = 10 ** np.random.default_rng(2026).uniform(0.0, 6.0, 30_000)
    result = benford_test(x, "first")
    assert isinstance(result, BenfordResult)
    assert result.chi2.pvalue > 0.05
    assert result.kuiper.pvalue > 0.05
    assert result.mad.details["conformity"] == MAD_LABELS[0]
    assert result.chi2.details["df"] == 8


def test_uniform_first_digits_are_rejected_on_every_statistic():
    x = np.repeat(np.arange(1, 10) + 0.5, 1000)  # 1/9 in every cell
    result = benford_test(x, "first")

    expected_counts = 9000.0 * benford_expected("first")
    chi2_by_hand = sum((1000.0 - e) ** 2 / e for e in expected_counts)
    assert result.chi2.statistic == pytest.approx(chi2_by_hand)
    assert result.chi2.pvalue < 1e-10
    assert result.mad.details["conformity"] == MAD_LABELS[3]
    assert result.kuiper.pvalue < 1e-10


def test_exact_benford_counts_give_close_conformity():
    for position in POSITIONS:
        result = benford_test(_exact_benford_sample(position), position)
        assert result.mad.statistic < MAD_BANDS[position][0]
        assert result.mad.details["conformity"] == MAD_LABELS[0]
        assert result.chi2.pvalue > 0.99
        assert result.kuiper.pvalue == pytest.approx(1.0)


def test_injected_first_digit_effect_is_recovered():
    """Contaminating a conforming sample with digit-5 values must show up as a 5 excess."""
    rng = np.random.default_rng(99)
    clean = 10 ** rng.uniform(0.0, 6.0, 20_000)
    planted = rng.uniform(5.0, 6.0, 4_000) * 10 ** rng.integers(0, 4, 4_000)
    result = benford_test(np.concatenate([clean, planted]), "first")
    table = result.table
    residual = table.observed_prop - table.expected_prop
    assert int(np.argmax(residual)) == 4  # digit 5 sits at index 4
    assert result.chi2.pvalue < 1e-10
    assert result.mad.details["conformity"] == MAD_LABELS[3]


def test_kuiper_statistic_is_hand_computable():
    # Every value has first digit 1: the observed CDF jumps to 1 at d = 1, so
    # D+ = 1 - log10(2) and D- = 0.
    ones = benford_test(np.full(500, 1.5), "first", statistics=("kuiper",))
    assert ones.kuiper.statistic == pytest.approx(1.0 - math.log10(2.0))
    assert ones.kuiper.details["d_minus"] == pytest.approx(0.0)
    assert ones.chi2 is None and ones.mad is None

    # Every value has first digit 9: the observed CDF stays at 0 until the last cell, so
    # D- = 1 - log10(10/9) and D+ = 0.
    nines = benford_test(np.full(500, 9.5), "first", statistics=("kuiper",))
    assert nines.kuiper.statistic == pytest.approx(1.0 - math.log10(10.0 / 9.0))
    assert nines.kuiper.details["d_plus"] == pytest.approx(0.0)


def test_kuiper_pvalue_matches_the_stephens_series():
    # lambda = 1 exactly at n = 100: (sqrt(100) + 0.155 + 0.24/sqrt(100)) = 10.179.
    n = 100.0
    v = 1.0 / (math.sqrt(n) + 0.155 + 0.24 / math.sqrt(n))
    series = 2.0 * sum((4 * j**2 - 1) * math.exp(-2 * j**2) for j in range(1, 40))
    assert series == pytest.approx(0.8220766, abs=1e-6)
    assert _kuiper_pvalue(v, n) == pytest.approx(series, rel=1e-9)
    # the series is short-circuited below lambda = 0.4 (Numerical Recipes)
    assert _kuiper_pvalue(0.0, n) == 1.0
    assert _kuiper_pvalue(0.5, n) == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(ValueError, match="finite and non-negative"):
        _kuiper_pvalue(-0.1, n)


@pytest.mark.parametrize("position", POSITIONS)
def test_mad_bands_are_the_nigrini_cut_offs(position):
    close, acceptable, marginal = MAD_BANDS[position]
    assert close < acceptable < marginal
    assert _mad_conformity(close / 2, position) == MAD_LABELS[0]
    assert _mad_conformity(close, position) == MAD_LABELS[1]
    assert _mad_conformity(acceptable, position) == MAD_LABELS[2]
    assert _mad_conformity(marginal, position) == MAD_LABELS[3]
    assert _mad_conformity(marginal * 10, position) == MAD_LABELS[3]


def test_mad_is_the_mean_absolute_deviation_and_carries_its_citation():
    x = np.repeat(np.arange(1, 10) + 0.5, 1000)
    result = benford_test(x, "first", statistics=("mad",))
    by_hand = sum(abs(1.0 / 9.0 - p) for p in benford_expected("first")) / 9.0
    assert result.mad.statistic == pytest.approx(by_hand)
    assert result.mad.pvalue is None
    assert "Nigrini" in result.mad.details["citation"]
    assert "confirm" in result.mad.details["citation"].lower()
    assert result.mad.details["bands"][MAD_LABELS[0]] == [0.0, MAD_BANDS["first"][0]]


def test_weighted_test_flags_its_approximation_and_scales_with_effective_n():
    x = np.repeat(np.arange(1, 10) + 0.5, 100)
    unweighted = benford_test(x, "first", statistics=("chi2",))
    weighted = benford_test(x, "first", weights=np.full(x.size, 3.0), statistics=("chi2",))
    # constant weights: identical proportions, identical effective n, identical statistic
    assert weighted.chi2.statistic == pytest.approx(unweighted.chi2.statistic)
    assert weighted.chi2.details["effective_n"] == pytest.approx(float(x.size))
    assert weighted.chi2.details["weighted_pvalue_is_approximate"] is True
    assert "weighted_pvalue_is_approximate" not in unweighted.chi2.details

    # unequal weights shrink the effective n, and the chi-square with it
    w = np.where(np.arange(x.size) % 2 == 0, 1.0, 9.0)
    uneven = benford_test(x, "first", weights=w, statistics=("chi2",))
    assert uneven.chi2.details["effective_n"] < x.size
    assert uneven.chi2.n == x.size


@pytest.mark.parametrize("position", POSITIONS)
def test_result_is_serialisable(position):
    result = benford_test(_exact_benford_sample(position, scale=2000), position)
    as_dict = result.to_dict()
    assert set(as_dict) == {"table", "chi2", "mad", "kuiper", "settings"}
    assert isinstance(as_dict["table"]["observed"], list)
    assert as_dict["chi2"]["method"] == f"benford_{position}_chi2"
    assert as_dict["mad"]["details"]["conformity"] in MAD_LABELS
    assert as_dict["kuiper"]["details"]["alternative"] == "greater"


def test_statistics_argument_is_validated_and_honoured():
    x = np.repeat(np.arange(1, 10) + 0.5, 20)
    only_mad = benford_test(x, statistics=("mad",))
    assert only_mad.mad is not None
    assert only_mad.chi2 is None
    assert only_mad.kuiper is None
    with pytest.raises(ValueError, match="unknown statistics"):
        benford_test(x, statistics=("chi2", "cramer_von_mises"))


def test_second_digit_test_runs_on_a_conforming_sample():
    x = 10 ** np.random.default_rng(5).uniform(0.0, 6.0, 30_000)
    result = benford_test(x, "second")
    assert result.chi2.details["df"] == 9
    assert result.chi2.pvalue > 0.01
    assert result.table.n <= x.size  # single-significant-digit values were excluded


def test_first_two_digit_test_has_ninety_cells():
    x = 10 ** np.random.default_rng(6).uniform(0.0, 6.0, 40_000)
    result = benford_test(x, "first_two")
    assert result.table.digits.size == 90
    assert result.chi2.details["df"] == 89
    assert result.chi2.pvalue > 0.01

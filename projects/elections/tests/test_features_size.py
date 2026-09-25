"""Precinct-size features. The arithmetic ones are checked against values worked out by hand.

``exact_integer_share`` is the function the integer-percentage trap turns on, so it is checked
against closed-form values rather than against itself: with 100 registered voters every
attainable percentage is a whole number, and with 2,500 the share is 101/2501, the "fewer than
1 in 20" quoted in ``docs/known_traps.md``.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from elections.features import (
    SIZE_BAND_EDGES,
    SIZE_BAND_LABELS,
    add_size_band,
    denominator_floor_summary,
    exact_integer_share,
    iter_size_strata,
    percentage_resolution,
    size_band,
    size_band_counts,
)


def test_the_documented_edges_are_present():
    """100 and 250 are the two figures docs/known_traps.md actually names."""
    assert 100.0 in SIZE_BAND_EDGES
    assert 250.0 in SIZE_BAND_EDGES
    assert len(SIZE_BAND_EDGES) == len(SIZE_BAND_LABELS) + 1
    assert SIZE_BAND_EDGES[-1] == math.inf
    assert list(SIZE_BAND_EDGES) == sorted(SIZE_BAND_EDGES)


def test_bands_are_right_closed_at_the_documented_edges():
    banded = size_band([1, 100, 101, 250, 251, 22671])
    assert list(banded) == ["1-100", "1-100", "101-250", "101-250", "251-500", "5001+"]


def test_a_station_with_no_registered_voters_gets_no_band():
    banded = size_band([0, -5, np.nan, 10])
    assert pd.isna(banded[0])
    assert pd.isna(banded[1])
    assert pd.isna(banded[2])
    assert banded[3] == "1-100"


def test_mismatched_edges_and_labels_are_refused():
    with pytest.raises(ValueError, match="edges need"):
        size_band([10], edges=(0.0, 100.0, np.inf), labels=("only-one",))


def test_add_size_band_copies_rather_than_mutates(duma_2011):
    before = list(duma_2011.columns)
    banded = add_size_band(duma_2011)
    assert list(duma_2011.columns) == before
    assert banded["size_band"].tolist()[:3] == ["1-100", "101-250", "1-100"]
    with pytest.raises(KeyError):
        add_size_band(duma_2011, column="electorate")


def test_size_band_counts_partition_each_election(tidy):
    counts = size_band_counts(tidy)
    for election in ("2011-duma", "2018-presidential"):
        rows = counts.loc[counts["election"] == election]
        assert rows["n"].sum() == 6, "every station, banded or not, is counted once"
        assert rows["share"].sum() == pytest.approx(1.0)
    duma = counts.loc[counts["election"] == "2011-duma"].set_index("size_band")["n"]
    # fixture sizes 100, 200, 50, 0, 1000, 2500
    assert duma.loc["1-100"] == 2
    assert duma.loc["101-250"] == 1
    assert duma.loc["501-1000"] == 1
    assert duma.loc["2001-5000"] == 1
    assert duma.loc["251-500"] == 0


def test_denominator_floor_summary_counts_what_the_floor_removes(duma_2011):
    summary = denominator_floor_summary(duma_2011["registered"], min_denominator=100)
    # sizes 100, 200, 50, 0, 1000, 2500: two below 100, none missing
    assert summary.n_total == 6
    assert summary.n_below == 2
    assert summary.n_missing == 0
    assert summary.n_kept == 4
    assert summary.share_below == pytest.approx(2 / 6)


def test_the_floor_is_inclusive_at_its_own_value():
    """A station with exactly min_denominator voters is kept, matching forensics_core."""
    assert denominator_floor_summary([100], min_denominator=100).n_below == 0
    assert denominator_floor_summary([99], min_denominator=100).n_below == 1


def test_missing_sizes_are_counted_separately_not_as_small():
    summary = denominator_floor_summary(pd.array([50, None, 500], dtype="Int64"))
    assert (summary.n_below, summary.n_missing, summary.n_kept) == (1, 1, 1)


def test_empty_sample_gives_nan_share_not_a_division_error():
    assert math.isnan(denominator_floor_summary([]).share_below)


def test_percentage_resolution_is_one_hundred_over_n():
    resolution = percentage_resolution([100, 200, 50, 0, 1000, 2500])
    np.testing.assert_allclose(
        resolution.to_numpy(), [1.0, 0.5, 2.0, np.nan, 0.1, 0.04], rtol=1e-12
    )


def test_exact_integer_share_closed_form():
    """(gcd(n, 100) + 1) / (n + 1), checked at the sizes the documentation talks about."""
    share = exact_integer_share([100, 250, 2500, 50, 3])
    assert share.iloc[0] == pytest.approx(1.0)  # every attainable percentage is an integer
    assert share.iloc[1] == pytest.approx(51 / 251)
    assert share.iloc[2] == pytest.approx(101 / 2501)
    assert share.iloc[2] < 0.05, "the 'fewer than 1 in 20' figure for 2,500 voters"
    assert share.iloc[3] == pytest.approx(1.0)  # 50 voters: every step is 2 percentage points
    assert share.iloc[4] == pytest.approx(2 / 4)  # gcd(3, 100) = 1


def test_exact_integer_share_falls_with_size_over_the_documented_range():
    share = exact_integer_share([100, 250, 1000, 2500])
    assert list(share) == sorted(share, reverse=True)


def test_exact_integer_share_rejects_a_non_integer_electorate():
    with pytest.raises(ValueError, match="integer-valued"):
        exact_integer_share([100.5])


def test_exact_integer_share_has_no_answer_for_an_empty_station():
    assert exact_integer_share([0, np.nan]).isna().all()


def test_iter_size_strata_yields_disjoint_bands_that_omit_unbanded_rows(duma_2011):
    strata = dict(iter_size_strata(duma_2011))
    assert list(strata) == ["1-100", "101-250", "501-1000", "2001-5000"]
    assert sum(len(sub) for sub in strata.values()) == 5, "the zero-voter station has no band"
    assert "size_band" not in strata["1-100"].columns
    seen = pd.concat(strata.values())
    assert seen.index.is_unique


def test_iter_size_strata_skips_bands_entirely_below_the_floor(duma_2011):
    labels = [label for label, _ in iter_size_strata(duma_2011, min_denominator=100)]
    assert "1-100" not in labels
    assert labels == ["101-250", "501-1000", "2001-5000"]


def test_iter_size_strata_can_keep_empty_bands(duma_2011):
    labels = [label for label, _ in iter_size_strata(duma_2011, skip_empty=False)]
    assert labels == list(SIZE_BAND_LABELS)

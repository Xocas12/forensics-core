"""The XBRL tag mapping: what it selects, what it excludes, and what it admits losing.

The synthetic quarter holds one firm with two annual filings, a duplicate later-filed 10-K for
one of those years, a 10-Q, and six decoy facts that each have to be excluded by exactly one
filter. Every expected value below is hand-computed from the fixture.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from aaer.clean import fsds
from aaer.clean import xbrl_map as xm
from aaer.features import beneish

ADSH_2019 = "0009000001-20-000001"
ADSH_2020 = "0009000001-21-000001"
ADSH_2020_LATE = "0009000001-21-000002"


@pytest.fixture
def quarter(fsds_zip: Path) -> fsds.FsdsQuarter:
    return fsds.read_fsds_zip(fsds_zip)


@pytest.fixture
def sub_one_filing_per_year(quarter: fsds.FsdsQuarter) -> pd.DataFrame:
    """The submissions table with the deliberately duplicated late 10-K removed.

    That duplicate exists so one test can prove which filing the deduplication keeps; every
    other test wants the firm's real figures, which live in the earlier filing.
    """
    return quarter.sub[quarter.sub["adsh"] != ADSH_2020_LATE]


# ------------------------------------------------------------------- the mapping as a table


def test_mapping_covers_every_item_beneish_requires():
    assert xm.check_mapping_covers_beneish() == ()
    assert set(xm.BENEISH_TAG_MAP) == set(beneish.REQUIRED_COLUMNS)


def test_every_entry_names_itself_and_lists_at_least_one_tag():
    for item, mapping in xm.BENEISH_TAG_MAP.items():
        assert mapping.item == item
        assert mapping.tags, f"{item} has no candidate tag"
        assert len(set(mapping.tags)) == len(mapping.tags), f"{item} repeats a tag"
        assert mapping.note.strip(), f"{item} has no note about what is doubtful"


def test_no_tag_is_claimed_by_two_items():
    """A tag mapped twice would let one item's value silently stand in for another's."""
    seen: dict[str, str] = {}
    for item, mapping in xm.BENEISH_TAG_MAP.items():
        for tag in mapping.tags:
            assert tag not in seen, f"{tag} is claimed by both {seen.get(tag)} and {item}"
            seen[tag] = item


def test_stocks_and_flows_select_different_qtrs_values():
    assert xm.BENEISH_TAG_MAP["total_assets"].kind == "instant"
    assert xm.BENEISH_TAG_MAP["total_assets"].qtrs == xm.QTRS_INSTANT == "0"
    assert xm.BENEISH_TAG_MAP["sales"].kind == "duration"
    assert xm.BENEISH_TAG_MAP["sales"].qtrs == xm.QTRS_ANNUAL == "4"


def test_only_the_observed_tag_is_marked_confirmed():
    """Honesty check: exactly one element name was seen in a fetched SEC response."""
    assert xm.CONFIRMED_ITEMS == ("receivables",)
    assert len(xm.UNCONFIRMED_ITEMS) == len(beneish.REQUIRED_COLUMNS) - 1
    assert "AccountsReceivableNetCurrent" in xm.BENEISH_TAG_MAP["receivables"].tags


def test_mapping_table_has_one_row_per_item():
    table = xm.mapping_table()
    assert len(table) == len(beneish.REQUIRED_COLUMNS)
    assert set(table["item"]) == set(beneish.REQUIRED_COLUMNS)
    assert int(table["confirmed"].sum()) == 1


# --------------------------------------------------------------------- selecting submissions


def test_only_annual_filings_survive_and_duplicates_collapse_to_the_latest(quarter):
    annual = xm.annual_submissions(quarter.sub)
    assert len(annual) == 2, "the 10-Q is excluded and the two 2020 10-Ks collapse to one"
    assert sorted(int(y) for y in annual["fy"]) == [2019, 2020]
    latest_2020 = annual.loc[annual["fy"] == 2020, "adsh"].iloc[0]
    assert latest_2020 == ADSH_2020_LATE, "the 2021-09-01 filing was filed after the 2021-02-15 one"
    assert str(annual["fy"].dtype) == "Int64"


def test_form_filter_is_configurable_and_excludes_by_default(quarter):
    both = xm.annual_submissions(quarter.sub, forms=("10-K", "10-Q"), fiscal_period="Q1")
    assert list(both["adsh"]) == ["0009000002-21-000001"]


# ------------------------------------------------------------------------- mapping the facts


def test_maps_one_row_per_firm_year_with_hand_computed_values(quarter, sub_one_filing_per_year):
    result = xm.map_beneish_items(sub_one_filing_per_year, quarter.num)
    frame = result.frame.set_index("fy")
    assert sorted(frame.index) == [2019, 2020]

    assert frame.loc[2019, "total_assets"] == 1000.0
    assert frame.loc[2019, "receivables"] == 100.0
    assert frame.loc[2019, "sales"] == 1000.0
    assert frame.loc[2019, "cogs"] == 600.0
    assert frame.loc[2020, "receivables"] == 200.0
    assert frame.loc[2020, "cogs"] == 700.0
    assert frame.loc[2020, "income_continuing_ops"] == 90.0
    assert frame.loc[2020, "cash_from_operations"] == 70.0


def test_the_deduplicated_submission_decides_which_value_is_used(quarter):
    """The later 10-K reports total assets 9999; the earlier one reports 1000."""
    result = xm.map_beneish_items(quarter.sub, quarter.num)
    frame = result.frame.set_index("fy")
    assert frame.loc[2020, "adsh"] == ADSH_2020_LATE
    assert frame.loc[2020, "total_assets"] == 9999.0
    # restricting to the earlier filing recovers the other value, which proves the join is real
    other = xm.map_beneish_items(
        quarter.sub[quarter.sub["adsh"] != ADSH_2020_LATE], quarter.num
    ).frame.set_index("fy")
    assert other.loc[2020, "total_assets"] == 1000.0
    assert other.loc[2020, "adsh"] == ADSH_2020


@pytest.mark.parametrize(
    ("decoy_value", "what_excludes_it"),
    [
        (7777.0, "ddate is the prior-year comparative, not the filing's own period"),
        (8888.0, "version is a filer extension, not us-gaap"),
        (6666.0, "segments is non-empty: a dimensional breakdown"),
        (5555.0, "coreg is non-empty: a co-registrant figure"),
        (4444.0, "uom is EUR, not USD"),
        (3333.0, "qtrs is 0 on a flow item that must be a four-quarter duration"),
        (2222.0, "the submission is a 10-Q"),
    ],
)
def test_each_decoy_fact_is_excluded(
    quarter, sub_one_filing_per_year, decoy_value, what_excludes_it
):
    frame = xm.map_beneish_items(sub_one_filing_per_year, quarter.num).frame
    numeric = frame[list(beneish.REQUIRED_COLUMNS)].to_numpy(dtype=float)
    assert decoy_value not in set(numeric[~np.isnan(numeric)]), what_excludes_it


def test_step_counts_account_for_every_loss(quarter):
    """The full fixture: 4 submissions, of which 2 are annual after deduplication.

    Only the 2019 firm-year is complete on all twelve items, because the 2020 filing that wins
    the deduplication is the late duplicate that reports total assets and nothing else. That is
    the loss the step table exists to make visible.
    """
    result = xm.map_beneish_items(quarter.sub, quarter.num)
    steps = result.steps.set_index("step")["n_rows"].to_dict()
    assert steps["submissions in input"] == 4
    assert steps["annual filings, deduplicated to one per (cik, fy)"] == 2
    assert steps["firm-years with at least one mapped fact"] == 2
    assert steps["firm-years complete on all 12 items"] == 1
    lost = result.steps.set_index("step")["n_lost"].to_dict()
    assert lost["annual filings, deduplicated to one per (cik, fy)"] == 2
    assert lost["firm-years complete on all 12 items"] == 1


def test_step_counts_when_every_firm_year_is_complete(quarter, sub_one_filing_per_year):
    result = xm.map_beneish_items(sub_one_filing_per_year, quarter.num)
    steps = result.steps.set_index("step")["n_rows"].to_dict()
    assert steps["submissions in input"] == 3
    assert steps["annual filings, deduplicated to one per (cik, fy)"] == 2
    assert steps["firm-years complete on all 12 items"] == 2


def test_item_coverage_reports_present_and_missing_counts(quarter, sub_one_filing_per_year):
    result = xm.map_beneish_items(sub_one_filing_per_year, quarter.num)
    coverage = result.item_coverage.set_index("item")
    assert len(coverage) == 12
    assert int(coverage["n_present"].sum()) == 24
    assert int(coverage["n_missing"].sum()) == 0
    assert coverage.loc["receivables", "share_present"] == pytest.approx(1.0)
    assert "AccountsReceivableNetCurrent=2" in coverage.loc["receivables", "tags_used"]
    assert result.unmapped_items == ()


def test_an_item_with_no_matching_fact_is_reported_not_dropped(quarter):
    """Deleting every Assets fact must surface as an unmapped item, not as a shorter table."""
    without_assets = quarter.num[quarter.num["tag"] != "Assets"]
    result = xm.map_beneish_items(quarter.sub, without_assets)
    assert "total_assets" in result.unmapped_items
    assert "total_assets" in result.frame.columns
    assert result.frame["total_assets"].isna().all()
    coverage = result.item_coverage.set_index("item")
    assert int(coverage.loc["total_assets", "n_present"]) == 0
    assert "UNMAPPED ITEMS" in result.summary()


def test_no_annual_filing_at_all_yields_an_empty_but_typed_frame(quarter):
    only_quarterly = quarter.sub[quarter.sub["form"] == "10-Q"]
    result = xm.map_beneish_items(only_quarterly, quarter.num)
    assert len(result.frame) == 0
    for item in beneish.REQUIRED_COLUMNS:
        assert item in result.frame.columns
    assert set(result.unmapped_items) == set(beneish.REQUIRED_COLUMNS)


def test_tag_frequency_flags_which_tags_the_mapping_knows(quarter):
    counts = xm.tag_frequency(quarter.num).set_index("tag")
    assert bool(counts.loc["Assets", "in_mapping"])
    assert counts.loc["Assets", "mapped_item"] == "total_assets"
    # 3 usable facts (2019, 2020, the late duplicate), 5 decoys, and one on the 10-Q
    assert int(counts.loc["Assets", "n_facts"]) == 9


# ---------------------------------------------------------------------------------- lagging


def test_lags_come_from_the_prior_years_own_filing(quarter, sub_one_filing_per_year):
    mapped = xm.map_beneish_items(sub_one_filing_per_year, quarter.num)
    lagged = xm.add_lags(mapped.frame)

    assert lagged.n_input_rows == 2
    assert lagged.n_with_any_lag == 1
    assert lagged.n_with_all_lags == 1

    frame = lagged.frame.set_index("fy")
    assert frame.loc[2020, "receivables_lag"] == 100.0
    assert frame.loc[2020, "total_assets_lag"] == 1000.0
    assert frame.loc[2020, "cogs_lag"] == 600.0
    assert pd.isna(frame.loc[2019, "total_assets_lag"]), "the first year a firm appears has no lag"


def test_lagged_columns_are_exactly_the_ones_beneish_asks_for(quarter, sub_one_filing_per_year):
    lagged = xm.add_lags(xm.map_beneish_items(sub_one_filing_per_year, quarter.num).frame)
    for column in (*beneish.REQUIRED_COLUMNS, *beneish.LAGGED_COLUMNS):
        assert column in lagged.frame.columns
    # income and cash flow are flows of year t only and must not acquire a lag column
    assert "income_continuing_ops_lag" not in lagged.frame.columns
    assert "cash_from_operations_lag" not in lagged.frame.columns


def test_add_lags_rejects_a_frame_missing_its_key():
    with pytest.raises(ValueError, match="missing columns"):
        xm.add_lags(pd.DataFrame({"fy": [2019], "total_assets": [1.0]}))


def test_the_mapped_and_lagged_frame_feeds_beneish_and_recovers_an_injected_effect(
    quarter, sub_one_filing_per_year
):
    """End to end on synthetic values: receivables double while sales are flat, so DSRI is 2.

    This is a plumbing test, not a finding. It asserts that the column names produced by the
    mapper are exactly the ones ``beneish_components`` consumes, and that a doubling injected
    into the fixture comes back out.
    """
    lagged = xm.add_lags(xm.map_beneish_items(sub_one_filing_per_year, quarter.num).frame)
    usable = lagged.frame[lagged.frame["fy"] == 2020]
    components = beneish.beneish_components(usable)

    assert components["DSRI"].iloc[0] == pytest.approx(2.0)  # (200/1000) / (100/1000)
    assert components["SGI"].iloc[0] == pytest.approx(1.0)  # sales flat
    assert components["GMI"].iloc[0] == pytest.approx(0.4 / 0.3)  # margin 40% -> 30%
    assert components["AQI"].iloc[0] == pytest.approx(1.0)
    assert components["TATA"].iloc[0] == pytest.approx(0.02)  # (90 - 70) / 1000

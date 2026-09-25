"""The loader: mapping, typing, padding and the errors it must raise instead of guessing."""

from __future__ import annotations

import zipfile

import pandas as pd
import pytest
from elections.clean import (
    CANONICAL_COLUMNS,
    MISSING_CANONICAL_COLUMNS,
    RawFileMissing,
    SchemaError,
    build_tidy,
    load_election,
    raw_path,
    read_raw,
)
from elections.clean.schema import COUNT_COLUMNS


def test_both_elections_land_on_the_same_columns_in_the_same_order(duma_2011, presidential_2018):
    assert list(duma_2011.columns) == list(CANONICAL_COLUMNS)
    assert list(presidential_2018.columns) == list(CANONICAL_COLUMNS)


def test_counts_are_nullable_integers_and_identifiers_are_text(duma_2011):
    for column in COUNT_COLUMNS:
        assert str(duma_2011[column].dtype) == "Int64", column
    for column in ("election", "region", "tik", "winner_label", "source_url"):
        assert str(duma_2011[column].dtype) == "string", column


def test_the_map_puts_the_right_numbers_in_the_right_columns(duma_2011):
    """Row 1 of the 2011 fixture, read straight off the file."""
    row = duma_2011.iloc[0]
    assert row["region"] == "Testonia"
    assert row["uik"] == 1
    assert row["registered"] == 100
    assert row["ballots_received"] == 120
    assert row["ballots_early"] == 2
    assert row["ballots_in_station"] == 60
    assert row["ballots_outside"] == 10
    assert row["ballots_cancelled"] == 50
    assert row["in_mobile_boxes"] == 10
    assert row["in_stationary_boxes"] == 60
    assert row["invalid"] == 5
    assert row["valid"] == 65
    assert row["lost_ballots"] == 0
    assert row["unaccounted_ballots"] == 0
    assert row["party_6_edinaya_rossiya"] == 35
    assert row["source_url"] == "https://example.invalid/uik/1"


def test_2018_candidates_are_mapped_in_ballot_order(presidential_2018):
    row = presidential_2018.iloc[0]
    assert row["cand_1_baburin"] == 2
    assert row["cand_2_grudinin"] == 8
    assert row["cand_3_zhirinovsky"] == 6
    assert row["cand_4_putin"] == 30
    assert row["cand_8_yavlinsky"] == 2


def test_columns_an_election_does_not_have_are_present_and_wholly_null(
    duma_2011, presidential_2018
):
    for column in MISSING_CANONICAL_COLUMNS["2011-duma"]:
        assert duma_2011[column].isna().all(), column
    for column in MISSING_CANONICAL_COLUMNS["2018-presidential"]:
        assert presidential_2018[column].isna().all(), column
    # and the ones it does have are not null anywhere in these fixtures
    assert duma_2011["party_6_edinaya_rossiya"].notna().all()
    assert presidential_2018["cand_4_putin"].notna().all()


def test_winner_columns_carry_the_election_specific_contestant(
    duma_2011, presidential_2018, hand_computed
):
    assert (duma_2011["winner_label"] == "United Russia").all()
    assert duma_2011["winner_votes"].equals(duma_2011["party_6_edinaya_rossiya"])
    assert int(duma_2011["winner_votes"].sum()) == hand_computed["winner_total"]["2011-duma"]
    assert (presidential_2018["winner_label"] == "Putin").all()
    assert presidential_2018["winner_votes"].equals(presidential_2018["cand_4_putin"])
    assert (
        int(presidential_2018["winner_votes"].sum())
        == hand_computed["winner_total"]["2018-presidential"]
    )


def test_totals_match_the_hand_computed_fixture_values(duma_2011, presidential_2018, hand_computed):
    assert len(duma_2011) == hand_computed["rows"]
    assert int(duma_2011["registered"].sum()) == hand_computed["registered_total"]["2011-duma"]
    assert (
        int(presidential_2018["registered"].sum())
        == (hand_computed["registered_total"]["2018-presidential"])
    )


def test_attrs_keep_the_raw_header_for_later_confirmation(duma_2011):
    header = duma_2011.attrs["raw_header"]
    assert len(header) == 29
    assert header[0] == "region"
    assert header[-1] == "url"
    assert duma_2011.attrs["election"] == "2011-duma"
    assert duma_2011.attrs["missing_canonical_columns"] == list(
        MISSING_CANONICAL_COLUMNS["2011-duma"]
    )


def test_a_zipped_file_reads_identically_to_the_plain_one(fixture_paths, tmp_path):
    """The real files arrive zipped; pandas infers that from the suffix."""
    source = fixture_paths["2011-duma"]
    archive = tmp_path / "2011.csv.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source, arcname="2011.csv")
    from_zip = read_raw(archive, "2011-duma")
    from_csv = read_raw(source, "2011-duma")
    pd.testing.assert_frame_equal(from_zip, from_csv, check_like=False)


def test_reading_the_wrong_election_raises_rather_than_mis_mapping(fixture_paths):
    with pytest.raises(SchemaError):
        read_raw(fixture_paths["2011-duma"], "2018-presidential")


def test_a_missing_raw_file_says_how_to_get_it(tmp_path):
    with pytest.raises(RawFileMissing, match="make data"):
        read_raw(tmp_path / "not-acquired.csv.zip", "2011-duma")


def test_load_election_reports_the_missing_file_by_its_expected_path(tmp_path):
    with pytest.raises(RawFileMissing) as excinfo:
        load_election("2018-presidential", tmp_path)
    assert "2018.csv.zip" in str(excinfo.value)


def test_raw_path_follows_the_acquire_layout(tmp_path):
    assert raw_path("2011-duma", tmp_path) == tmp_path / "raw" / "dkobak" / "2011.csv.zip"
    with pytest.raises(SchemaError):
        raw_path("2024-presidential", tmp_path)


def test_build_tidy_stacks_the_acquired_files(tmp_path, fixture_paths, hand_computed):
    """End to end through the real entry point, on a synthetic data directory."""
    for election, source in fixture_paths.items():
        target = raw_path(election, tmp_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(source, arcname=f"{election}.csv")

    stacked = build_tidy(tmp_path, validate=False)
    assert len(stacked) == 2 * hand_computed["rows"]
    assert list(stacked.columns) == list(CANONICAL_COLUMNS)
    assert set(stacked["election"]) == {"2011-duma", "2018-presidential"}
    assert set(stacked.attrs["raw_headers"]) == {"2011-duma", "2018-presidential"}

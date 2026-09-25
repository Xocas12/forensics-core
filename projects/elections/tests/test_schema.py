"""The column map must be complete, disjoint where it claims to be, and self-checking."""

from __future__ import annotations

import csv

import pytest
from elections.clean import schema


def test_positional_map_covers_every_raw_column_exactly_once():
    for election in schema.ELECTIONS:
        positions = schema.column_positions(election)
        expected_n = schema.EXPECTED_N_COLUMNS[election]
        assert sorted(positions) == list(range(expected_n))
        assert len(set(positions.values())) == expected_n, "a canonical name is reused"


def test_map_targets_are_canonical_columns():
    for election in schema.ELECTIONS:
        targets = set(schema.column_positions(election).values())
        assert targets <= set(schema.CANONICAL_COLUMNS)


def test_missing_columns_are_exactly_the_ones_the_map_does_not_fill():
    for election in schema.ELECTIONS:
        mapped = set(schema.column_positions(election).values())
        # winner_label, winner_votes and election are added by the loader, not mapped.
        derived = {"election", "winner_label", "winner_votes"}
        unfilled = set(schema.CANONICAL_COLUMNS) - mapped - derived
        assert unfilled == set(schema.MISSING_CANONICAL_COLUMNS[election])


def test_the_two_elections_share_the_protocol_columns_and_differ_on_the_rest():
    mapped_2011 = set(schema.column_positions("2011-duma").values())
    mapped_2018 = set(schema.column_positions("2018-presidential").values())
    assert set(schema.PROTOCOL_COLUMNS) <= mapped_2011 & mapped_2018
    assert set(schema.ABSENTEE_COLUMNS) <= mapped_2011
    assert not set(schema.ABSENTEE_COLUMNS) & mapped_2018
    assert set(schema.PARTY_COLUMNS_2011) & mapped_2018 == set()
    assert set(schema.CANDIDATE_COLUMNS_2018) & mapped_2011 == set()


def test_winner_column_is_a_contestant_of_its_own_election():
    for election in schema.ELECTIONS:
        assert schema.WINNER_COLUMN[election] in schema.contestant_columns(election)
    # United Russia sits at raw index 26 in the 2011 file (docs/data_dictionary.md).
    assert schema.column_positions("2011-duma")[26] == "party_6_edinaya_rossiya"
    # Putin is the fourth of eight candidates, raw index 18 in the 2018 file.
    assert schema.column_positions("2018-presidential")[18] == "cand_4_putin"


def test_canonical_columns_for_drops_only_the_missing_ones():
    for election in schema.ELECTIONS:
        available = schema.canonical_columns_for(election)
        missing = set(schema.MISSING_CANONICAL_COLUMNS[election])
        assert set(available) == set(schema.CANONICAL_COLUMNS) - missing
        assert list(available) == [c for c in schema.CANONICAL_COLUMNS if c in set(available)]


@pytest.fixture
def good_headers(fixture_paths):
    """The synthetic files' own headers, which are built to satisfy the rules."""
    headers = {}
    for election, path in fixture_paths.items():
        with path.open(encoding="utf-8") as handle:
            headers[election] = next(csv.reader(handle))
    return headers


def test_verify_header_accepts_the_synthetic_headers(good_headers):
    for election, header in good_headers.items():
        schema.verify_header(header, election)  # must not raise


def test_verify_header_rejects_a_wrong_column_count(good_headers):
    header = good_headers["2011-duma"][:-1]
    with pytest.raises(schema.SchemaError, match="expected 29 columns, found 28"):
        schema.verify_header(header, "2011-duma")


def test_verify_header_rejects_swapped_ballot_box_columns(good_headers):
    """The swap the arithmetic checks cannot see: mobile and stationary exchanged."""
    header = list(good_headers["2011-duma"])
    header[9], header[10] = header[10], header[9]
    with pytest.raises(schema.SchemaError) as excinfo:
        schema.verify_header(header, "2011-duma")
    assert "in_mobile_boxes" in str(excinfo.value)
    assert "in_stationary_boxes" in str(excinfo.value)


def test_verify_header_rejects_valid_where_invalid_belongs(good_headers):
    """Invalid and valid differ by one prefix; the exclusion rule is what catches it."""
    header = list(good_headers["2018-presidential"])
    header[12] = header[11]
    with pytest.raises(schema.SchemaError) as excinfo:
        schema.verify_header(header, "2018-presidential")
    assert "[12] -> valid" in str(excinfo.value)


def test_verify_header_rejects_a_renamed_identifier(good_headers):
    header = list(good_headers["2018-presidential"])
    header[2] = "precinct"
    with pytest.raises(schema.SchemaError, match="expected 'uik', found 'precinct'"):
        schema.verify_header(header, "2018-presidential")


def test_verify_header_rejects_the_wrong_elections_header(good_headers):
    with pytest.raises(schema.SchemaError):
        schema.verify_header(good_headers["2011-duma"], "2018-presidential")


def test_unknown_election_is_rejected_everywhere():
    for call in (
        lambda: schema.column_positions("2012-presidential"),
        lambda: schema.contestant_columns("2012-presidential"),
        lambda: schema.canonical_columns_for("2012-presidential"),
        lambda: schema.verify_header(["region"], "2012-presidential"),
    ):
        with pytest.raises(schema.SchemaError, match="unknown election"):
            call()

"""Every acceptance check must raise on a violated input, and pass on a clean one.

The published anchors (95,225 rows, 109,229,337 registered voters, 32,371,737 votes for the
winning list in 2011) can only be satisfied by the real file, which is not in this repository.
So the passing branch is exercised by monkeypatching each anchor to the synthetic file's own
hand-computed value, and the anchors themselves are asserted separately as constants.
"""

from __future__ import annotations

import pandas as pd
import pytest
from elections.clean import checks


def test_the_published_anchors_are_the_documented_ones():
    """docs/validation_anchors.md, Tier 0."""
    assert checks.EXPECTED_ROW_COUNTS == {"2011-duma": 95_225, "2018-presidential": 97_699}
    assert checks.EXPECTED_REGISTERED_TOTALS == {
        "2011-duma": 109_229_337,
        "2018-presidential": 109_008_428,
    }
    assert checks.EXPECTED_WINNER_TOTALS == {"2011-duma": 32_371_737}


# --------------------------------------------------------------------------------------
# row count
# --------------------------------------------------------------------------------------


def test_row_count_passes_at_the_anchor_and_fails_off_it(duma_2011, monkeypatch):
    monkeypatch.setitem(checks.EXPECTED_ROW_COUNTS, "2011-duma", len(duma_2011))
    checks.check_row_count(duma_2011, "2011-duma")
    with pytest.raises(checks.IntegrityError, match=r"loaded 5"):
        checks.check_row_count(duma_2011.iloc[:-1], "2011-duma")


def test_row_count_reports_the_signed_shortfall(duma_2011):
    with pytest.raises(checks.IntegrityError) as excinfo:
        checks.check_row_count(duma_2011, "2011-duma")
    assert "95,225" in str(excinfo.value)
    assert "-95,219" in str(excinfo.value)


# --------------------------------------------------------------------------------------
# registered voters
# --------------------------------------------------------------------------------------


def test_registered_total_passes_at_the_anchor(duma_2011, monkeypatch, hand_computed):
    monkeypatch.setitem(
        checks.EXPECTED_REGISTERED_TOTALS,
        "2011-duma",
        hand_computed["registered_total"]["2011-duma"],
    )
    checks.check_registered_total(duma_2011, "2011-duma")


def test_registered_total_fails_when_one_station_is_altered(duma_2011, monkeypatch, hand_computed):
    monkeypatch.setitem(
        checks.EXPECTED_REGISTERED_TOTALS,
        "2011-duma",
        hand_computed["registered_total"]["2011-duma"],
    )
    tampered = duma_2011.copy()
    tampered.loc[0, "registered"] = tampered.loc[0, "registered"] + 1
    with pytest.raises(checks.IntegrityError, match=r"\+1"):
        checks.check_registered_total(tampered, "2011-duma")


def test_a_null_in_the_denominator_is_refused_rather_than_skipped(duma_2011, monkeypatch):
    monkeypatch.setitem(checks.EXPECTED_REGISTERED_TOTALS, "2011-duma", 0)
    holed = duma_2011.copy()
    holed.loc[0, "registered"] = pd.NA
    with pytest.raises(checks.IntegrityError, match="null values"):
        checks.check_registered_total(holed, "2011-duma")


def test_a_frame_without_the_column_is_refused(duma_2011):
    with pytest.raises(checks.IntegrityError, match="missing required columns"):
        checks.check_registered_total(duma_2011.drop(columns=["registered"]), "2011-duma")


# --------------------------------------------------------------------------------------
# winner total
# --------------------------------------------------------------------------------------


def test_winner_total_passes_at_the_anchor(duma_2011, monkeypatch, hand_computed):
    monkeypatch.setitem(
        checks.EXPECTED_WINNER_TOTALS, "2011-duma", hand_computed["winner_total"]["2011-duma"]
    )
    checks.check_winner_total(duma_2011, "2011-duma")


def test_winner_total_fails_off_the_anchor(duma_2011, monkeypatch, hand_computed):
    monkeypatch.setitem(
        checks.EXPECTED_WINNER_TOTALS, "2011-duma", hand_computed["winner_total"]["2011-duma"] + 7
    )
    with pytest.raises(checks.IntegrityError, match=r"-7"):
        checks.check_winner_total(duma_2011, "2011-duma")


def test_2018_has_no_winner_anchor_and_says_so(presidential_2018):
    """Honest gap, not a silent pass: three published figures disagree."""
    with pytest.raises(checks.NoAnchorError, match="ACCESS_NOTES"):
        checks.check_winner_total(presidential_2018, "2018-presidential")


# --------------------------------------------------------------------------------------
# the ballot identity
# --------------------------------------------------------------------------------------


def test_ballot_identity_holds_on_both_synthetic_files(duma_2011, presidential_2018):
    checks.check_ballot_identity(duma_2011)
    checks.check_ballot_identity(presidential_2018)


def test_ballot_identity_catches_a_single_broken_row(duma_2011):
    tampered = duma_2011.copy()
    tampered.loc[2, "in_stationary_boxes"] = tampered.loc[2, "in_stationary_boxes"] + 1
    with pytest.raises(checks.IntegrityError) as excinfo:
        checks.check_ballot_identity(tampered)
    assert "fails on 1 of 6 rows" in str(excinfo.value)
    assert "[2]" in str(excinfo.value)


def test_ballot_identity_treats_a_null_as_a_violation(duma_2011):
    holed = duma_2011.copy()
    holed.loc[1, "valid"] = pd.NA
    with pytest.raises(checks.IntegrityError, match="fails on 1 of 6 rows"):
        checks.check_ballot_identity(holed)


def test_ballot_identity_limits_how_many_offenders_it_names(duma_2011):
    tampered = duma_2011.copy()
    tampered["invalid"] = tampered["invalid"] + 1
    with pytest.raises(checks.IntegrityError) as excinfo:
        checks.check_ballot_identity(tampered, max_reported=2)
    message = str(excinfo.value)
    assert "fails on 6 of 6 rows" in message
    assert message.rstrip().endswith("[0, 1]")


# --------------------------------------------------------------------------------------
# keys and completeness
# --------------------------------------------------------------------------------------


def test_station_keys_are_unique_within_and_across_elections(tidy):
    checks.check_station_keys_unique(tidy)


def test_duplicated_station_keys_are_caught(duma_2011):
    doubled = pd.concat([duma_2011, duma_2011.iloc[[0]]], ignore_index=True)
    with pytest.raises(checks.IntegrityError, match="share a station key"):
        checks.check_station_keys_unique(doubled)


def test_stacking_two_elections_without_the_election_column_is_caught(duma_2011, presidential_2018):
    """The failure the election column exists to prevent: 2011 uik 1 and 2018 uik 1 collide."""
    renumbered = presidential_2018.copy()
    renumbered["uik"] = duma_2011["uik"].to_numpy()
    renumbered["region"] = duma_2011["region"].to_numpy()
    renumbered["tik"] = duma_2011["tik"].to_numpy()
    renumbered["election"] = "2011-duma"
    with pytest.raises(checks.IntegrityError, match="share a station key"):
        checks.check_station_keys_unique(pd.concat([duma_2011, renumbered], ignore_index=True))


def test_shared_columns_must_be_complete(duma_2011):
    checks.check_shared_columns_complete(duma_2011)
    holed = duma_2011.copy()
    holed.loc[0, "in_mobile_boxes"] = pd.NA
    with pytest.raises(checks.IntegrityError, match="in_mobile_boxes"):
        checks.check_shared_columns_complete(holed)


def test_election_specific_nulls_do_not_trip_the_completeness_check(presidential_2018):
    """The six absentee columns are null for all of 2018 and that is correct, not damage."""
    assert presidential_2018["abs_line_1"].isna().all()
    checks.check_shared_columns_complete(presidential_2018)


# --------------------------------------------------------------------------------------
# the whole battery
# --------------------------------------------------------------------------------------


def test_run_all_checks_reports_what_it_could_and_could_not_anchor(
    duma_2011, presidential_2018, monkeypatch, hand_computed
):
    for election, frame in (("2011-duma", duma_2011), ("2018-presidential", presidential_2018)):
        monkeypatch.setitem(checks.EXPECTED_ROW_COUNTS, election, len(frame))
        monkeypatch.setitem(
            checks.EXPECTED_REGISTERED_TOTALS, election, hand_computed["registered_total"][election]
        )
    monkeypatch.setitem(
        checks.EXPECTED_WINNER_TOTALS, "2011-duma", hand_computed["winner_total"]["2011-duma"]
    )

    report_2011 = checks.run_all_checks(duma_2011, "2011-duma")
    assert set(report_2011.passed) == {
        "row_count",
        "registered_total",
        "ballot_identity",
        "shared_columns_complete",
        "station_keys_unique",
        "winner_total",
    }
    assert report_2011.skipped == ()

    report_2018 = checks.run_all_checks(presidential_2018, "2018-presidential")
    assert "winner_total" not in report_2018.passed
    assert [name for name, _ in report_2018.skipped] == ["winner_total"]
    assert "no winner vote total has been confirmed" in report_2018.skipped[0][1]


def test_run_all_checks_stops_at_the_first_failure(duma_2011):
    with pytest.raises(checks.IntegrityError):
        checks.run_all_checks(duma_2011, "2011-duma")


def test_unknown_election_is_rejected():
    from elections.clean import SchemaError

    with pytest.raises(SchemaError, match="unknown election"):
        checks.check_row_count(pd.DataFrame(), "2007-duma")

"""The derived quantities, against values computed by hand from the fixture rows.

The 2011 fixture's first row is built so that the two turnout definitions disagree: 70 ballots
in the boxes but 72 issued, out of 100 registered voters. If a change to the code let one
definition stand in for the other, this file is where it shows up.
"""

from __future__ import annotations

import numpy as np
import pytest
from elections.clean import (
    SchemaError,
    add_derived,
    ballots_counted,
    turnout_ballots_in_boxes,
    turnout_ballots_issued,
    vote_share,
    winner_share,
)


def test_turnout_on_the_ballots_in_boxes_basis(duma_2011):
    turnout = turnout_ballots_in_boxes(duma_2011)
    # (mobile + stationary) / registered, row by row
    expected = [0.70, 0.60, 0.50, np.nan, 0.50, 0.60]
    np.testing.assert_allclose(turnout.to_numpy(), expected)
    assert turnout.name == "turnout_boxes"


def test_turnout_on_the_ballots_issued_basis_differs_where_the_protocol_differs(duma_2011):
    issued = turnout_ballots_issued(duma_2011)
    expected = [0.72, 0.60, 0.50, np.nan, 0.50, 0.60]
    np.testing.assert_allclose(issued.to_numpy(), expected)
    # row 0 is the one where they part company: 72 ballots issued, 70 in the boxes
    boxes = turnout_ballots_in_boxes(duma_2011)
    assert issued.iloc[0] != boxes.iloc[0]
    assert issued.iloc[0] == pytest.approx(0.72)


def test_a_station_with_no_registered_voters_gives_nan_not_infinity(duma_2011):
    turnout = turnout_ballots_in_boxes(duma_2011)
    assert duma_2011.loc[3, "registered"] == 0
    assert np.isnan(turnout.iloc[3])
    assert np.isfinite(turnout.drop(index=3).to_numpy()).all()


def test_as_percent_multiplies_by_exactly_one_hundred(duma_2011):
    fraction = turnout_ballots_in_boxes(duma_2011)
    percent = turnout_ballots_in_boxes(duma_2011, as_percent=True)
    np.testing.assert_allclose(percent.to_numpy(), fraction.to_numpy() * 100.0)
    assert percent.iloc[0] == pytest.approx(70.0)


def test_ballots_counted_is_valid_plus_invalid(duma_2011):
    np.testing.assert_allclose(
        ballots_counted(duma_2011).to_numpy(), [70.0, 120.0, 25.0, 0.0, 500.0, 1500.0]
    )


def test_vote_share_default_denominator_includes_invalid_ballots(duma_2011):
    # row 0: 35 votes for the winning list out of 65 valid + 5 invalid = 70
    with_invalid = vote_share(duma_2011, "party_6_edinaya_rossiya")
    assert with_invalid.iloc[0] == pytest.approx(35 / 70)
    without = vote_share(duma_2011, "party_6_edinaya_rossiya", include_invalid=False)
    assert without.iloc[0] == pytest.approx(35 / 65)
    assert with_invalid.name == "share_party_6_edinaya_rossiya"


def test_winner_share_matches_the_election_specific_column(duma_2011, presidential_2018):
    np.testing.assert_allclose(
        winner_share(duma_2011).to_numpy(),
        vote_share(duma_2011, "party_6_edinaya_rossiya").to_numpy(),
    )
    np.testing.assert_allclose(
        winner_share(presidential_2018).to_numpy(),
        vote_share(presidential_2018, "cand_4_putin").to_numpy(),
    )
    assert winner_share(duma_2011).name == "winner_share"


def test_a_contestant_the_election_did_not_have_is_all_nan(duma_2011):
    """2011 has no Putin column with data in it; the answer is NaN, never zero."""
    share = vote_share(duma_2011, "cand_4_putin")
    assert share.isna().all()


def test_derived_columns_are_appended_without_disturbing_the_original(duma_2011):
    before = list(duma_2011.columns)
    enriched = add_derived(duma_2011)
    assert list(duma_2011.columns) == before, "add_derived must not mutate its argument"
    assert list(enriched.columns) == [
        *before,
        "turnout_boxes",
        "turnout_issued",
        "winner_share",
    ]
    assert enriched.attrs["derived_scale"] == "fraction"
    assert add_derived(duma_2011, as_percent=True).attrs["derived_scale"] == "percent"


def test_a_frame_missing_a_needed_column_is_refused(duma_2011):
    with pytest.raises(SchemaError, match="in_mobile_boxes"):
        turnout_ballots_in_boxes(duma_2011.drop(columns=["in_mobile_boxes"]))

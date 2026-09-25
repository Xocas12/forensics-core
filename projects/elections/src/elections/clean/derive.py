"""The derived quantities, defined once. Trap 5 in ``docs/known_traps.md`` is why.

"Turnout" has two defensible definitions in these protocols and they do not agree: ballots
found in the boxes over registered voters, and ballots issued to voters over registered
voters. They differ by lost and unaccounted ballots. "Vote share" has two too, depending on
whether invalid ballots are in the denominator. Left implicit, the definition drifts between
elections and between analyses, and the drift looks like a finding.

So the definitions live here, they are named after what they divide, and every one of them
takes its numerator and denominator from named canonical columns rather than positions.

Scale. These return fractions in ``[0, 1]`` by default. Pass ``as_percent=True`` for the
0-100 scale that :func:`forensics_core.digits.integer_pct.integer_excess` expects; that
function's whole subject is the behaviour of a percentage near integers, so feeding it a
fraction silently measures nothing.

Denominators of zero. A station with no registered voters yields ``NaN``, never ``inf`` and
never zero, matching :func:`forensics_core.digits.integer_pct.percentage`. The 2011 file's
smallest station has 2 registered voters, so this is not hypothetical bookkeeping: division
guards and the small-precinct trap are the same problem seen from two sides.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from elections.clean.schema import SchemaError

__all__ = [
    "add_derived",
    "ballots_counted",
    "turnout_ballots_in_boxes",
    "turnout_ballots_issued",
    "vote_share",
    "winner_share",
]

#: Columns summed to give ballots actually found in the boxes.
_IN_BOXES = ("in_mobile_boxes", "in_stationary_boxes")

#: Columns summed to give ballots handed to voters.
_ISSUED = ("ballots_early", "ballots_in_station", "ballots_outside")


def _require(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise SchemaError(f"frame is missing columns {absent} needed for this quantity")


def _floats(frame: pd.DataFrame, columns: tuple[str, ...]) -> np.ndarray:
    """Row-wise sum of ``columns`` as float64, with nulls propagating to NaN."""
    stacked = [frame[c].to_numpy(dtype="float64", na_value=np.nan) for c in columns]
    return np.sum(stacked, axis=0)


def _ratio(
    frame: pd.DataFrame,
    numerator: tuple[str, ...],
    denominator: tuple[str, ...],
    *,
    as_percent: bool,
    name: str,
) -> pd.Series:
    num = _floats(frame, numerator)
    den = _floats(frame, denominator)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    if as_percent:
        out = out * 100.0
    return pd.Series(out, index=frame.index, name=name)


def ballots_counted(frame: pd.DataFrame) -> pd.Series:
    """Valid plus invalid ballots: the denominator of a vote share.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame carrying ``valid`` and ``invalid``.

    Returns
    -------
    pandas.Series
        Float series named ``ballots_counted``. Equal, row by row, to the ballots found in
        the boxes wherever :func:`elections.clean.checks.check_ballot_identity` passes.
    """
    _require(frame, ("valid", "invalid"))
    return pd.Series(
        _floats(frame, ("valid", "invalid")), index=frame.index, name="ballots_counted"
    )


def turnout_ballots_in_boxes(frame: pd.DataFrame, *, as_percent: bool = False) -> pd.Series:
    """Turnout on the ballots-in-boxes basis: ``(mobile + stationary) / registered``.

    The preferred definition in ``docs/data_dictionary.md``: it is available in both files and
    it is the quantity the published literature analyses, so a replication that used the other
    definition would not be comparing like with like.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame carrying ``in_mobile_boxes``, ``in_stationary_boxes`` and ``registered``.
    as_percent : bool, default False
        Return 0-100 instead of 0-1.

    Returns
    -------
    pandas.Series
        Named ``turnout_boxes``; ``NaN`` where ``registered`` is zero, negative or null.
    """
    _require(frame, (*_IN_BOXES, "registered"))
    return _ratio(frame, _IN_BOXES, ("registered",), as_percent=as_percent, name="turnout_boxes")


def turnout_ballots_issued(frame: pd.DataFrame, *, as_percent: bool = False) -> pd.Series:
    """Turnout on the ballots-issued basis: ``(early + in station + outside) / registered``.

    Differs from :func:`turnout_ballots_in_boxes` by lost and unaccounted ballots. Kept as a
    named alternative rather than a variant spelling, so that a result computed on this basis
    says so.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame carrying ``ballots_early``, ``ballots_in_station``, ``ballots_outside`` and
        ``registered``.
    as_percent : bool, default False
        Return 0-100 instead of 0-1.

    Returns
    -------
    pandas.Series
        Named ``turnout_issued``; ``NaN`` where ``registered`` is zero, negative or null.
    """
    _require(frame, (*_ISSUED, "registered"))
    return _ratio(frame, _ISSUED, ("registered",), as_percent=as_percent, name="turnout_issued")


def vote_share(
    frame: pd.DataFrame,
    contestant: str,
    *,
    include_invalid: bool = True,
    as_percent: bool = False,
) -> pd.Series:
    """Share of the vote for one party list or candidate.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame carrying ``contestant``, ``valid`` and ``invalid``.
    contestant : str
        A canonical contestant column, e.g. ``"party_6_edinaya_rossiya"`` or
        ``"cand_4_putin"``. Also accepts ``"winner_votes"``.
    include_invalid : bool, default True
        Denominator is ``valid + invalid`` when true and ``valid`` alone when false. The
        default follows ``docs/data_dictionary.md``, which records that the literature usually
        includes invalid ballots; the flag exists so that the choice is visible at every call
        site rather than assumed.
    as_percent : bool, default False
        Return 0-100 instead of 0-1.

    Returns
    -------
    pandas.Series
        Named ``share_<contestant>``; ``NaN`` where the denominator is zero or null, which for
        a contestant column that this election does not have means every row.
    """
    denominator = ("valid", "invalid") if include_invalid else ("valid",)
    _require(frame, (contestant, *denominator))
    return _ratio(
        frame,
        (contestant,),
        denominator,
        as_percent=as_percent,
        name=f"share_{contestant}",
    )


def winner_share(
    frame: pd.DataFrame, *, include_invalid: bool = True, as_percent: bool = False
) -> pd.Series:
    """Vote share of each election's contestant of record, from the ``winner_votes`` column.

    This is the one form of vote share that is comparable across the two elections, which is
    why the tidy frame carries ``winner_votes`` as a column of its own rather than leaving
    callers to remember that it is United Russia in 2011 and Putin in 2018.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame carrying ``winner_votes``, ``valid`` and ``invalid``.
    include_invalid : bool, default True
        As in :func:`vote_share`.
    as_percent : bool, default False
        Return 0-100 instead of 0-1.

    Returns
    -------
    pandas.Series
        Named ``winner_share``.
    """
    series = vote_share(
        frame, "winner_votes", include_invalid=include_invalid, as_percent=as_percent
    )
    return series.rename("winner_share")


def add_derived(frame: pd.DataFrame, *, as_percent: bool = False) -> pd.DataFrame:
    """Return a copy of ``frame`` with the three standard derived columns appended.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame.
    as_percent : bool, default False
        Scale of all three columns. Recorded in ``attrs["derived_scale"]`` so that a frame
        cannot be mistaken for the other scale later.

    Returns
    -------
    pandas.DataFrame
        Copy with ``turnout_boxes``, ``turnout_issued`` and ``winner_share`` added.
    """
    out = frame.copy()
    out["turnout_boxes"] = turnout_ballots_in_boxes(frame, as_percent=as_percent)
    out["turnout_issued"] = turnout_ballots_issued(frame, as_percent=as_percent)
    out["winner_share"] = winner_share(frame, as_percent=as_percent)
    out.attrs = {**frame.attrs, "derived_scale": "percent" if as_percent else "fraction"}
    return out

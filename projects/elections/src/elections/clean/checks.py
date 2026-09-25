"""Integrity checks that raise. These are the loader's acceptance criteria, not diagnostics.

Every check here was run against the real files during scaffolding and passed; the values are
recorded in ``docs/data_dictionary.md`` and ``docs/validation_anchors.md``. They are cheap,
and they fail on exactly the mistakes that are otherwise invisible: a mis-set encoding, a
column map applied to the wrong file, a partially written download, an upstream revision.

A check raises :class:`IntegrityError` rather than returning a flag because a frame that
fails one of them must not reach an analysis. Trap 4 in ``docs/known_traps.md`` is precisely
this: scraped hierarchical tables produce missing leaves and impossible rows, and the way
those become findings is by being carried silently into a test.

What is deliberately **not** asserted. There is no anchor for the winner's national vote total
in 2018. The commission's own portal summary (56,426,399) and its Resolution 152/1255-7
(56,430,712) disagree, the mirror's registered-voter sum matches the Resolution while its
winner total was never measured during scaffolding, and an independent scrape of the same
election taken six days after the vote gives a third number (56,437,774). Asserting any of
the three would be inventing an anchor. :func:`check_winner_total` raises
:class:`NoAnchorError` for 2018 instead, and ``data/ACCESS_NOTES.md`` records the choice as a
human decision.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from elections.clean.schema import (
    ELECTIONS,
    PROTOCOL_COLUMNS,
    WINNER_COLUMN,
    SchemaError,
)

__all__ = [
    "EXPECTED_REGISTERED_TOTALS",
    "EXPECTED_ROW_COUNTS",
    "EXPECTED_WINNER_TOTALS",
    "CheckReport",
    "IntegrityError",
    "NoAnchorError",
    "check_ballot_identity",
    "check_registered_total",
    "check_row_count",
    "check_shared_columns_complete",
    "check_station_keys_unique",
    "check_winner_total",
    "run_all_checks",
]


class IntegrityError(ValueError):
    """Raised when loaded data contradicts a documented, previously verified fact."""


class NoAnchorError(LookupError):
    """Raised when a check is asked for an election that has no confirmed published value."""


#: Rows per election. Counted from the raw CSVs during scaffolding and restated in the
#: mirror's own ``data/README.md``.
EXPECTED_ROW_COUNTS: dict[str, int] = {"2011-duma": 95_225, "2018-presidential": 97_699}

#: Sum of the registered-voter column. 2011 reproduces the commission's archived national
#: total exactly. 2018 matches Resolution 152/1255-7 and exceeds the portal summary's
#: 109,001,306 by 7,122, which the mirror attributes to four later-cancelled stations.
EXPECTED_REGISTERED_TOTALS: dict[str, int] = {
    "2011-duma": 109_229_337,
    "2018-presidential": 109_008_428,
}

#: Sum of the winning contestant's votes, where a value measured on *this file* exists.
#: 2018 is absent on purpose; see the module docstring.
EXPECTED_WINNER_TOTALS: dict[str, int] = {"2011-duma": 32_371_737}


@dataclass(frozen=True)
class CheckReport:
    """What :func:`run_all_checks` actually managed to check.

    Attributes
    ----------
    election : str
        The election the checks were run for.
    passed : tuple of str
        Names of the checks that ran and passed.
    skipped : tuple of tuple
        ``(check name, reason)`` for checks that could not run because no published anchor
        exists. A skipped check is a gap in the evidence and is reported as one; it is never
        counted as a pass.
    """

    election: str
    passed: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        head = f"{self.election}: {len(self.passed)} checks passed"
        if not self.skipped:
            return head
        tail = "; ".join(f"{name} skipped ({why})" for name, why in self.skipped)
        return f"{head}, {len(self.skipped)} not anchored: {tail}"


def _require_known_election(election: str) -> None:
    if election not in ELECTIONS:
        raise SchemaError(f"unknown election {election!r}; expected one of {ELECTIONS}")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    absent = [c for c in columns if c not in frame.columns]
    if absent:
        raise IntegrityError(f"frame is missing required columns: {absent}")


def _total(frame: pd.DataFrame, column: str) -> int:
    """Sum one count column as a Python int, refusing to skip nulls silently."""
    series = frame[column]
    n_null = int(series.isna().sum())
    if n_null:
        raise IntegrityError(
            f"column {column!r} has {n_null:,} null values; a total over it would be a "
            "sum of an unknown subset, not a national total"
        )
    return int(series.sum())


def check_row_count(frame: pd.DataFrame, election: str) -> None:
    """One row per polling station: 95,225 in 2011 and 97,699 in 2018.

    Parameters
    ----------
    frame : pandas.DataFrame
        Rows for a single election.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.

    Raises
    ------
    IntegrityError
        If the row count differs from :data:`EXPECTED_ROW_COUNTS`.
    """
    _require_known_election(election)
    expected = EXPECTED_ROW_COUNTS[election]
    if len(frame) != expected:
        raise IntegrityError(
            f"{election}: expected {expected:,} polling stations, loaded {len(frame):,} "
            f"({len(frame) - expected:+,})"
        )


def check_registered_total(frame: pd.DataFrame, election: str) -> None:
    """The registered-voter column must sum to the commission's national total.

    The strongest single check available: it is sensitive to a wrong column, a truncated
    file, a dropped region and a mis-set encoding all at once.

    Parameters
    ----------
    frame : pandas.DataFrame
        Rows for a single election, carrying a ``registered`` column.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.

    Raises
    ------
    IntegrityError
        If the sum differs from :data:`EXPECTED_REGISTERED_TOTALS`, or if the column has
        nulls.
    """
    _require_known_election(election)
    _require_columns(frame, ("registered",))
    expected = EXPECTED_REGISTERED_TOTALS[election]
    total = _total(frame, "registered")
    if total != expected:
        raise IntegrityError(
            f"{election}: registered voters sum to {total:,}, expected {expected:,} "
            f"({total - expected:+,})"
        )


def check_winner_total(frame: pd.DataFrame, election: str) -> None:
    """The winning contestant's votes must sum to the value measured on this file.

    Parameters
    ----------
    frame : pandas.DataFrame
        Rows for a single election.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.

    Raises
    ------
    NoAnchorError
        For 2018, which has no confirmed file-level winner total. Three published figures
        disagree and none of them was measured on these bytes; see the module docstring.
    IntegrityError
        If the sum differs from :data:`EXPECTED_WINNER_TOTALS`.
    """
    _require_known_election(election)
    expected = EXPECTED_WINNER_TOTALS.get(election)
    if expected is None:
        raise NoAnchorError(
            f"{election}: no winner vote total has been confirmed against this file; "
            "see data/ACCESS_NOTES.md, action 1"
        )
    column = WINNER_COLUMN[election]
    _require_columns(frame, (column,))
    total = _total(frame, column)
    if total != expected:
        raise IntegrityError(
            f"{election}: {column} sums to {total:,}, expected {expected:,} ({total - expected:+,})"
        )


def check_ballot_identity(frame: pd.DataFrame, *, max_reported: int = 10) -> None:
    """Ballots counted must equal ballots found: ``invalid + valid == mobile + stationary``.

    The commission's protocol makes this an accounting identity, and it held for all 95,225
    rows of the 2011 file during scaffolding. Nothing equivalent was ever measured on the 2018
    file; :func:`run_all_checks` applies the check there regardless, and its docstring says
    why and what to do when it fires. It is a per-row check, so unlike the national totals it
    localises the damage: a violated row is a specific station whose protocol did not add up
    or whose columns were mis-read.

    Parameters
    ----------
    frame : pandas.DataFrame
        Any number of elections' rows, carrying the four ballot columns.
    max_reported : int, default 10
        How many offending row labels to name in the error message.

    Raises
    ------
    IntegrityError
        If any row violates the identity. Null values count as violations: the identity
        cannot be shown to hold for a row whose counts are missing.
    """
    columns = ("invalid", "valid", "in_mobile_boxes", "in_stationary_boxes")
    _require_columns(frame, columns)
    counted = frame["invalid"] + frame["valid"]
    found = frame["in_mobile_boxes"] + frame["in_stationary_boxes"]
    holds = (counted == found).fillna(False).astype(bool)
    n_bad = int((~holds).sum())
    if n_bad:
        offenders = list(frame.index[~holds][:max_reported])
        raise IntegrityError(
            f"ballot identity invalid + valid == mobile + stationary fails on {n_bad:,} of "
            f"{len(frame):,} rows; first offending index labels: {offenders}"
        )


def check_station_keys_unique(frame: pd.DataFrame) -> None:
    """``(election, region, tik, uik)`` must identify a row uniquely.

    Recorded as true for both files during scaffolding. A duplicate means either a genuinely
    duplicated territorial commission in the scrape (trap 4 in ``docs/known_traps.md``) or two
    elections stacked without an ``election`` column.

    Parameters
    ----------
    frame : pandas.DataFrame
        The tidy frame, one or both elections.

    Raises
    ------
    IntegrityError
        If any key repeats.
    """
    key = ("election", "region", "tik", "uik")
    _require_columns(frame, key)
    duplicated = frame.duplicated(subset=list(key), keep=False)
    n_dup = int(duplicated.sum())
    if n_dup:
        sample = frame.loc[duplicated, list(key)].head(5).to_dict("records")
        raise IntegrityError(
            f"{n_dup:,} rows share a station key with another row; first examples: {sample}"
        )


def check_shared_columns_complete(frame: pd.DataFrame) -> None:
    """The twelve protocol lines that both elections publish must be non-null everywhere.

    These are the columns the whole project rests on, and they are the columns for which
    "missing" cannot mean "this election did not have it". Anything null here is a parsing or
    acquisition failure.

    Parameters
    ----------
    frame : pandas.DataFrame
        The tidy frame.

    Raises
    ------
    IntegrityError
        If any shared protocol column has a null value.
    """
    _require_columns(frame, PROTOCOL_COLUMNS)
    counts = {c: int(frame[c].isna().sum()) for c in PROTOCOL_COLUMNS}
    offenders = {c: n for c, n in counts.items() if n}
    if offenders:
        raise IntegrityError(f"shared protocol columns contain nulls: {offenders}")


def run_all_checks(frame: pd.DataFrame, election: str) -> CheckReport:
    """Run every applicable check on one election's rows and report what was checkable.

    One of them is applied further than it was measured. :func:`check_ballot_identity` was
    run against the 2011 file during scaffolding and held for all 95,225 rows; nothing was
    measured for 2018, so applying it there is an untested extension of a 2011 measurement,
    not a documented fact about the 2018 file. It is applied anyway because the identity is
    the commission's own protocol arithmetic and a silent failure of it would be worse than a
    loud one, but an operator should read a 2018 failure as "this assumption has not been
    tested here" first and as "the data is broken" second.

    Triage when that happens, in order: re-run the load with validation off
    (``load_election(..., validate=False)``, or ``python -m elections.clean --no-validate``,
    which is what stops :func:`elections.clean.loader.build_tidy` aborting on the first
    failure); then run the cell under "The arithmetic identity, and the rest of the acceptance
    checks" in ``notebooks/00_data_audit.ipynb``, which reports the identity instead of
    raising and displays the offending stations by region, TIK and UIK. Only with those rows
    in hand is it possible to say whether 2018 breaks the identity, or whether the column map
    is wrong for that file.

    Parameters
    ----------
    frame : pandas.DataFrame
        Rows for a single election, in the canonical schema.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.

    Returns
    -------
    CheckReport
        Names of the checks that passed and of any that could not run for want of a published
        anchor.

    Raises
    ------
    IntegrityError
        From the first check that fails. Nothing is aggregated: a frame that fails one of
        these is not fit to analyse, so there is no value in collecting the rest.
    """
    _require_known_election(election)
    passed: list[str] = []
    skipped: list[tuple[str, str]] = []

    check_row_count(frame, election)
    passed.append("row_count")
    check_registered_total(frame, election)
    passed.append("registered_total")
    check_ballot_identity(frame)
    passed.append("ballot_identity")
    check_shared_columns_complete(frame)
    passed.append("shared_columns_complete")
    if "election" in frame.columns:
        check_station_keys_unique(frame)
        passed.append("station_keys_unique")
    else:
        skipped.append(("station_keys_unique", "frame has no election column"))
    try:
        check_winner_total(frame, election)
    except NoAnchorError as exc:
        skipped.append(("winner_total", str(exc)))
    else:
        passed.append("winner_total")

    return CheckReport(election=election, passed=tuple(passed), skipped=tuple(skipped))

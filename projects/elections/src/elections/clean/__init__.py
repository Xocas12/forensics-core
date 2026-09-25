"""Turn the two raw precinct files into one tidy frame that both elections can share.

The problem this package exists for is stated in ``docs/data_dictionary.md``: the 2011 file
has 29 columns and the 2018 file 24, the absentee-certificate protocol lines were abolished
between them, and even the columns they share are labelled differently. There is no way to
stack them safely without an explicit, checked column map.

Four modules, in the order they run:

``schema``
    The column map itself, the canonical names, which columns each election does not have,
    and the header check that verifies the map against the file it is about to be applied to.
``loader``
    Read, verify, rename, cast, pad, stack, and write the Parquet.
``checks``
    The acceptance criteria, as functions that raise: row counts, national registered-voter
    totals, the winner's total where one has been confirmed, and the per-row ballot identity.
``derive``
    Turnout on both documented bases, and vote share, defined once so the definition cannot
    drift between elections.

Typical use::

    from elections.clean import build_tidy, add_derived
    tidy = add_derived(build_tidy())
"""

from elections.clean.checks import (
    EXPECTED_REGISTERED_TOTALS,
    EXPECTED_ROW_COUNTS,
    EXPECTED_WINNER_TOTALS,
    CheckReport,
    IntegrityError,
    NoAnchorError,
    check_ballot_identity,
    check_registered_total,
    check_row_count,
    check_shared_columns_complete,
    check_station_keys_unique,
    check_winner_total,
    run_all_checks,
)
from elections.clean.derive import (
    add_derived,
    ballots_counted,
    turnout_ballots_in_boxes,
    turnout_ballots_issued,
    vote_share,
    winner_share,
)
from elections.clean.loader import (
    DATA_DIR,
    TIDY_RELATIVE_PATH,
    RawFileMissing,
    build_tidy,
    load_election,
    raw_path,
    read_raw,
    write_tidy_parquet,
)
from elections.clean.schema import (
    CANONICAL_COLUMNS,
    ELECTIONS,
    MISSING_CANONICAL_COLUMNS,
    SchemaError,
    canonical_columns_for,
    column_positions,
    contestant_columns,
    verify_header,
)

__all__ = [
    "CANONICAL_COLUMNS",
    "DATA_DIR",
    "ELECTIONS",
    "EXPECTED_REGISTERED_TOTALS",
    "EXPECTED_ROW_COUNTS",
    "EXPECTED_WINNER_TOTALS",
    "MISSING_CANONICAL_COLUMNS",
    "TIDY_RELATIVE_PATH",
    "CheckReport",
    "IntegrityError",
    "NoAnchorError",
    "RawFileMissing",
    "SchemaError",
    "add_derived",
    "ballots_counted",
    "build_tidy",
    "canonical_columns_for",
    "check_ballot_identity",
    "check_registered_total",
    "check_row_count",
    "check_shared_columns_complete",
    "check_station_keys_unique",
    "check_winner_total",
    "column_positions",
    "contestant_columns",
    "load_election",
    "raw_path",
    "read_raw",
    "run_all_checks",
    "turnout_ballots_in_boxes",
    "turnout_ballots_issued",
    "verify_header",
    "vote_share",
    "winner_share",
    "write_tidy_parquet",
]

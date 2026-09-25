"""Raw zipped CSV in, one tidy frame out, with the acceptance checks run on the way through.

The pipeline is deliberately short and deliberately noisy:

1. read the raw CSV out of its zip as text, so that nothing is inferred from the values;
2. verify the header against :func:`elections.clean.schema.verify_header`, which is what makes
   the positional column map a checked assumption rather than a hope;
3. rename by position to the canonical names;
4. cast the count columns to nullable integers, so that a stray non-numeric value raises here
   instead of turning a column into text three steps later;
5. add ``election``, ``winner_label`` and ``winner_votes``, and pad out the columns the
   election does not have, so both elections share one schema;
6. run :func:`elections.clean.checks.run_all_checks`, which raises on any disagreement with
   the published totals.

Step 6 is on by default. It can be switched off, and the only good reason to do so is to look
at a file that has already failed it.

Nothing here writes into ``data/raw`` or ``data/interim``. :func:`write_tidy_parquet` is the
one function that writes at all, and it writes one file, to ``data/processed``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from elections.clean.checks import CheckReport, run_all_checks
from elections.clean.schema import (
    CANONICAL_COLUMNS,
    COUNT_COLUMNS,
    ELECTIONS,
    MISSING_CANONICAL_COLUMNS,
    RAW_RELATIVE_PATHS,
    WINNER_COLUMN,
    WINNER_LABEL,
    SchemaError,
    column_positions,
    verify_header,
)

__all__ = [
    "DATA_DIR",
    "TIDY_RELATIVE_PATH",
    "RawFileMissing",
    "build_tidy",
    "load_election",
    "raw_path",
    "read_raw",
    "write_tidy_parquet",
]

#: ``projects/elections/data``.
DATA_DIR: Path = Path(__file__).resolve().parents[3] / "data"

#: Where :func:`write_tidy_parquet` puts the tidy frame, relative to the data directory.
TIDY_RELATIVE_PATH = "processed/precincts.parquet"

#: Text columns of the tidy frame.
_TEXT_COLUMNS = ("election", "region", "tik", "winner_label", "source_url")


class RawFileMissing(FileNotFoundError):
    """Raised when a raw file has not been acquired yet."""


def raw_path(election: str, data_dir: Path | None = None) -> Path:
    """Where the raw file for one election is expected to be.

    Parameters
    ----------
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    data_dir : pathlib.Path, optional
        Project data directory; defaults to :data:`DATA_DIR`.

    Returns
    -------
    pathlib.Path
        Path under ``data/raw``, whether or not the file exists.
    """
    if election not in ELECTIONS:
        raise SchemaError(f"unknown election {election!r}; expected one of {ELECTIONS}")
    return (data_dir or DATA_DIR) / "raw" / RAW_RELATIVE_PATHS[election]


def read_raw(path: Path, election: str) -> pd.DataFrame:
    """Read one raw CSV (zipped or plain) and map it onto the canonical schema.

    No validation of totals happens here: this is the mapping step, and it is separated from
    the checking step so that a file which fails a check can still be inspected.

    Parameters
    ----------
    path : pathlib.Path
        The raw ``.csv.zip`` (or ``.csv``) as published by the mirror.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`; selects the column map.

    Returns
    -------
    pandas.DataFrame
        Columns exactly :data:`elections.clean.schema.CANONICAL_COLUMNS`, in that order.
        Counts are nullable ``Int64``; columns the election does not have are entirely null.
        ``attrs`` carries ``raw_header`` (the header as read, in file order), ``source_path``,
        ``election`` and ``missing_canonical_columns``.

    Raises
    ------
    RawFileMissing
        If ``path`` does not exist.
    SchemaError
        If the header does not match the documented column map.
    """
    path = Path(path)
    if not path.exists():
        raise RawFileMissing(
            f"{path} has not been acquired. Run `make data` (or "
            f"`python -m elections.acquire --all`) from projects/elections first."
        )

    # utf-8-sig, not utf-8: the mirror publishes UTF-8 without a byte-order mark, but a BOM
    # left by an intermediate tool would otherwise prefix the first column name with U+FEFF
    # and fail the header check for a reason that has nothing to do with the schema.
    # utf-8-sig reads plain UTF-8 identically.
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    raw_header = [str(c) for c in frame.columns]
    verify_header(raw_header, election)

    positions = column_positions(election)
    frame.columns = pd.Index([positions[i] for i in range(len(raw_header))])

    for column in frame.columns:
        if column in COUNT_COLUMNS:
            frame[column] = pd.to_numeric(frame[column]).astype("Int64")

    frame["election"] = election
    frame["winner_label"] = WINNER_LABEL[election]
    frame["winner_votes"] = frame[WINNER_COLUMN[election]]

    out = _pad_to_canonical(frame)
    out.attrs = {
        "raw_header": raw_header,
        "source_path": str(path),
        "election": election,
        "missing_canonical_columns": list(MISSING_CANONICAL_COLUMNS[election]),
    }
    return out


def _pad_to_canonical(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the canonical columns this election does not have, typed, and order the result."""
    out = pd.DataFrame(index=frame.index)
    for column in CANONICAL_COLUMNS:
        if column in frame.columns:
            out[column] = frame[column]
        elif column in COUNT_COLUMNS:
            out[column] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
        else:
            out[column] = pd.Series(pd.NA, index=frame.index, dtype="string")
    for column in _TEXT_COLUMNS:
        out[column] = out[column].astype("string")
    return out


def load_election(
    election: str,
    data_dir: Path | None = None,
    *,
    validate: bool = True,
) -> tuple[pd.DataFrame, CheckReport | None]:
    """Load one election from ``data/raw`` and, by default, check it against its anchors.

    Parameters
    ----------
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    data_dir : pathlib.Path, optional
        Project data directory; defaults to :data:`DATA_DIR`.
    validate : bool, default True
        Run :func:`elections.clean.checks.run_all_checks`.

    Returns
    -------
    frame : pandas.DataFrame
        In the canonical schema.
    report : CheckReport or None
        What was checked, or ``None`` when ``validate`` is false.

    Raises
    ------
    RawFileMissing
        If the file has not been acquired.
    elections.clean.checks.IntegrityError
        If the loaded data contradicts a published total or the ballot identity.
    """
    frame = read_raw(raw_path(election, data_dir), election)
    report = run_all_checks(frame, election) if validate else None
    return frame, report


def build_tidy(
    data_dir: Path | None = None,
    *,
    elections: Sequence[str] | None = None,
    validate: bool = True,
) -> pd.DataFrame:
    """Stack the elections into the single tidy frame the analysis layer consumes.

    Parameters
    ----------
    data_dir : pathlib.Path, optional
        Project data directory; defaults to :data:`DATA_DIR`.
    elections : sequence of str, optional
        Which elections to include; defaults to all of
        :data:`elections.clean.schema.ELECTIONS`.
    validate : bool, default True
        Run the acceptance checks on each election before stacking.

    Returns
    -------
    pandas.DataFrame
        One row per polling station per election, columns exactly
        :data:`elections.clean.schema.CANONICAL_COLUMNS`, index reset. ``attrs["checks"]``
        maps each election to the string form of its check report, and
        ``attrs["raw_headers"]`` keeps each file's header for reference.

    Raises
    ------
    RawFileMissing
        If any requested election has not been acquired.
    elections.clean.checks.IntegrityError
        From the first failing check.
    """
    wanted: Iterable[str] = elections if elections is not None else ELECTIONS
    frames: list[pd.DataFrame] = []
    reports: dict[str, str] = {}
    headers: dict[str, list[str]] = {}
    for election in wanted:
        frame, report = load_election(election, data_dir, validate=validate)
        headers[election] = list(frame.attrs["raw_header"])
        if report is not None:
            reports[election] = str(report)
        frames.append(frame)

    tidy = pd.concat(frames, ignore_index=True)
    tidy = tidy[list(CANONICAL_COLUMNS)]
    tidy.attrs = {"checks": reports, "raw_headers": headers}
    return tidy


def write_tidy_parquet(
    data_dir: Path | None = None,
    *,
    out_path: Path | None = None,
    elections: Sequence[str] | None = None,
    validate: bool = True,
) -> Path:
    """Build the tidy frame and write it to Parquet.

    The only function in this package that writes anything.

    Parameters
    ----------
    data_dir : pathlib.Path, optional
        Project data directory; defaults to :data:`DATA_DIR`.
    out_path : pathlib.Path, optional
        Destination; defaults to ``<data_dir>/processed/precincts.parquet``.
    elections : sequence of str, optional
        Which elections to include.
    validate : bool, default True
        Run the acceptance checks first. Writing an unchecked file is possible and is a bad
        idea: the checks are what make the file safe to analyse.

    Returns
    -------
    pathlib.Path
        The file written.
    """
    tidy = build_tidy(data_dir, elections=elections, validate=validate)
    target = out_path or ((data_dir or DATA_DIR) / TIDY_RELATIVE_PATH)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_parquet(target, index=False)
    return target

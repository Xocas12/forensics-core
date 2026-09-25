"""The Hokkaido SRC "Soviet and Russian Economic Statistical Series", loaded as published.

Placed beside :mod:`gosplan.acquire.western_estimates`, which fetches it, although it is not
a Western estimate: it is a transcription of the *official* Narkhoz series, the reported
side against which the reconstructions are compared.

Of the national-accounts and Warwick sources the registry verifies, this is the only one a
loader can be written for without assuming anything. The registry records the header of the
series files (``CODE NUMBER, FULL NAME, UNIT, SOURCE`` followed by one column per year from
1940 to 1989) and its download plan records the one cleaning rule they need: **treat 0.0 as
missing**. Everything else in the family is a documented gap -- the Harrison ``.xls``
workbooks and the World Bank Lotus and MicroTSP files need a converter the stack does not
have, and the Maddison workbook's GDP column has no recorded unit or price base. See
:data:`gosplan.clean.UNLOADED` and ``docs/data_dictionary.md``.

Two things the registry does not record, and which the loader therefore does not fill in:

* **Currency basis.** The files span 1940-1989, across the 1961 redenomination, and nothing
  recorded says whether a rouble series is in old or new roubles. ``currency_basis`` is left
  blank on every row, the loader's equivalent of the transcription rule that a transcriber
  who cannot tell leaves the cell blank rather than guess. A monetary series from this
  loader is therefore not yet comparable with anything.
* **Territorial basis.** Recorded as ``unstated``.

The ``UNIT`` column is kept exactly as published, including where the registry records that
a unit label disagrees with the magnitudes it labels ("Mil. rubles" over figures in the
billions). Correcting it would be a finding, not a cleaning step.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from gosplan.clean._common import (
    CURRENCY_BASIS_COLUMN,
    SOURCE_ID_COLUMN,
    TERRITORIAL_BASIS_COLUMN,
    UNIT_COLUMN,
    SchemaError,
    finish,
    read_published_csv,
    to_number,
    withhold_sealed,
)
from gosplan.transcribe.schema import TerritorialBasis

__all__ = [
    "SESS_ID_COLUMNS",
    "SESS_MISSING_CODE",
    "SESS_RAW_DIR",
    "SESS_SOURCE_ID",
    "load_hokudai_sess",
]

#: Registry id.
SESS_SOURCE_ID = "hokudai_sess"

#: Where :func:`gosplan.acquire.western_estimates.hokudai_sess` puts the series files,
#: relative to ``data/raw``.
SESS_RAW_DIR = "hokudai_sess/series"

#: The leading columns of every series file, as the registry's notes record them. The
#: remaining columns are years.
SESS_ID_COLUMNS: tuple[str, ...] = ("CODE NUMBER", "FULL NAME", "UNIT", "SOURCE")

#: The registry's download plan: "Treat 0.0 as missing."
SESS_MISSING_CODE = 0.0

#: File names the acquirer writes, matching the registry's ``USSR/S<code>.csv`` pattern.
_SERIES_FILE_RE = re.compile(r"^S\d+\.csv$")
_YEAR_RE = re.compile(r"^\d{4}$")


def _series_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if _SERIES_FILE_RE.match(p.name))
        if not files:
            raise SchemaError(f"{path} holds no files matching {_SERIES_FILE_RE.pattern}")
        return files
    return [path]


def _load_one(path: Path) -> pd.DataFrame:
    raw = read_published_csv(path)
    cols = tuple(raw.columns)
    head, years = cols[: len(SESS_ID_COLUMNS)], cols[len(SESS_ID_COLUMNS) :]
    if head != SESS_ID_COLUMNS or not years or not all(_YEAR_RE.match(c) for c in years):
        raise SchemaError(
            f"{SESS_SOURCE_ID}: {path.name} has header {list(cols)}; the registry records "
            f"{list(SESS_ID_COLUMNS)} followed by year columns"
        )
    long = raw.melt(
        id_vars=list(SESS_ID_COLUMNS),
        value_vars=list(years),
        var_name="year",
        value_name="value_raw",
    )
    long["year"] = long["year"].astype("Int64")
    number = to_number(long["value_raw"], what=f"{path.name} values")
    long["value"] = number.mask(number.eq(SESS_MISSING_CODE).fillna(False))
    return long


def load_hokudai_sess(path: Path) -> pd.DataFrame:
    """Load one SESS series file, or every ``S<code>.csv`` in a directory, in long form.

    Parameters
    ----------
    path : Path
        A single series CSV, or the directory the acquirer writes them to
        (:data:`SESS_RAW_DIR` under ``data/raw``).

    Returns
    -------
    pandas.DataFrame
        One row per series and year: the four published identifier columns under their
        published names, ``year`` (integer), ``value_raw`` (the cell exactly as published),
        ``value`` (float, missing wherever the published cell was blank or the registry's
        missing code ``0.0``), then ``source_id``, ``unit`` (a copy of ``UNIT``),
        ``territorial_basis`` (``unstated``) and ``currency_basis`` (blank: not recorded).
        ``attrs["n_withheld"]`` is the number of rows the seal withheld.

    Raises
    ------
    SchemaError
        If a file's header is not the recorded one, or a cell is not a number.
    """
    frames = [_load_one(p) for p in _series_files(Path(path))]
    frame = pd.concat(frames, ignore_index=True)

    frame[SOURCE_ID_COLUMN] = SESS_SOURCE_ID
    frame[UNIT_COLUMN] = frame["UNIT"]
    frame[TERRITORIAL_BASIS_COLUMN] = TerritorialBasis.UNSTATED.value
    frame[CURRENCY_BASIS_COLUMN] = pd.Series(pd.NA, index=frame.index, dtype="string")

    # The files carry no region column. The full series name is offered to the seal as both
    # the region and the series, so a series whose name identifies the held-out unit and its
    # crop is withheld for the held-out years.
    frame, n_withheld = withhold_sealed(
        frame,
        region=frame["FULL NAME"],
        series=frame["FULL NAME"],
        years=[frame["year"]],
    )
    return finish(frame, source_id=SESS_SOURCE_ID, n_withheld=n_withheld)

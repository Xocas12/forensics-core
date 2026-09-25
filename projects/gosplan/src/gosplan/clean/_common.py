"""Shared plumbing for the gosplan loaders: reading a published file, checking its header
against the registry, attaching the basis columns, and routing rows through the seal.

Everything here is pure and network-free. A loader reads a file that
:mod:`gosplan.acquire` has already put under ``data/raw``; it never fetches, and it never
writes anything back.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from gosplan.seal import filter_sealed

#: The columns every loader adds to the publisher's own. ``unit`` is the unit the publisher
#: states, copied verbatim; ``territorial_basis`` and ``currency_basis`` use the vocabulary of
#: :class:`gosplan.transcribe.schema.TerritorialBasis` and
#: :class:`gosplan.transcribe.schema.CurrencyBasis`, so a loaded series and a transcribed
#: table can be set side by side without a translation step.
SOURCE_ID_COLUMN = "source_id"
UNIT_COLUMN = "unit"
TERRITORIAL_BASIS_COLUMN = "territorial_basis"
CURRENCY_BASIS_COLUMN = "currency_basis"
BASIS_COLUMNS: tuple[str, ...] = (
    SOURCE_ID_COLUMN,
    UNIT_COLUMN,
    TERRITORIAL_BASIS_COLUMN,
    CURRENCY_BASIS_COLUMN,
)

#: Key of ``DataFrame.attrs`` carrying how many rows the seal withheld. Counting withheld rows
#: is the one thing ``gosplan.seal`` permits doing with them.
N_WITHHELD_ATTR = "n_withheld"

#: Key of ``DataFrame.attrs`` carrying the registry id the frame was loaded from.
SOURCE_ID_ATTR = "source_id"

#: No registry entry records the text encoding of the files these loaders read. Strict UTF-8
#: is used because it fails loudly on bytes it cannot decode rather than silently
#: substituting characters; a file that fails here needs its encoding recorded in the
#: registry, not guessed in code.
TEXT_ENCODING = "utf-8"


class SchemaError(ValueError):
    """Raised when a file does not have the layout its registry entry records.

    A loader that meets an unrecorded layout stops rather than adapts: the registry is the
    only authority on what a column is called, and adapting would be assuming.
    """


def read_published_csv(path: Path, *, member: str | None = None) -> pd.DataFrame:
    """Read a published CSV, from disk or from inside a zip, as untyped strings.

    Every cell is read as a string and nothing is converted to missing on the way in, so
    that each loader decides explicitly what counts as a number and what counts as absent.

    Parameters
    ----------
    path : Path
        A ``.csv`` file, or a ``.zip`` archive holding ``member``.
    member : str, optional
        Name of the CSV inside the archive. Required when ``path`` is a zip.
    """
    path = Path(path)
    if zipfile.is_zipfile(path):
        if member is None:
            raise SchemaError(f"{path} is a zip archive but no member name was given")
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if member not in names:
                raise SchemaError(
                    f"{path} does not contain {member!r}, which the registry records; "
                    f"it contains {names}"
                )
            raw = zf.read(member)
        text = raw.decode(TEXT_ENCODING)
    else:
        text = path.read_text(encoding=TEXT_ENCODING)
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def require_exact_header(frame: pd.DataFrame, expected: Sequence[str], source_id: str) -> None:
    """Refuse a frame whose columns are not exactly the ones the registry records."""
    got = tuple(frame.columns)
    if got != tuple(expected):
        raise SchemaError(
            f"{source_id}: header {list(got)} does not match the columns recorded in "
            f"data/SOURCES.yaml {list(expected)}. Record the new layout in the registry "
            "before loading it."
        )


def to_number(values: pd.Series, *, what: str, integer: bool = False) -> pd.Series:
    """Convert published strings to numbers; blank becomes missing, anything else raises.

    Raises
    ------
    SchemaError
        If a non-blank cell is not a number, naming the column and the offending value.
    """
    stripped = values.str.strip()
    blank = stripped.eq("")
    try:
        out = pd.to_numeric(stripped.mask(blank), errors="raise")
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"column {what!r} holds a value that is not a number: {exc}") from exc
    return out.astype("Int64" if integer else "Float64")


def withhold_sealed(
    frame: pd.DataFrame,
    *,
    region: pd.Series,
    series: pd.Series,
    years: Sequence[pd.Series],
) -> tuple[pd.DataFrame, int]:
    """Drop every row the seal holds out, under any of several year readings.

    Where a source carries more than one year for a row (a marketing year and a calendar
    year, say), the row is withheld if *any* of them falls inside the held-out window. That
    is deliberately conservative: which year the anchor "is" is not a question a loader may
    settle, and the expensive mistake is letting a held-out row through.

    The decision itself is :func:`gosplan.seal.filter_sealed`'s, so when the seal is lifted
    this is a no-op and nothing here needs to know the anchor's definition.

    Returns
    -------
    (frame, n_withheld)
    """
    frame = frame.reset_index(drop=True)
    drop = pd.Index([], dtype="int64")
    for year in years:
        probe = pd.DataFrame(
            {
                "region": region.to_numpy(),
                "series": series.to_numpy(),
                "year": year.to_numpy(),
            },
            index=frame.index,
        )
        kept, _ = filter_sealed(probe)
        drop = drop.union(probe.index.difference(kept.index))
    return frame.drop(index=drop).reset_index(drop=True), len(drop)


def finish(frame: pd.DataFrame, *, source_id: str, n_withheld: int) -> pd.DataFrame:
    """Stamp the provenance attributes every loader's return value carries."""
    frame.attrs[SOURCE_ID_ATTR] = source_id
    frame.attrs[N_WITHHELD_ATTR] = n_withheld
    return frame

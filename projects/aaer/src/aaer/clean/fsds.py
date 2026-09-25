"""Read SEC Financial Statement Data Sets quarterly zips into the SUB / NUM / PRE / TAG tables.

Format, as documented and as confirmed by unzipping two quarters
----------------------------------------------------------------
The documentation PDF (registry entry ``sec_fsds_readme``) states the file format verbatim:
"Tab Delimited Value (.txt): utf-8, tab-delimited, \\n-terminated lines, with the first line
containing the column names in lowercase", and defines four tables -- 5.1 SUB (submissions),
5.2 TAG (tags), 5.3 NUM (numbers), 5.4 PRE (presentation) -- with primary keys
``SUB(adsh)``, ``TAG(tag, version)``, ``NUM(adsh, tag, version, ddate, qtrs, uom, segments,
coreg)`` and ``PRE(adsh, report, line)``. Every quarterly zip holds exactly ``sub.txt``,
``tag.txt``, ``num.txt``, ``pre.txt`` and ``readme.htm``.

The column names in :data:`SUB_COLUMNS`, :data:`NUM_COLUMNS`, :data:`PRE_COLUMNS` and
:data:`TAG_COLUMNS` were read directly off the 2009q2 zip during scaffolding and confirmed by
an independent second fetch (registry ``sec_fsds_quarterly_zips``). They are checked on load
and a mismatch is **reported, not raised**: the SEC regenerated the historical files in
November 2024 and may do so again.

Scale
-----
2009q2 holds 22 submissions and 4,000 numeric facts in a 145 KB zip. Recent quarters are
~120 MB and hold millions of NUM rows. :func:`read_fsds_zip` loads a whole quarter into memory,
which is fine for one quarter and not fine for seventy; for the full panel, iterate quarters
and reduce (see :func:`iter_fsds_zips`) or push the NUM table into DuckDB.

Everything is read as text. Numeric coercion happens once, in :func:`read_fsds_zip`, and only
for ``NUM.value``; identifiers such as ``adsh``, ``cik`` and ``ddate`` stay strings because
they are codes, and leading zeros in a CIK are meaningful.
"""

from __future__ import annotations

import csv
import io
import warnings
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

#: SUB, the submissions table. One row per filing; key ``adsh``.
SUB_COLUMNS: tuple[str, ...] = (
    "adsh",
    "cik",
    "name",
    "sic",
    "countryba",
    "stprba",
    "cityba",
    "zipba",
    "bas1",
    "bas2",
    "baph",
    "countryma",
    "stprma",
    "cityma",
    "zipma",
    "mas1",
    "mas2",
    "countryinc",
    "stprinc",
    "ein",
    "former",
    "changed",
    "afs",
    "wksi",
    "fye",
    "form",
    "period",
    "fy",
    "fp",
    "filed",
    "accepted",
    "prevrpt",
    "detail",
    "instance",
    "nciks",
    "aciks",
)

#: NUM, the numeric facts table. Key ``(adsh, tag, version, ddate, qtrs, uom, segments, coreg)``.
NUM_COLUMNS: tuple[str, ...] = (
    "adsh",
    "tag",
    "version",
    "ddate",
    "qtrs",
    "uom",
    "segments",
    "coreg",
    "value",
    "footnote",
)

#: PRE, the presentation table. Key ``(adsh, report, line)``.
PRE_COLUMNS: tuple[str, ...] = (
    "adsh",
    "report",
    "line",
    "stmt",
    "inpth",
    "rfile",
    "tag",
    "version",
    "plabel",
    "negating",
)

#: TAG, the tag dictionary. Key ``(tag, version)``; ``custom`` marks filer extension tags.
TAG_COLUMNS: tuple[str, ...] = (
    "tag",
    "version",
    "custom",
    "abstract",
    "datatype",
    "iord",
    "crdr",
    "tlabel",
    "doc",
)

#: Expected header per member file.
EXPECTED_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "sub.txt": SUB_COLUMNS,
    "num.txt": NUM_COLUMNS,
    "pre.txt": PRE_COLUMNS,
    "tag.txt": TAG_COLUMNS,
}

#: Data members of a quarterly zip. ``readme.htm`` is documentation and is not read here.
FSDS_TABLES: tuple[str, ...] = ("sub.txt", "num.txt", "pre.txt", "tag.txt")


@dataclass(frozen=True)
class FsdsQuarter:
    """One quarterly zip, read into four frames.

    Attributes
    ----------
    quarter : str
        Label such as ``"2009q2"``, taken from the file name.
    sub, num, pre, tag : pandas.DataFrame
        The four tables, all string dtype except ``num.value`` which is float.
    header_mismatches : mapping
        ``member -> (unexpected_columns, missing_columns)`` for any table whose header differs
        from the documented one. Empty when everything matched.
    path : Path
        The zip that was read.
    """

    quarter: str
    sub: pd.DataFrame
    num: pd.DataFrame
    pre: pd.DataFrame
    tag: pd.DataFrame
    header_mismatches: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = field(
        default_factory=dict
    )
    path: Path | None = None

    @property
    def is_empty(self) -> bool:
        """True for the 2009q1 placeholder: headers present, no rows anywhere."""
        return len(self.sub) == 0 and len(self.num) == 0

    def row_counts(self) -> dict[str, int]:
        """Rows per table, for a coverage table."""
        return {
            "sub": len(self.sub),
            "num": len(self.num),
            "pre": len(self.pre),
            "tag": len(self.tag),
        }


def quarter_from_path(path: Path | str) -> str:
    """``.../fsds/2009q2.zip`` -> ``"2009q2"``. The stem is used verbatim."""
    return Path(path).stem.lower()


def _read_member(zf: zipfile.ZipFile, member: str) -> tuple[pd.DataFrame, tuple, tuple]:
    with zf.open(member) as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")
        frame = pd.read_csv(
            text,
            sep="\t",
            dtype=str,
            na_filter=False,
            quoting=csv.QUOTE_NONE,
            on_bad_lines="warn",
            engine="c",
        )
    expected = EXPECTED_COLUMNS[member]
    got = tuple(frame.columns)
    unexpected = tuple(c for c in got if c not in expected)
    missing = tuple(c for c in expected if c not in got)
    return frame, unexpected, missing


def read_fsds_zip(path: Path | str, *, tables: Iterable[str] = FSDS_TABLES) -> FsdsQuarter:
    """Read one quarterly zip.

    Parameters
    ----------
    path : path-like
        A downloaded ``YYYYqN.zip``.
    tables : iterable of str, default :data:`FSDS_TABLES`
        Members to read. Any member not read comes back as an empty frame with the documented
        columns, so downstream code does not have to test for its presence.

    Returns
    -------
    FsdsQuarter

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    zipfile.BadZipFile
        If the file is not a zip -- which is what a captured error page saved under a ``.zip``
        name looks like, so do not suppress it.

    Warns
    -----
    UserWarning
        If a member is absent from the archive, or its header differs from the documented one.
        A header change is reported rather than raised because the SEC has regenerated these
        files before; the mismatch is also carried in
        :attr:`FsdsQuarter.header_mismatches`.
    """
    p = Path(path)
    wanted = set(tables)
    frames: dict[str, pd.DataFrame] = {}
    mismatches: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}

    with zipfile.ZipFile(p) as zf:
        present = {name.lower() for name in zf.namelist()}
        for member in FSDS_TABLES:
            if member not in wanted:
                frames[member] = pd.DataFrame(columns=list(EXPECTED_COLUMNS[member]), dtype=str)
                continue
            if member not in present:
                warnings.warn(f"{p.name}: member {member!r} is absent", stacklevel=2)
                frames[member] = pd.DataFrame(columns=list(EXPECTED_COLUMNS[member]), dtype=str)
                continue
            frame, unexpected, missing = _read_member(zf, member)
            if unexpected or missing:
                mismatches[member] = (unexpected, missing)
                warnings.warn(
                    f"{p.name}: {member} header differs from the documented one "
                    f"(unexpected={list(unexpected)}, missing={list(missing)})",
                    stacklevel=2,
                )
            frames[member] = frame

    num = frames["num.txt"]
    if "value" in num.columns:
        # always float, never int: an all-integral quarter must not change the column dtype
        num = num.assign(value=pd.to_numeric(num["value"], errors="coerce").astype("float64"))

    return FsdsQuarter(
        quarter=quarter_from_path(p),
        sub=frames["sub.txt"],
        num=num,
        pre=frames["pre.txt"],
        tag=frames["tag.txt"],
        header_mismatches=mismatches,
        path=p,
    )


def iter_fsds_zips(
    raw_dir: Path | str, *, tables: Iterable[str] = FSDS_TABLES
) -> Iterator[FsdsQuarter]:
    """Yield each ``*.zip`` under ``raw_dir`` (normally ``data/raw/fsds``) in quarter order.

    Use this rather than :func:`read_quarters` when the whole panel does not fit in memory:
    reduce each quarter to what you need and discard it before the next one is read.
    """
    for path in sorted(Path(raw_dir).glob("*.zip"), key=lambda p: p.stem):
        yield read_fsds_zip(path, tables=tables)


def read_quarters(
    paths: Iterable[Path | str], *, tables: Iterable[str] = FSDS_TABLES
) -> FsdsQuarter:
    """Read several quarters and concatenate them into one :class:`FsdsQuarter`.

    A ``quarter`` column is added to every frame so a row can always be traced back to the zip
    it came from, and the combined ``quarter`` label lists the range that was read. TAG rows are
    deduplicated on ``(tag, version)``: the tag dictionary is repeated in full in every quarter.

    Beware the memory cost -- see the module docstring.
    """
    quarters = [read_fsds_zip(p, tables=tables) for p in paths]
    if not quarters:
        empty = {m: pd.DataFrame(columns=list(EXPECTED_COLUMNS[m]), dtype=str) for m in FSDS_TABLES}
        return FsdsQuarter(
            "", empty["sub.txt"], empty["num.txt"], empty["pre.txt"], empty["tag.txt"]
        )

    def _cat(attr: str) -> pd.DataFrame:
        parts = [getattr(q, attr).assign(quarter=q.quarter) for q in quarters]
        return pd.concat(parts, ignore_index=True)

    labels = [q.quarter for q in quarters]
    mismatches: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for q in quarters:
        for member, diff in q.header_mismatches.items():
            mismatches[f"{q.quarter}/{member}"] = diff
    tag = _cat("tag").drop_duplicates(subset=["tag", "version"], keep="first")
    return FsdsQuarter(
        quarter=f"{labels[0]}..{labels[-1]}" if len(labels) > 1 else labels[0],
        sub=_cat("sub"),
        num=_cat("num"),
        pre=_cat("pre"),
        tag=tag,
        header_mismatches=mismatches,
    )

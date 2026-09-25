"""SEC DERA Financial Statement Data Sets: the free structured-financials path.

These quarterly zips are the only free, structured, machine-readable source of U.S. financial
statement line items in the registry. They are what :mod:`aaer.clean.fsds` and
:mod:`aaer.clean.xbrl_map` turn into the twelve items :data:`aaer.features.beneish.REQUIRED_COLUMNS`
needs, and their coverage is the project's central constraint.

Two facts about coverage, both taken from the registry rather than assumed
-------------------------------------------------------------------------
1. **2009q1 exists but is empty by design.** The documentation PDF (registry entry
   ``sec_fsds_readme``) states verbatim that "there is a file named 2009q1.zip on the SEC
   website that contains data sets with column headings only and no rows, merely so that all
   years prior to this year will consist of four zip files". Entry ``sec_fsds_2009q1`` confirms
   it by unzipping: ``sub.txt`` 223 bytes, ``num.txt`` 62 bytes, zero data rows.
   **The first quarter with rows is 2009q2** (22 submissions, 4,000 numeric facts).
2. **Scope begins 15 April 2009.** The same PDF: "Submitted from 4/15/2009 through the Data
   Cutoff Date inclusive". Nothing before that exists in this series at any price, which is why
   the labelled violations of the 1990s and 2000s cannot be met on this path. See
   ``data/ACCESS_NOTES.md``.

Size, before you run ``--all``
------------------------------
:func:`fsds_quarterly_zips` downloads every quarter from 2009q2 to the last one confirmed to
exist (2026q2 as of the scaffolding probe): about 69 files ranging from 145 KB to ~120 MB,
**several GB in total**. Members already on disk are not re-requested. To take a slice instead,
call the acquirer directly with a shorter ``quarters`` list, or run
``python -m aaer.acquire sec_fsds_2009q1 sec_fsds_readme`` and fetch quarters deliberately.

SEC access policy (descriptive ``User-Agent`` with a contact address; 10 requests/second
ceiling) applies to every request here and is discussed in :mod:`aaer.acquire.sec_edgar`.
A HEAD with a non-descriptive ``User-Agent`` was answered with HTTP 403 by Akamai during
scaffolding (registry entry ``sec_fsds_quarterly_zips``).

The Financial Statement **and Notes** Data Sets are a different, much larger series carrying
footnote text. Only their landing page and documentation are acquired here: the compact FSDS
is sufficient for ratio features, as the registry entry ``sec_fsn_page`` itself notes.
"""

from __future__ import annotations

import re
from pathlib import Path

from aaer.acquire._common import fetch_file, fetch_many
from aaer.acquire.registry import AcquireResult, register

#: Directory the quarterly zips are served from (confirmed pattern, registry ``sec_fsds_page``).
FSDS_ZIP_BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"

#: Nominal first quarter. Column headings only, no rows -- see the module docstring.
FSDS_FIRST_QUARTER = "2009q1"

#: First quarter that actually contains rows.
FSDS_FIRST_QUARTER_WITH_ROWS = "2009q2"

#: Last quarter confirmed to exist on the landing page, 2026-09-03, re-confirmed 2026-09-04.
#: A new quarter appears roughly a month after the quarter ends; raise this only after the
#: landing page has been re-read, and let the run report a 404 rather than guessing.
FSDS_LATEST_VERIFIED_QUARTER = "2026q2"

#: Members of every quarterly zip (registry ``sec_fsds_quarterly_zips``, confirmed by unzip).
FSDS_ZIP_MEMBERS = ("sub.txt", "tag.txt", "num.txt", "pre.txt", "readme.htm")

_QUARTER_RE = re.compile(r"^(\d{4})q([1-4])$")


def parse_quarter(quarter: str) -> tuple[int, int]:
    """``"2009q2"`` -> ``(2009, 2)``. Raises :class:`ValueError` on anything else."""
    m = _QUARTER_RE.match(quarter)
    if m is None:
        raise ValueError(f"not a quarter label like '2009q2': {quarter!r}")
    return int(m.group(1)), int(m.group(2))


def format_quarter(year: int, quarter: int) -> str:
    """``(2009, 2)`` -> ``"2009q2"``."""
    if not 1 <= quarter <= 4:
        raise ValueError(f"quarter must be 1..4, got {quarter}")
    return f"{year}q{quarter}"


def quarters(
    first: str = FSDS_FIRST_QUARTER_WITH_ROWS,
    last: str = FSDS_LATEST_VERIFIED_QUARTER,
) -> list[str]:
    """Inclusive list of quarter labels from ``first`` to ``last``.

    Parameters
    ----------
    first, last : str
        Quarter labels such as ``"2009q2"``. ``first`` defaults to the first quarter with rows,
        not to the nominal first quarter; ``last`` defaults to the last quarter the registry
        records as confirmed to exist, so the default range asks for nothing unobserved.

    Returns
    -------
    list of str

    Raises
    ------
    ValueError
        If either label is malformed or ``last`` precedes ``first``.
    """
    y0, q0 = parse_quarter(first)
    y1, q1 = parse_quarter(last)
    start, end = 4 * y0 + (q0 - 1), 4 * y1 + (q1 - 1)
    if end < start:
        raise ValueError(f"last quarter {last!r} precedes first quarter {first!r}")
    return [format_quarter(i // 4, i % 4 + 1) for i in range(start, end + 1)]


def quarter_zip_url(quarter: str) -> str:
    """Download URL of one quarterly zip."""
    parse_quarter(quarter)
    return f"{FSDS_ZIP_BASE}/{quarter}.zip"


def quarter_zip_path(quarter: str) -> str:
    """Destination of one quarterly zip, relative to ``data/raw``."""
    parse_quarter(quarter)
    return f"fsds/{quarter}.zip"


@register("sec_fsds_quarterly_zips")
def fsds_quarterly_zips(
    source,
    data_dir: Path,
    *,
    force: bool = False,
    quarters_wanted: list[str] | None = None,
) -> AcquireResult:
    """Every quarterly zip from 2009q2 to the last confirmed quarter.

    2009q1 is excluded here and acquired separately by :func:`fsds_2009q1`, because it is an
    empty placeholder rather than data and a loader that treats a zero-row quarter as a parse
    failure would be wrong about it.

    The digest recorded in the registry for this entry belongs to **2009q2** and is checked
    against that file only; the other quarters have no recorded digest, so they are accepted on
    HTTP 200 and their sha256 goes into ``data/fetch_log.jsonl``.
    """
    wanted = quarters_wanted if quarters_wanted is not None else quarters()
    items = [(quarter_zip_url(q), quarter_zip_path(q)) for q in wanted]
    expected = (
        {quarter_zip_path(FSDS_FIRST_QUARTER_WITH_ROWS): source.sha256} if source.sha256 else {}
    )
    return fetch_many(
        source,
        data_dir,
        items,
        expected=expected,
        force=force,
        resume=True,
        unit="quarterly zips",
    )


@register("sec_fsds_2009q1")
def fsds_2009q1(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The nominal first quarter: 13,540 bytes, five members, zero data rows.

    Kept so that a completeness check over the quarter sequence can assert "this quarter has no
    rows" instead of "this quarter is missing". Do not treat its zero row count as a bug.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        quarter_zip_path(FSDS_FIRST_QUARTER),
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("sec_fsds_readme")
def fsds_readme(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The FSDS documentation PDF: table definitions 5.1 SUB, 5.2 TAG, 5.3 NUM, 5.4 PRE.

    Section 5.3 is what the ``qtrs`` convention used by :mod:`aaer.clean.xbrl_map` must be
    confirmed against; that convention is currently marked unconfirmed there.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "fsds/financial-statement-data-sets.pdf",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("sec_fsds_page")
def fsds_landing_page(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The current landing page, kept so the list of quarters can be re-derived from HTML.

    Do not trust a summarised link count from this page: three probes counted 68, 69 and an
    arithmetic 70 links for the same period (registry ``sec_fsds_page``). Iterate the URL
    pattern and let 404s be reported.
    """
    return fetch_file(source, data_dir, source.url, "fsds/landing_page.html", force=force)


@register("sec_fsds_listing")
def fsds_listing_page(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The older ``/dera/data/financial-statement-data-sets.html`` listing URL.

    A second, separately verified route to the same list of quarterly zips. Kept because the
    canonical URL of this dataset has already moved once.
    """
    return fetch_file(source, data_dir, source.url, "fsds/listing_page_dera.html", force=force)


@register("sec_fsn_readme")
def fsn_readme(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Documentation of the Financial Statement **and Notes** series (tables SUB..CAL).

    Acquired as the reference for what the compact FSDS leaves out (``DIM``, ``TXT``, ``REN``,
    ``CAL``), not because the notes data is used.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "fsds_notes/aqfsn_1.pdf",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("sec_fsn_page")
def fsn_landing_page(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Landing page of the notes series; the zips themselves are not acquired.

    The quarterly-to-monthly boundary this page describes was reported differently by two
    probes, so it must be parsed from the raw HTML if it is ever needed.
    """
    return fetch_file(source, data_dir, source.url, "fsds_notes/landing_page.html", force=force)

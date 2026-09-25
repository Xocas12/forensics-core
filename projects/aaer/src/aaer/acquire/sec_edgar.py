"""SEC enforcement releases, the SEC access-policy pages, and the data.sec.gov XBRL APIs.

SEC fair-access policy, which this module is bound by
-----------------------------------------------------
Every request to ``sec.gov``, ``data.sec.gov`` and ``efts.sec.gov`` must carry a descriptive
``User-Agent`` containing a contact address, and no client may exceed **10 requests per
second** in total. Both requirements are quoted verbatim in the registry:

* ``sec_accessing_edgar_data`` (*Accessing EDGAR Data*,
  https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) records
  "Current max request rate: 10 requests/second." and the sample header
  ``User-Agent: Sample Company Name AdminContact@<sample company domain>.com``, together with
  ``Accept-Encoding: gzip, deflate`` and ``Host: www.sec.gov``.
* ``sec_webmaster_faq`` records "Note that our current maximum access rate is 10 requests per
  second."
* ``sec_rate_control_announcement_2021`` (27 July 2021) records that "the SEC will limit
  automated searches to a total of no more than 10 requests per second regardless of the
  number of machines used to submit requests".

Compliance is not implemented here. It is implemented once, in
:func:`forensics_core.provenance.manifest.fetch`, which refuses to make any request until
``config/forensics.toml`` holds a real contact string, puts that string in the ``User-Agent``,
and paces requests with a per-host token bucket. This repository's ``config/forensics.toml``
sets ``www.sec.gov``, ``data.sec.gov`` and ``efts.sec.gov`` to **4 requests per second**, i.e.
below the published ceiling, and the entry ``sec_fsds_quarterly_zips`` records that a HEAD with
a non-descriptive ``User-Agent`` was answered with HTTP 403 by Akamai -- so the contact string
is not decoration.

What this module acquires
-------------------------
The AAER listing (34 pages of 100 rows, ``?page=N``, 0-indexed), the RSS feed that carries the
10 newest releases, one sample release PDF whose text layout is the template for label
extraction, the four SEC policy and API documentation pages, and one sample
``companyfacts`` response.

What it deliberately does not acquire, and why
----------------------------------------------
* The ~3,342 individual release PDFs. The listing pages hold their URLs; the registry entry
  ``aaer_listing_secgov`` estimates 0.5-1 GB for the full set. Downloading them is a separate,
  explicit step that should be driven by the parsed listing table
  (:mod:`aaer.clean.aaer_releases`), not by ``--all``.
* ``sec_edgar_fullindex_1994q3``. It is an index of *filings*, not of financial statement line
  items; the registry entry itself says that turning pre-XBRL 10-Ks into a panel of the 28
  Compustat-equivalent items "is the whole project, not a data-acquisition step".
* ``sec_efts_fulltext_search``. The registry URL is one ad-hoc query against the full-text
  search backend, not a dataset, and its pagination parameters were never verified.

One parser helper is borrowed, and it costs an import
--------------------------------------------------------
Turning the listing into a table of releases belongs to :mod:`aaer.clean.aaer_releases`, and
none of that happens here -- with one exception. :func:`aaer.clean.aaer_releases.total_items`,
a single regular expression reading the "1 to 100 of N items" line, is imported so that
:func:`aaer_listing` knows how many pages to request. Reusing it is deliberate: the alternative
is a second copy of the same pattern that can drift from the parser's. The cost is that
importing this module imports the clean layer, so ``python -m aaer.acquire --list`` loads
``pandas`` and ``lxml`` even though it makes no request and parses nothing. ``china`` borrows
from its own clean layer in the same way (``china.acquire.pbc``, ``.nbs_api``, ``.yearbook``),
so this is the programme's shape rather than a local shortcut.
"""

from __future__ import annotations

import math
from pathlib import Path

from aaer.acquire._common import fetch_file, fetch_many
from aaer.acquire.registry import AcquireResult, register
from aaer.clean.aaer_releases import total_items

#: Listing page. ``?page=N`` is 0-indexed; page 0 is the URL without a query string.
AAER_LISTING_URL = (
    "https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases"
)

#: Rows per listing page, read from the listing's own "1 to 100 of 3342 items" line
#: (registry entry ``aaer_listing_secgov``).
AAER_ROWS_PER_PAGE = 100

#: Total rows and page count as observed on 2026-09-03 and re-confirmed on 2026-09-04. Used
#: only as a fallback: the real count is re-read from page 0 on every run, because the listing
#: grows by a few releases a month.
AAER_ITEMS_AT_SCAFFOLD = 3342
AAER_PAGES_AT_SCAFFOLD = 34

#: Where the listing pages land, relative to ``data/raw``.
AAER_LISTING_DIR = "aaer_listing"


def listing_page_url(page: int) -> str:
    """URL of listing page ``page`` (0-indexed, as the site itself numbers them)."""
    if page < 0:
        raise ValueError(f"page must be >= 0, got {page}")
    return AAER_LISTING_URL if page == 0 else f"{AAER_LISTING_URL}?page={page}"


def listing_page_path(page: int) -> str:
    """Destination of listing page ``page``, relative to ``data/raw``."""
    return f"{AAER_LISTING_DIR}/page_{page:03d}.html"


def page_count(n_items: int, rows_per_page: int = AAER_ROWS_PER_PAGE) -> int:
    """Number of listing pages holding ``n_items`` rows at ``rows_per_page`` rows each."""
    if n_items < 0:
        raise ValueError(f"n_items must be >= 0, got {n_items}")
    return math.ceil(n_items / rows_per_page)


def _pages_from_disk(data_dir: Path) -> tuple[int, str]:
    """Re-read the page count from a downloaded page 0; fall back to the scaffold constant."""
    first = data_dir / "raw" / listing_page_path(0)
    if not first.exists():
        return AAER_PAGES_AT_SCAFFOLD, "page 0 not on disk, using the scaffolded count"
    try:
        n_items = total_items(first.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # a changed page must not abort the run
        return AAER_PAGES_AT_SCAFFOLD, f"item count unreadable ({exc}), using the scaffolded count"
    if n_items is None:
        return AAER_PAGES_AT_SCAFFOLD, "item count absent from page 0, using the scaffolded count"
    return page_count(n_items), f"{n_items:,} items reported by page 0"


@register("aaer_listing_secgov")
def aaer_listing(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Every page of the AAER listing: date, respondent, release numbers and the PDF link.

    Page 0 is re-fetched on **every** run, ``--force`` or not, and its "1 to N of M items" line
    decides how many pages follow. That one unconditional request is the price of the count
    adapting as releases are added instead of being frozen at the 34 pages counted during
    scaffolding: idempotence in :func:`aaer.acquire._common.fetch_many` is presence-on-disk, so
    a cached page 0 would otherwise never be re-read and the count would never move.

    Pages 1..N-1 keep the ordinary presence-based rule and are not re-requested unless ``force``
    is given; see :mod:`aaer.acquire._common` for why that is presence-based rather than
    checksum-based.

    A failed or challenged page 0 overwrites nothing useful but does leave whatever came back on
    disk, so :func:`_pages_from_disk` can find an unreadable page 0 and fall back to
    :data:`AAER_PAGES_AT_SCAFFOLD`. Which of the two happened is named in the returned detail
    string, so a run that quietly used the stale count still says so.
    """
    first = fetch_many(
        source,
        data_dir,
        [(listing_page_url(0), listing_page_path(0))],
        force=True,
        unit="pages",
    )
    n_pages, provenance = _pages_from_disk(data_dir)
    rest = fetch_many(
        source,
        data_dir,
        [(listing_page_url(p), listing_page_path(p)) for p in range(1, n_pages)],
        force=force,
        unit="pages",
    )
    detail = f"page 0: {first.detail} [{provenance}]; pages 1-{n_pages - 1}: {rest.detail}"
    return AcquireResult(source.id, first.ok and rest.ok, detail, first.paths + rest.paths)


@register("aaer_rss_feed")
def aaer_rss(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The 10 most recent releases as RSS.

    An incremental trigger, not a backfill source, and it does **not** carry AAER numbers --
    only the 33-/34- release numbers, via the PDF filename (registry entry ``aaer_rss_feed``).
    """
    return fetch_file(source, data_dir, source.url, "sec/aaer_friactions.xml", force=force)


@register("aaer_release_pdf_sample")
def aaer_release_pdf(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """One release PDF (AAER-4599, Exchange Act Rel. 34-106274, 3 September 2026).

    Acquired because the label extractor in :mod:`aaer.clean.aaer_releases` is written against
    its header layout: the registry records that page 1 carries the lines "ACCOUNTING AND
    AUDITING ENFORCEMENT Release No. 4599 / September 3, 2026" and "In the Matter of PAUL
    FRENKIEL", and that the text layer extracts cleanly.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "aaer_releases/AAER-4599_34-106274.pdf",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("sec_accessing_edgar_data")
def accessing_edgar_data(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """*Accessing EDGAR Data*: the fair-access page this module's docstring quotes."""
    return fetch_file(
        source, data_dir, source.url, "sec_policy/accessing-edgar-data.html", force=force
    )


@register("sec_webmaster_faq")
def webmaster_faq(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Webmaster FAQ: the "Undeclared Automated Tool" error and the 10 rps ceiling."""
    return fetch_file(source, data_dir, source.url, "sec_policy/webmaster-faq.html", force=force)


@register("sec_rate_control_announcement_2021")
def rate_control_announcement(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The 27 July 2021 announcement of the 10 rps limit, kept as dated evidence of the rule."""
    return fetch_file(
        source, data_dir, source.url, "sec_policy/rate-control-limits-2021.html", force=force
    )


@register("sec_edgar_apis_page")
def edgar_apis_page(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Documentation of the four data.sec.gov endpoints and the nightly bulk zips.

    The bulk ``companyfacts.zip`` it advertises is **not** acquired: its size was never
    observed (the registry says "expect >1 GB") and the project's structured-financials path
    runs off the Financial Statement Data Sets instead (:mod:`aaer.acquire.fsds`).
    """
    return fetch_file(source, data_dir, source.url, "sec_policy/edgar-apis.html", force=force)


@register("sec_companyfacts_api_sample")
def companyfacts_sample(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """One ``companyfacts`` response (Apple Inc., CIK 0000320193), as a schema specimen.

    This is the only file in the project in which a us-gaap tag name was observed directly in
    an SEC response (``AccountsReceivableNetCurrent``), which is why
    :mod:`aaer.clean.xbrl_map` can mark exactly one of its twelve mappings as seen rather than
    assumed. Acquiring it is the first step of confirming the rest.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "sec_api/companyfacts_CIK0000320193.json",
        force=force,
    )

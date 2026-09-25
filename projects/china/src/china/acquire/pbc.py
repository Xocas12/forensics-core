"""People's Bank of China: the only free route to provincial credit, and a national control.

Provincial bank credit is the one physical proxy this project asked for that is **not**
available as a table anywhere free. That is a three-way confirmed negative, recorded in the
registry: the bureau's provincial annual database has exactly one leaf in its finance branch
and it is insurance premiums; the yearbook's finance chapter has no by-region deposits or
loans table in either the 2017 or the 2024 edition; and the central bank's own sources-and-
uses of credit funds table has no region dimension at all.

What does exist free is the annual *China Regional Financial Operation Report*. Each year
publishes a main report of about five megabytes plus one three-page summary per province
(and one for Shenzhen, which is not a province), and the summaries state the year-end
balance of loans **in prose and rounded**, for example "5.5 trillion yuan". So provincial
credit enters this project at roughly two significant figures, and any test built on it has
to survive that.

Two crawls live here:

``pbc_regional_financial_operation_reports``
    index page -> one page per year -> every PDF on that page. Around 33 files a year, a main
    report of about 5.3 MB plus 32 summaries of about 100 KB, over the twenty years the index
    lists: 2004-2015 and 2017-2024. So expect on the order of **660 files and 170 MB**. There
    is no 2016 edition: the verification pass checked and the index does not list one.

    The registry's download plan quotes "~430 total" instead. That figure belongs to the
    thirteen-year 2012-2024 window in the entry's title, while the same entry's verification
    field records the twenty years the index actually lists, and
    :func:`find_report_years` applies no year filter. If a smaller run is wanted, filter the
    years explicitly and say which window was taken; do not quote 430 for a crawl of 20.
``pbc_credit_statistics``
    the single verified national spreadsheet, kept as a control total. National only, by
    construction.
"""

from __future__ import annotations

import re
from pathlib import Path

from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_file, fetch_files
from china.acquire.registry import AcquireResult, register
from china.clean._html import decode_html, iter_anchors

__all__ = [
    "REPORT_INDEX_URL",
    "find_report_pdfs",
    "find_report_years",
]

#: Landing page of the regional financial operation report channel.
REPORT_INDEX_URL = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/125960/126049/index.html"

#: Per-year pages live under the report channel with a numeric id and a hexadecimal id.
_YEAR_PAGE_RE = re.compile(
    r"^(?:https?://[^/]+)?(/zhengcehuobisi/125207/125227/125960/126049/\d+/[0-9a-f]+/index\.html)$",
    re.IGNORECASE,
)
_PDF_RE = re.compile(r"\.pdf$", re.IGNORECASE)
_YEAR_RE = re.compile(r"(19|20)\d{2}")

#: Ceiling per PDF. The main report is about 5.3 megabytes; anything an order of magnitude
#: larger is a redirect to something else and should fail rather than fill the disk.
_MAX_PDF_BYTES = 64 * 1024 * 1024


def _absolute(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return "https://www.pbc.gov.cn" + (href if href.startswith("/") else "/" + href)


def find_report_years(index_html: bytes | str) -> dict[int, str]:
    """Map report year to per-year page URL, from the channel index page.

    The year is taken from the **link text**, which carries it in every listing style the
    channel has used, rather than from the URL, which carries only opaque ids.

    Parameters
    ----------
    index_html : bytes or str
        The index page.

    Returns
    -------
    dict of int to str
        Year to absolute URL. Later links win, which is harmless because the channel lists
        each year once.

    Raises
    ------
    ValueError
        If the page has no links at all, which means the fetch returned an error page.
    """
    text = decode_html(index_html) if isinstance(index_html, bytes) else index_html
    anchors = iter_anchors(text)
    if not anchors:
        raise ValueError("no links on the report index page; the fetch did not return it")
    years: dict[int, str] = {}
    for anchor in anchors:
        if not _YEAR_PAGE_RE.match(anchor.href):
            continue
        found = _YEAR_RE.search(anchor.text)
        if found is None:
            continue
        years[int(found.group(0))] = _absolute(anchor.href)
    return years


def find_report_pdfs(year_html: bytes | str) -> list[tuple[str, str]]:
    """Every PDF linked from one year's report page, with its link text.

    The link text is what maps a file to a province: the channel numbers them
    ``N.<province> ... .pdf``. Parsing that mapping is the loader's job
    (:func:`china.clean.pbc_reports.map_summaries_to_provinces`), not the fetcher's, so the
    text is returned rather than acted on.

    Parameters
    ----------
    year_html : bytes or str
        One year's report page.

    Returns
    -------
    list of (str, str)
        ``(absolute_url, link_text)`` in document order, deduplicated on the URL.
    """
    text = decode_html(year_html) if isinstance(year_html, bytes) else year_html
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in iter_anchors(text):
        if not _PDF_RE.search(anchor.href):
            continue
        url = _absolute(anchor.href)
        if url in seen:
            continue
        seen.add(url)
        out.append((url, anchor.text))
    return out


@register("pbc_regional_financial_operation_reports")
def regional_reports(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The regional financial operation reports: index, per-year pages, and every PDF.

    Three passes, each idempotent. The index and the year pages are always re-read from disk
    when they are already there, so a resumed run makes no request for a year it has already
    enumerated. PDFs are named by the last segment of their URL, which is the publisher's own
    opaque identifier; the year page is kept alongside them so the file-to-province mapping
    can be recovered later without another request.

    A year whose page cannot be fetched or parsed costs that year only. The result line names
    how many years were enumerated and how many files landed.
    """
    raw_dir = data_dir / "raw"
    index_rel = "pbc/report_index.html"
    index_path = raw_dir / index_rel

    if force or not index_path.exists():
        index_result = fetch_file(
            source,
            data_dir,
            url=source.url or REPORT_INDEX_URL,
            dest_rel=index_rel,
            force=force,
        )
        if not index_result.ok:
            return AcquireResult(
                source.id, False, f"report index unavailable: {index_result.detail}"
            )

    try:
        years = find_report_years(index_path.read_bytes())
    except (OSError, ValueError) as exc:
        return AcquireResult(source.id, False, f"report index unparseable: {exc}")
    if not years:
        return AcquireResult(
            source.id,
            False,
            "report index parsed but listed no per-year report pages; the channel layout "
            "has changed and find_report_years needs revisiting",
        )

    problems: list[str] = []
    work: list[tuple[str, ...]] = []
    for year, url in sorted(years.items()):
        year_rel = f"pbc/{year}/index.html"
        year_path = raw_dir / year_rel
        if force or not year_path.exists():
            year_result = fetch_file(source, data_dir, url=url, dest_rel=year_rel, force=force)
            if not year_result.ok:
                problems.append(f"{year}: {year_result.detail}")
                continue
        try:
            pdfs = find_report_pdfs(year_path.read_bytes())
        except OSError as exc:  # pragma: no cover - only on a disk error
            problems.append(f"{year}: {exc}")
            continue
        if not pdfs:
            problems.append(f"{year}: page fetched but links no PDF")
            continue
        for url_pdf, _text in pdfs:
            work.append((url_pdf, f"pbc/{year}/{url_pdf.rsplit('/', 1)[-1]}"))

    result = fetch_files(
        source, data_dir, work, force=force, max_bytes=_MAX_PDF_BYTES, label="report PDFs"
    )
    detail = f"{len(years)} report years enumerated; {result.detail}"
    if problems:
        detail += f"; {len(problems)} year-level problems: {problems[0]}"
    ok = result.ok and not problems
    return AcquireResult(source.id, ok, detail, result.paths, result.skipped_cached)


@register("pbc_credit_statistics")
def credit_statistics(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The national sources-and-uses of credit funds spreadsheet, as a control total.

    Nineteen kilobytes, digest pinned from the registry. It is acquired despite having **no**
    region dimension, for two reasons: it is the national denominator the provincial loan
    balances have to be checked against, and it is the primary evidence for the negative
    result that provincial credit is not freely published as a table. The bilingual sheet has
    merged header cells, so a loader must map rows by label rather than by index.

    Only the one verified file is fetched. The registry's download plan describes crawling
    the whole 1999-2026 archive of these spreadsheets; that is not implemented here, because
    a national series has no provincial content and the project needs it only as a level
    check.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_file(
        source,
        data_dir,
        url=source.url,
        dest_rel=f"pbc/credit/{source.url.rsplit('/', 1)[-1]}",
        expected_sha256=source.sha256 or None,
        force=force,
    )

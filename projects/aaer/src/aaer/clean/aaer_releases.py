"""Parse the SEC AAER listing pages into a tidy table of enforcement releases.

Input is the HTML saved by :func:`aaer.acquire.sec_edgar.aaer_listing` under
``data/raw/aaer_listing/page_NNN.html``. Output is one row per release: AAER number, date,
respondent, the Securities Act / Exchange Act release numbers, and the URL of the order PDF.

How the parser identifies fields, and why it does not use column positions
--------------------------------------------------------------------------
The registry entry ``aaer_listing_secgov`` describes the page as a table with Date,
Respondent(s) and Release No(s) columns and a hyperlink to a PDF, and reports "1 to 100 of 3342
items" with pages 2..34 addressed by ``?page=N``. That description came from a fetch tool's
**summariser**, not from reading the markup: no class name, no ``id``, no column order and no
date format was ever observed. The same entry warns that the summariser misspelled a
respondent's name, and instructs that the raw HTML be parsed rather than the summarised text.

So this parser assumes only that releases live in ``<table>`` rows, and identifies each field
by its content:

* the **AAER number** by the pattern ``AAER-<digits>`` anywhere in the row,
* the **PDF link** by the first anchor whose ``href`` ends in ``.pdf``,
* other **release numbers** by ``<prefix>-<digits>`` tokens that are not the AAER number
  (only ``33-`` and ``34-`` prefixes were actually observed),
* the **date** by trying a short list of formats against each cell,
* the **respondent** as the cell with the most text left once release numbers, AAER numbers
  and PDF file names have been stripped out -- not the longest cell, because the cell holding
  the release numbers also holds the hyperlink and is often longer while naming nobody.

Nothing is dropped quietly. :class:`ListingParse` reports how many table rows were seen, how
many became releases, and why the rest did not, so a page whose markup has changed shows up as
"0 of 100 rows parsed" rather than as a short table.

The parser has **not been run against a real listing page**; no page was fetched during this
session. It was developed against the synthetic fixture in
``tests/fixtures/synthetic_aaer_listing_page.html``, which encodes the structure the registry
describes. Expect to adjust :func:`parse_listing_page` the first time it meets the real markup,
and check :attr:`ListingParse.n_dropped` before trusting the output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
import pandas as pd

#: Base used to absolutise relative hrefs found in the listing.
SEC_BASE_URL = "https://www.sec.gov/"

#: "1 to 100 of 3342 items" -> 3342.
_TOTAL_ITEMS_RE = re.compile(r"of\s+([\d,]+)\s+items", re.IGNORECASE)

#: Dash characters an HTML table might place between "AAER" and its number: ASCII hyphen, en
#: dash, em dash. Written as escapes so that this source file stays ASCII.
_DASHES = "-\u2013\u2014"

#: "AAER-4599", "AAER 4599", "AAER No. 4599". A non-breaking space (HTML ``&nbsp;``) is matched
#: by ``\s``, which is Unicode-aware in Python.
_AAER_RE = re.compile(rf"AAER\s*(?:No\.?\s*)?[{_DASHES}]?\s*(\d+)", re.IGNORECASE)

#: A release-number token such as "34-106274". Deliberately generic: only the ``33-`` and
#: ``34-`` prefixes were observed in the registry, and asserting a full list of SEC release
#: prefixes here would be inventing a taxonomy. ``AAER-`` matches are filtered out afterwards.
_RELEASE_NO_RE = re.compile(r"\b([0-9A-Z]{2,4}-\d{3,7})\b")

#: A PDF file name appearing as link text, e.g. "34-900001.pdf".
_PDF_NAME_RE = re.compile(r"\S+\.pdf\b", re.IGNORECASE)

#: Date formats tried, in order. The listing's own format was never observed; these are the
#: forms the SEC uses elsewhere on the same site (the RSS feed's ``pubDate`` reads
#: "September 3, 2026") plus ISO.
_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m-%d-%Y")

#: Columns of the tidy release table, in order.
RELEASE_COLUMNS: tuple[str, ...] = (
    "aaer_number",
    "date",
    "respondent",
    "release_numbers",
    "pdf_url",
    "source_file",
)


@dataclass(frozen=True)
class ListingParse:
    """One or more listing pages, parsed, with the loss accounting attached.

    Attributes
    ----------
    releases : pandas.DataFrame
        Columns :data:`RELEASE_COLUMNS`. ``aaer_number`` is nullable integer, ``date`` is
        ``datetime64[ns]`` and may be ``NaT``, everything else is object dtype.
    n_rows_seen : int
        Table rows examined, header rows excluded.
    n_dropped : int
        Rows that carried neither an AAER number nor a PDF link and were therefore not treated
        as releases.
    drop_reasons : mapping
        Counts by reason, so a markup change is visible rather than silent.
    n_missing_date, n_missing_pdf, n_missing_aaer_number : int
        Releases kept despite a missing field. These are held, not dropped.
    total_items : int or None
        The "of N items" figure, when the page states one.
    """

    releases: pd.DataFrame
    n_rows_seen: int = 0
    n_dropped: int = 0
    drop_reasons: Mapping[str, int] = field(default_factory=dict)
    n_missing_date: int = 0
    n_missing_pdf: int = 0
    n_missing_aaer_number: int = 0
    total_items: int | None = None

    @property
    def n_releases(self) -> int:
        """Rows in :attr:`releases`."""
        return len(self.releases)

    def summary(self) -> str:
        """One line fit for a log: what was seen, what was kept, what was incomplete."""
        return (
            f"{self.n_releases} releases from {self.n_rows_seen} table rows "
            f"({self.n_dropped} dropped: {dict(self.drop_reasons)}); "
            f"missing date {self.n_missing_date}, pdf {self.n_missing_pdf}, "
            f"aaer number {self.n_missing_aaer_number}"
        )


def total_items(html: str) -> int | None:
    """Read the "1 to 100 of N items" count from a listing page.

    Parameters
    ----------
    html : str
        Raw page HTML.

    Returns
    -------
    int or None
        ``N``, or ``None`` when the page states no such count.
    """
    m = _TOTAL_ITEMS_RE.search(html)
    if m is None:
        return None
    return int(m.group(1).replace(",", ""))


def parse_date(text: str) -> pd.Timestamp | None:
    """Parse one cell as a date, trying :data:`_DATE_FORMATS`; ``None`` if none of them fit."""
    cleaned = " ".join(text.split())
    for fmt in _DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(cleaned, fmt))
        except ValueError:
            continue
    return None


def _cell_text(el) -> str:
    """Collapsed text of an element. ``str.split`` also folds non-breaking spaces."""
    return " ".join(el.text_content().split())


def _release_numbers(row_text: str, aaer_number: int | None) -> list[str]:
    found = [t for t in _RELEASE_NO_RE.findall(row_text) if not t.upper().startswith("AAER")]
    if aaer_number is not None:
        found = [t for t in found if t != f"AAER-{aaer_number}"]
    seen: dict[str, None] = {}
    for t in found:
        seen.setdefault(t, None)
    return list(seen)


def _identifier_residue(text: str) -> str:
    """``text`` with release numbers, AAER numbers and PDF file names stripped out.

    The respondent is picked as the cell with the most left over after this, rather than as
    the longest cell or a fixed column: on the page the registry describes, the cell holding
    the release numbers also holds the hyperlink, so it is often the longest one while carrying
    no name at all.
    """
    stripped = _PDF_NAME_RE.sub(" ", text)
    stripped = _AAER_RE.sub(" ", stripped)
    stripped = _RELEASE_NO_RE.sub(" ", stripped)
    return " ".join(stripped.replace(",", " ").replace(";", " ").split())


def parse_listing_page(
    html: str, *, source_file: str = "", base_url: str = SEC_BASE_URL
) -> ListingParse:
    """Parse one saved listing page.

    Parameters
    ----------
    html : str
        Raw page HTML as downloaded.
    source_file : str, default ""
        Provenance label written into every row, normally the file name.
    base_url : str, default :data:`SEC_BASE_URL`
        Base for absolutising relative hrefs.

    Returns
    -------
    ListingParse
    """
    doc = lxml.html.fromstring(html)
    rows: list[dict[str, object]] = []
    seen = dropped = missing_date = missing_pdf = missing_aaer = 0
    reasons: dict[str, int] = {}

    for tr in doc.xpath("//table//tr"):
        cells = tr.xpath("./td")
        if not cells:  # header rows carry only <th>
            continue
        seen += 1
        row_text = _cell_text(tr)
        aaer_match = _AAER_RE.search(row_text)
        aaer_number = int(aaer_match.group(1)) if aaer_match else None

        links = [
            a
            for a in tr.xpath(".//a[@href]")
            if a.get("href", "").split("?")[0].lower().endswith(".pdf")
        ]
        pdf_url = urljoin(base_url, links[0].get("href")) if links else None

        if aaer_number is None and pdf_url is None:
            dropped += 1
            key = "no_aaer_number_and_no_pdf_link"
            reasons[key] = reasons.get(key, 0) + 1
            continue

        texts = [_cell_text(c) for c in cells]
        date = next((d for d in (parse_date(t) for t in texts) if d is not None), None)
        release_numbers = _release_numbers(row_text, aaer_number)

        candidates = [_identifier_residue(t) for t in texts if t and parse_date(t) is None]
        candidates = [t for t in candidates if t]
        respondent = max(candidates, key=len) if candidates else ""

        missing_date += date is None
        missing_pdf += pdf_url is None
        missing_aaer += aaer_number is None
        rows.append(
            {
                "aaer_number": aaer_number,
                "date": date,
                "respondent": respondent,
                "release_numbers": ";".join(release_numbers),
                "pdf_url": pdf_url,
                "source_file": source_file,
            }
        )

    frame = pd.DataFrame(rows, columns=list(RELEASE_COLUMNS))
    frame["aaer_number"] = frame["aaer_number"].astype("Int64")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return ListingParse(
        releases=frame,
        n_rows_seen=seen,
        n_dropped=dropped,
        drop_reasons=reasons,
        n_missing_date=missing_date,
        n_missing_pdf=missing_pdf,
        n_missing_aaer_number=missing_aaer,
        total_items=total_items(html),
    )


def parse_listing_pages(paths: Iterable[Path]) -> ListingParse:
    """Parse several saved pages and concatenate them, deduplicating on AAER number.

    Parameters
    ----------
    paths : iterable of Path
        Saved listing pages, in any order; they are sorted by name for determinism.

    Returns
    -------
    ListingParse
        Counts are summed across pages. ``total_items`` is taken from the first page that
        states one, and a duplicate AAER number keeps its first occurrence -- the listing
        paginates a table that grows at the front, so the same release can appear on two pages
        downloaded minutes apart.
    """
    parses = [
        parse_listing_page(p.read_text(encoding="utf-8", errors="replace"), source_file=p.name)
        for p in sorted(paths, key=lambda q: q.name)
    ]
    if not parses:
        return ListingParse(releases=pd.DataFrame(columns=list(RELEASE_COLUMNS)))

    frame = pd.concat([p.releases for p in parses], ignore_index=True)
    labelled = frame["aaer_number"].notna()
    frame = pd.concat(
        [frame[labelled].drop_duplicates(subset="aaer_number", keep="first"), frame[~labelled]],
        ignore_index=True,
    ).sort_values(["aaer_number", "date"], na_position="last", ignore_index=True)

    reasons: dict[str, int] = {}
    for p in parses:
        for key, count in p.drop_reasons.items():
            reasons[key] = reasons.get(key, 0) + count
    return ListingParse(
        releases=frame,
        n_rows_seen=sum(p.n_rows_seen for p in parses),
        n_dropped=sum(p.n_dropped for p in parses),
        drop_reasons=reasons,
        n_missing_date=sum(p.n_missing_date for p in parses),
        n_missing_pdf=sum(p.n_missing_pdf for p in parses),
        n_missing_aaer_number=sum(p.n_missing_aaer_number for p in parses),
        total_items=next((p.total_items for p in parses if p.total_items is not None), None),
    )


def load_listing(raw_dir: Path) -> ListingParse:
    """Parse every ``page_*.html`` under ``raw_dir`` (normally ``data/raw/aaer_listing``)."""
    return parse_listing_pages(sorted(Path(raw_dir).glob("page_*.html")))

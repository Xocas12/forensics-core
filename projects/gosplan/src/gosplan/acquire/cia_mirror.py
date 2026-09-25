"""The declassified CIA estimates of the Soviet economy, fetched from the archive.org mirror.

**Why not cia.gov.** The CIA's own Electronic Reading Room blocks scripted access outright.
No ``cia.gov/readingroom`` path that is not the home page returns what it was asked for.
``/search/site/...``, ``/node/<id>``, ``/document/<docid>`` and ``/docs/<DOCID>.pdf`` answer a
``302`` to the reading-room root with an Akamai-style ``Access Denied`` body; the ``uzbek
cotton`` probes recorded under ``cia_foia_uzbek_cotton`` instead answered ``200`` carrying the
reading-room home page in place of the document. The registry records that the denial was
identical across the research user agent, a Chrome user agent with matching ``Accept``
headers, replayed session cookies plus ``Referer``, single-word queries and a separate fetch
tool, and that the **first** request is denied: it is a block, not a
rate limit, so retrying and backing off cannot help and only adds denied requests to the
CIA's logs. See registry ids ``cia_readingroom_search``, ``cia_readingroom_document_pdf``,
``cia_reading_room_soviet_io``, ``cia_foia_uzbek_cotton`` and
``cia_readingroom_caesar_polo_esau``, all marked ``blocked``, and none of which has an
acquirer.

**What this module targets instead.** The archive.org collection ``ciareadingroom`` is a
per-document mirror of the same corpus (973,499 items at the time the registry was written),
queryable through the standard archive.org search and metadata APIs, and it answers anonymous
requests normally. Item identifiers are ``cia-readingroom-document-<cia docid lowercase>``
and the per-item files drop that prefix.

**The caveat that must travel with anything drawn from it.** The mirror is a third-party
upload made in October 2024. Its completeness relative to the CIA's own holdings has *not*
been verified, and archive.org's ``advancedsearch`` matches item metadata (title, date,
description) rather than full document text. A search here that returns nothing is evidence
about the mirror's metadata, not about what the CIA released.

What is acquired is the **search manifest**, not the corpus: one JSON page per query, listing
identifiers, titles and dates. Pulling 973,499 PDFs is neither necessary nor polite;
:func:`document_file_urls` turns a manifest row into the per-document URLs so that a later,
explicitly scoped step can fetch the handful of documents a transcription target needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from gosplan.acquire._common import (
    fetch_file,
    ia_download_url,
    ia_num_found,
    ia_search_docs,
    read_json,
)
from gosplan.acquire.registry import AcquireResult, register

#: The archive.org collection that mirrors the CIA reading room.
COLLECTION = "ciareadingroom"

#: Query terms to manifest, as ``(slug, query)``. The first three are the queries whose hit
#: counts the registry recorded from this same mirror (784, 328 and 33 respectively), so a
#: fresh run can be compared against a known baseline; the fourth is the project's anchor,
#: which the blocked ``cia_foia_uzbek_cotton`` entry names as the search a human would run.
QUERIES: tuple[tuple[str, str], ...] = (
    ("soviet_economy_gnp", "Soviet economy GNP"),
    ("soviet_agricultural_statistics_cotton", "Soviet agricultural statistics cotton"),
    ("soviet_economic_statistics_falsification", "Soviet economic statistics falsification"),
    ("uzbek_cotton", "Uzbek cotton"),
)

#: Hit counts recorded in the registry for the first three queries above, for comparison.
RECORDED_HITS: dict[str, int] = {
    "soviet_economy_gnp": 784,
    "soviet_agricultural_statistics_cotton": 328,
    "soviet_economic_statistics_falsification": 33,
}

#: Rows per search page and the ceiling on pages per query. 10 x 1000 is far above every
#: recorded hit count; the cap exists so that a query that accidentally matches the whole
#: collection cannot walk 974 pages.
ROWS_PER_PAGE = 1000
MAX_PAGES = 10


def search_url(query: str, *, page: int = 1, rows: int = ROWS_PER_PAGE) -> str:
    """Build one ``advancedsearch.php`` URL, following the registry's download plan.

    Parameters
    ----------
    query : str
        Free-text terms; they are ANDed with the collection facet.
    page : int, default 1
        1-based page number.
    rows : int, default 1000
        Rows per page.

    Returns
    -------
    str
        A fully encoded archive.org search URL returning JSON.
    """
    params = [
        ("q", f"collection:{COLLECTION} AND ({query})"),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "date"),
        ("rows", str(rows)),
        ("page", str(page)),
        ("output", "json"),
    ]
    return "https://archive.org/advancedsearch.php?" + urlencode(params)


def document_file_urls(identifier: str) -> dict[str, str]:
    """URLs for the artefacts of one mirrored CIA document.

    The mirror stores each document as ``<identifier>/<docid>.pdf`` plus archive.org's
    derived text layer. Both are returned so that a caller can take the text for triage and
    the PDF for anything that has to be read off the page image.

    Parameters
    ----------
    identifier : str
        An archive.org identifier of the form ``cia-readingroom-document-<docid>``.

    Returns
    -------
    dict
        ``{"pdf": url, "text": url}``. The names follow the pattern recorded in the registry
        (the item prefix is dropped from the filename); confirm them against
        ``https://archive.org/metadata/<identifier>`` before a bulk pull, because archive.org
        does not guarantee derived-file names.
    """
    docid = identifier.removeprefix("cia-readingroom-document-")
    return {
        "pdf": ia_download_url(identifier, f"{docid}.pdf"),
        "text": ia_download_url(identifier, f"{docid}_djvu.txt"),
    }


@register("ia_ciareadingroom_mirror")
def cia_reading_room_mirror(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Manifest the mirrored CIA reading room for the project's query list.

    One JSON file per query page under ``data/raw/cia_mirror/``, plus the collection census
    from the registry's own URL. Paging stops as soon as a page returns no documents, so a
    query with 33 hits costs one request.

    Documents themselves are not downloaded here: see the module docstring and
    :func:`document_file_urls`.
    """
    out_dir = "cia_mirror"
    outcomes = []
    notes: list[str] = []

    census = fetch_file(
        source.id,
        data_dir,
        source.url or search_url("*", rows=0),
        f"{out_dir}/collection_census.json",
        force=force,
    )
    outcomes.append(census)
    if census.ok and census.path is not None and census.path.exists():
        found = ia_num_found(read_json(census.path))
        if found is not None:
            notes.append(f"collection numFound={found:,}")

    for slug, query in QUERIES:
        seen = 0
        for page in range(1, MAX_PAGES + 1):
            rel = f"{out_dir}/search_{slug}_p{page}.json"
            got = fetch_file(source.id, data_dir, search_url(query, page=page), rel, force=force)
            outcomes.append(got)
            if not got.ok or got.path is None or not got.path.exists():
                break
            docs = ia_search_docs(read_json(got.path))
            seen += len(docs)
            if len(docs) < ROWS_PER_PAGE:
                break
        expected = RECORDED_HITS.get(slug)
        drift = "" if expected is None else f" (registry recorded {expected})"
        notes.append(f"{slug}: {seen} hits{drift}")

    bad = [o for o in outcomes if not o.ok]
    paths = tuple(o.path for o in outcomes if o.ok and o.path is not None)
    detail = "; ".join(notes) if notes else f"{len(outcomes)} requests"
    if bad:
        detail = f"{detail}; {len(bad)} request(s) failed: {bad[0].detail}"
    return AcquireResult(source.id, not bad, detail, paths, all(o.cached for o in outcomes))

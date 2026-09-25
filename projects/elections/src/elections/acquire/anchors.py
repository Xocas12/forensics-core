"""Archived official pages: the national totals every loaded row has to add up to.

``docs/validation_anchors.md`` Tier 0 says the loader must reproduce the commission's own
national figures before any statistical claim is made. Those figures were read from three
archived pages, and this module caches those pages so the anchors can be re-read rather than
re-quoted. Nothing here is precinct data.

The commission's live sites are unreachable from outside Russia at the network level
(``cec_vybory_izbirkom_live``, ``cikrf_ru_live``), so the Internet Archive is the only route
to the authority's own numbers. It is a good enough route for national summaries and a bad
one for precinct tables: archive coverage of the leaf pages collapses outside Moscow, and the
per-subdomain census that would establish real coverage across roughly 85 regional subdomains
is a project of its own. That census is deliberately not attempted here; the registry entries
``wayback_vybory_2011_duma`` and ``wayback_vybory_2018_pres`` describe it under
``download_plan`` if it is ever wanted.

**None of these three downloads pins a digest.** The Wayback Machine rewrites archived pages
and injects a toolbar, so the body is not byte-stable; the independent verification pass on
``cikrf_eng_2018_wayback`` re-fetched it, found the same content and a different digest, and
said so. The registry's recorded digests are the record of one fetch, not an integrity target.

The unresolved discrepancy these pages document, restated because it is a decision and not a
defect: for 2018 the archived portal summary gives 56,426,399 votes for the winner and
109,001,306 registered voters, while the commission's own Resolution 152/1255-7 gives
56,430,712 and 109,008,428. The precinct file sums to the Resolution figure for registered
voters. Which one is the anchor is recorded as an open decision in ``data/ACCESS_NOTES.md``.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from elections.acquire._common import fetch_file
from elections.acquire.registry import AcquireResult, register


def _archived_page(source: Source, data_dir: Path, dest_rel: str, force: bool) -> AcquireResult:
    """Fetch one archived page at its registry URL, unpinned, into ``data/raw/anchors``."""
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_file(source, data_dir, url=source.url, dest_rel=dest_rel, force=force)


@register("cikrf_eng_2018_wayback")
def cikrf_english_results_2018(
    source: Source, data_dir: Path, force: bool = False
) -> AcquireResult:
    """The commission's English 2018 results page (Wayback, 2019-09-14).

    Source of the Resolution 152/1255-7 figures used as the 2018 Tier 0 anchor: 109,008,428
    on the electoral register, 56,430,712 votes for the winner, 76.69 per cent.
    """
    return _archived_page(source, data_dir, "anchors/cikrf_eng_2018.html", force)


@register("wayback_vybory_2011_duma")
def vybory_2011_duma_summary(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The archived results root for the 2011 State Duma election (Wayback, 2021-12-29).

    Windows-1251 HTML carrying the national summary table: 109,229,337 voters on the register
    and 32,371,737 votes for the winning list, 49.31 per cent. Both are Tier 0 anchors and
    both are reproduced exactly by summing the precinct file, which is the strongest available
    evidence that the mirror is faithful.

    Only this one page is fetched. The registry entry's ``download_plan`` describes a much
    larger crawl of territorial-commission pages; that is not attempted, because archive
    coverage below the region level is uneven enough that a partial harvest would be worse
    than none.
    """
    return _archived_page(source, data_dir, "anchors/vybory_2011_duma_summary.html", force)


@register("wayback_vybory_2018_pres")
def vybory_2018_presidential_summary(
    source: Source, data_dir: Path, force: bool = False
) -> AcquireResult:
    """The archived results root for the 2018 presidential election (Wayback, 2021-10-17).

    Windows-1251 HTML carrying the portal's own national summary: 109,001,306 voters on the
    register and 56,426,399 votes for the winner, the figures that disagree with the
    Resolution. Cached so the disagreement can be looked at rather than quoted. As for 2011,
    only the summary page is fetched, not the leaf crawl the entry describes.
    """
    return _archived_page(source, data_dir, "anchors/vybory_2018_pres_summary.html", force)

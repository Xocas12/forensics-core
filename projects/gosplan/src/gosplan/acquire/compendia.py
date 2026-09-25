"""Congressional compendia and the anchor's documentation.

Two groups, both of which exist to constrain the official series from outside.

**The Joint Economic Committee compendia** are the published form of the CIA's Soviet
national-accounts work: *USSR: Measures of Economic Growth and Development, 1950-80* (1982),
*Soviet Economy in the 1980's: Problems and Prospects* (1982) and *Gorbachev's Economic Plans*
(1987). The committee's own site answers ``403 Forbidden`` to scripts (registry id
``jec_senate_gov_reports``, marked blocked), so the routes of record are archive.org and the
Wayback Machine, which serve the same public-domain files. Everything fetched here is a
scanned PDF: these are reading and table-extraction targets, not machine-readable data.

**The anchor's documentation** is the Cucciolla (2017) article and thesis, which carry the
only quantitative statement of the Uzbek cotton affair that the project treats as citable.
They are acquired because ``docs/validation_anchors.md`` records an unresolved internal
inconsistency in them -- 270,000 to 340,000 tons per year in one passage against 4.548
million tons over 1978-1983, about 758,000 tons per year, in another -- and that has to be
settled by reading the sources, not by picking the number that suits. The Wikipedia figure of
981,000 tons for 1983 alone is unverified against anything and is not acquired at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gosplan.acquire._common import fetch_file, ia_download_url, ia_select, many, read_json, single
from gosplan.acquire.registry import AcquireResult, register

#: Wayback snapshot of *Gorbachev's Economic Plans*, volume 1, recorded verbatim in the
#: registry's download plan. The ``id_`` flag makes the Wayback Machine return the archived
#: bytes rather than a rewritten page.
GORBACHEV_VOL1_WAYBACK = (
    "http://web.archive.org/web/20240918021631id_/"
    "https://www.jec.senate.gov/reports/100th%20Congress/"
    "Gorbachev's%20Economic%20Plan%20Volume%20I%20(1438).pdf"
)


def _ia_identifier(url: str) -> str:
    """Identifier from an archive.org ``/metadata/<id>`` or ``/download/<id>/<file>`` URL."""
    parts = [p for p in url.split("/") if p]
    for marker in ("metadata", "download"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return parts[-1] if parts else ""


def _ia_item(
    source: Any,
    data_dir: Path,
    identifier: str,
    prefix: str,
    *,
    force: bool = False,
) -> AcquireResult:
    """Fetch one archive.org item's metadata, then its scanned PDF and text derivative."""
    meta = fetch_file(
        source.id,
        data_dir,
        f"https://archive.org/metadata/{identifier}",
        f"{prefix}/{identifier}_metadata.json",
        force=force,
    )
    if not meta.ok or meta.path is None or not meta.path.exists():
        return AcquireResult(source.id, False, f"metadata: {meta.detail}")

    metadata = read_json(meta.path)
    chosen = ia_select(metadata, formats=("text pdf", "djvutxt"), suffixes=(".pdf", "_djvu.txt"))
    names = [str(f["name"]) for f in chosen if f.get("name") and "_encrypted" not in str(f["name"])]
    if not names:
        return AcquireResult(
            source.id,
            False,
            f"metadata fetched ({meta.detail}) but it lists no PDF or text derivative",
            (meta.path,),
        )
    items = [(ia_download_url(identifier, n), f"{prefix}/{n}") for n in names]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"metadata + {result.detail}",
        (meta.path, *result.paths),
        result.skipped_cached,
    )


@register("jec_ussr_measures_1982")
def jec_ussr_measures(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """*USSR: Measures of Economic Growth and Development, 1950-80* (JEC, 1982).

    The CIA's own summary of why this volume exists, quoted in the archive.org record: the
    Soviet Union does not publish measures comparable with Western ones, so the agency
    supplied its estimates of Soviet GNP. That makes the volume both a data source and a
    piece of evidence about the reconstruction methods whose disagreement
    ``docs/known_traps.md`` warns about.

    Fetched from the ERIC upload on archive.org. Two other digitisations exist -- a microfiche
    upload and three HathiTrust full-view copies -- and the committee's own PDF is reachable
    through a recorded Wayback snapshot; none is fetched, because one copy of a scan is
    enough and the alternatives are recorded in the registry if this one moves.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return _ia_item(source, data_dir, _ia_identifier(source.url), "jec", force=force)


@register("jec_soviet_economy_1980s_1982")
def jec_soviet_economy_1980s(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """*Soviet Economy in the 1980's: Problems and Prospects*, part 1 (JEC, 1982).

    Part 1 only. **Part 2 is not acquired and must not be quietly treated as present**: no
    fetch of it ever succeeded, its committee URL was seen only in web-search results, and no
    archive.org item for it was located. Anything computed from this volume covers half of
    it.

    Do not confuse this compendium with the RAND paper of nearly the same name (registry id
    ``dtic_ada121312_rand``, Gustafson 1982), which the registry keeps solely to prevent the
    mix-up and which has no acquirer.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    result = _ia_item(source, data_dir, _ia_identifier(source.url), "jec", force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"{result.detail}; part 2 not acquired (no confirmed source)",
        result.paths,
        result.skipped_cached,
    )


@register("jec_gorbachev_economic_plans_1987")
def jec_gorbachev_plans(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """*Gorbachev's Economic Plans* (JEC, 1987): volume 1 via the Wayback Machine.

    The HathiTrust bibliographic record is fetched first because it is the evidence that both
    volumes are public domain and full view; the API answers without the Cloudflare challenge
    that blocks the catalogue and page-viewer pages themselves.

    **Volume 2 is not acquired.** Its committee URL came only from a web search and no
    snapshot of it was confirmed, so there is nothing here to fetch that anyone has verified.
    Obtaining it is a human task: either a HathiTrust session for ``mdp.39015009962542`` or a
    Wayback availability lookup on the committee URL, after which the result belongs in the
    registry before any code touches it.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    items = [
        (source.url, "jec/gorbachev_hathitrust_record.json"),
        (GORBACHEV_VOL1_WAYBACK, "jec/gorbachev_economic_plans_vol1.pdf"),
    ]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"{result.detail}; volume 2 not acquired (no confirmed URL)",
        result.paths,
        result.skipped_cached,
    )


@register("cucciolla_2017_phd_thesis_imt_lucca")
def cucciolla_thesis(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Cucciolla (2017), *The Uzbek cotton affair (1975-1991)*, via a Wayback snapshot.

    The canonical host does not resolve, one institutional mirror answers 403 and the CORE
    record is behind a Cloudflare challenge; the Wayback snapshot is the only route that
    worked, and it is pinned to the digest recorded when the thesis was downloaded and its
    title page read. A Wayback snapshot is immutable by construction, so a digest mismatch
    here would mean the wrong document, not a new edition.

    The passages the project needs -- the affair's tonnage and rouble figures, and a table of
    annual Soviet cotton production -- are indexed by approximate page in the registry entry.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(
        source,
        data_dir,
        source.url,
        "anchor/cucciolla_2017_thesis.pdf",
        force=force,
        expected_sha256=source.sha256 or None,
    )


@register("cucciolla_2017_cahiers_monde_russe")
def cucciolla_article(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Cucciolla (2017) in *Cahiers du monde russe* 58/4, open access on OpenEdition.

    The single citable statement of the anchor's magnitude, at paragraph 23, together with
    the paragraph-11 figures that contradict it. Stored as HTML with no digest pinned: the
    article was read through a fetch tool that reported no byte-level record, so there is
    nothing honest to pin it to. Cite by paragraph number, which is stable in OpenEdition's
    markup, not by page.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(source, data_dir, source.url, "anchor/cucciolla_2017_article.html", force=force)

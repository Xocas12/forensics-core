"""Commission-level ancillary data: what the results tables do not contain.

``docs/known_traps.md`` trap 1 is the reason this module exists. The results files carry no
precinct type and no precinct name: the ``uik`` column is a bare number, so hospital, prison,
military and remote stations - the small ones that produce round percentages honestly -
cannot be identified from the results at all. The GIS-Lab dump of the commission register is
the only source in the registry that names and geolocates the stations, and its February 2018
snapshot sits three weeks before the March 2018 vote.

Two limits that belong with the download, not with the analysis that uses it:

* **2018 only.** The earliest snapshot GIS-Lab published is April 2014, and Russia replaced
  ad-hoc per-election commissions with permanent five-year ones in 2013, so it cannot be
  back-joined to 2011 precinct numbers with any confidence (registry entry
  ``gislab_cik_uik_20140404_head``). The 2011 size-conditioning control has no station-type
  covariate available and must say so.
* **The join is not a key join.** 97,476 commissions against 97,699 result rows, with the
  region as a slug on one side and a full Russian name on the other, and the TIK name carrying
  a numeric prefix in the results. The registry's ``download_plan`` sets out the three-step
  key. Unmatched rows must be flagged rather than dropped: special precincts are exactly the
  ones most likely to fail the join, and dropping them reintroduces the bias being controlled.

Extraction is not done here. The archive is 7-Zip, which needs ``py7zr``; that package is not
currently a dependency of this project, so unpacking belongs to ``elections.clean`` once it is
added.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import RateLimiter, Source

from elections.acquire._common import fetch_file
from elections.acquire.registry import AcquireResult, register

#: The registry's ``download_plan`` for ``gislab_cik_uik_20180215`` asks for about one request
#: per second on this small volunteer-run host. That is the research pass's own recommendation
#: recorded there, not a published limit from gis-lab.info. ``config/forensics.toml`` is shared
#: by the whole workspace and lists no entry for this host, so the pace is set here instead.
GISLAB_RATE_LIMIT = RateLimiter(1.0)


@register("gislab_cik_uik_20180215")
def cik_uik_20180215(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The GAS Vybory commission register, snapshot of 15 February 2018 (4.9 MB, 7-Zip).

    One member, ``cik_uik.csv``, 100,399 rows: 85 regional commissions, 2,838 territorial and
    97,476 precinct commissions, with name, postal address, voting-room address and
    coordinates. This is the only verified way to identify special precincts, which is what
    the size-conditioning control in ``docs/known_traps.md`` needs a covariate for.

    Pinned to the digest in the registry: unlike the Wayback pages, this is a static file on
    an ordinary web server and its bytes should not move.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or "http://gis-lab.info/data/cik/cik_uik_20180215.7z",
        dest_rel="gislab/cik_uik_20180215.7z",
        expected_sha256=source.sha256,
        force=force,
        limiter=GISLAB_RATE_LIMIT,
    )


@register("gislab_wiki_wayback")
def gislab_wiki_documentation(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The archived GIS-Lab wiki page: the only reachable schema documentation for the dump.

    The live wiki has been returning HTTP 502 (registry entry ``gislab_wiki_live``) while the
    data host beside it serves files normally, so this Wayback snapshot is where the field
    descriptions, the list of snapshot dates and the known-deficiencies section come from.
    Reference material, cached next to the archive it documents.

    No digest is pinned. The Wayback Machine injects its own toolbar and timestamps into the
    body, so the bytes differ between fetches; the verification pass on a sibling Wayback
    entry in this registry saw exactly that (same content, different digest, six bytes of
    size difference).
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_file(
        source,
        data_dir,
        url=source.url,
        dest_rel="gislab/wiki_gas_vybory_wayback.html",
        force=force,
    )

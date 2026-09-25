"""Method references that are fetchable, cached beside the data they will be applied to.

Only one of the two papers behind the Tier 1 anchors can be retrieved by a script. The PNAS
supplementary material is behind a bot block (HTTP 403 to every non-browser client) and the
authors' own data host no longer resolves, so ``klimek_pnas_2012_si`` stays a human task in
``data/ACCESS_NOTES.md``. The PubMed Central full text of the same paper is open, and it
carries the two method details the turnout-bimodality stub needs to cite: the rule excluding
units with an electorate below 100, and the authors' claim that their results do not depend
much on the level of aggregation.

The paper's own supplementary payload is two files and neither is data - the article's
"Associated Data" section lists an 812-byte index page and one SI PDF - so nothing here
substitutes for the precinct data, and no bytes of Klimek et al. data are budgeted for.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from elections.acquire._common import challenge_marker, fetch_file
from elections.acquire.registry import AcquireResult, register

_KLIMEK_REL = "literature/klimek_pnas_2012_pmc.html"

#: The article page recorded at 152,062 bytes. A body far below this is an interstitial or a
#: stub, not the full text; used only to decide whether to look for a challenge marker.
_MIN_PLAUSIBLE_BYTES = 50_000


@register("pmc_klimek_2012")
def klimek_2012_full_text(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """PubMed Central full text of Klimek, Yegorov, Hanel & Thurner (2012), PNAS 109(41).

    Fetched with a guard rather than plainly, because this host has already been seen serving
    a reCAPTCHA interstitial under HTTP 200 to a scripted client (registry entry
    ``klimek_pnas_2012_si``). A 200 that carries a challenge page would otherwise be recorded
    in ``SOURCES.yaml`` as ``verified``, which would be a false integrity claim. When the
    guard fires the downloaded file is left in place, named in the failure detail, so that a
    human can look at what actually came back.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    result = fetch_file(source, data_dir, url=source.url, dest_rel=_KLIMEK_REL, force=force)
    if not result.ok or result.skipped_cached:
        return result

    path = result.paths[0]
    marker = challenge_marker(path)
    if marker is not None:
        return AcquireResult(
            source.id,
            False,
            f"host returned an anti-bot interstitial (matched {marker!r}), not the article; "
            f"body kept at raw/{_KLIMEK_REL} for inspection",
            result.paths,
        )
    if path.stat().st_size < _MIN_PLAUSIBLE_BYTES:
        return AcquireResult(
            source.id,
            False,
            f"body is {path.stat().st_size:,} bytes, far short of the 152,062 recorded for "
            f"this page; kept at raw/{_KLIMEK_REL} for inspection",
            result.paths,
        )
    return result

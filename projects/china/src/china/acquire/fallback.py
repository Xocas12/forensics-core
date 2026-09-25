"""Fallback and control-total sources: national aggregates that the blocked portal would have given.

Neither of these is provincial, and that is the point. When the provincial spine is a stack of
JPEG scans, the two things worth having in machine-readable form are the **denominator** of
the provincial-sum gap and a **national control total** for the freight proxy, so that an
extraction error in one province shows up as a failed reconciliation rather than as a finding.

``worldbank_chn_gdp``
    National gross domestic product in current local currency, one request, no key, no
    authentication. Carries a vintage warning that has to be honoured: it is the **current**
    vintage, already revised through the fourth economic census, so pairing it with a
    2015-vintage provincial sum measures the revision and not the gap. For a same-vintage
    comparison the denominator has to come from the same yearbook edition as the provincial
    rows, which is another JPEG. The World Bank series is the cross-check, not the anchor.

``mot_transport_statistical_bulletins``
    The transport ministry's annual bulletin gives national freight totals only, confirmed by
    the verification pass finding no by-province table on the page. It is acquired as the
    control total for the provincial rail-freight column of yearbook table 16-14.

No digest is pinned on the World Bank response. Its body legitimately changes whenever an
indicator is revised, which is information, not an acquisition failure; the response carries
its own ``lastupdated`` field for exactly that check, and the registry's recorded digest was
the point-in-time record. Note that "was": both entries here are multi-file families under a
single source id, so the first successful run overwrites the recorded digest with the last
member's. ``data/fetch_log.jsonl`` keeps the per-file record; ``data/SOURCES.yaml`` does not.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_files
from china.acquire.registry import AcquireResult, register

__all__ = ["WORLD_BANK_INDICATORS", "worldbank_url"]

#: World Bank indicator codes named in the registry's download plan, with why each is wanted.
WORLD_BANK_INDICATORS: dict[str, str] = {
    "NY.GDP.MKTP.CN": "current local currency; divide by 1e8 for the yearbook's 100 million yuan",
    "NY.GDP.MKTP.KN": "constant local currency, for real comparisons",
    "NY.GDP.MKTP.KD.ZG": "annual growth rate, the headline the provincial indices are read against",
}

_WORLD_BANK_TEMPLATE = (
    "https://api.worldbank.org/v2/country/CHN/indicator/{indicator}"
    "?format=json&per_page=100&date=1990:2024"
)

#: The railway statistics bulletin PDF, confirmed by a HEAD request returning 200 and a
#: content length of 7,473,376 bytes. Its provincial content was **not** verified; it is
#: acquired for its national rail freight totals.
RAILWAY_BULLETIN_2023 = (
    "https://www.mot.gov.cn/shuju/fenxigongbao/hangyegongbao/202601/P020260127538858021035.pdf"
)


def worldbank_url(indicator: str) -> str:
    """URL for one World Bank indicator, on the query string the registry verified.

    Parameters
    ----------
    indicator : str
        Indicator code, e.g. ``"NY.GDP.MKTP.CN"``.

    Returns
    -------
    str
        Absolute URL.

    Raises
    ------
    KeyError
        If the indicator is not one of :data:`WORLD_BANK_INDICATORS`. Fetching an indicator
        nobody wrote down is how an unregistered series gets into a pipeline.
    """
    if indicator not in WORLD_BANK_INDICATORS:
        raise KeyError(
            f"{indicator!r} is not in WORLD_BANK_INDICATORS; add it there, with a reason, first"
        )
    return _WORLD_BANK_TEMPLATE.format(indicator=indicator)


@register("worldbank_chn_gdp")
def worldbank_gdp(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """National gross domestic product, three indicators, as the gap's denominator of last resort.

    The first URL is the registry's own, so the file the registry describes is the file that
    lands. The other two come from the same template with the indicator swapped, exactly as
    the entry's download plan sets out.
    """
    primary = source.url or worldbank_url("NY.GDP.MKTP.CN")
    work: list[tuple[str, ...]] = [(primary, "worldbank/NY.GDP.MKTP.CN.json")]
    work.extend(
        (worldbank_url(indicator), f"worldbank/{indicator}.json")
        for indicator in ("NY.GDP.MKTP.KN", "NY.GDP.MKTP.KD.ZG")
    )
    return fetch_files(source, data_dir, work, force=force, label="indicator series")


@register("mot_transport_statistical_bulletins")
def transport_bulletins(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The 2023 transport bulletin page and the railway statistics bulletin PDF.

    National totals only. The verification pass grepped the bulletin page and found the
    national railway freight sentence and zero occurrences of any by-province marker, so this
    is a control total and not a provincial source; provincial rail freight comes from
    yearbook table 16-14.

    Only the 2023 edition is acquired, because that is the one the registry verified. The
    entry's download plan describes crawling the bulletin index for every year; that index
    was returned by search but never fetched, so building a crawler against it would be
    writing code against a page nobody has seen.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_files(
        source,
        data_dir,
        [
            # No digest. The registry records none for this entry, and reading
            # ``source.sha256`` here would be worse than useless: this is a two-file family
            # under one id, so ``fetch`` rewrites the entry with the railway PDF's digest
            # after the first run and a later ``--force`` would check the bulletin page
            # against it. See ``_common.py`` on digests recorded for a family.
            (source.url, "mot/bulletin_2023.html"),
            (RAILWAY_BULLETIN_2023, "mot/railway_bulletin_2023.pdf"),
        ],
        force=force,
        label="bulletin files",
    )

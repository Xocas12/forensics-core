"""Physical cotton output and the hydrological correlate: the anchor's independent evidence.

The Uzbek cotton affair is the project's only validation anchor, and it is testable only
because the padded quantity -- raw cotton delivered -- was also estimated by parties the
falsifiers did not control. Two of those estimates are machine-readable and cover the
1978-1983 window:

* **FAOSTAT** bulk crop production. The USSR is filed under the *Europe* regional file
  (area code 228), not Asia; the Uzbek SSR has no back-cast, its FAOSTAT series beginning in
  1992 (area code 235, in the Asia file). So FAOSTAT gives a union-level series across the
  window and a republic-level series only after the union dissolved.
* **USDA Foreign Agricultural Service** production, supply and distribution. USSR market
  years 1960-1986, Uzbekistan from 1987, twelve attributes each. Reported in 480-lb lint
  bales, not tonnes of seed cotton, so it measures a different physical quantity than
  FAOSTAT and than the Soviet annuals: reconciling the three is a units problem before it is
  a forensics problem (``docs/data_dictionary.md``).

Neither is pinned to a checksum. Both publishers revise and republish on a schedule -- USDA
around the monthly WASDE release -- and pinning would report a legitimate republication as
corruption. Change is detected instead by the digest the registry records after each fetch.

The **hydrological correlate is missing for the anchor window**, and this module fetches the
CAWater-Info pages anyway so that the gap is documented rather than assumed. The Amu Darya
water-delivery tables that the design assumed would provide an irrigation-withdrawal control
begin in 1992. The morphometric and river-resource pages of the same database were never
opened during scaffolding and are the only remaining candidates for a pre-1992 series; they
are fetched here so a person can look. Until one of them yields numbers, the independent
physical check on the anchor is FAOSTAT versus USDA and nothing else.

Nothing here parses, converts or joins anything. Unit conversion (bales to tonnes, lint to
seed cotton) and the three-way reconciliation belong downstream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gosplan.acquire._common import many, single
from gosplan.acquire.registry import AcquireResult, register

#: CAWater-Info "Database of the Aral Sea" pages named in the registry's download plan. The
#: first four are the water-delivery tables (1992 onward, i.e. **after** the anchor window);
#: the last two were never opened and are the pre-1992 candidates.
_CAWATER_BASE = "http://www.cawater-info.net/aral/data"
CAWATER_PAGES: tuple[str, ...] = (
    "amu_water_delivery_aral_veg",
    "amu_water_delivery_aral_nonveg",
    "syr_water_delivery_aral_veg",
    "syr_water_delivery_aral_nonveg",
    "morpho",
    "resources",
)


@register("faostat_qcl_bulk_europe_ussr")
def faostat_europe(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """FAOSTAT QCL bulk, Europe region: USSR (area 228) seed cotton, 1961-1991.

    Item codes of interest are 328 (seed cotton, unginned), 767 (cotton lint, ginned) and
    329 (cotton seed); element 5510 is production in tonnes, 5312 area harvested, 5419 yield.
    The registry records that USSR seed cotton carries the official flag ``A`` for all 31
    years while cotton lint for the same area is flagged ``X`` (unofficial), which is why the
    flag column must survive into any derived table.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(source, data_dir, source.url, "faostat/qcl_europe.zip", force=force)


@register("faostat_qcl_bulk_asia_uzbekistan")
def faostat_asia(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """FAOSTAT QCL bulk, Asia region: Uzbekistan (area 235) seed cotton, 1992-2024.

    Acquired despite starting after the anchor window: it is the post-Soviet continuation of
    the same physical series and the only FAOSTAT republic-level cotton data that exists. Do
    not splice it onto the union series without saying so -- 228 and 235 are different
    territories.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(source, data_dir, source.url, "faostat/qcl_asia.zip", force=force)


@register("usda_psd_cotton_bulk")
def usda_psd_cotton(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """USDA FAS PSD bulk cotton file: USSR 1960-1986, Uzbekistan 1987 onward.

    The independent Western estimate of the same quantity FAOSTAT reports, and the natural
    cross-source reconciliation partner. Two traps recorded in the registry: values are
    thousands of 480-lb lint bales rather than tonnes of seed cotton, and the file carries no
    "Former Soviet Union" aggregate, so 1987-1991 union totals have to be summed across the
    successor republics -- an aggregation whose composition must be stated wherever it is
    used.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(source, data_dir, source.url, "usda_psd/psd_cotton_csv.zip", force=force)


@register("cawater_aral_database")
def cawater_aral(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """CAWater-Info Aral Sea database pages, English and Russian variants.

    Fetched to settle a feasibility question, not because the data is known to be useful.
    The water-delivery tables verified during scaffolding run 1992-2025 and therefore do
    **not** cover the 1978-1983 padding window. ``morpho`` (Aral morphometry, described as
    1911-2018) and ``resources`` (Amu Darya and Syr Darya river resources) were never opened
    and may or may not contain numeric tables for the Soviet period; the Russian-language
    variants sometimes carry longer series than the English ones, so both are pulled.

    The pages are windows-1251 HTML served over plain HTTP; no HTTPS endpoint was confirmed.
    """
    items: list[tuple[str, str]] = []
    for stem in CAWATER_PAGES:
        items.append((f"{_CAWATER_BASE}/{stem}_e.htm", f"cawater/{stem}_e.htm"))
        items.append((f"{_CAWATER_BASE}/{stem}.htm", f"cawater/{stem}_ru.htm"))
    return many(source, data_dir, items, force=force)

"""The documentary sources: the accounting reform, and the admitted falsifications.

These six pages are not inputs to a model. They are the evidence for the two things the
project's design rests on, and each one is quoted verbatim in
``docs/validation_anchors.md``:

* **When the reform bites.** The National Bureau of Statistics' own question-and-answer page
  of 27 December 2019 states that the plan was approved in June 2017 and that unified
  accounting was implemented in early 2020, computing the **2019** regional product. So the
  break in any discontinuity test is the 2019 **data year**, not the 2017 approval. The
  earlier Q&A with the deputy head, Xinhua of 13 November 2019 and China Daily of 7 January
  2020 corroborate it.
* **Which provinces and years are positives.** China Daily of 18 January 2017 for Liaoning
  (fiscal data, 2011-2014), Xinhua of 20 January 2018 for Inner Mongolia and for Binhai New
  Area in Tianjin. Read the fine print in ``docs/validation_anchors.md`` before using any of
  them as a label: the Liaoning admission concerns fiscal rather than gross-product data, and
  the Tianjin revision is sub-provincial.

No digest is pinned on any of these. A news page's bytes legitimately change (footers,
navigation, advertising), so a pinned digest would turn ordinary page maintenance into an
acquisition failure. The anchor is the quoted text, which lives in the docs, not the byte
count. The registry's recorded digest stays as the point-in-time record it is.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_file
from china.acquire.registry import AcquireResult, register

__all__ = ["NEWS_DEST"]

#: Registry id -> destination file under ``data/raw``.
NEWS_DEST: dict[str, str] = {
    "nbs_qa_unified_accounting_2019_12_27": "news/nbs_qa_2019_12_27.html",
    "nbs_qa_unified_accounting_plan_2017": "news/nbs_qa_reform_plan_2017.html",
    "chinadaily_reform_2020_01_07": "news/chinadaily_reform_2020_01_07.html",
    "chinadaily_liaoning_2017_01_18": "news/chinadaily_liaoning_2017_01_18.html",
    "xinhua_reform_2019_11_13": "news/xinhua_reform_2019_11_13.html",
    "xinhua_data_inflation_2018_01_20": "news/xinhua_data_inflation_2018_01_20.html",
}


def _page(source: Source, data_dir: Path, force: bool) -> AcquireResult:
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    dest_rel = NEWS_DEST.get(source.id)
    if dest_rel is None:  # pragma: no cover - guarded by test_acquire_registry
        return AcquireResult(source.id, False, f"no destination configured for {source.id!r}")
    return fetch_file(source, data_dir, url=source.url, dest_rel=dest_rel, force=force)


@register("nbs_qa_unified_accounting_2019_12_27")
def nbs_qa_2019(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The bureau's Q&A of 27 December 2019: the primary source for the reform's first data year.

    It is this page, and not a press report, that fixes the break at the 2019 data year.
    """
    return _page(source, data_dir, force)


@register("nbs_qa_unified_accounting_plan_2017")
def nbs_qa_plan(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The earlier Q&A with the bureau's deputy head on the reform plan itself.

    The source for the reform's stated motive, in the bureau's own words: that the summed
    regional product and national gross domestic product were too far apart. The page's own
    publication date is not in the static HTML, so it must be read in a browser; the registry
    records that caveat.
    """
    return _page(source, data_dir, force)


@register("chinadaily_reform_2020_01_07")
def chinadaily_reform(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """China Daily, 7 January 2020, reporting the bureau head on 5 January 2020.

    Carries the English sentence stating that the new accounting system takes effect while
    calculating the annual regional product of 2019.
    """
    return _page(source, data_dir, force)


@register("chinadaily_liaoning_2017_01_18")
def chinadaily_liaoning(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """China Daily, 18 January 2017: the Liaoning governor's admission.

    States the years 2011 to 2014 and the phrase "large-scale financial deception", and notes
    that provincial product grew 0.26 percent in 2015. It states **no** magnitude for a
    gross-product distortion, which is why the Liaoning label is a fiscal one.
    """
    return _page(source, data_dir, force)


@register("xinhua_reform_2019_11_13")
def xinhua_reform(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Xinhua, 13 November 2019: the reform announced, and the pre-reform regime named.

    Records that regional and national product had used a graded accounting system since
    1985, which is the regime the discontinuity test is measuring the end of.
    """
    return _page(source, data_dir, force)


@register("xinhua_data_inflation_2018_01_20")
def xinhua_data_inflation(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Xinhua, 20 January 2018: the Inner Mongolia and Binhai New Area revisions.

    The source of the three quantities in ``docs/validation_anchors.md``: Inner Mongolia's
    2016 fiscal revenue cut by 53 billion yuan (26.3 percent), Binhai New Area's 2016 product
    revised down 33.4 percent to 665 billion yuan, and Liaoning reporting a 2.5 percent drop
    in 2016 regional product against 6.7 percent national growth. Binhai is sub-provincial:
    see :data:`china.clean.provinces.SUBPROVINCIAL_UNITS`.
    """
    return _page(source, data_dir, force)

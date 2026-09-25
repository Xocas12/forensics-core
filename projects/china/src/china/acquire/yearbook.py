"""China Statistical Yearbook web editions: the project's spine, and its bottleneck.

The National Bureau of Statistics' portal cannot deliver a provincial series today: its
legacy ``easyquery`` API is blocked from this network and its replacement, which does answer
anonymously, has an unknown values endpoint (see ``data/ACCESS_NOTES.md`` and
:mod:`china.acquire.nbs_api`). So the provincial series has to come from the yearbook editions
published at ``https://www.stats.gov.cn/sj/ndsj/<year>/``. Those pages **are** reachable, and
they have one property nothing else in this project has: each edition is a frozen snapshot
that was never retro-revised, so the archive of editions is exactly the vintage series the
project needs. The 2015 edition still carries Liaoning's pre-revision 2011-2014 figures.

The cost is that the tables are **JPEG scans**. The 2024 edition's contents frame holds 762
links, 702 of them ``.jpg``, and not one spreadsheet. So this module acquires images and
contents frames; turning an image into numbers is
:func:`china.clean.yearbook.extract_table_image`, which is a stub.

How a table is located
----------------------
Never by guessing a file name. Both the naming convention and the table numbering drift
between editions (2017 ``html/EN0309.jpg``, 2020 ``html/E0309.jpg``, 2024
``html/E03-09.jpg``), so the acquirers here:

1. make sure the edition's contents frame is on disk, fetching the missing ones under the
   ``csy_web_editions`` registry id, which is the entry that describes them;
2. parse it with :func:`china.clean.yearbook.parse_toc`;
3. select by printed title, not by number, with
   :func:`china.clean.yearbook.find_tables`;
4. fetch whatever that resolves to, alongside the one file the registry itself verified,
   whose recorded digest is checked.

That means the first run of any table acquirer also pays for the contents-frame crawl: 21
small pages, one English contents frame per edition from 2005 to 2025. Every later run finds
them on disk and makes no request for them. :func:`edition_manifests` is the larger crawl,
both languages and both pages per edition, 84 in all.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source, load_sources

from china.acquire._common import fetch_file, fetch_files
from china.acquire.registry import AcquireResult, register
from china.clean.yearbook import TOC_FILENAMES, find_tables, parse_toc

__all__ = [
    "EDITION_YEARS",
    "YEARBOOK_BASE",
    "edition_index_url",
    "edition_toc_url",
    "table_url",
]

#: Root of the yearbook editions on the live server.
YEARBOOK_BASE = "https://www.stats.gov.cn/sj/ndsj"

#: Editions the yearbook index page lists, verified during scaffolding: the index enumerates
#: ``/sj/ndsj/{2005..2025}/indexch.htm``. Editions before 2005 exist only as complete-volume
#: archives on the Wayback Machine (registry id ``wayback_nbs_yearbooks``).
EDITION_YEARS: tuple[int, ...] = tuple(range(2005, 2026))

#: The registry entry that describes the contents frames. Contents frames are always fetched
#: under this id, whoever triggers the fetch, so that provenance stays with the entry that
#: documents them.
TOC_SOURCE_ID = "csy_web_editions"

#: Table titles that have been stable across the editions examined, and the registry entries
#: that verified one instance of each.
GRP_TITLE = "Gross Regional Product"
ELECTRICITY_TITLE = "Electricity Consumption by Region"
FREIGHT_TITLES = (
    "Freight Traffic by Region",
    "Freight Ton-kilometers by Region",
    "Cross-region Freight Transport of National Railways",
)


def edition_index_url(year: int, language: str = "en") -> str:
    """URL of an edition's frameset index.

    Parameters
    ----------
    year : int
        Edition year.
    language : {"en", "zh"}, default "en"
        English editions are ``indexeh.htm``, Chinese ``indexch.htm``.

    Returns
    -------
    str
        Absolute URL.

    Raises
    ------
    ValueError
        For an unknown ``language``.
    """
    if language not in TOC_FILENAMES:
        raise ValueError(f"language must be one of {sorted(TOC_FILENAMES)}, got {language!r}")
    leaf = "indexeh.htm" if language == "en" else "indexch.htm"
    return f"{YEARBOOK_BASE}/{year}/{leaf}"


def edition_toc_url(year: int, language: str = "en") -> str:
    """URL of an edition's contents frame.

    Parameters
    ----------
    year : int
        Edition year.
    language : {"en", "zh"}, default "en"
        English contents frames are ``left_.htm``, Chinese ``left.htm``.

    Returns
    -------
    str
        Absolute URL.

    Raises
    ------
    ValueError
        For an unknown ``language``.
    """
    if language not in TOC_FILENAMES:
        raise ValueError(f"language must be one of {sorted(TOC_FILENAMES)}, got {language!r}")
    return f"{YEARBOOK_BASE}/{year}/{TOC_FILENAMES[language]}"


def table_url(year: int, filename: str) -> str:
    """URL of one table file inside an edition.

    Parameters
    ----------
    year : int
        Edition year.
    filename : str
        File name as it appears in the contents frame, with or without its ``html/`` prefix.

    Returns
    -------
    str
        Absolute URL.
    """
    return f"{YEARBOOK_BASE}/{year}/html/{filename.rsplit('/', 1)[-1]}"


def _referer(year: int, language: str = "en") -> dict[str, str]:
    """The ``Referer`` the registry's verified probes sent for a table request."""
    return {"Referer": edition_index_url(year, language)}


def _toc_rel(year: int, language: str) -> str:
    return f"csy/{year}/toc_{language}.htm"


def _table_rel(year: int, filename: str) -> str:
    return f"csy/{year}/html/{filename.rsplit('/', 1)[-1]}"


def _toc_source(data_dir: Path) -> Source | None:
    """The ``csy_web_editions`` registry entry, or ``None`` if it is missing."""
    registry = data_dir / "SOURCES.yaml"
    if not registry.exists():
        return None
    for entry in load_sources(registry):
        if entry.id == TOC_SOURCE_ID:
            return entry
    return None


#: Digest of the 2024 English contents frame. The ``csy_web_editions`` entry records
#: ``sha256: aa9eb99e...`` while its ``bytes: 904`` is the frameset; its ``evidence`` field
#: resolves the ambiguity, stating "I fetched left_.htm for 2024 (200, 81,548 bytes, sha256
#: aa9eb99e...)". Pinned here against that reading. A mismatch is reported as one failed file
#: and is worth investigating rather than papering over: it means either the registry entry
#: is internally inconsistent or a "frozen" edition changed.
TOC_2024_EN_SHA256 = "aa9eb99e8f0c851a4a0947ef9355a942f9c0839b9502677e55b063bf22b21f3a"

#: Digests recorded for the 2023 contents frames by ``nbs_yearbook_2023_html_tables``.
TOC_2023_SHA256 = {
    "en": "9e2232db7ec403a0e57ea73db546b1d0f4eec63d12fa3d9205e3fdd719114984",
    "zh": "bde8516b33a3be0c5be145dbf74ee812f6fa05cccec0d145f4d35e6526881d29",
}

#: Digests the registry recorded for the one table image each multi-file entry verified,
#: copied here as constants rather than read from ``Source.sha256`` at run time.
#:
#: The reason is that the digest in the registry does not survive a run. ``fetch`` rewrites
#: the entry's ``sha256``, ``bytes`` and ``local_path`` on every success, and every acquirer
#: below fetches a whole family of files under one source id, so after one ``make data`` the
#: entry holds whichever member happened to be fetched last. Reading ``source.sha256`` on the
#: next run would therefore compare the 2024 anchor against some other edition's image and
#: report a spurious mismatch. These constants are the values the registry carried when it
#: was written, and they are what the anchors are checked against. See ``_common.py`` and the
#: "digests recorded for a family" note in ``data/ACCESS_NOTES.md``.
ANCHOR_SHA256: dict[str, str] = {
    "csy_2024_grp": "4cb499b75a1d5e26675bb84ec125ad097b7f9020de8d71d01b5d58c5a0625ba5",
    "csy_electricity_by_region": "04484a50e9e34418c70763968491e076e2cba7c12f5eb36ad62675daf1e6e96b",
    "csy_freight_by_region": "ae9a06d879ae5441e58295a31623e8ba8af0e9a0149fae4cb6ca2771a2902ad2",
    "china_statistical_yearbook_online": (
        "1e6c24df01d51661a9956f05a4b6be6a0a954f3ff664a7ec138347bb9ccc85a5"
    ),
}


def _toc_digest(year: int, language: str) -> str | None:
    if year == 2024 and language == "en":
        return TOC_2024_EN_SHA256
    if year == 2023:
        return TOC_2023_SHA256.get(language)
    return None


def ensure_edition_tocs(
    data_dir: Path,
    years: tuple[int, ...] = EDITION_YEARS,
    language: str = "en",
    *,
    force: bool = False,
) -> tuple[list[int], list[str]]:
    """Make sure each edition's contents frame is on disk, fetching the missing ones.

    Fetched under :data:`TOC_SOURCE_ID`, not under the caller's id, so that the contents
    frames are always attributed to the registry entry that documents them.

    Parameters
    ----------
    data_dir : Path
        The project's ``data/`` directory.
    years : tuple of int, default :data:`EDITION_YEARS`
        Editions to make available.
    language : {"en", "zh"}, default "en"
        Which contents frame.
    force : bool, default False
        Re-fetch even when a copy is on disk.

    Returns
    -------
    available : list of int
        Editions whose contents frame is now readable.
    problems : list of str
        One line per edition that could not be made available, and one line if the registry
        entry for the contents frames is missing altogether. Never raises: a missing edition
        costs that edition, not the run.
    """
    toc_source = _toc_source(data_dir)
    if toc_source is None:
        return [], [f"registry entry {TOC_SOURCE_ID!r} is missing; cannot fetch contents frames"]

    wanted = [
        (
            edition_toc_url(year, language),
            _toc_rel(year, language),
            _toc_digest(year, language),
            _referer(year, language),
        )
        for year in years
        if force or not (data_dir / "raw" / _toc_rel(year, language)).exists()
    ]
    problems: list[str] = []
    if wanted:
        result = fetch_files(
            toc_source,
            data_dir,
            wanted,
            force=force,
            label="contents frames",
        )
        if not result.ok:
            problems.append(f"contents frames: {result.detail}")

    available = [year for year in years if (data_dir / "raw" / _toc_rel(year, language)).exists()]
    return available, problems


def resolve_tables(
    data_dir: Path,
    titles: tuple[str, ...],
    years: tuple[int, ...] = EDITION_YEARS,
    language: str = "en",
    *,
    max_per_edition: int = 8,
) -> tuple[list[tuple[str, str, None, dict[str, str]]], list[str]]:
    """Look up, in every available edition, the tables whose printed title matches.

    Parameters
    ----------
    data_dir : Path
        The project's ``data/`` directory.
    titles : tuple of str
        Title phrases, matched case-insensitively as substrings.
    years : tuple of int, default :data:`EDITION_YEARS`
        Editions to search. Editions whose contents frame is not on disk are skipped and
        reported.
    language : {"en", "zh"}, default "en"
        Which contents frame to read.
    max_per_edition : int, default 8
        Ceiling on matches taken from one edition for one title, so that a loose phrase
        cannot turn into a hundred-file download without anyone noticing.

    Returns
    -------
    items : list of tuple
        Work items for :func:`china.acquire._common.fetch_files`: ``(url, dest_rel, None,
        headers)``. No digest, because these files were located rather than verified.
    problems : list of str
        Editions that could not be read or that carry no matching table. An edition with no
        match is a real answer, not an error, and is reported as such.
    """
    items: list[tuple[str, str, None, dict[str, str]]] = []
    problems: list[str] = []
    seen: set[str] = set()

    for year in years:
        path = data_dir / "raw" / _toc_rel(year, language)
        if not path.exists():
            continue
        try:
            toc = parse_toc(path.read_bytes())
        except (OSError, ValueError) as exc:
            problems.append(f"{year}: contents frame unreadable ({exc})")
            continue
        for title in titles:
            matches = find_tables(toc, title)
            if matches.empty:
                problems.append(f"{year}: no table titled like {title!r}")
                continue
            for filename in list(matches["filename"])[:max_per_edition]:
                rel = _table_rel(year, str(filename))
                if rel in seen:
                    continue
                seen.add(rel)
                items.append((table_url(year, str(filename)), rel, None, _referer(year, language)))
    return items, problems


def _acquire_table_family(
    source: Source,
    data_dir: Path,
    *,
    anchor_year: int,
    anchor_filename: str,
    anchor_sha256: str,
    titles: tuple[str, ...],
    force: bool,
) -> AcquireResult:
    """Fetch the registry's verified table plus the same table in every other edition.

    ``anchor_sha256`` is required, and callers pass it by subscripting
    :data:`ANCHOR_SHA256` rather than reading ``source.sha256``: a new family acquirer that
    forgets to add its anchor to that mapping then fails loudly instead of quietly fetching
    its one verified file without a digest check. The swept editions carry no digest, because
    the registry never recorded one for them.
    """
    anchor = (
        table_url(anchor_year, anchor_filename),
        _table_rel(anchor_year, anchor_filename),
        anchor_sha256,
        _referer(anchor_year),
    )
    available, problems = ensure_edition_tocs(data_dir, force=False)
    items, resolve_problems = resolve_tables(data_dir, titles)
    problems.extend(p for p in resolve_problems if "unreadable" in p)

    work: list[tuple[str, ...]] = [anchor]
    work.extend(item for item in items if item[1] != anchor[1])

    result = fetch_files(source, data_dir, work, force=force, label="table images")
    detail = f"{result.detail}; {len(available)} editions with a contents frame"
    if problems:
        detail += f"; {len(problems)} contents-frame problems: {problems[0]}"
    return AcquireResult(result.source_id, result.ok, detail, result.paths, result.skipped_cached)


@register("china_statistical_yearbook_online")
def yearbook_index(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The two yearbook index pages: the list of editions in Chinese and in English.

    These are the pages that establish which editions exist. The Chinese index carries the
    registry's recorded digest and enumerates ``/sj/ndsj/{2005..2025}/indexch.htm``; the
    English index is the smaller companion at ``/english/Statisticaldata/yearbook/``.
    """
    return fetch_files(
        source,
        data_dir,
        [
            (
                source.url or f"{YEARBOOK_BASE}/",
                "csy/index_zh.htm",
                ANCHOR_SHA256["china_statistical_yearbook_online"],
            ),
            (
                "https://www.stats.gov.cn/english/Statisticaldata/yearbook/",
                "csy/index_en.htm",
            ),
        ],
        force=force,
        label="index pages",
    )


@register("csy_web_editions")
def edition_manifests(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Every edition's frameset and contents frame, in both languages: the edition manifests.

    The contents frame is the only correct way to find a table, because file names and table
    numbers both drift between editions. Fetching all of them, in both languages, also gives
    the Chinese menu as a cross-check when an English table number is missing from an older
    edition, which the registry's download plan recommends.

    21 editions times four small pages, 84 requests; the framesets are 904 bytes each and the
    contents frames 60 to 85 kilobytes.
    """
    work: list[tuple[str, ...]] = []
    for language in ("en", "zh"):
        for year in EDITION_YEARS:
            work.append(
                (
                    edition_index_url(year, language),
                    f"csy/{year}/index_{language}.htm",
                    None,
                    _referer(year, language),
                )
            )
            work.append(
                (
                    edition_toc_url(year, language),
                    _toc_rel(year, language),
                    _toc_digest(year, language),
                    _referer(year, language),
                )
            )
    return fetch_files(source, data_dir, work, force=force, label="edition manifest pages")


@register("csy_2024_grp")
def grp_2024(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Table 3-9, gross regional product, current vintage plus every other edition's copy.

    The 2024 edition's table is a single-year cross-section for 2023 with the sectoral
    decomposition, and its digest is pinned from the registry. The sweep across the other
    editions is what makes this a vintage series rather than a snapshot: the same table in
    the 2015 edition still shows Liaoning's pre-revision figures.
    """
    return _acquire_table_family(
        source,
        data_dir,
        anchor_year=2024,
        anchor_filename="E03-09.jpg",
        anchor_sha256=ANCHOR_SHA256["csy_2024_grp"],
        titles=(GRP_TITLE,),
        force=force,
    )


@register("csy_2015_grp_vintage")
def grp_2015(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Table 3-9 in the 2015 edition: the pre-revision Liaoning panel, 2010-2014.

    The project's anchor, and it is observable: this edition prints levels and indices for
    five data years at once, so one image yields five vintage-2015 data years. The registry
    records its digest and the Liaoning row verbatim; the digest is pinned so that a changed
    file fails acquisition rather than quietly changing the anchor.

    Fetches only this one image. The cross-edition sweep belongs to ``csy_2024_grp``, which
    covers the same table in every edition including this one; that acquirer will find this
    file already on disk.

    This is the one yearbook entry whose registry ``sha256`` can safely be read at run time:
    the id maps to exactly one file, so ``fetch`` rewriting the entry after a success writes
    back the same digest. The family acquirers use :data:`ANCHOR_SHA256` instead, for the
    reason given there.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or table_url(2015, "EN0309.jpg"),
        dest_rel=_table_rel(2015, "EN0309.jpg"),
        headers=_referer(2015),
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("csy_electricity_by_region")
def electricity(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Table 9-14, electricity consumption by region, across editions.

    Provincial electricity is genuinely free, but each edition prints selected years only
    (1995, 2000, 2005, 2010, 2015, 2020 and the two most recent), so an annual panel exists
    only by stacking editions. The China Electricity Council, which the table footnote names
    as the upstream source, is unreachable from this network and has no acquirer.
    """
    return _acquire_table_family(
        source,
        data_dir,
        anchor_year=2024,
        anchor_filename="E09-14.jpg",
        anchor_sha256=ANCHOR_SHA256["csy_electricity_by_region"],
        titles=(ELECTRICITY_TITLE,),
        force=force,
    )


@register("csy_freight_by_region")
def freight(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Tables 16-14, 16-15 and 16-17, freight by region, across editions.

    16-14 is tonnage, 16-15 ton-kilometres (the better proxy, because it embeds distance) and
    16-17 the inter-provincial railway goods exchange, which is a bilateral flow matrix and
    therefore unusually informative for checking a province against its neighbours. Each
    edition carries one cross-section, so the annual panel again comes from stacking
    editions. Note the ``Not Classified by Region`` residual row: excluded from provincial
    sums by :func:`china.clean.provinces.is_non_province_row`.
    """
    return _acquire_table_family(
        source,
        data_dir,
        anchor_year=2024,
        anchor_filename="E16-14.jpg",
        anchor_sha256=ANCHOR_SHA256["csy_freight_by_region"],
        titles=FREIGHT_TITLES,
        force=force,
    )


@register("nbs_yearbook_2023_html_tables")
def edition_2023_tables(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The 2023 edition's electricity and freight tables, with the digests recorded for them.

    This entry is the one that established the project's central constraint: the 2023 edition
    is image-only, 706 ``.jpg`` references in the Chinese menu and no spreadsheet at all. It
    overlaps ``csy_electricity_by_region`` and ``csy_freight_by_region``, which sweep the same
    two tables across every edition; the files are written to the same paths, so whichever
    acquirer runs second finds them already held and makes no request. What this entry adds is
    the pinned digest for each of the two 2023 images.
    """
    return fetch_files(
        source,
        data_dir,
        [
            (
                table_url(2023, "E09-14.jpg"),
                _table_rel(2023, "E09-14.jpg"),
                "4ac4bda56241455412ff0eab41d30f41e882238793ea559b81e5827398971bf3",
                _referer(2023),
            ),
            (
                table_url(2023, "E16-14.jpg"),
                _table_rel(2023, "E16-14.jpg"),
                "10bfd2c553b233d377675a77ee5ee69c11cb031b3d06c4afd8de792fc78be90d",
                _referer(2023),
            ),
        ],
        force=force,
        label="2023 table images",
    )

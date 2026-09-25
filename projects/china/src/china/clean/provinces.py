"""The province list problem: canonical names, aliases, and rows that are not provinces.

Three distinct hazards live here, and each one silently corrupts a provincial-sum minus
national comparison if it is not handled:

1. **Names drift between yearbook editions.** The 2015 edition of the China Statistical
   Yearbook labels one row ``Tibet``; the 2024 edition labels the same row ``Xizang``. That
   is recorded as evidence on registry entries ``csy_2015_grp_vintage`` and ``csy_2024_grp``.
   Stack two vintages without a name map and one province silently becomes two.
2. **Some rows in a provincial table are not provinces.** Table 16-14 "Freight Traffic by
   Region" carries a ``National Total`` row and a ``Not Classified by Region`` residual row
   (civil aviation and pipelines). Summing the column as printed double counts the national
   total and then adds the residual on top.
3. **The interesting revisions happened below the provincial level.** The Tianjin episode of
   January 2018 was a revision of **Binhai New Area**, a sub-provincial development zone, not
   of Tianjin as a whole; the Inner Mongolia episode named the city of **Baotou** as well as
   the region. A sub-provincial unit must never enter a provincial panel, and a provincial
   series must not be expected to show a sub-provincial revision at full size.

Nothing in this module is inferred from data. The canonical list is the 31 mainland
provincial-level units that the yearbook's regional tables carry (the registry records "31
regions" for every regional table examined); the aliases and non-province rows are marked
below as either attested in ``data/SOURCES.yaml`` or still TO CONFIRM against real table
text once a table has been extracted.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ATTESTED_REGION_CODES",
    "BOUNDARY_CHANGES",
    "NON_PROVINCE_ROWS",
    "PROVINCES",
    "REBASING_YEARS",
    "SUBPROVINCIAL_UNITS",
    "BoundaryChange",
    "SubprovincialUnit",
    "canonical_province",
    "is_non_province_row",
    "is_province",
    "normalize_label",
    "subprovincial_unit",
]

#: The 31 mainland provincial-level units, in the order the yearbook's regional tables print
#: them (municipalities and provinces by region). Hong Kong, Macao and Taiwan are not in
#: those tables and are not in this list.
PROVINCES: tuple[str, ...] = (
    "Beijing",
    "Tianjin",
    "Hebei",
    "Shanxi",
    "Inner Mongolia",
    "Liaoning",
    "Jilin",
    "Heilongjiang",
    "Shanghai",
    "Jiangsu",
    "Zhejiang",
    "Anhui",
    "Fujian",
    "Jiangxi",
    "Shandong",
    "Henan",
    "Hubei",
    "Hunan",
    "Guangdong",
    "Guangxi",
    "Hainan",
    "Chongqing",
    "Sichuan",
    "Guizhou",
    "Yunnan",
    "Xizang",
    "Shaanxi",
    "Gansu",
    "Qinghai",
    "Ningxia",
    "Xinjiang",
)

#: Alias -> canonical name, keyed by :func:`normalize_label` output.
#:
#: ATTESTED means the alias was read off a real table during source verification and is
#: recorded in ``data/SOURCES.yaml``. TO CONFIRM means it is the conventional form and has
#: not yet been seen in an extracted table; confirm it before relying on it.
_ALIASES: dict[str, str] = {
    # ATTESTED: csy_2015_grp_vintage evidence -- that edition labels the row "Tibet" where
    # CSY 2024 labels it "Xizang".
    "tibet": "Xizang",
    "tibet autonomous region": "Xizang",
    "xizang autonomous region": "Xizang",
    # TO CONFIRM: the pinyin romanisation used in some official tables.
    "nei mongol": "Inner Mongolia",
    "nei monggol": "Inner Mongolia",
    "inner mongolia autonomous region": "Inner Mongolia",
    # TO CONFIRM: long-form autonomous-region names.
    "guangxi zhuang autonomous region": "Guangxi",
    "ningxia hui autonomous region": "Ningxia",
    "xinjiang uygur autonomous region": "Xinjiang",
    # TO CONFIRM: the two easily confused Shan- provinces. Kept explicit so a transcription
    # of "Shannxi", a common disambiguation spelling of Shaanxi, does not fall through to
    # Shanxi.
    "shannxi": "Shaanxi",
}

#: Row labels that appear inside a regional table but are not provincial units. Summing a
#: column without removing these is the simplest way to manufacture a fake gap.
#:
#: The first two entries are ATTESTED: registry entry ``csy_freight_by_region`` records that
#: table 16-14 carries "a 'National Total' row and a 'Not Classified by Region' residual row".
NON_PROVINCE_ROWS: frozenset[str] = frozenset(
    {
        "national total",
        "not classified by region",
        "total",
        "china",
        "nationwide",
    }
)


@dataclass(frozen=True)
class SubprovincialUnit:
    """A unit below the provincial level that is in the evidence but not in the panel.

    Attributes
    ----------
    name : str
        The unit as named in the source that reported it.
    parent : str
        The canonical provincial-level unit it sits inside.
    why : str
        Why the project has to know about it.
    """

    name: str
    parent: str
    why: str


#: Sub-provincial units the project must recognise and must never sum into a provincial panel.
SUBPROVINCIAL_UNITS: tuple[SubprovincialUnit, ...] = (
    SubprovincialUnit(
        "Binhai New Area",
        "Tianjin",
        "Where the January 2018 Tianjin revision actually happened: 2016 gross regional "
        "product revised down 33.4 percent to 665 billion yuan (Xinhua, 20 January 2018, "
        "registry id xinhua_data_inflation_2018_01_20). Tianjin's provincial series absorbs "
        "only part of that.",
    ),
    SubprovincialUnit(
        "Baotou",
        "Inner Mongolia",
        "Named alongside the region in the January 2018 Inner Mongolia episode: fiscal "
        "revenues cut 49 percent to 13.7 billion yuan (Caixin, 29 January 2018, registry id "
        "caixin_fudged_numbers_2018_01_29, paywalled, visible text only).",
    ),
    SubprovincialUnit(
        "Shenzhen",
        "Guangdong",
        "The central bank's regional financial operation report publishes 32 summaries: the "
        "31 provincial-level units plus Shenzhen (registry id "
        "pbc_regional_financial_operation_reports). A naive file-per-province mapping "
        "produces 32 provinces.",
    ),
)

#: Canonical name -> the four 6-digit region codes actually attested in ``data/SOURCES.yaml``.
#:
#: The full GB/T 2260 code list is deliberately NOT hard-coded. The National Bureau of
#: Statistics catalogue API returns its own region list with 12-digit codes (the 6-digit code
#: zero-padded); harvest it from the API response rather than typing 31 codes from memory.
ATTESTED_REGION_CODES: dict[str, str] = {
    "Beijing": "110000",  # nbs_easyquery_legacy url, wdcode=reg valuecode=110000
    "Tianjin": "120000",  # nbs_dg_api_values download_plan
    "Inner Mongolia": "150000",  # nbs_dg_api_values download_plan
    "Liaoning": "210000",  # nbs_dg_api_values evidence, das code 210000000000
}


@dataclass(frozen=True)
class BoundaryChange:
    """A provincial boundary change that puts a level shift in the panel.

    Attributes
    ----------
    year : int
        Year the change took effect.
    created : str
        The unit that came into existence as a provincial-level unit.
    from_parent : str
        The unit it was separated from.
    """

    year: int
    created: str
    from_parent: str


#: Boundary changes inside the period the project's series can cover, from
#: ``docs/known_traps.md``. A series that crosses one of these is two series.
BOUNDARY_CHANGES: tuple[BoundaryChange, ...] = (
    BoundaryChange(1988, "Hainan", "Guangdong"),
    BoundaryChange(1997, "Chongqing", "Sichuan"),
)

#: Economic-census years that trigger rebasing and back-revision of both national and
#: provincial series (``docs/known_traps.md``). Test around these, not across them.
REBASING_YEARS: tuple[int, ...] = (2004, 2008, 2013, 2018)


def normalize_label(label: str) -> str:
    """Reduce a table row label to a comparison key.

    Lower-cases, collapses internal whitespace, and drops the punctuation that yearbook
    footnote markers and optical character recognition both introduce.

    Parameters
    ----------
    label : str
        A row label as printed or as extracted.

    Returns
    -------
    str
        The comparison key. Empty input gives an empty string.

    Examples
    --------
    >>> normalize_label("  Inner  Mongolia a) ")
    'inner mongolia a'
    """
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in label)
    return " ".join(cleaned.lower().split())


_CANONICAL_KEYS: dict[str, str] = {normalize_label(p): p for p in PROVINCES}
_SUBPROVINCIAL_KEYS: dict[str, SubprovincialUnit] = {
    normalize_label(u.name): u for u in SUBPROVINCIAL_UNITS
}


def canonical_province(label: str) -> str | None:
    """Map a row label to its canonical provincial-level name.

    Parameters
    ----------
    label : str
        A row label from a regional table, in any edition's spelling.

    Returns
    -------
    str or None
        The canonical name from :data:`PROVINCES`, or ``None`` if the label is not a
        provincial-level unit. ``None`` covers three situations the caller must not
        conflate: an aggregate or residual row (:func:`is_non_province_row` is True), a
        sub-provincial unit (:func:`subprovincial_unit` returns it), and an unrecognised
        string, which usually means an extraction error and should be reported, not dropped.

    Examples
    --------
    >>> canonical_province("Tibet")
    'Xizang'
    >>> canonical_province("Not Classified by Region") is None
    True
    """
    key = normalize_label(label)
    if not key:
        return None
    if key in _CANONICAL_KEYS:
        return _CANONICAL_KEYS[key]
    if key in _ALIASES:
        return _ALIASES[key]
    # Footnote markers survive extraction as a trailing single letter, e.g. "Xizang a".
    parts = key.split()
    if len(parts) > 1 and len(parts[-1]) == 1:
        stem = " ".join(parts[:-1])
        if stem in _CANONICAL_KEYS:
            return _CANONICAL_KEYS[stem]
        if stem in _ALIASES:
            return _ALIASES[stem]
    return None


def is_province(label: str) -> bool:
    """True if ``label`` names one of the 31 provincial-level units.

    Parameters
    ----------
    label : str
        A row label.

    Returns
    -------
    bool
        True only for provincial-level units. Sub-provincial units and aggregate rows are
        False.
    """
    return canonical_province(label) is not None


def is_non_province_row(label: str) -> bool:
    """True if ``label`` is an aggregate or residual row to drop before summing.

    Parameters
    ----------
    label : str
        A row label.

    Returns
    -------
    bool
        True for the national total, the "Not Classified by Region" residual and their
        common spellings. A sub-provincial unit is **not** covered by this predicate: it is
        a real place, just not a province, and :func:`is_province` is what excludes it.
    """
    return normalize_label(label) in NON_PROVINCE_ROWS


def subprovincial_unit(label: str) -> SubprovincialUnit | None:
    """Return the :class:`SubprovincialUnit` a label names, if any.

    Parameters
    ----------
    label : str
        A row label, or a file-name stem from a per-region source such as the central
        bank's regional financial operation report summaries.

    Returns
    -------
    SubprovincialUnit or None
        The matching entry of :data:`SUBPROVINCIAL_UNITS`, else ``None``.
    """
    return _SUBPROVINCIAL_KEYS.get(normalize_label(label))

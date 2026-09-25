"""The tidy provincial-year panel: one row per province, year, series and **vintage**.

Every number this project uses ends up in one long frame with seven columns::

    province  year  series  value  unit  vintage  source_id

Three of those need justifying, because a wider "province x year" table would be the obvious
alternative and would be wrong here.

``series``
    The project mixes gross regional product with electricity, freight, loans and
    nightlights. They have different units, different coverage and different revision
    histories. Long format keeps a missing proxy from widening every row.

``vintage``
    **The column the whole project turns on.** Revisions overwrite history: the National
    Bureau of Statistics and the provincial bureaus serve the current vintage only, and the
    padded Liaoning figures for 2011-2014 do not appear in it. They do appear in the 2015
    edition of the China Statistical Yearbook, which is a frozen snapshot that was never
    retro-revised (registry ids ``csy_2015_grp_vintage`` and ``csy_web_editions``). So the
    same (province, year, series) legitimately holds several different values, one per
    vintage, and the difference between them is the measurement. A panel without a vintage
    column silently keeps whichever value was loaded last.

``source_id``
    Every row must be traceable to one entry of ``data/SOURCES.yaml``. A row whose
    ``source_id`` is not in the registry is not admissible evidence.

The key is therefore ``(province, year, series, vintage)`` and **not** ``(province, year,
series)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from china.clean.provinces import PROVINCES, canonical_province

__all__ = [
    "MAX_YEAR",
    "MIN_YEAR",
    "NATIONAL",
    "PANEL_COLUMNS",
    "PANEL_DTYPES",
    "PANEL_KEY",
    "SERIES",
    "SeriesSpec",
    "coerce_panel",
    "concat_vintages",
    "empty_panel",
    "read_panel",
    "validate_panel",
    "vintage_of_yearbook_edition",
    "write_panel",
]

#: Column order of the tidy panel. Fixed: loaders emit exactly these, in this order.
PANEL_COLUMNS: tuple[str, ...] = (
    "province",
    "year",
    "series",
    "value",
    "unit",
    "vintage",
    "source_id",
)

#: pandas dtypes for :data:`PANEL_COLUMNS`.
PANEL_DTYPES: dict[str, str] = {
    "province": "string",
    "year": "int64",
    "series": "string",
    "value": "float64",
    "unit": "string",
    "vintage": "string",
    "source_id": "string",
}

#: The unique key of a row. Note that ``vintage`` is part of it.
PANEL_KEY: tuple[str, ...] = ("province", "year", "series", "vintage")

#: Reserved value of ``province`` for the national aggregate. It is deliberately not one of
#: the 31 provinces, so that ``frame[frame.province != NATIONAL]`` is the provincial panel
#: and summing it can never double count the national row.
NATIONAL = "China"

#: Plausible-year bounds used only for validation. Not a claim about coverage: the catalogue
#: API advertises gross regional product from 1992 and freight from 1979, and the yearbook
#: editions on the live server run 2005 to 2025.
MIN_YEAR = 1949
MAX_YEAR = 2035


@dataclass(frozen=True)
class SeriesSpec:
    """Definition of one series name that may appear in the ``series`` column.

    Attributes
    ----------
    name : str
        The canonical series name.
    unit : str
        The unit every value of this series must carry. Conversion happens in the loader,
        never downstream.
    description : str
        What the number is, in the publisher's own terms.
    source_ids : tuple of str
        Registry ids that can supply this series. Empty means no verified free source has
        been found, which is itself a finding to be reported, not a gap to be filled with a
        substitute.
    unit_confirmed : bool
        False where the unit was not read off the table during source verification and must
        be confirmed at extraction time.
    """

    name: str
    unit: str
    description: str
    source_ids: tuple[str, ...] = ()
    unit_confirmed: bool = True


#: The series the project can build, and where each one comes from. A loader may not invent
#: a series name: add it here first, with its unit and its registry ids.
SERIES: dict[str, SeriesSpec] = {
    s.name: s
    for s in (
        SeriesSpec(
            "grp_nominal",
            "100 million yuan",
            "Gross regional product at current prices, as printed in yearbook table 3-9. "
            "Recent editions footnote the latest year as preliminary, so the same data year "
            "reappears revised in the following edition.",
            ("csy_2015_grp_vintage", "csy_2024_grp", "csy_web_editions"),
        ),
        SeriesSpec(
            "grp_index_preceding_year",
            "index, preceding year = 100",
            "Gross regional product index at constant prices, preceding year = 100. This is "
            "the real growth measure; it is not the growth rate of grp_nominal.",
            ("csy_2015_grp_vintage", "csy_2024_grp", "csy_web_editions"),
        ),
        SeriesSpec(
            "gdp_national_nominal",
            "100 million yuan",
            "National gross domestic product at current prices. Take it from the same "
            "yearbook edition as the provincial rows whenever the comparison is a gap; the "
            "World Bank series is the current vintage only and mixing vintages fabricates a "
            "gap that is really a revision.",
            ("csy_web_editions", "worldbank_chn_gdp"),
        ),
        SeriesSpec(
            "electricity_consumption",
            "100 million kWh",
            "Electricity consumption by region, yearbook table 9-14. The columns are "
            "selected years per edition (1995, 2000, 2005, 2010, 2015, 2020 and the two most "
            "recent), so an annual panel has to be stacked across editions. Data since 2000 "
            "are the China Electricity Council's, per the table footnote.",
            ("csy_electricity_by_region", "nbs_yearbook_2023_html_tables"),
        ),
        SeriesSpec(
            "freight_total",
            "10 000 tons",
            "Freight traffic by region, all modes, yearbook table 16-14.",
            ("csy_freight_by_region", "nbs_yearbook_2023_html_tables"),
        ),
        SeriesSpec(
            "freight_rail",
            "10 000 tons",
            "Railway freight traffic by region, yearbook table 16-14. The table's "
            "'Not Classified by Region' row is aviation and pipelines and must be excluded "
            "from any provincial sum.",
            ("csy_freight_by_region", "nbs_yearbook_2023_html_tables"),
        ),
        SeriesSpec(
            "freight_ton_km",
            "TO CONFIRM",
            "Freight ton-kilometres by region, yearbook table 16-15. A better proxy than "
            "tonnage because it embeds distance. The table was listed in the 2017 and 2024 "
            "tables of contents but was not opened during source verification, so its unit "
            "is unconfirmed.",
            ("csy_freight_by_region",),
            unit_confirmed=False,
        ),
        SeriesSpec(
            "loans_outstanding",
            "100 million yuan",
            "Year-end balance of loans of banking institutions in domestic and foreign "
            "currency, from the central bank's regional financial operation report "
            "summaries. Published as prose and rounded (for example '5.5 trillion yuan'), so "
            "precision is roughly two significant figures.",
            ("pbc_regional_financial_operation_reports",),
        ),
        SeriesSpec(
            "loans_outstanding_national",
            "100 million yuan",
            "National total loans from the central bank's sources-and-uses of credit funds "
            "table. National only: that table has no region dimension, which is the "
            "documented reason provincial credit is the hardest proxy in this project.",
            ("pbc_credit_statistics",),
        ),
        SeriesSpec(
            "nightlights_dn_sum",
            "digital number, dimensionless",
            "Sum of harmonised DMSP and VIIRS digital-number values over a province's "
            "boundary. Dimensionless by construction; comparable across years only because "
            "the product is harmonised, and the modelled DMSP-to-VIIRS join must still be "
            "tested as a break.",
            ("figshare_li2020_harmonized_ntl",),
        ),
    )
}

_VINTAGE_RE = re.compile(r"^[a-z0-9]+[a-z0-9._-]*$")


def vintage_of_yearbook_edition(edition_year: int) -> str:
    """Vintage label for a China Statistical Yearbook edition.

    The edition year, not the data year: the 2015 edition carries data years 2010-2014, and
    it is the edition that identifies the vintage.

    Parameters
    ----------
    edition_year : int
        Year printed on the yearbook edition, e.g. 2015.

    Returns
    -------
    str
        For example ``"csy2015"``.

    Raises
    ------
    ValueError
        If ``edition_year`` is outside :data:`MIN_YEAR` to :data:`MAX_YEAR`.

    Examples
    --------
    >>> vintage_of_yearbook_edition(2024)
    'csy2024'
    """
    if not MIN_YEAR <= int(edition_year) <= MAX_YEAR:
        raise ValueError(f"edition_year {edition_year} outside [{MIN_YEAR}, {MAX_YEAR}]")
    return f"csy{int(edition_year)}"


def empty_panel() -> pd.DataFrame:
    """An empty panel with the right columns and dtypes.

    Returns
    -------
    pandas.DataFrame
        Zero rows, columns :data:`PANEL_COLUMNS`, dtypes :data:`PANEL_DTYPES`.
    """
    return pd.DataFrame({c: pd.Series(dtype=PANEL_DTYPES[c]) for c in PANEL_COLUMNS})


def coerce_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Put a loader's output into panel form: column order, dtypes, canonical province names.

    Province labels are mapped through
    :func:`china.clean.provinces.canonical_province`, so that a 2015-edition ``Tibet`` row
    and a 2024-edition ``Xizang`` row become the same province. A label that maps to nothing
    is left exactly as it was: :func:`validate_panel` then rejects it, which is the intended
    outcome, because an unrecognised province label almost always means the extraction went
    wrong and must be looked at rather than dropped.

    Parameters
    ----------
    frame : pandas.DataFrame
        Must contain at least :data:`PANEL_COLUMNS`; extra columns are dropped.

    Returns
    -------
    pandas.DataFrame
        Coerced copy, sorted by :data:`PANEL_KEY` with a fresh index.

    Raises
    ------
    KeyError
        If a required column is missing.
    """
    missing = [c for c in PANEL_COLUMNS if c not in frame.columns]
    if missing:
        raise KeyError(f"panel is missing columns: {missing}")
    out = frame.loc[:, list(PANEL_COLUMNS)].copy()
    out["province"] = out["province"].map(
        lambda v: v if v == NATIONAL else (canonical_province(str(v)) or v)
    )
    for column, dtype in PANEL_DTYPES.items():
        out[column] = out[column].astype(dtype)
    return out.sort_values(list(PANEL_KEY)).reset_index(drop=True)


def validate_panel(frame: pd.DataFrame, *, known_source_ids: set[str] | None = None) -> list[str]:
    """Check a panel against the schema and return the problems as text.

    Returns a list rather than raising so that a loader can report every problem in one
    pass. Callers that want an exception use ``assert not validate_panel(frame)``.

    Parameters
    ----------
    frame : pandas.DataFrame
        The panel to check.
    known_source_ids : set of str, optional
        Ids present in ``data/SOURCES.yaml``. When given, every ``source_id`` in the panel
        must be one of them: a row that cannot be traced to the registry is not evidence.

    Returns
    -------
    list of str
        Empty when the panel is valid. Each element names one problem and, where the
        problem is row-level, the first few offending values.
    """
    problems: list[str] = []

    if list(frame.columns) != list(PANEL_COLUMNS):
        problems.append(f"columns are {list(frame.columns)}, expected {list(PANEL_COLUMNS)}")
        return problems

    known_provinces = {*PROVINCES, NATIONAL}
    bad_prov = sorted({str(v) for v in frame["province"] if str(v) not in known_provinces})
    if bad_prov:
        problems.append(f"unknown province labels: {bad_prov[:5]}")

    bad_series = sorted({str(v) for v in frame["series"] if str(v) not in SERIES})
    if bad_series:
        problems.append(f"unknown series names: {bad_series[:5]}")

    for name, spec in SERIES.items():
        rows = frame.loc[frame["series"] == name]
        wrong = sorted({str(u) for u in rows["unit"] if str(u) != spec.unit})
        if wrong:
            problems.append(f"series {name!r} must carry unit {spec.unit!r}, found {wrong[:3]}")

    years = pd.to_numeric(frame["year"], errors="coerce")
    if years.isna().any() or not years.between(MIN_YEAR, MAX_YEAR).all():
        problems.append(f"year outside [{MIN_YEAR}, {MAX_YEAR}] or not an integer")

    values = pd.to_numeric(frame["value"], errors="coerce")
    n_bad_values = int((~values.notna()).sum())
    if n_bad_values:
        problems.append(
            f"{n_bad_values} non-finite values; a missing observation is an absent row, "
            "not a NaN row"
        )

    empty_vintage = int((frame["vintage"].astype("string").fillna("").str.len() == 0).sum())
    if empty_vintage:
        problems.append(f"{empty_vintage} rows with an empty vintage")
    bad_vintage = sorted(
        {v for v in frame["vintage"].astype("string").dropna() if not _VINTAGE_RE.match(str(v))}
    )
    if bad_vintage:
        problems.append(f"vintage labels must be lowercase slugs, found {bad_vintage[:3]}")

    if known_source_ids is not None:
        unknown = sorted({str(s) for s in frame["source_id"] if str(s) not in known_source_ids})
        if unknown:
            problems.append(f"source_id values not in SOURCES.yaml: {unknown[:5]}")

    dupes = frame.duplicated(subset=list(PANEL_KEY), keep=False)
    if bool(dupes.any()):
        offenders = frame.loc[dupes, list(PANEL_KEY)].head(3).to_dict("records")
        problems.append(
            f"{int(dupes.sum())} rows duplicate the key {PANEL_KEY}: {offenders}. "
            "Two values for one key means two vintages that were not labelled as such."
        )

    return problems


def concat_vintages(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Stack per-vintage panels into one.

    Concatenation is the whole operation: vintages are **not** merged, deduplicated or
    reconciled here. Two values for one (province, year, series) under two vintages is the
    signal, not a conflict.

    Parameters
    ----------
    frames : list of pandas.DataFrame
        Panels, each already through :func:`coerce_panel`.

    Returns
    -------
    pandas.DataFrame
        The stacked panel, coerced and sorted. An empty list gives :func:`empty_panel`.
    """
    if not frames:
        return empty_panel()
    return coerce_panel(pd.concat(frames, ignore_index=True))


def write_panel(frame: pd.DataFrame, path: Path) -> Path:
    """Write a validated panel to Parquet.

    Parameters
    ----------
    frame : pandas.DataFrame
        The panel. It is validated first; an invalid panel is not written.
    path : Path
        Destination. Parent directories are created.

    Returns
    -------
    Path
        ``path``.

    Raises
    ------
    ValueError
        If :func:`validate_panel` reports anything.
    """
    problems = validate_panel(frame)
    if problems:
        raise ValueError("refusing to write an invalid panel: " + "; ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def read_panel(path: Path) -> pd.DataFrame:
    """Read a panel written by :func:`write_panel`.

    Parameters
    ----------
    path : Path
        Parquet file.

    Returns
    -------
    pandas.DataFrame
        The panel, coerced to :data:`PANEL_DTYPES`.
    """
    return coerce_panel(pd.read_parquet(path))

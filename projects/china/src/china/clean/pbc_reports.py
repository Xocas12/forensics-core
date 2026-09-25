"""Loader for the central bank's regional financial operation reports.

Provincial credit is the hardest series in this project, and it arrives as **prose in a PDF**.
Each year's report page links a main report of about five megabytes plus one three-page
summary per province, and the summary states the year-end loan balance in a sentence. The
verification pass read one of them and quoted it; with the numbers changed to obviously
artificial ones, it looks like this::

    2099 year-end, the province's banking institutions had a domestic and foreign currency
    loan balance of 9.9 trillion yuan, up 111 hundred million from the start of the year,
    a year-on-year increase of 2.2 percent.

Three consequences the project has to live with:

* **Precision is about two significant figures.** "5.5 trillion" is what is published. A test
  that needs the third digit of provincial credit cannot be run on this source.
* **The unit varies within a sentence.** The balance is in trillions, the change in hundreds
  of millions. Both are converted here to the panel's 100 million yuan.
* **The file-to-province mapping is in the link text, not the file name.** The PDFs are named
  with opaque publisher identifiers. The province name is the run of characters between the
  title's opening bracket and the words "financial operation report", and it is in Chinese.

That last point used to stop the module cold, because no Chinese-to-canonical table had been
read from any source. One is now recorded as data in ``data/provinces.yaml``: every canonical
province, the English spellings the repository attests, the one Chinese name the registry
quotes verbatim, and the units among these files that are not provinces.
:func:`load_province_mapping` reads that file and validates it against
:mod:`china.clean.provinces`, and :func:`map_province_names` refuses any published name the
table does not know. The Chinese column is deliberately thin: a Chinese name enters it only
when the repository itself attests one, so completing it from a fetched year page remains
the one-off task recorded in the README.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

from china.clean._html import decode_html, iter_anchors
from china.clean.provinces import BOUNDARY_CHANGES, PROVINCES, SUBPROVINCIAL_UNITS

__all__ = [
    "BALANCE_COLUMNS",
    "PROVINCES_YAML",
    "SUMMARY_COLUMNS",
    "extract_pdf_text",
    "load_province_mapping",
    "map_province_names",
    "parse_loan_balances",
    "parse_summary_links",
    "to_panel",
]

# Chinese literals are written as escapes to keep this file ASCII. Each is annotated with its
# romanisation and meaning; all of them appear verbatim in the registry's evidence fields.
_LOAN_BALANCE = "\u5404\u9879\u8d37\u6b3e\u4f59\u989d"  # ge xiang dai kuan yu e, loan balance
_TRILLION = "\u4e07\u4ebf"  # wan yi, 10^12
_HUNDRED_MILLION = "\u4ebf"  # yi, 10^8
_YUAN = "\u5143"  # yuan
_YEAR_END = "\u5e74\u672b"  # nian mo, year-end
_YOY_GROWTH = "\u540c\u6bd4\u589e\u957f"  # tong bi zeng zhang, year-on-year growth
_SUMMARY = "\u6458\u8981"  # zhai yao, summary/abstract
_FINANCIAL_REPORT = "\u91d1\u878d\u8fd0\u884c\u62a5\u544a"  # jin rong yun xing bao gao
_BRACKET_OPEN = "\u300a"  # opening double angle bracket used around Chinese titles
_BRACKET_CLOSE = "\u300b"

#: How many 100 million yuan each published unit is worth.
_UNIT_FACTOR = {_TRILLION: 10_000.0, _HUNDRED_MILLION: 1.0}

_BALANCE_RE = re.compile(
    rf"{_LOAN_BALANCE}\s*([0-9]+(?:\.[0-9]+)?)\s*({_TRILLION}|{_HUNDRED_MILLION}){_YUAN}"
)
_YEAR_RE = re.compile(rf"((?:19|20)[0-9]{{2}}){_YEAR_END}")
_GROWTH_RE = re.compile(rf"{_YOY_GROWTH}\s*(-?[0-9]+(?:\.[0-9]+)?)\s*%")
_TITLE_RE = re.compile(
    rf"{_BRACKET_OPEN}([^{_BRACKET_CLOSE}]*?){_FINANCIAL_REPORT}[^{_BRACKET_CLOSE}]*{_BRACKET_CLOSE}"
)
_FULLWIDTH_PERIOD = "\uff0e"  # the channel numbers some links with a full-width stop
_ORDINAL_RE = re.compile(rf"^\s*(\d+)\s*[.{_FULLWIDTH_PERIOD}]")
_PDF_RE = re.compile(r"\.pdf$", re.IGNORECASE)

#: Columns of the frame :func:`parse_loan_balances` returns.
BALANCE_COLUMNS: tuple[str, ...] = (
    "year",
    "value_100m_yuan",
    "published_figure",
    "published_unit",
    "yoy_growth_pct",
)

#: Columns of the frame :func:`parse_summary_links` returns.
SUMMARY_COLUMNS: tuple[str, ...] = (
    "ordinal",
    "href",
    "link_text",
    "province_zh",
    "is_summary",
)

#: The recorded published-name table :func:`map_province_names` applies by default. Same
#: convention as ``DATA_DIR`` in ``china.acquire.__main__``: the project directory is three
#: parents up from this file.
PROVINCES_YAML = Path(__file__).resolve().parents[3] / "data" / "provinces.yaml"


def extract_pdf_text(path: Path) -> str:
    """Read a report PDF's text.

    A thin wrapper so that the choice of extraction library is made in one place and the
    parsers below can be tested on strings without a PDF anywhere near them.

    Parameters
    ----------
    path : Path
        The PDF.

    Returns
    -------
    str
        Concatenated page text, pages separated by newlines. Pages that yield no text
        contribute an empty string rather than being skipped, so page numbering is preserved.

    Raises
    ------
    ImportError
        If ``pdfplumber`` is not installed.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency is declared in pyproject
        raise ImportError("pdfplumber is required to read the report PDFs") from exc
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def parse_loan_balances(text: str) -> pd.DataFrame:
    """Find every published year-end loan balance in a summary's text.

    Parameters
    ----------
    text : str
        Text of one provincial summary, from :func:`extract_pdf_text`.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`BALANCE_COLUMNS`, one row per balance sentence found, in order of
        appearance:

        ``year``
            The year of the nearest preceding "year-end" marker, or ``<NA>`` when there is
            none. Left missing rather than guessed: a balance whose year is unknown is not a
            panel row.
        ``value_100m_yuan``
            The figure converted to the panel's unit. Trillions are multiplied by 10,000.
        ``published_figure`` and ``published_unit``
            What was actually printed, kept so the rounding is visible downstream.
        ``yoy_growth_pct``
            The year-on-year growth stated after the balance, if any.

        An empty frame means no balance sentence matched, which for a main report rather than
        a summary is the expected result.
    """
    rows: list[dict[str, object]] = []
    for match in _BALANCE_RE.finditer(text):
        before = text[: match.start()]
        year_matches = _YEAR_RE.findall(before)
        after = text[match.end() : match.end() + 200]
        growth = _GROWTH_RE.search(after)
        figure = float(match.group(1))
        unit = match.group(2)
        rows.append(
            {
                "year": int(year_matches[-1]) if year_matches else pd.NA,
                "value_100m_yuan": figure * _UNIT_FACTOR[unit],
                "published_figure": figure,
                "published_unit": unit,
                "yoy_growth_pct": float(growth.group(1)) if growth else pd.NA,
            }
        )
    frame = pd.DataFrame(rows, columns=list(BALANCE_COLUMNS))
    frame["year"] = frame["year"].astype("Int64")
    frame["yoy_growth_pct"] = pd.to_numeric(frame["yoy_growth_pct"], errors="coerce")
    return frame


def parse_summary_links(year_html: bytes | str) -> pd.DataFrame:
    """Parse one year's report page into its PDF links, with the province name as published.

    Parameters
    ----------
    year_html : bytes or str
        The year page.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`SUMMARY_COLUMNS`:

        ``ordinal``
            The number the channel prefixes each link with; the main report is 1.
        ``province_zh``
            The characters between the title's opening bracket and "financial operation
            report". For the main report this is the country name rather than a province,
            which is exactly why ``is_summary`` exists.
        ``is_summary``
            True when the link text is marked as a summary. The main report is not.

        Rows whose title does not match the pattern keep an empty ``province_zh`` rather than
        being dropped: an unmatched title is something to look at.
    """
    text = decode_html(year_html) if isinstance(year_html, bytes) else year_html
    rows: list[dict[str, object]] = []
    for anchor in iter_anchors(text):
        if not _PDF_RE.search(anchor.href):
            continue
        ordinal_match = _ORDINAL_RE.match(anchor.text)
        title_match = _TITLE_RE.search(anchor.text)
        rows.append(
            {
                "ordinal": int(ordinal_match.group(1)) if ordinal_match else pd.NA,
                "href": anchor.href,
                "link_text": anchor.text,
                "province_zh": title_match.group(1).strip() if title_match else "",
                "is_summary": _SUMMARY in anchor.text,
            }
        )
    frame = pd.DataFrame(rows, columns=list(SUMMARY_COLUMNS))
    frame["ordinal"] = frame["ordinal"].astype("Int64")
    frame["is_summary"] = frame["is_summary"].astype("boolean")
    return frame


def load_province_mapping(path: Path | None = None) -> dict[str, str]:
    """Load the recorded published-name table from ``data/provinces.yaml``.

    The file is validated against :mod:`china.clean.provinces` on every load, so the file
    and the code cannot drift apart silently:

    * the canonical names must be exactly the 31 of :data:`china.clean.provinces.PROVINCES`;
    * every boundary change recorded in :data:`china.clean.provinces.BOUNDARY_CHANGES` must
      appear in the file with the same year and parent, and no others;
    * every sub-provincial unit recorded in
      :data:`china.clean.provinces.SUBPROVINCIAL_UNITS` must appear under ``not_provinces``
      with the same parent, and no others.

    Parameters
    ----------
    path : Path, optional
        Override the table's location, :data:`PROVINCES_YAML`. Tests use this to point at
        a table deliberately written wrong.

    Returns
    -------
    dict of str to str
        Published name to target. Every key matches exactly; there is no fuzzy matching.
        A target is either a canonical name from :data:`china.clean.provinces.PROVINCES` or
        an explicit not-a-province label naming the unit and its parent.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If the file is malformed, disagrees with :mod:`china.clean.provinces`, or gives one
        published spelling two targets.
    """
    if path is None:
        path = PROVINCES_YAML
    if not path.exists():
        raise FileNotFoundError(
            f"the recorded province table {path} does not exist; it ships with the project "
            "under data/ and map_province_names needs it"
        )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("provinces"), list):
        raise ValueError(f"{path} must be a mapping carrying a 'provinces' list")

    table: dict[str, str] = {}

    def add(spelling: str, target: str) -> None:
        if not spelling:
            raise ValueError(f"{path} records an empty published name")
        if spelling in table:
            raise ValueError(
                f"{path} gives the published name {spelling!r} two targets: "
                f"{table[spelling]!r} and {target!r}"
            )
        table[spelling] = target

    separations: dict[str, tuple[int, str]] = {}
    for row in document["provinces"]:
        if not isinstance(row, dict) or "canonical" not in row:
            raise ValueError(
                f"{path} has a provinces entry that is not a mapping with a 'canonical' name"
            )
        canonical = row["canonical"]
        if not isinstance(canonical, str) or canonical not in PROVINCES:
            raise ValueError(
                f"{path} maps onto {canonical!r}, which is not one of the 31 canonical names "
                "in china.clean.provinces.PROVINCES"
            )
        for field in ("english", "chinese"):
            spellings = row.get(field) or []
            if not isinstance(spellings, list) or not all(
                isinstance(s, str) and s for s in spellings
            ):
                raise ValueError(f"{path} entry {canonical!r} carries a malformed {field!r} list")
        add(canonical, canonical)
        for spelling in row.get("english") or []:
            add(spelling, canonical)
        for spelling in row.get("chinese") or []:
            add(spelling, canonical)
        if "separated" in row:
            record = row["separated"]
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("year"), int)
                or record.get("from") not in PROVINCES
            ):
                raise ValueError(
                    f"{path} entry {canonical!r} carries a 'separated' record that is not a "
                    "mapping of a 'from' canonical province and an integer 'year'"
                )
            separations[canonical] = (record["year"], record["from"])

    recorded_canonicals = {row["canonical"] for row in document["provinces"]}
    missing = [p for p in PROVINCES if p not in recorded_canonicals]
    if missing:
        raise ValueError(
            f"{path} has no entry for {missing}, which the canonical list in "
            "china.clean.provinces carries; a province outside the table would raise at "
            "mapping time"
        )

    recorded = {(b.created, b.year, b.from_parent) for b in BOUNDARY_CHANGES}
    in_file = {(name, year, parent) for name, (year, parent) in separations.items()}
    if in_file != recorded:
        raise ValueError(
            f"{path} records the boundary changes {sorted(in_file)} but "
            f"china.clean.provinces records {sorted(recorded)}; the two must agree, because "
            "a series spanning a separation is two series"
        )

    rows = document.get("not_provinces")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must carry a 'not_provinces' list")
    units: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or "name" not in row or "parent" not in row:
            raise ValueError(f"{path} has a not_provinces entry without a 'name' and a 'parent'")
        if row["parent"] not in PROVINCES:
            raise ValueError(
                f"{path} gives the sub-provincial unit {row['name']!r} the parent "
                f"{row['parent']!r}, which is not a canonical province"
            )
        units.add((row["name"], row["parent"]))
        add(
            row["name"],
            f"{row['name']} (sub-provincial unit of {row['parent']}, not a province)",
        )
    recorded_units = {(u.name, u.parent) for u in SUBPROVINCIAL_UNITS}
    if units != recorded_units:
        raise ValueError(
            f"{path} and china.clean.provinces disagree about the sub-provincial units: the "
            f"file has {sorted(units)}, the code records {sorted(recorded_units)}"
        )
    return table


def map_province_names(names: pd.Series, mapping: dict[str, str] | None = None) -> pd.Series:
    """Map published names onto the project's canonical names.

    Two ways to call it, with deliberately different behaviour for a name the mapping does
    not know:

    * **No mapping.** The recorded table ``data/provinces.yaml`` is loaded through
      :func:`load_province_mapping` and applied strictly. That table is validated against
      the canonical province list on every load, so it is complete by construction, and a
      published name it does not know is not a row to tolerate: it raises, naming the name.
      A silent drop here would quietly shrink the panel and nobody would notice which
      province went missing.
    * **An explicit mapping.** Exactly that mapping is applied, and it may be partial: the
      loader tests map synthetic fixture names. An unmatched name stays ``<NA>``, where it
      is visible, rather than becoming a guess.

    Either way there is no fuzzy matching. A name either resolves exactly or it raises.

    Parameters
    ----------
    names : pandas.Series
        Published names, e.g. the ``province_zh`` column of :func:`parse_summary_links`.
    mapping : dict of str to str, optional
        Published name to canonical name. Omit it to use the recorded table.

    Returns
    -------
    pandas.Series
        Canonical names, as pandas string dtype.

    Raises
    ------
    ValueError
        If an explicit mapping is empty, or if no mapping was given and a published name is
        not in the recorded table.
    """
    if mapping is None:
        mapping = load_province_mapping()
        strict = True
    else:
        strict = False
    if not mapping:
        raise ValueError(
            "map_province_names was given an empty Chinese-to-canonical mapping; use "
            "load_province_mapping() to read the recorded table data/provinces.yaml"
        )
    if strict:
        unknown = sorted({str(v) for v in names if pd.notna(v) and str(v) not in mapping})
        if unknown:
            raise ValueError(
                f"{len(unknown)} published names are not in the recorded province table "
                f"{PROVINCES_YAML}: {unknown[:5]}. A row that cannot be stamped with a "
                "province must not leave the panel silently; add the name to "
                "data/provinces.yaml with its source, or fix the extraction that produced it"
            )
    return names.map(mapping).astype("string")


def to_panel(
    balances: pd.DataFrame,
    *,
    province: str,
    vintage: str,
    source_id: str = "pbc_regional_financial_operation_reports",
) -> pd.DataFrame:
    """Turn one province's parsed balances into tidy panel rows.

    Parameters
    ----------
    balances : pandas.DataFrame
        Output of :func:`parse_loan_balances`, for a single province's summary.
    province : str
        Canonical province name.
    vintage : str
        Vintage label; for these reports the publication year of the report, since a later
        report restates an earlier year.
    source_id : str, default "pbc_regional_financial_operation_reports"
        Registry id to stamp on every row.

    Returns
    -------
    pandas.DataFrame
        Rows in :data:`china.clean.schema.PANEL_COLUMNS`, carrying ``loans_outstanding``.
        Balances with no year are dropped, and the count of dropped rows is in the frame's
        ``attrs["n_dropped_no_year"]``.
    """
    from china.clean.schema import PANEL_COLUMNS, SERIES

    usable = balances.dropna(subset=["year"])
    frame = pd.DataFrame(
        {
            "province": province,
            "year": usable["year"].astype("int64"),
            "series": "loans_outstanding",
            "value": usable["value_100m_yuan"].astype("float64"),
            "unit": SERIES["loans_outstanding"].unit,
            "vintage": vintage,
            "source_id": source_id,
        },
        columns=list(PANEL_COLUMNS),
    )
    frame.attrs["n_dropped_no_year"] = int(len(balances) - len(usable))
    return frame

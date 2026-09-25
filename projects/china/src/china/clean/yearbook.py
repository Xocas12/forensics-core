"""China Statistical Yearbook web editions: the table of contents is data, the tables are not.

Each edition at ``https://www.stats.gov.cn/sj/ndsj/<year>/`` is a frameset whose contents
frame (``left_.htm`` in English, ``left.htm`` in Chinese) is a flat menu of links, declared
``gb2312`` and safely decoded as ``gb18030``. That menu **is** machine-readable, and parsing
it is what this module does for real: it yields the table number, the printed title and the
file name of every table in an edition, which is the only correct way to locate a table,
because both the file-naming convention and the table numbering drift between editions.

Attested in ``data/SOURCES.yaml``:

* the 2024 English menu links tables as ``html/E03-09.jpg`` with anchor text
  ``3-9 Gross Regional Product (2023)``;
* the 2017 and 2020 editions use ``html/EN0309.jpg`` and ``html/E0309.jpg`` for what the 2024
  edition calls ``E03-09.jpg``;
* the 2024 menu holds 762 links, of which 702 are ``.jpg``, 33 ``.htm`` and 27 ``.pdf``, and
  **none** is a spreadsheet.

That last point is the project's bottleneck. The tables themselves are JPEG scans, so there
is no honest parser to write for them yet: :func:`extract_table_image` and
:func:`grp_image_to_panel` are stubs with fixed signatures, and they raise. Do not replace
them with something that returns plausible numbers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from china.clean._html import iter_anchors

__all__ = [
    "TOC_ENCODING",
    "TOC_FILENAMES",
    "decode_toc",
    "extract_table_image",
    "find_tables",
    "grp_image_to_panel",
    "parse_toc",
    "table_number_from_filename",
]

#: Contents-frame file name by language, as observed on the live server.
TOC_FILENAMES: dict[str, str] = {"en": "left_.htm", "zh": "left.htm"}

#: The pages declare ``gb2312``; ``gb18030`` is its superset and decodes them without loss.
TOC_ENCODING = "gb18030"

#: Columns of the frame :func:`parse_toc` returns.
TOC_COLUMNS: tuple[str, ...] = (
    "href",
    "filename",
    "kind",
    "table_number",
    "file_table_number",
    "title",
    "data_year",
)

#: ``E03-09.jpg``, ``EN0309.jpg``, ``E0309.jpg`` and their ``C``-prefixed Chinese twins. The
#: last two digits are the table, everything before them the chapter.
_FILE_NUMBER_RE = re.compile(r"^(?P<lang>[EC])N?(?P<chapter>\d{1,2})-?(?P<table>\d{2})\b")
#: A printed table number at the head of a menu entry, e.g. ``3-9 Gross Regional Product``.
_TITLE_NUMBER_RE = re.compile(r"^\s*(\d{1,2}-\d{1,2})\b")
#: A trailing data year in parentheses, e.g. ``Freight Traffic by Region (2022)``.
_TITLE_YEAR_RE = re.compile(r"\((\d{4})\)\s*$")


def decode_toc(raw: bytes) -> str:
    """Decode a contents-frame page.

    Parameters
    ----------
    raw : bytes
        Bytes as served.

    Returns
    -------
    str
        The page decoded as :data:`TOC_ENCODING`, with undecodable bytes replaced rather
        than raising: a single bad byte in a footnote must not cost the whole menu.
    """
    return raw.decode(TOC_ENCODING, errors="replace")


def table_number_from_filename(filename: str) -> str | None:
    """Recover the printed table number from a yearbook table file name.

    Handles both conventions in use across editions: the hyphenated ``E03-09.jpg`` of the
    2020s and the run-together ``EN0309.jpg`` / ``E0309.jpg`` of earlier editions. The last
    two digits are always the table within the chapter.

    Parameters
    ----------
    filename : str
        Bare file name, with or without a directory prefix.

    Returns
    -------
    str or None
        For example ``"3-9"``. ``None`` for appendix files and anything that does not match
        the convention, which the caller should treat as "look at the title instead", not as
        an error.

    Examples
    --------
    >>> table_number_from_filename("html/E03-09.jpg")
    '3-9'
    >>> table_number_from_filename("EN1614.jpg")
    '16-14'
    >>> table_number_from_filename("zbe23.pdf") is None
    True
    """
    stem = filename.rsplit("/", 1)[-1]
    match = _FILE_NUMBER_RE.match(stem)
    if match is None:
        return None
    return f"{int(match.group('chapter'))}-{int(match.group('table'))}"


def parse_toc(raw: bytes | str) -> pd.DataFrame:
    """Parse an edition's contents frame into one row per link.

    Parameters
    ----------
    raw : bytes or str
        The contents-frame page. Bytes are decoded with :func:`decode_toc`.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`TOC_COLUMNS`, in document order, one row per anchor:

        ``href``
            The link target exactly as written, e.g. ``html/E03-09.jpg``.
        ``filename``
            Its last path segment.
        ``kind``
            Lower-case extension: ``jpg``, ``htm``, ``pdf`` or ``other``. An edition whose
            regional tables are all ``jpg`` needs optical character recognition; one with
            ``htm`` tables does not, and that is worth checking edition by edition.
        ``table_number``
            The number printed at the head of the menu entry, e.g. ``3-9``, or ``<NA>``.
        ``file_table_number``
            The number implied by the file name. It agrees with ``table_number`` in the
            editions checked so far, but the registry warns that numbering drifts, so both
            are kept and disagreement is left visible rather than resolved here.
        ``title``
            Menu text with tags and entities removed and whitespace collapsed.
        ``data_year``
            Year in a trailing parenthesis, e.g. 2023 in ``Gross Regional Product (2023)``,
            else ``<NA>``. This is the **data** year; the edition year is one greater in
            every case seen so far, but that is a pattern, not a rule, so a caller must not
            derive one from the other.

    Raises
    ------
    ValueError
        If the page contains no anchors at all. That means the fetch returned an error page
        or a frameset rather than the contents frame, and silently returning an empty table
        would make a whole edition disappear from the manifest without a word.
    """
    text = decode_toc(raw) if isinstance(raw, bytes) else raw
    rows: list[dict[str, object]] = []
    for anchor in iter_anchors(text):
        href = anchor.href
        title = anchor.text
        filename = href.rsplit("/", 1)[-1]
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        kind = suffix if suffix in {"jpg", "jpeg", "htm", "html", "pdf", "xls", "xlsx"} else "other"
        number_match = _TITLE_NUMBER_RE.match(title)
        year_match = _TITLE_YEAR_RE.search(title)
        rows.append(
            {
                "href": href,
                "filename": filename,
                "kind": "jpg" if kind == "jpeg" else kind,
                "table_number": number_match.group(1) if number_match else pd.NA,
                "file_table_number": table_number_from_filename(filename) or pd.NA,
                "title": title,
                "data_year": int(year_match.group(1)) if year_match else pd.NA,
            }
        )
    if not rows:
        raise ValueError(
            "no anchors found: this is not a yearbook contents frame (an error page, or the "
            "frameset index rather than left_.htm / left.htm)"
        )
    frame = pd.DataFrame(rows, columns=list(TOC_COLUMNS))
    frame["data_year"] = frame["data_year"].astype("Int64")
    for column in ("href", "filename", "kind", "table_number", "file_table_number", "title"):
        frame[column] = frame[column].astype("string")
    return frame


def find_tables(toc: pd.DataFrame, title_contains: str) -> pd.DataFrame:
    """Select the menu entries whose title contains a phrase, case-insensitively.

    Locating a table by its **title** and not by its number is deliberate: the registry
    records that the file-naming convention changed between the 2017 and 2024 editions and
    warns that a table number is not guaranteed to mean the same table in every edition.
    Titles such as ``Gross Regional Product``, ``Electricity Consumption by Region`` and
    ``Freight Traffic by Region`` have been stable across the editions examined.

    Parameters
    ----------
    toc : pandas.DataFrame
        Output of :func:`parse_toc`.
    title_contains : str
        Phrase to look for.

    Returns
    -------
    pandas.DataFrame
        The matching rows, in document order. Empty when nothing matches, which for a given
        edition is a real answer: that edition may not carry the table.

    Raises
    ------
    ValueError
        If ``title_contains`` is empty, which would match every row.
    """
    if not title_contains.strip():
        raise ValueError("title_contains must be a non-empty phrase")
    mask = toc["title"].str.contains(title_contains, case=False, regex=False, na=False)
    return toc.loc[mask].copy()


def extract_table_image(
    path: Path,
    *,
    edition_year: int,
    table_number: str,
    language: str = "en",
) -> pd.DataFrame:
    """Extract one yearbook table from its JPEG scan. **Stub: raises.**

    The interface is fixed here so that the loaders, the panel builder and the tests can be
    written against it before the extraction back end exists.

    Intended contract: return a frame whose first column is the row label exactly as printed
    (so that :func:`china.clean.provinces.canonical_province` can be applied and unmatched
    labels reported), whose remaining columns are the table's own column headers in printed
    order, and whose ``attrs`` carry ``{"edition_year", "table_number", "language",
    "footnotes", "source_path", "sha256"}``. Values stay as printed: no unit conversion, no
    dropping of aggregate rows, no filling of blanks.

    Parameters
    ----------
    path : Path
        The downloaded JPEG, under ``data/raw``.
    edition_year : int
        Edition the image came from. Part of the vintage, so it is required, not inferred
        from the path.
    table_number : str
        Printed table number, e.g. ``"3-9"``, taken from the edition's contents frame rather
        than assumed.
    language : {"en", "zh"}, default "en"
        Which edition of the table. The Chinese and English scans of the same table carry
        the same numbers, so the pair is a free transcription cross-check.

    Returns
    -------
    pandas.DataFrame
        As described above.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: choose and pin an extraction back end (the registry's ``download_plan``
    suggests Tesseract with ``chi_sim+eng``, or a table-structure model), then gate every
    extracted table on the arithmetic checks in ``docs/data_dictionary.md`` before any value
    is allowed into the panel.
    """
    raise NotImplementedError(
        "yearbook tables are JPEG scans; an optical-character-recognition back end and its "
        "per-table arithmetic validation are not implemented"
    )


def grp_image_to_panel(
    frame: pd.DataFrame,
    *,
    edition_year: int,
    source_id: str,
) -> pd.DataFrame:
    """Turn an extracted table 3-9 into tidy panel rows. **Stub: raises.**

    Parameters
    ----------
    frame : pandas.DataFrame
        Output of :func:`extract_table_image` for a gross regional product table.
    edition_year : int
        Edition the table came from; becomes the ``vintage`` through
        :func:`china.clean.schema.vintage_of_yearbook_edition`.
    source_id : str
        Registry id the image was acquired under.

    Returns
    -------
    pandas.DataFrame
        Rows in :data:`china.clean.schema.PANEL_COLUMNS`, carrying ``grp_nominal`` and
        ``grp_index_preceding_year``. Older editions print several data years in one table
        and therefore yield several data years for one vintage; recent editions print a
        single-year cross-section and yield one.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the column-layout map per edition family (multi-year levels plus indices in
    the 2015-style editions, single-year cross-section with a sectoral decomposition in the
    2024-style ones), and the decision about what to do with a footnoted preliminary year.
    """
    raise NotImplementedError(
        "panel construction from an extracted table 3-9 awaits extract_table_image and the "
        "per-edition column-layout map"
    )

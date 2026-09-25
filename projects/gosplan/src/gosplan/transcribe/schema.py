"""The schema for one transcribed Soviet statistical table, and the printed-number parser.

Why a schema at all. The primary series this project needs exist as printed Russian tables in
volumes whose bundled optical character recognition destroys column structure
(``docs/known_traps.md``, trap 9). Getting them into a machine-readable form means people
typing digits off page images. Everything that then goes wrong -- a value in old roubles
compared against one in new roubles, a pre-war total compared against a post-war one, a
five-year-plan column read as a single year, a decimal comma read as a thousands separator --
is invisible once the number is in a column of floats. So the unit of transcription here is
not a number: it is a **cell carried with everything needed to know what it means**.

Four fields exist because of specific documented traps. Three of them are mandatory --
``currency_basis``, ``territorial_basis`` and ``confidence`` -- and the fourth,
``definition_note``, is optional, because most tables add nothing to their heading; it is
nonetheless the only place a definitional revision can be recorded, and the validator asks
for it wherever a restatement is implied:

``currency_basis``
    The rouble was redenominated 10:1 in 1961. Value series spanning the reform show a
    discontinuity of exactly one order of magnitude, and later volumes sometimes restate
    pre-1961 figures in new roubles and sometimes do not. A monetary cell whose basis is not
    declared is not usable, so the validator rejects it.
``territorial_basis``
    The 1939-40 annexations changed the territory "USSR" refers to. Soviet yearbooks often
    print both "within boundaries before 17 September 1939" and "within present boundaries";
    which one a table uses is a property of the table, not of the series.
``definition_note``
    Gross output, net output, "normative net output" and the 1988 shift toward net material
    product presentations are different quantities under similar headings. What the printed
    table says it is measuring is copied here verbatim, from the table's own head note or the
    volume's methodological chapter. Optional, and the one field in this list that is: see
    ``REQUIRED_FIELDS`` below, and the ``new_roubles_before_reform`` and
    ``old_roubles_late_edition`` warnings that ask for it when the units imply a restatement.
``confidence``
    Whether the transcriber could actually read the digits, and how the cell was printed when
    it holds no number. Digit tests are only meaningful on cells flagged ``clear``.

The table-level fields (:class:`TableIdentity`) are repeated on every row of the flat CSV that
a person fills in, and the validator checks they never vary within a file. That redundancy is
deliberate: a row torn out of context still says which page of which edition it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "CELL_FIELDS",
    "FIELD_NAMES",
    "NIL_MARKERS",
    "NO_DATA_MARKERS",
    "REQUIRED_FIELDS",
    "TABLE_FIELDS",
    "CellRole",
    "Confidence",
    "CurrencyBasis",
    "ParsedNumber",
    "TableIdentity",
    "TerritorialBasis",
    "TranscribedCell",
    "TranscribedTable",
    "flatten_table",
    "parse_printed_number",
    "split_row",
]


class CurrencyBasis(StrEnum):
    """Which rouble, if any, a value is expressed in.

    The 1961 redenomination rescaled every monetary series by a factor of ten. A table that
    does not say which unit it uses cannot be compared with one that does, so
    ``unstated`` is not a member of this enumeration: a transcriber who cannot tell must
    leave the cell blank and say why in ``notes``, not record a guess.
    """

    NOT_MONETARY = "not_monetary"
    OLD_ROUBLES = "old_roubles"
    NEW_ROUBLES = "new_roubles"
    FOREIGN_CURRENCY = "foreign_currency"


class TerritorialBasis(StrEnum):
    """The territory a figure refers to, as the printed table states it.

    ``unstated`` is allowed because many tables genuinely do not say, but the validator
    treats it as an error for any table touching 1939 or 1940 and as a warning otherwise.
    """

    PRE_1939_BOUNDARIES = "pre_1939_boundaries"
    PRESENT_BOUNDARIES = "present_boundaries"
    OTHER_STATED = "other_stated"
    UNSTATED = "unstated"


class CellRole(StrEnum):
    """Whether a cell is an addend, a subtotal, or the printed total of its group.

    Needed for the reconciliation check: a total must equal the sum of the ``data`` cells in
    its group, and subtotals must be excluded from that sum or they double-count.
    """

    DATA = "data"
    SUBTOTAL = "subtotal"
    TOTAL = "total"


class Confidence(StrEnum):
    """How the cell was read, or why it holds no number.

    The last three members are not degrees of doubt: they record what was actually printed.
    A cell printed as a nil mark and a cell printed as a no-data mark are different
    statements, and neither is a zero.
    """

    CLEAR = "clear"
    AMBIGUOUS_DIGIT = "ambiguous_digit"
    DAMAGED_PRINT = "damaged_print"
    ILLEGIBLE = "illegible"
    NIL_PRINTED = "nil_printed"
    NO_DATA_PRINTED = "no_data_printed"


#: Confidence values that assert a number was read. The others require a blank ``value``.
NUMERIC_CONFIDENCE: frozenset[str] = frozenset(
    {Confidence.CLEAR, Confidence.AMBIGUOUS_DIGIT, Confidence.DAMAGED_PRINT}
)

#: Marks that stand for "the phenomenon does not occur" rather than a number.
#:
#: **This mapping is a default, not a finding.** Each volume prints its own key of
#: conventional signs, and a transcriber must confirm the key in the volume being
#: transcribed before relying on it; where it differs, pass the volume's own marker sets to
#: :func:`parse_printed_number`. Written with escapes because every source file in this
#: repository is ASCII: hyphen-minus, en dash, em dash, minus sign.
MINUS_LIKE: tuple[str, ...] = ("-", "\u2013", "\u2014", "\u2212")
NIL_MARKERS: frozenset[str] = frozenset(MINUS_LIKE)

#: Marks that stand for "no data available". Same caveat as :data:`NIL_MARKERS`: ellipsis
#: typed as two, three or four periods, and the single ellipsis character.
NO_DATA_MARKERS: frozenset[str] = frozenset({"..", "...", "....", "\u2026"})

#: Characters that group digits in printed tables: ordinary space, non-breaking space, thin
#: space, narrow non-breaking space, and the apostrophe used by some typesetters.
_GROUPING: tuple[str, ...] = (" ", "\u00a0", "\u2009", "\u202f", "\u2019", "'")

_PERIOD_RE = re.compile(r"^\d{4}(?:-\d{4}|/\d{2})?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TableIdentity(BaseModel):
    """Everything that identifies the printed table a cell was copied from.

    Constant across every row of one filled template; the validator enforces that.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(description="id of the SOURCES.yaml entry the scan came from")
    volume: str = Field(description="volume as printed on the title page, transliterated")
    edition_year: int = Field(
        ge=1900, le=1995, description="year the edition covers, e.g. 1985 for the 1985 annual"
    )
    page: int = Field(ge=1, description="printed page number the table starts on")
    table_number: str = Field(
        description="table number as printed; the literal 'unnumbered' when there is none"
    )
    title_ru: str = Field(description="table heading copied character for character")
    title_translit: str = Field(description="the same heading transliterated to ASCII")
    territorial_basis: TerritorialBasis = Field(
        description="territory the figures refer to, per the table or its head note"
    )
    transcriber: str = Field(description="who typed it; initials are enough, but not blank")
    transcription_date: str = Field(description="ISO date, YYYY-MM-DD, when it was typed")

    @field_validator("source_id", "volume", "table_number", "title_ru", "title_translit")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("transcriber")
    @classmethod
    def _named(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a transcription with no transcriber cannot be double-checked")
        return v.strip()

    @field_validator("transcription_date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        if not _ISO_DATE_RE.match(v.strip()):
            raise ValueError("transcription_date must be an ISO date, YYYY-MM-DD")
        return v.strip()


class TranscribedCell(BaseModel):
    """One cell of a printed table, with what is needed to interpret it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_label: str = Field(description="row stub as printed")
    row_label_translit: str = Field(default="", description="row stub transliterated to ASCII")
    column_label: str = Field(description="column head as printed")
    column_label_translit: str = Field(default="", description="column head transliterated")
    period: str = Field(description="YYYY, YYYY-YYYY for a plan period, or YYYY/YY for a crop year")
    value_raw: str = Field(description="the cell exactly as printed, marks and separators kept")
    value: float | None = Field(default=None, description="parsed number; blank if none printed")
    unit: str = Field(description="unit of measurement as the table states it")
    currency_basis: CurrencyBasis = Field(description="which rouble, or not_monetary")
    row_role: CellRole = Field(default=CellRole.DATA)
    column_role: CellRole = Field(default=CellRole.DATA)
    definition_note: str = Field(
        default="", description="what the table says it is measuring, copied not paraphrased"
    )
    confidence: Confidence = Field(description="how the cell was read, or how it was printed")
    notes: str = Field(default="", description="anything a second transcriber would need")

    @field_validator("row_label", "column_label", "unit", "value_raw")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("period")
    @classmethod
    def _period(cls, v: str) -> str:
        text = v.strip()
        if not _PERIOD_RE.match(text):
            raise ValueError("period must look like 1985, 1981-1985 or 1984/85")
        return text


class TranscribedTable(BaseModel):
    """A table identity plus its cells, as one object."""

    model_config = ConfigDict(extra="forbid")

    identity: TableIdentity
    cells: tuple[TranscribedCell, ...]


#: Table-level column names, in the order they appear in a template.
TABLE_FIELDS: tuple[str, ...] = tuple(TableIdentity.model_fields)

#: Cell-level column names, in the order they appear in a template.
CELL_FIELDS: tuple[str, ...] = tuple(TranscribedCell.model_fields)

#: The full flat column order of a transcription template. Derived from the models rather
#: than typed out, so a template can never drift from the schema it claims to follow.
FIELD_NAMES: tuple[str, ...] = TABLE_FIELDS + CELL_FIELDS

#: Columns a filled template must not leave blank. ``value`` is excluded on purpose: a cell
#: printed as a nil or no-data mark has no number, and forcing one there would manufacture
#: data. ``row_label_translit``, ``definition_note`` and ``notes`` are optional aids.
REQUIRED_FIELDS: tuple[str, ...] = tuple(
    f
    for f in FIELD_NAMES
    if f
    not in {
        "value",
        "row_label_translit",
        "column_label_translit",
        "definition_note",
        "notes",
    }
)


@dataclass(frozen=True)
class ParsedNumber:
    """The result of reading one printed cell.

    Attributes
    ----------
    value : float or None
        The number, or None when the cell held a nil mark, a no-data mark, nothing, or
        something that could not be parsed.
    kind : str
        ``"number"``, ``"nil"``, ``"no_data"``, ``"blank"`` or ``"unparsable"``.
    digits : str
        Significant decimal digits with sign, separators and decimal mark removed, in printed
        order. This is what the double-transcription comparison counts disagreements over,
        and what a first-digit or first-two-digit test would consume.
    decimals : int
        Number of digits printed after the decimal mark. Drives the rounding tolerance used
        when checking a printed total against the sum of its addends.
    negative : bool
        Whether the printed cell carried a minus sign.
    """

    value: float | None
    kind: Literal["number", "nil", "no_data", "blank", "unparsable"]
    digits: str = ""
    decimals: int = 0
    negative: bool = False


def parse_printed_number(
    raw: str,
    *,
    nil_markers: frozenset[str] = NIL_MARKERS,
    no_data_markers: frozenset[str] = NO_DATA_MARKERS,
) -> ParsedNumber:
    """Read one printed table cell into a number, or say why it is not one.

    Handles the three conventions of Soviet printed statistics that break a naive
    ``float()``: the decimal separator is a comma, digit groups are separated by spaces of
    various widths, and a cell may carry a conventional mark instead of a figure.

    Parameters
    ----------
    raw : str
        The cell exactly as printed, as the transcriber typed it.
    nil_markers, no_data_markers : frozenset of str
        The volume's own conventional marks. Defaults are :data:`NIL_MARKERS` and
        :data:`NO_DATA_MARKERS`, which must be confirmed against the volume's key page.

    Returns
    -------
    ParsedNumber
        ``kind`` distinguishes a genuine number from an absent phenomenon, from missing data,
        from an empty cell and from a string nobody can interpret. A nil mark is never
        returned as 0.0: "this did not happen" and "this was zero" are different claims, and
        collapsing them silently invents data.

    Examples
    --------
    >>> parse_printed_number("9 221").value
    9221.0
    >>> parse_printed_number("12,1").decimals
    1
    >>> parse_printed_number("-").kind
    'nil'
    >>> parse_printed_number("...").kind
    'no_data'
    >>> parse_printed_number("1 234,5").digits
    '12345'
    """
    text = raw.strip()
    if not text:
        return ParsedNumber(None, "blank")
    if text in nil_markers:
        return ParsedNumber(None, "nil")
    if text in no_data_markers:
        return ParsedNumber(None, "no_data")

    body = text
    negative = False
    if body[0] in {*MINUS_LIKE, "+"}:
        negative = body[0] != "+"
        body = body[1:].strip()

    for ch in _GROUPING:
        body = body.replace(ch, "")
    if body.count(",") + body.count(".") > 1:
        return ParsedNumber(None, "unparsable")
    normalised = body.replace(",", ".")
    if not normalised or not re.fullmatch(r"\d+(?:\.\d+)?", normalised):
        return ParsedNumber(None, "unparsable")

    decimals = len(normalised.split(".")[1]) if "." in normalised else 0
    digits = normalised.replace(".", "")
    value = float(normalised)
    return ParsedNumber(-value if negative else value, "number", digits, decimals, negative)


def split_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split one flat template row into its table-level and cell-level halves."""
    return (
        {k: row.get(k) for k in TABLE_FIELDS},
        {k: row.get(k) for k in CELL_FIELDS},
    )


def flatten_table(table: TranscribedTable) -> list[dict[str, Any]]:
    """Render a :class:`TranscribedTable` back into flat template rows.

    The inverse of reading a filled template, and the function a writer should use rather
    than assembling dictionaries by hand: the column order comes from :data:`FIELD_NAMES`, so
    it cannot drift.
    """
    head = table.identity.model_dump(mode="json")
    rows: list[dict[str, Any]] = []
    for cell in table.cells:
        row = dict(head)
        row.update(cell.model_dump(mode="json"))
        rows.append({k: row[k] for k in FIELD_NAMES})
    return rows

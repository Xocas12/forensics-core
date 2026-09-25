"""The transcription schema and the printed-number parser.

Every expected value here was computed by hand from the printing conventions the parser
claims to handle, not by running the parser and recording what it said.
"""

from __future__ import annotations

import pytest
from gosplan.transcribe.schema import (
    CELL_FIELDS,
    FIELD_NAMES,
    TABLE_FIELDS,
    CellRole,
    Confidence,
    CurrencyBasis,
    TableIdentity,
    TerritorialBasis,
    TranscribedCell,
    TranscribedTable,
    flatten_table,
    parse_printed_number,
    split_row,
)
from pydantic import ValidationError

NBSP = "\u00a0"
THIN_SPACE = "\u2009"
EN_DASH = "\u2013"
EM_DASH = "\u2014"
ELLIPSIS = "\u2026"


def _identity(**over):
    base = {
        "source_id": "ia_narkhoz_1985_item",
        "volume": "SYNTHETIC FIXTURE",
        "edition_year": 1985,
        "page": 111,
        "table_number": "T-0",
        "title_ru": "SINTETICHESKAIA TABLITSA",
        "title_translit": "Synthetic table",
        "territorial_basis": TerritorialBasis.PRESENT_BOUNDARIES,
        "transcriber": "TEST",
        "transcription_date": "2026-09-07",
    }
    base.update(over)
    return base


def _cell(**over):
    base = {
        "row_label": "Shop A",
        "column_label": "Output",
        "period": "1985",
        "value_raw": "11,1",
        "value": 11.1,
        "unit": "thousand widgets",
        "currency_basis": CurrencyBasis.NOT_MONETARY,
        "confidence": Confidence.CLEAR,
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ column order


def test_field_names_are_the_two_models_concatenated_without_duplicates():
    assert FIELD_NAMES == TABLE_FIELDS + CELL_FIELDS
    assert len(set(FIELD_NAMES)) == len(FIELD_NAMES)


def test_field_names_cover_every_element_the_brief_requires():
    required = {
        "source_id",
        "volume",
        "edition_year",
        "page",
        "table_number",
        "title_ru",
        "title_translit",
        "row_label",
        "column_label",
        "period",
        "value",
        "unit",
        "currency_basis",
        "territorial_basis",
        "definition_note",
        "transcriber",
        "transcription_date",
        "confidence",
    }
    assert required <= set(FIELD_NAMES)


def test_split_row_partitions_a_flat_row_exactly():
    row = dict.fromkeys(FIELD_NAMES, "x")
    head, cell = split_row(row)
    assert tuple(head) == TABLE_FIELDS
    assert tuple(cell) == CELL_FIELDS


def test_flatten_table_emits_rows_in_schema_column_order():
    table = TranscribedTable(
        identity=TableIdentity(**_identity()),
        cells=(TranscribedCell(**_cell()), TranscribedCell(**_cell(period="1980"))),
    )
    rows = flatten_table(table)
    assert len(rows) == 2
    for row in rows:
        assert tuple(row) == FIELD_NAMES
    assert rows[0]["source_id"] == "ia_narkhoz_1985_item"
    assert rows[1]["period"] == "1980"


# ------------------------------------------------------------------ number parsing


@pytest.mark.parametrize(
    ("raw", "value", "digits", "decimals"),
    [
        ("9221", 9221.0, "9221", 0),
        ("9 221", 9221.0, "9221", 0),
        (f"9{NBSP}221", 9221.0, "9221", 0),
        (f"9{THIN_SPACE}221", 9221.0, "9221", 0),
        ("12,1", 12.1, "121", 1),
        ("12.1", 12.1, "121", 1),
        ("1 234,5", 1234.5, "12345", 1),
        ("0,0", 0.0, "00", 1),
        ("100,00", 100.0, "10000", 2),
    ],
)
def test_printed_numbers_parse_with_soviet_conventions(raw, value, digits, decimals):
    got = parse_printed_number(raw)
    assert got.kind == "number"
    assert got.value == pytest.approx(value)
    assert got.digits == digits
    assert got.decimals == decimals


@pytest.mark.parametrize("mark", ["-", EN_DASH, EM_DASH])
def test_nil_marks_are_not_zero(mark):
    got = parse_printed_number(mark)
    assert got.kind == "nil"
    assert got.value is None, "a dash means the phenomenon did not occur, not that it was zero"


@pytest.mark.parametrize("mark", ["...", "..", ELLIPSIS])
def test_no_data_marks_are_distinguished_from_nil(mark):
    assert parse_printed_number(mark).kind == "no_data"


def test_blank_and_unparsable_are_distinguished():
    assert parse_printed_number("   ").kind == "blank"
    assert parse_printed_number("1O,5").kind == "unparsable"
    assert parse_printed_number("12,3,4").kind == "unparsable"
    assert parse_printed_number("about 12").kind == "unparsable"


def test_a_dash_followed_by_digits_is_a_negative_number_not_a_nil_mark():
    got = parse_printed_number(f"{EN_DASH}12,5")
    assert got.kind == "number"
    assert got.value == pytest.approx(-12.5)


def test_minus_prefixed_number_is_negative_not_nil():
    got = parse_printed_number("-12,5")
    assert got.kind == "number"
    assert got.negative is True
    assert got.value == pytest.approx(-12.5)
    assert got.digits == "125", "the sign is tracked separately from the digit string"


def test_volume_specific_marker_sets_can_be_supplied():
    """Each volume prints its own key of conventional signs; the defaults are overridable."""
    got = parse_printed_number("x", nil_markers=frozenset({"x"}))
    assert got.kind == "nil"


# ------------------------------------------------------------------ model validation


def test_a_transcription_with_no_transcriber_is_refused():
    with pytest.raises(ValidationError):
        TableIdentity(**_identity(transcriber="  "))


def test_a_non_iso_transcription_date_is_refused():
    with pytest.raises(ValidationError):
        TableIdentity(**_identity(transcription_date="7 September 2026"))


def test_an_edition_year_outside_the_soviet_period_is_refused():
    with pytest.raises(ValidationError):
        TableIdentity(**_identity(edition_year=2015))


@pytest.mark.parametrize("period", ["1985", "1981-1985", "1984/85"])
def test_accepted_period_forms(period):
    assert TranscribedCell(**_cell(period=period)).period == period


@pytest.mark.parametrize("period", ["85", "1985 g.", "five year plan", "1981--1985"])
def test_rejected_period_forms(period):
    with pytest.raises(ValidationError):
        TranscribedCell(**_cell(period=period))


def test_a_blank_unit_is_refused():
    with pytest.raises(ValidationError):
        TranscribedCell(**_cell(unit=""))


def test_currency_basis_has_no_unstated_member():
    """A monetary figure whose rouble is unknown must be left blank, not guessed."""
    assert "unstated" not in {m.value for m in CurrencyBasis}
    assert "unstated" in {m.value for m in TerritorialBasis}


def test_cell_roles_cover_totals_and_subtotals():
    assert {m.value for m in CellRole} == {"data", "subtotal", "total"}

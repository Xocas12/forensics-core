"""Validation of filled transcription templates.

Two of these tests are the ones the brief asks for by name: a clean synthetic transcription
that passes, and a deliberately corrupted one that must be rejected with the specific codes
naming each corruption. The rest pin down the arithmetic, which is where a validator is most
likely to be quietly wrong: the rounding tolerance is derived by hand from the printed
precision rather than trusted.
"""

from __future__ import annotations

import pytest
from gosplan.transcribe.templates import read_filled
from gosplan.transcribe.validate import rounding_tolerance, validate_file, validate_rows

CLEAN = "synthetic_transcription_clean.csv"
CORRUPT = "synthetic_transcription_corrupt.csv"


def _base_row(**over):
    row = {
        "source_id": "ia_narkhoz_1985_item",
        "volume": "SYNTHETIC FIXTURE",
        "edition_year": "1985",
        "page": "111",
        "table_number": "T-0",
        "title_ru": "SINTETICHESKAIA TABLITSA",
        "title_translit": "Synthetic table",
        "territorial_basis": "present_boundaries",
        "transcriber": "TEST",
        "transcription_date": "2026-09-07",
        "row_label": "Shop A",
        "row_label_translit": "",
        "column_label": "Output",
        "column_label_translit": "",
        "period": "1985",
        "value_raw": "11,1",
        "value": "11.1",
        "unit": "thousand widgets",
        "currency_basis": "not_monetary",
        "row_role": "data",
        "column_role": "data",
        "definition_note": "",
        "confidence": "clear",
        "notes": "",
    }
    row.update(over)
    return row


def _table(rows_spec):
    """Build a small table: (row_label, value_raw, row_role) tuples in one column and period."""
    return [
        _base_row(row_label=label, value_raw=raw, value=raw.replace(",", "."), row_role=role)
        for label, raw, role in rows_spec
    ]


# ------------------------------------------------------------------ the two fixtures


def test_the_clean_transcription_passes_with_no_errors_or_warnings(fixtures_dir):
    report = validate_file(fixtures_dir / CLEAN)
    assert report.ok
    assert report.issues == ()
    assert report.n_rows == 15


def test_the_corrupted_transcription_is_rejected(fixtures_dir):
    report = validate_file(fixtures_dir / CORRUPT)
    assert not report.ok
    codes = report.codes()
    expected = {
        "total_mismatch",
        "currency_basis_missing",
        "unparsable_value",
        "value_present_without_number",
        "value_mismatch",
        "missing_required",
        "duplicate_cell",
        "confidence_marker_mismatch",
        "territorial_basis_unstated",
    }
    assert expected <= set(codes), f"missing {sorted(expected - set(codes))}"


def test_each_corruption_is_reported_against_the_row_that_carries_it(fixtures_dir):
    report = validate_file(fixtures_dir / CORRUPT)
    by_code = {i.code: i for i in report.errors}
    assert by_code["total_mismatch"].row == 4
    assert "76.6" in by_code["total_mismatch"].message
    assert "66.6" in by_code["total_mismatch"].message
    assert by_code["currency_basis_missing"].row == 5
    assert by_code["unparsable_value"].row == 6
    assert by_code["missing_required"].field == "unit"
    assert "1981" in by_code["duplicate_cell"].message


def test_an_unstated_territorial_basis_is_an_error_only_across_the_boundary_change(
    fixtures_dir,
):
    report = validate_file(fixtures_dir / CORRUPT)
    territorial = [i for i in report.issues if i.code == "territorial_basis_unstated"]
    errors = [i for i in territorial if i.severity == "error"]
    warnings = [i for i in territorial if i.severity == "warning"]
    assert len(errors) == 1, "only the row whose period spans 1939-40 is fatal"
    assert "1938-1941" in errors[0].message
    assert warnings, "the rest are still worth flagging"


def test_the_pair_fixtures_are_themselves_valid(fixtures_dir):
    for name in ("synthetic_transcription_pair_a.csv", "synthetic_transcription_pair_b.csv"):
        report = validate_file(fixtures_dir / name)
        assert report.ok, report.summary()


# ------------------------------------------------------------------ rounding tolerance


@pytest.mark.parametrize(
    ("n_addends", "decimals", "expected"),
    [
        (3, 1, 0.2),
        (4, 0, 2.5),
        (1, 2, 0.01),
        (9, 0, 5.0),
        (0, 0, 0.5),
    ],
)
def test_rounding_tolerance_is_half_a_last_place_per_printed_figure(n_addends, decimals, expected):
    assert rounding_tolerance(n_addends, decimals) == pytest.approx(expected)


def test_rounding_tolerance_rejects_nonsense():
    with pytest.raises(ValueError):
        rounding_tolerance(-1, 0)
    with pytest.raises(ValueError):
        rounding_tolerance(3, -1)


def test_a_total_inside_the_rounding_tolerance_is_accepted():
    """0.1 + 0.1 + 0.1 printed as 0.4: off by 0.1, tolerance for 3 addends at 1 dp is 0.2."""
    rows = _table(
        [("A", "0,1", "data"), ("B", "0,1", "data"), ("C", "0,1", "data"), ("T", "0,4", "total")]
    )
    report = validate_rows(rows)
    assert "total_mismatch" not in report.codes()


def test_a_total_outside_the_rounding_tolerance_is_rejected():
    """Same table printed as 0.7: off by 0.4, which no rounding of three figures explains."""
    rows = _table(
        [("A", "0,1", "data"), ("B", "0,1", "data"), ("C", "0,1", "data"), ("T", "0,7", "total")]
    )
    report = validate_rows(rows)
    assert report.codes()["total_mismatch"] == 1
    assert not report.ok


def test_subtotals_are_excluded_from_the_sum_rather_than_double_counted():
    rows = _table(
        [
            ("A", "10,0", "data"),
            ("B", "20,0", "data"),
            ("A+B", "30,0", "subtotal"),
            ("C", "5,0", "data"),
            ("T", "35,0", "total"),
        ]
    )
    report = validate_rows(rows)
    assert "total_mismatch" not in report.codes()


def test_a_total_is_reported_as_unchecked_when_an_addend_holds_no_number():
    rows = _table([("A", "10,0", "data"), ("B", "20,0", "data"), ("T", "30,0", "total")])
    rows[1]["value_raw"] = "..."
    rows[1]["value"] = ""
    rows[1]["confidence"] = "no_data_printed"
    report = validate_rows(rows)
    assert report.codes()["total_unchecked"] == 1
    assert "total_mismatch" not in report.codes()
    assert report.ok, "an unverifiable total is a warning, not a rejection"


# ------------------------------------------------------------------ the other checks


def test_a_header_that_has_drifted_from_the_schema_is_rejected():
    rows = [_base_row()]
    rows[0].pop("unit")
    rows[0]["units"] = "thousand widgets"
    report = validate_rows(rows)
    codes = report.codes()
    assert codes["missing_column"] == 1
    assert codes["unknown_column"] == 1


def test_a_table_level_field_that_varies_within_one_file_is_rejected():
    rows = [_base_row(period="1980"), _base_row(period="1985", page="222")]
    report = validate_rows(rows)
    assert report.codes()["table_field_varies"] == 1


def test_a_monetary_unit_without_a_declared_rouble_is_rejected():
    rows = [_base_row(unit="million rubles", currency_basis="not_monetary")]
    report = validate_rows(rows)
    assert report.codes()["currency_basis_missing"] == 1
    assert not report.ok


def test_a_rouble_basis_on_a_physical_unit_is_only_a_warning():
    rows = [_base_row(unit="thousand tonnes", currency_basis="new_roubles")]
    report = validate_rows(rows)
    assert report.codes()["currency_basis_unexpected"] == 1
    assert report.ok, "the monetary-unit test is a heuristic and must not reject on its own"


def test_new_roubles_before_the_1961_reform_must_be_explained():
    rows = [
        _base_row(
            period="1950",
            unit="million rubles",
            currency_basis="new_roubles",
            definition_note="",
        )
    ]
    report = validate_rows(rows)
    assert report.codes()["new_roubles_before_reform"] == 1


def test_a_declared_restatement_across_the_reform_is_accepted():
    rows = [
        _base_row(
            period="1950",
            unit="million rubles",
            currency_basis="new_roubles",
            definition_note="restated in post-1961 roubles by the compilers",
        )
    ]
    assert "new_roubles_before_reform" not in validate_rows(rows).codes()


def test_a_marker_cell_may_not_carry_a_value():
    rows = [_base_row(value_raw="-", value="0", confidence="nil_printed")]
    report = validate_rows(rows)
    assert report.codes()["value_present_without_number"] == 1


def test_a_confidence_of_clear_on_a_marker_cell_is_rejected():
    rows = [_base_row(value_raw="...", value="", confidence="clear")]
    report = validate_rows(rows)
    assert report.codes()["confidence_marker_mismatch"] == 1


def test_declared_plausible_bounds_are_enforced_when_supplied():
    rows = [_base_row(value_raw="11,1", value="11.1")]
    ok = validate_rows(rows, bounds={"thousand widgets": (0.0, 100.0)})
    bad = validate_rows(rows, bounds={"thousand widgets": (100.0, 200.0)})
    assert "out_of_bounds" not in ok.codes()
    assert bad.codes()["out_of_bounds"] == 1


def test_a_suspected_decimal_shift_is_flagged_as_a_warning_not_an_error():
    """A value ten times its own series median is the classic separator-read-as-decimal error."""
    rows = [
        _base_row(period=str(year), value_raw=raw, value=raw)
        for year, raw in (
            ("1981", "100"),
            ("1982", "102"),
            ("1983", "104"),
            ("1984", "1010"),
            ("1985", "106"),
        )
    ]
    report = validate_rows(rows)
    assert report.codes()["decimal_shift_suspected"] == 1
    assert report.ok, "a real order-of-magnitude jump must not be erased by the validator"


def test_an_empty_file_is_an_error_rather_than_a_silent_pass():
    report = validate_rows([])
    assert not report.ok
    assert report.codes()["empty_file"] == 1


def test_the_report_serialises_for_storage_beside_the_transcription(fixtures_dir):
    payload = validate_file(fixtures_dir / CORRUPT).to_dict()
    assert payload["ok"] is False
    assert payload["n_errors"] == len(validate_file(fixtures_dir / CORRUPT).errors)
    assert {"severity", "code", "message", "row", "field"} <= set(payload["issues"][0])


def test_reading_the_clean_fixture_yields_the_schema_columns(fixtures_dir):
    from gosplan.transcribe.schema import FIELD_NAMES

    rows = read_filled(fixtures_dir / CLEAN)
    assert tuple(rows[0]) == FIELD_NAMES

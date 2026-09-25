"""Template generation, the target queue, and reading a filled form back.

The property that matters most here is that a generated template's columns are exactly the
schema's columns. That is the whole mechanism by which a form cannot drift from what the
validator enforces, so it is asserted directly against the file on disk rather than against
the function's return value.
"""

from __future__ import annotations

import csv
import json

import pytest
from forensics_core.provenance.manifest import load_sources
from gosplan.transcribe.schema import FIELD_NAMES, REQUIRED_FIELDS
from gosplan.transcribe.targets import TARGETS, target_by_id
from gosplan.transcribe.templates import (
    EXTRA_VALUES_COLUMN,
    TEMPLATE_ENCODING,
    field_specs,
    read_filled,
    write_all_templates,
    write_template,
)
from gosplan.transcribe.validate import validate_file


def test_generated_csv_header_is_exactly_the_schema_columns(tmp_path):
    csv_path, _ = write_template(TARGETS[0], tmp_path, blank_rows=3)
    with csv_path.open(encoding=TEMPLATE_ENCODING, newline="") as fh:
        header = next(csv.reader(fh))
    assert tuple(header) == FIELD_NAMES


def test_generated_csv_prefills_only_the_source_id(tmp_path):
    target = TARGETS[0]
    csv_path, _ = write_template(target, tmp_path, blank_rows=2)
    with csv_path.open(encoding=TEMPLATE_ENCODING, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    for row in rows:
        assert row["source_id"] == target.source_id
        assert row["unit"] == "", "a pre-filled unit becomes an unchecked default"
        assert row["currency_basis"] == ""
        assert row["territorial_basis"] == ""
        assert row["transcriber"] == ""


def test_an_untouched_template_reads_back_as_no_rows(tmp_path):
    """A blank row carrying only the pre-filled source_id is not a transcription."""
    csv_path, _ = write_template(TARGETS[0], tmp_path, blank_rows=5)
    assert read_filled(csv_path) == []


def test_a_prefilled_transcriber_does_not_make_a_blank_row_look_used(tmp_path):
    csv_path, _ = write_template(TARGETS[0], tmp_path, blank_rows=4, transcriber="JD")
    assert read_filled(csv_path) == []


def test_only_the_rows_someone_typed_into_reach_the_validator(tmp_path, fixtures_dir):
    """A part-filled template validates as its filled rows, not as its blank ones."""
    filled = read_filled(fixtures_dir / "synthetic_transcription_clean.csv")[:3]
    path = tmp_path / "part_filled.csv"
    with path.open("w", encoding=TEMPLATE_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELD_NAMES), lineterminator="\n")
        writer.writeheader()
        for row in filled:
            writer.writerow({name: row.get(name, "") for name in FIELD_NAMES})
        for _ in range(20):
            writer.writerow({**dict.fromkeys(FIELD_NAMES, ""), "source_id": row["source_id"]})

    report = validate_file(path)
    assert report.n_rows == 3
    assert report.ok, [str(i) for i in report.errors]


def test_a_wholly_empty_row_is_dropped_on_read(tmp_path):
    path = tmp_path / "t.csv"
    with path.open("w", encoding=TEMPLATE_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELD_NAMES), lineterminator="\n")
        writer.writeheader()
        writer.writerow(dict.fromkeys(FIELD_NAMES, ""))
        writer.writerow({**dict.fromkeys(FIELD_NAMES, ""), "row_label": "Shop A"})
        writer.writerow(dict.fromkeys(FIELD_NAMES, ""))
    rows = read_filled(path)
    assert len(rows) == 1
    assert rows[0]["row_label"] == "Shop A"


def test_field_specification_covers_every_column_with_its_allowed_values(tmp_path):
    _, spec_path = write_template(TARGETS[0], tmp_path, blank_rows=1)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert tuple(spec["schema_columns"]) == FIELD_NAMES
    by_name = {f["name"]: f for f in spec["fields"]}
    assert tuple(by_name) == FIELD_NAMES
    assert set(by_name["currency_basis"]["allowed_values"]) == {
        "not_monetary",
        "old_roubles",
        "new_roubles",
        "foreign_currency",
    }
    assert by_name["unit"]["required"] is True
    assert by_name["value"]["required"] is False, "a nil-marked cell has no number to record"
    assert by_name["source_id"]["level"] == "table"
    assert by_name["value_raw"]["level"] == "cell"


def test_field_specs_agree_with_the_required_field_list():
    required = {f["name"] for f in field_specs() if f["required"]}
    assert required == set(REQUIRED_FIELDS)


def test_target_prompts_are_recorded_beside_the_form_not_inside_it(tmp_path):
    target = TARGETS[0]
    csv_path, spec_path = write_template(target, tmp_path, blank_rows=1)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["target"]["target_id"] == target.target_id
    assert spec["target"]["check_against_the_page"]["expected_unit"] == target.expected_unit
    body = csv_path.read_text(encoding=TEMPLATE_ENCODING)
    assert target.expected_unit not in body


def test_write_all_templates_emits_two_files_per_target(tmp_path):
    written = write_all_templates(tmp_path)
    assert len(written) == 2 * len(TARGETS)
    assert len({p.name for p in written}) == len(written)


# ------------------------------------------------------------------------- targets


def test_every_target_names_a_source_in_the_registry(sources_yaml):
    known = {s.id for s in load_sources(sources_yaml)}
    for target in TARGETS:
        assert target.source_id in known, f"{target.target_id} names an unregistered source"
        if target.cross_check_source_id:
            assert target.cross_check_source_id in known


def test_target_ids_and_priorities_are_unique():
    assert len({t.target_id for t in TARGETS}) == len(TARGETS)
    assert len({t.priority for t in TARGETS}) == len(TARGETS)


def test_a_target_that_nobody_has_opened_says_so():
    """The queue must not imply that a table has been located when it has not."""
    unconfirmed = [t for t in TARGETS if not t.confirmed_present]
    assert unconfirmed, "an all-confirmed queue would be a claim nobody checked"
    for target in unconfirmed:
        assert target.locator.strip(), f"{target.target_id} says where to look"


def test_the_highest_priority_target_is_one_that_has_been_seen():
    first = min(TARGETS, key=lambda t: t.priority)
    assert first.confirmed_present is True


def test_target_by_id_names_the_alternatives_when_it_fails():
    with pytest.raises(KeyError) as exc:
        target_by_id("no_such_target")
    assert TARGETS[0].target_id in str(exc.value)


# ------------------------------------------------------------------------- reading


def test_read_filled_reads_csv_and_json_identically(tmp_path, fixtures_dir):
    from_csv = read_filled(fixtures_dir / "synthetic_transcription_pair_a.csv")
    json_path = tmp_path / "same.json"
    json_path.write_text(json.dumps(from_csv), encoding="utf-8")
    assert read_filled(json_path) == from_csv


def test_a_row_longer_than_the_header_is_reported_not_silently_truncated(tmp_path, fixtures_dir):
    """Trailing surplus fields are exactly where csv.DictReader loses data quietly."""
    source = (fixtures_dir / "synthetic_transcription_clean.csv").read_text(
        encoding=TEMPLATE_ENCODING
    )
    header, first, *_ = source.splitlines()
    path = tmp_path / "too_long.csv"
    path.write_text(
        f"{header}\n{first},SOMETHING THE TRANSCRIBER ADDED\n", encoding=TEMPLATE_ENCODING
    )

    rows = read_filled(path)
    assert rows[0][EXTRA_VALUES_COLUMN] == "SOMETHING THE TRANSCRIBER ADDED"

    report = validate_file(path)
    assert report.codes()["row_too_long"] == 1
    assert not report.ok
    assert "SOMETHING THE TRANSCRIBER ADDED" in str(report.errors[0])
    assert report.codes()["unknown_column"] == 0, "the surplus is one error, not two"


def test_read_filled_strips_whitespace_but_does_not_clean_values(tmp_path):
    path = tmp_path / "t.csv"
    with path.open("w", encoding=TEMPLATE_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELD_NAMES), lineterminator="\n")
        writer.writeheader()
        row = dict.fromkeys(FIELD_NAMES, "")
        row["value_raw"] = "  1O,5  "
        writer.writerow(row)
    rows = read_filled(path)
    assert rows[0]["value_raw"] == "1O,5", "the reader must not fix what the validator reports"

"""Generate the blank forms a transcriber fills in, and read them back.

The columns of a template are :data:`gosplan.transcribe.schema.FIELD_NAMES`, which is itself
derived from the pydantic models rather than typed out. That is the whole point of generating
templates from code: if the schema gains a field, every template gains the column, and a
filled file whose header no longer matches is rejected by the validator instead of being
silently read with a column missing.

Two files are written per target:

``<target_id>.csv``
    UTF-8 with a byte-order mark, because these are opened in spreadsheet software on
    Windows and a BOM-less UTF-8 CSV renders Cyrillic as mojibake there, which is exactly how
    a transcription gets corrupted before anyone has typed a digit. Only ``source_id`` is
    pre-filled, and ``transcriber`` when the caller asks for it. Nothing else is: a
    pre-filled unit or currency basis is a default that a tired transcriber accepts, and the
    entire purpose of those columns is that somebody looked at the page and said what it
    was. Because those pre-filled columns are present in every blank row,
    :func:`read_filled` treats a row that holds nothing but them as one the transcriber
    never used and drops it; see :data:`PREFILLED_FIELDS`.
``<target_id>.fields.json``
    The field list with types, allowed values, requiredness and the target's own prompts.
    Machine-readable, so a spreadsheet validation or a data-entry form can be built from it,
    and so a filled file can be checked against the schema version it was generated from.

Templates are written wherever the caller asks. The conventional location is
``data/transcription/templates/`` and filled files go to ``data/transcription/filled/``;
neither directory is created by this repository, because nothing in ``data/`` that is not
provenance belongs in version control.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, get_args, get_origin

from gosplan.transcribe.schema import (
    CELL_FIELDS,
    FIELD_NAMES,
    REQUIRED_FIELDS,
    TABLE_FIELDS,
    TableIdentity,
    TranscribedCell,
)
from gosplan.transcribe.targets import TARGETS, TranscriptionTarget

__all__ = [
    "EXTRA_VALUES_COLUMN",
    "PREFILLED_FIELDS",
    "TEMPLATE_ENCODING",
    "FieldSpec",
    "field_specs",
    "read_filled",
    "row_was_used",
    "write_all_templates",
    "write_template",
]

#: UTF-8 with a BOM. See the module docstring: this is a data-integrity choice, not a style
#: preference.
TEMPLATE_ENCODING = "utf-8-sig"

#: Blank rows written into a fresh template. Enough to start typing; the transcriber adds
#: rows as the table requires.
DEFAULT_BLANK_ROWS = 20

#: The columns :func:`write_template` is allowed to pre-fill in a blank row. A row whose
#: only non-empty columns are these carries nothing anybody typed off a page, so
#: :func:`read_filled` drops it. Without this the "wholly empty row" rule could never fire on
#: a generated template, and an untouched blank row would reach the validator as a data row
#: missing every required field.
PREFILLED_FIELDS: frozenset[str] = frozenset({"source_id", "transcriber"})

#: Key under which :func:`read_filled` parks any values a CSV row carries past the last
#: header column, joined with `` | ``. It is not a schema column: the validator reports it as
#: a ``row_too_long`` error rather than letting the surplus disappear.
EXTRA_VALUES_COLUMN = "__extra__"


class FieldSpec(dict):
    """One column's specification, as a plain dict so it serialises without ceremony."""


def _type_name(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is not None:
        inner = [a for a in get_args(annotation) if a is not type(None)]
        name = "|".join(_type_name(a) for a in inner)
        return f"{name} or blank" if type(None) in get_args(annotation) else name
    return getattr(annotation, "__name__", str(annotation))


def _allowed_values(annotation: Any) -> list[str] | None:
    candidates = [annotation, *(get_args(annotation) or ())]
    for cand in candidates:
        members = getattr(cand, "__members__", None)
        if members:
            return [str(m.value) for m in members.values()]
    return None


def field_specs() -> list[FieldSpec]:
    """Describe every template column: level, type, allowed values, requiredness, purpose.

    Read straight off the pydantic models, so this cannot drift from what the validator
    enforces.

    Returns
    -------
    list of FieldSpec
        One entry per column of :data:`~gosplan.transcribe.schema.FIELD_NAMES`, in order.
    """
    out: list[FieldSpec] = []
    for model, level, names in (
        (TableIdentity, "table", TABLE_FIELDS),
        (TranscribedCell, "cell", CELL_FIELDS),
    ):
        for name in names:
            info = model.model_fields[name]
            out.append(
                FieldSpec(
                    name=name,
                    level=level,
                    type=_type_name(info.annotation),
                    allowed_values=_allowed_values(info.annotation),
                    required=name in REQUIRED_FIELDS,
                    description=info.description or "",
                )
            )
    return out


def _target_prompts(target: TranscriptionTarget) -> dict[str, Any]:
    """The target's expectations, kept out of the CSV and recorded beside it.

    These are prompts to check against the printed page. They are deliberately not written
    into the spreadsheet: a hint sitting in a cell becomes an answer.
    """
    return {
        "target_id": target.target_id,
        "source_id": target.source_id,
        "priority": target.priority,
        "title_translit": target.title_translit,
        "why": target.why,
        "locator": target.locator,
        "confirmed_present": target.confirmed_present,
        "cross_check_source_id": target.cross_check_source_id,
        "check_against_the_page": {
            "expected_unit": target.expected_unit,
            "expected_currency_basis": str(target.expected_currency_basis),
            "expected_territorial_basis": str(target.expected_territorial_basis),
        },
        "notes": target.notes,
    }


def write_template(
    target: TranscriptionTarget,
    dest_dir: Path,
    *,
    blank_rows: int = DEFAULT_BLANK_ROWS,
    transcriber: str = "",
) -> tuple[Path, Path]:
    """Write the CSV form and its field specification for one target.

    Parameters
    ----------
    target : TranscriptionTarget
        The table to be transcribed.
    dest_dir : Path
        Directory to write into; created if missing.
    blank_rows : int, default 20
        How many empty rows to leave. Purely a convenience.
    transcriber : str, optional
        Pre-fill the transcriber column. Left blank by default so that an unattributed
        transcription fails validation rather than being credited to whoever ran the script.

    Returns
    -------
    (Path, Path)
        The CSV path and the field-specification path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dest_dir / f"{target.target_id}.csv"
    spec_path = dest_dir / f"{target.target_id}.fields.json"

    prefill = {"source_id": target.source_id, "transcriber": transcriber}
    with csv_path.open("w", encoding=TEMPLATE_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELD_NAMES), lineterminator="\n")
        writer.writeheader()
        for _ in range(max(0, blank_rows)):
            writer.writerow({name: prefill.get(name, "") for name in FIELD_NAMES})

    spec = {
        "schema_columns": list(FIELD_NAMES),
        "fields": field_specs(),
        "target": _target_prompts(target),
    }
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return csv_path, spec_path


def write_all_templates(
    dest_dir: Path,
    targets: Sequence[TranscriptionTarget] = TARGETS,
    *,
    blank_rows: int = DEFAULT_BLANK_ROWS,
    transcriber: str = "",
) -> list[Path]:
    """Write a template pair for every target, in priority order."""
    written: list[Path] = []
    for target in sorted(targets, key=lambda t: (t.priority, t.target_id)):
        written.extend(
            write_template(target, dest_dir, blank_rows=blank_rows, transcriber=transcriber)
        )
    return written


def read_filled(path: Path) -> list[dict[str, str]]:
    """Read a filled template, CSV or JSON, as a list of string-valued rows.

    No coercion and no cleaning happen here beyond stripping surrounding whitespace: a
    template is read exactly as typed so that the validator sees what the transcriber wrote,
    including the mistakes it exists to catch.

    Rows the transcriber never used are dropped: a template ships with blank rows and nobody
    deletes the ones they did not need. "Never used" means every non-empty column is one of
    :data:`PREFILLED_FIELDS`, not merely that the row is wholly empty, because a generated
    template writes ``source_id`` into every blank row and a wholly-empty test would
    therefore never fire on one.

    Values a CSV row carries past the last header column are **not** discarded. They are
    collected under :data:`EXTRA_VALUES_COLUMN` so that the validator can reject the file:
    a row longer than the header means the template was edited into a different shape, and
    silently dropping the surplus would let that pass as clean.

    Parameters
    ----------
    path : Path
        ``.csv`` (read as UTF-8 with an optional byte-order mark) or ``.json`` (a list of
        objects).

    Returns
    -------
    list of dict
        One dict per used row. Missing columns are absent rather than filled in, so the
        validator can report them.
    """
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows_in: Iterable[Any] = payload if isinstance(payload, list) else []
        rows = [_normalise_row(row) for row in rows_in if isinstance(row, dict)]
    else:
        with path.open("r", encoding=TEMPLATE_ENCODING, newline="") as fh:
            reader = csv.DictReader(fh, restkey=EXTRA_VALUES_COLUMN)
            rows = [_normalise_row(row) for row in reader]
    return [row for row in rows if row_was_used(row)]


def _normalise_row(row: Mapping[Any, Any]) -> dict[str, str]:
    """One raw row as strings, with any surplus CSV fields kept under one key."""
    out: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        if isinstance(value, list):
            out[str(key)] = " | ".join("" if v is None else str(v).strip() for v in value)
        else:
            out[str(key)] = "" if value is None else str(value).strip()
    return out


def row_was_used(row: Mapping[str, str]) -> bool:
    """True when a row holds something beyond the columns a template pre-fills.

    Examples
    --------
    >>> row_was_used({"source_id": "ia_narkhoz_1985_item", "row_label": ""})
    False
    >>> row_was_used({"source_id": "ia_narkhoz_1985_item", "row_label": "Uzbek SSR"})
    True
    """
    return any(str(value).strip() for key, value in row.items() if key not in PREFILLED_FIELDS)

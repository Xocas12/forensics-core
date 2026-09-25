"""Turning printed Soviet statistical tables into checked, provenanced, machine-readable data.

This package is the project's central deliverable, and it exists because of a finding rather
than a preference. The registry records that the optical character recognition bundled with
the archive.org scans of *Narodnoe khoziaistvo SSSR* fails on numeric tables: the cover title
of the 1985 volume came out garbled, and rows of figures arrive with their column separators
merged or dropped, so row and column alignment is gone. There is no machine-readable
transcription of these annuals on Zenodo, GitHub or Harvard Dataverse. The series this
project needs therefore has to be created, by people, from page images -- and the difference
between a transcription that can carry a forensic claim and one that cannot is entirely in
the checking.

Four pieces, in the order they are used:

:mod:`~gosplan.transcribe.schema`
    What a transcribed cell is: the value, and every field needed to know what it means --
    which rouble, which territory, which definition, which page, who typed it, and how
    confident they were. Plus the parser for printed Soviet numbers, which use a decimal
    comma, spaced digit groups, and conventional marks that are not zeros.
:mod:`~gosplan.transcribe.targets`
    Which tables to transcribe, in priority order, each tied to a ``SOURCES.yaml`` id and
    each honest about whether anyone has actually seen it.
:mod:`~gosplan.transcribe.templates`
    The blank forms, generated from the schema so their columns cannot drift, and the reader
    that brings a filled form back.
:mod:`~gosplan.transcribe.validate` and :mod:`~gosplan.transcribe.compare`
    The two gates. The validator checks one file against the schema, the traps and the
    table's own printed totals. The comparator checks one transcription against a second,
    independent one, and reports the per-cell and per-digit-position disagreement rate that
    ``docs/known_traps.md`` requires before any digit test may be run.

Command line::

    python -m gosplan.transcribe targets
    python -m gosplan.transcribe template --out data/transcription/templates
    python -m gosplan.transcribe validate <filled.csv>
    python -m gosplan.transcribe compare <a.csv> <b.csv>
"""

from gosplan.transcribe.compare import (
    ComparisonReport,
    compare_files,
    compare_transcriptions,
    digit_tests_permitted,
)
from gosplan.transcribe.schema import (
    FIELD_NAMES,
    CurrencyBasis,
    TableIdentity,
    TerritorialBasis,
    TranscribedCell,
    TranscribedTable,
    parse_printed_number,
)
from gosplan.transcribe.targets import TARGETS, TranscriptionTarget, target_by_id
from gosplan.transcribe.templates import read_filled, write_all_templates, write_template
from gosplan.transcribe.validate import Issue, ValidationReport, validate_file, validate_rows

__all__ = [
    "FIELD_NAMES",
    "TARGETS",
    "ComparisonReport",
    "CurrencyBasis",
    "Issue",
    "TableIdentity",
    "TerritorialBasis",
    "TranscribedCell",
    "TranscribedTable",
    "TranscriptionTarget",
    "ValidationReport",
    "compare_files",
    "compare_transcriptions",
    "digit_tests_permitted",
    "parse_printed_number",
    "read_filled",
    "target_by_id",
    "validate_file",
    "validate_rows",
    "write_all_templates",
    "write_template",
]

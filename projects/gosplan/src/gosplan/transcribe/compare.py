"""Double transcription: measure how often two independent readings of a table disagree.

``docs/known_traps.md``, trap 9, states the rule this module exists to enforce: *digit tests
on badly transcribed tables detect the transcription*. The bundled optical character
recognition of the Soviet annuals is known to be bad on numeric columns, and a human typing
from a page image has an error rate too -- smaller, but unknown until it is measured. A
first-digit or first-two-digit test consumes exactly the quantity that transcription error
corrupts, so running one on a table whose error rate nobody has measured produces a number
that cannot be interpreted in either direction: conformity might be real or might be error
washing out a real signal, and non-conformity might be padding or might be typing.

So: two people (or one person twice, blind to the first pass, or a person against an
independent existing transcription such as the Hokkaido SRC series) transcribe the same
table, and this module reports how far apart they are -- per cell and, because that is what a
digit test consumes, **per digit position**.

Two rates are reported and they are not the same thing.

*Cell disagreement rate* is the share of jointly transcribed cells whose printed form was
read differently at all. It is the honest headline number for "how reliable is this table".

*Digit disagreement rate*, per position, is what bears on a digit test. A pair of readings
can disagree on 2 percent of cells while disagreeing on 0.4 percent of digits, and it is the
second figure that says whether a first-digit test is measuring anything.

Alignment is from the most significant digit by default, because that is the position a
Benford-type test reads. Where two readings differ in length -- one dropped a digit -- every
position past the shorter string counts as compared and disagreeing, which is the
conservative treatment: a dropped digit shifts every subsequent position, and pretending
otherwise would understate the damage.

No threshold is built in. There is no published standard for an acceptable transcription
error rate in this setting, and inventing one here would be exactly the kind of borrowed
number this programme refuses. :func:`digit_tests_permitted` therefore takes the threshold as
a required argument, so that whoever runs a digit test has to write down what they consider
acceptable and defend it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from gosplan.transcribe.schema import TABLE_FIELDS, parse_printed_number
from gosplan.transcribe.templates import read_filled
from gosplan.transcribe.validate import cell_key

__all__ = [
    "CellDisagreement",
    "ComparisonReport",
    "DigitPositionStats",
    "compare_files",
    "compare_transcriptions",
    "digit_disagreements",
    "digit_tests_permitted",
]

Alignment = Literal["leading", "trailing"]


def digit_disagreements(digits_a: str, digits_b: str, align: Alignment = "leading") -> int:
    """Count positions at which two digit strings differ.

    Compared over ``max(len(a), len(b))`` positions: a position present in one string and not
    the other counts as a disagreement, because a dropped or added digit displaces everything
    after it.

    Parameters
    ----------
    digits_a, digits_b : str
        Significant digits, separators and decimal marks already removed (this is what
        :attr:`gosplan.transcribe.schema.ParsedNumber.digits` holds).
    align : {"leading", "trailing"}, default "leading"
        Which end to index from. ``leading`` matches how a first-digit or first-two-digits
        test reads a number; ``trailing`` matches a terminal-digit test.

    Returns
    -------
    int
        Number of differing positions.

    Examples
    --------
    >>> digit_disagreements("9221", "9231")
    1
    >>> digit_disagreements("1234", "234")
    4
    >>> digit_disagreements("1234", "234", align="trailing")
    1
    """
    width = max(len(digits_a), len(digits_b))
    if width == 0:
        return 0
    if align == "leading":
        a = digits_a.ljust(width, "\0")
        b = digits_b.ljust(width, "\0")
    else:
        a = digits_a.rjust(width, "\0")
        b = digits_b.rjust(width, "\0")
    return sum(1 for x, y in zip(a, b, strict=True) if x != y)


@dataclass(frozen=True)
class CellDisagreement:
    """One cell the two transcriptions did not agree on."""

    key: tuple[str, str, str]
    kind: Literal["raw_text", "missing_in_a", "missing_in_b"]
    raw_a: str
    raw_b: str
    value_a: float | None
    value_b: float | None
    digits_a: str
    digits_b: str
    n_digit_positions: int
    n_digit_disagreements: int
    row_a: int | None = None
    row_b: int | None = None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.key}: {self.raw_a!r} vs {self.raw_b!r} "
            f"({self.n_digit_disagreements}/{self.n_digit_positions} digit positions)"
        )


@dataclass(frozen=True)
class DigitPositionStats:
    """Disagreement count at one digit position, across every jointly transcribed cell."""

    position: int
    n_compared: int
    n_disagreements: int

    @property
    def rate(self) -> float:
        """Disagreements divided by comparisons; 0.0 when nothing was compared."""
        return self.n_disagreements / self.n_compared if self.n_compared else 0.0


@dataclass(frozen=True)
class ComparisonReport:
    """The result of comparing two transcriptions of the same printed table."""

    name_a: str
    name_b: str
    align: Alignment
    n_rows_a: int
    n_rows_b: int
    n_common: int
    n_cell_disagreements: int
    n_digits_compared: int
    n_digit_disagreements: int
    by_position: tuple[DigitPositionStats, ...] = field(default_factory=tuple)
    disagreements: tuple[CellDisagreement, ...] = field(default_factory=tuple)
    keys_only_in_a: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    keys_only_in_b: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    identity_differences: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    @property
    def cell_disagreement_rate(self) -> float:
        """Share of jointly transcribed cells read differently. 0.0 when nothing is common."""
        return self.n_cell_disagreements / self.n_common if self.n_common else 0.0

    @property
    def digit_disagreement_rate(self) -> float:
        """Share of compared digit positions that differ."""
        return (
            self.n_digit_disagreements / self.n_digits_compared if self.n_digits_compared else 0.0
        )

    @property
    def same_table(self) -> bool:
        """True when both files claim the same printed table and cover the same cells."""
        return not self.identity_differences and not self.keys_only_in_a and not self.keys_only_in_b

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form, suitable for storing beside the transcription as provenance."""
        return {
            "name_a": self.name_a,
            "name_b": self.name_b,
            "align": self.align,
            "n_rows_a": self.n_rows_a,
            "n_rows_b": self.n_rows_b,
            "n_common": self.n_common,
            "n_cell_disagreements": self.n_cell_disagreements,
            "cell_disagreement_rate": self.cell_disagreement_rate,
            "n_digits_compared": self.n_digits_compared,
            "n_digit_disagreements": self.n_digit_disagreements,
            "digit_disagreement_rate": self.digit_disagreement_rate,
            "by_position": [
                {
                    "position": p.position,
                    "n_compared": p.n_compared,
                    "n_disagreements": p.n_disagreements,
                    "rate": p.rate,
                }
                for p in self.by_position
            ],
            "keys_only_in_a": [list(k) for k in self.keys_only_in_a],
            "keys_only_in_b": [list(k) for k in self.keys_only_in_b],
            "identity_differences": [list(d) for d in self.identity_differences],
            "disagreements": [
                {
                    "key": list(d.key),
                    "kind": d.kind,
                    "raw_a": d.raw_a,
                    "raw_b": d.raw_b,
                    "n_digit_positions": d.n_digit_positions,
                    "n_digit_disagreements": d.n_digit_disagreements,
                }
                for d in self.disagreements
            ],
        }

    def summary(self) -> str:
        """One line with both rates and the coverage of the comparison."""
        return (
            f"{self.name_a} vs {self.name_b}: {self.n_common} common cells, "
            f"{self.n_cell_disagreements} disagree "
            f"({self.cell_disagreement_rate:.3%}); "
            f"{self.n_digit_disagreements}/{self.n_digits_compared} digit positions "
            f"({self.digit_disagreement_rate:.3%})"
        )


def _index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], tuple[int, Mapping]]:
    out: dict[tuple[str, str, str], tuple[int, Mapping]] = {}
    for i, row in enumerate(rows, start=1):
        out.setdefault(cell_key(row), (i, row))
    return out


def compare_transcriptions(
    rows_a: Sequence[Mapping[str, Any]],
    rows_b: Sequence[Mapping[str, Any]],
    *,
    name_a: str = "a",
    name_b: str = "b",
    align: Alignment = "leading",
) -> ComparisonReport:
    """Compare two independent transcriptions of one printed table.

    Cells are matched on ``(row_label, column_label, period)``. Where a key appears twice in
    one file the first occurrence is used and the duplicate is left for
    :func:`gosplan.transcribe.validate.validate_rows` to report; validate both files before
    comparing them.

    A cell counts as a disagreement when the two ``value_raw`` strings differ after stripping
    surrounding whitespace. That is stricter than comparing parsed values on purpose: two
    readings that parse to the same number but were typed differently -- ``1 234`` against
    ``1234`` -- agree on the figure, but the difference says the transcribers were not
    following the same convention, and that is worth seeing before it turns into a real
    disagreement somewhere else.

    Parameters
    ----------
    rows_a, rows_b : sequence of mapping
        Filled template rows, as :func:`gosplan.transcribe.templates.read_filled` returns.
    name_a, name_b : str
        Labels for the report.
    align : {"leading", "trailing"}, default "leading"
        Digit alignment; see :func:`digit_disagreements`.

    Returns
    -------
    ComparisonReport
        Per-cell and per-digit-position disagreement counts and rates, the cells that
        disagree, the keys present in only one file, and any table-level field on which the
        two files describe different tables.
    """
    index_a = _index(rows_a)
    index_b = _index(rows_b)
    common = sorted(set(index_a) & set(index_b))

    identity_differences: list[tuple[str, str, str]] = []
    for name in TABLE_FIELDS:
        values_a = {str(r.get(name, "")).strip() for r in rows_a} - {""}
        values_b = {str(r.get(name, "")).strip() for r in rows_b} - {""}
        if len(values_a) == 1 and len(values_b) == 1 and values_a != values_b:
            if name not in {"transcriber", "transcription_date"}:
                identity_differences.append((name, values_a.pop(), values_b.pop()))

    disagreements: list[CellDisagreement] = []
    position_compared: dict[int, int] = {}
    position_bad: dict[int, int] = {}
    n_digits_compared = 0
    n_digit_disagreements = 0

    for key in common:
        row_a_no, row_a = index_a[key]
        row_b_no, row_b = index_b[key]
        raw_a = str(row_a.get("value_raw", "") or "").strip()
        raw_b = str(row_b.get("value_raw", "") or "").strip()
        pa = parse_printed_number(raw_a)
        pb = parse_printed_number(raw_b)

        width = max(len(pa.digits), len(pb.digits))
        n_bad = digit_disagreements(pa.digits, pb.digits, align)
        n_digits_compared += width
        n_digit_disagreements += n_bad
        for offset in range(width):
            if align == "leading":
                position = offset + 1
                char_a = pa.digits[offset] if offset < len(pa.digits) else None
                char_b = pb.digits[offset] if offset < len(pb.digits) else None
            else:
                position = offset + 1
                char_a = pa.digits[-1 - offset] if offset < len(pa.digits) else None
                char_b = pb.digits[-1 - offset] if offset < len(pb.digits) else None
            position_compared[position] = position_compared.get(position, 0) + 1
            if char_a != char_b:
                position_bad[position] = position_bad.get(position, 0) + 1

        if raw_a != raw_b:
            disagreements.append(
                CellDisagreement(
                    key=key,
                    kind="raw_text",
                    raw_a=raw_a,
                    raw_b=raw_b,
                    value_a=pa.value,
                    value_b=pb.value,
                    digits_a=pa.digits,
                    digits_b=pb.digits,
                    n_digit_positions=width,
                    n_digit_disagreements=n_bad,
                    row_a=row_a_no,
                    row_b=row_b_no,
                )
            )

    only_a = tuple(sorted(set(index_a) - set(index_b)))
    only_b = tuple(sorted(set(index_b) - set(index_a)))
    for key in only_a:
        row_no, row = index_a[key]
        disagreements.append(
            CellDisagreement(
                key,
                "missing_in_b",
                str(row.get("value_raw", "")),
                "",
                None,
                None,
                "",
                "",
                0,
                0,
                row_a=row_no,
            )
        )
    for key in only_b:
        row_no, row = index_b[key]
        disagreements.append(
            CellDisagreement(
                key,
                "missing_in_a",
                "",
                str(row.get("value_raw", "")),
                None,
                None,
                "",
                "",
                0,
                0,
                row_b=row_no,
            )
        )

    by_position = tuple(
        DigitPositionStats(p, position_compared[p], position_bad.get(p, 0))
        for p in sorted(position_compared)
    )
    n_cell_disagreements = sum(1 for d in disagreements if d.kind == "raw_text")

    return ComparisonReport(
        name_a=name_a,
        name_b=name_b,
        align=align,
        n_rows_a=len(rows_a),
        n_rows_b=len(rows_b),
        n_common=len(common),
        n_cell_disagreements=n_cell_disagreements,
        n_digits_compared=n_digits_compared,
        n_digit_disagreements=n_digit_disagreements,
        by_position=by_position,
        disagreements=tuple(disagreements),
        keys_only_in_a=only_a,
        keys_only_in_b=only_b,
        identity_differences=tuple(identity_differences),
    )


def compare_files(path_a: Path, path_b: Path, *, align: Alignment = "leading") -> ComparisonReport:
    """Read two filled templates from disk and compare them."""
    return compare_transcriptions(
        read_filled(path_a),
        read_filled(path_b),
        name_a=path_a.name,
        name_b=path_b.name,
        align=align,
    )


def digit_tests_permitted(
    report: ComparisonReport,
    *,
    max_digit_disagreement_rate: float,
    require_full_coverage: bool = True,
) -> bool:
    """Whether a digit test may be run on the table this report describes.

    Parameters
    ----------
    report : ComparisonReport
        The double-transcription comparison for the table.
    max_digit_disagreement_rate : float
        The threshold, which the caller must choose and state. There is no default because
        there is no published standard for this; whatever is used has to be defended in
        writing next to the result.
    require_full_coverage : bool, default True
        Also require that the two transcriptions describe the same table and cover the same
        cells. A rate computed over half a table says nothing about the other half.

    Returns
    -------
    bool
        True when the measured digit disagreement rate is at or below the threshold and, if
        required, the coverage is complete.

    Raises
    ------
    ValueError
        If the threshold is not in [0, 1], or if nothing was compared, since an empty
        comparison has a rate of zero and would otherwise pass every threshold.
    """
    if not 0.0 <= max_digit_disagreement_rate <= 1.0:
        raise ValueError("max_digit_disagreement_rate must lie in [0, 1]")
    if report.n_digits_compared == 0:
        raise ValueError(
            "no digit positions were compared; a rate of zero here means no evidence, not agreement"
        )
    if require_full_coverage and not report.same_table:
        return False
    return report.digit_disagreement_rate <= max_digit_disagreement_rate

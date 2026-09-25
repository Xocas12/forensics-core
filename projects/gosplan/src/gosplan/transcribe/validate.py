"""Checks that run on a filled transcription template before it is allowed near an analysis.

The premise is that a transcribed table is guilty until checked. Typing digits off a scanned
Russian page produces a specific and well-understood family of errors -- a decimal comma read
as a thousands separator, a digit dropped from a five-figure number, a row read off the line
above, a units column left at whatever the previous table used -- and every one of them
survives into a float column looking exactly like data.

The checks divide into four kinds.

**Structural.** The header must be exactly the schema's columns; no row may carry values
past the last header column; required fields must be present; enumerations must hold
declared members; the table-level fields must not vary within one file. These catch a
template edited into a different shape.

**Semantic.** A monetary unit must declare which rouble. A table touching 1939 or 1940 must
declare its territorial basis. A cell whose confidence says a number was read must contain
one, and a cell printed with a conventional mark must not. These catch the traps in
``docs/known_traps.md`` at the point where a person can still go back and look at the page.

**Arithmetic.** Where the printed table carries totals, the total must equal the sum of its
addends to within the tolerance that rounding permits, computed from the number of addends
and the number of printed decimals rather than from a guessed epsilon. This is the strongest
check available, because it uses information the printer put on the page.

**Distributional.** Values wildly out of line with their own series are flagged as suspected
decimal shifts. This is the only check that can fire on a correct transcription, so it is a
warning: a real order-of-magnitude jump in a Soviet series is interesting, and the validator
must not be able to erase it.

Errors mean the file must not be used. Warnings mean a person must look and then either fix
the cell or record why it is right.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from gosplan.transcribe.schema import (
    FIELD_NAMES,
    NUMERIC_CONFIDENCE,
    REQUIRED_FIELDS,
    TABLE_FIELDS,
    CellRole,
    Confidence,
    CurrencyBasis,
    TerritorialBasis,
    parse_printed_number,
)
from gosplan.transcribe.templates import EXTRA_VALUES_COLUMN, read_filled

__all__ = [
    "MONETARY_UNIT_PATTERN",
    "Issue",
    "ValidationReport",
    "cell_key",
    "rounding_tolerance",
    "validate_file",
    "validate_rows",
]

Severity = Literal["error", "warning"]

#: Heuristic for "this unit is money". Deliberately broad and deliberately advisory: a unit
#: that matches must declare a currency basis (an error), while a unit that does not match
#: but declares one only earns a warning, because no regular expression knows every way a
#: Soviet table names a monetary unit.
MONETARY_UNIT_PATTERN = re.compile(r"rub|roubl|rubl|kopeck|kopeik|kop\.", re.IGNORECASE)

#: The year the rouble was redenominated 10:1.
CURRENCY_REFORM_YEAR = 1961

#: Years whose territorial basis is never safe to leave unstated.
BOUNDARY_CHANGE_YEARS = (1939, 1940)

#: Ratios treated as a suspected misplaced decimal mark, and the relative slack allowed
#: around each when comparing a value against its own series median.
_DECIMAL_SHIFT_RATIOS = (0.01, 0.1, 10.0, 100.0)
_DECIMAL_SHIFT_SLACK = 0.05
_DECIMAL_SHIFT_MIN_SERIES = 4

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PERIOD_RE = re.compile(r"^(\d{4})(?:-(\d{4})|/(\d{2}))?$")


@dataclass(frozen=True)
class Issue:
    """One problem found in a filled template.

    Attributes
    ----------
    severity : {"error", "warning"}
        ``error`` means do not use the file.
    code : str
        Stable machine-readable identifier, so a test or a script can assert on the kind of
        problem rather than on wording.
    message : str
        What is wrong, with the offending values quoted.
    row : int or None
        1-based data row (the header is not counted). None for whole-file problems.
    field : str or None
        Column the problem sits in, when it sits in one.
    """

    severity: Severity
    code: str
    message: str
    row: int | None = None
    field: str | None = None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        where = f"row {self.row}" if self.row is not None else "file"
        col = f".{self.field}" if self.field else ""
        return f"[{self.severity}] {self.code} ({where}{col}): {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """The outcome of validating one filled template."""

    name: str
    n_rows: int
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[Issue, ...]:
        """Issues that make the file unusable."""
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> tuple[Issue, ...]:
        """Issues a person must look at but which do not by themselves reject the file."""
        return tuple(i for i in self.issues if i.severity == "warning")

    @property
    def ok(self) -> bool:
        """True when there are no errors. Warnings do not make a file invalid."""
        return not self.errors

    def codes(self) -> Counter[str]:
        """Count of issues by code, for tests and for a one-line summary."""
        return Counter(i.code for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form."""
        return {
            "name": self.name,
            "n_rows": self.n_rows,
            "ok": self.ok,
            "n_errors": len(self.errors),
            "n_warnings": len(self.warnings),
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "row": i.row,
                    "field": i.field,
                }
                for i in self.issues
            ],
        }

    def summary(self) -> str:
        """One line: name, rows, and counts by severity."""
        verdict = "PASS" if self.ok else "FAIL"
        return (
            f"{verdict} {self.name}: {self.n_rows} rows, "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


def rounding_tolerance(n_addends: int, decimals: int) -> float:
    """How far a printed total may legitimately sit from the sum of its printed addends.

    Each printed figure is its true value rounded to ``decimals`` places, so it differs from
    the truth by at most ``0.5 * 10**-decimals``. Summing ``n`` printed addends accumulates at
    most ``n`` such errors, and the printed total carries one more. The bound is therefore
    ``(n + 1) * 0.5 * 10**-decimals``, which is exact under the assumption that the printer
    rounded rather than truncated -- a table that truncates needs twice this, and a table that
    prints a total computed from unrounded figures is already covered.

    Parameters
    ----------
    n_addends : int
        Number of printed addends contributing to the total.
    decimals : int
        Decimal places printed. Zero for whole numbers.

    Returns
    -------
    float
        The absolute tolerance.

    Examples
    --------
    >>> rounding_tolerance(3, 1)
    0.2
    >>> rounding_tolerance(4, 0)
    2.5
    """
    if n_addends < 0:
        raise ValueError("n_addends must be non-negative")
    if decimals < 0:
        raise ValueError("decimals must be non-negative")
    return (n_addends + 1) * 0.5 * 10.0 ** (-decimals)


def cell_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """The identity of a cell within one table: row label, column label, period."""
    return (
        str(row.get("row_label", "")).strip(),
        str(row.get("column_label", "")).strip(),
        str(row.get("period", "")).strip(),
    )


def _period_years(period: str) -> list[int]:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        return []
    start = int(m.group(1))
    if m.group(2):
        return [start, int(m.group(2))]
    if m.group(3):
        return [start, start + 1]
    return [start]


def _as_enum(value: str, enum_cls: type, field_name: str, row_no: int) -> tuple[Any, Issue | None]:
    text = (value or "").strip()
    try:
        return enum_cls(text), None
    except ValueError:
        allowed = ", ".join(str(m.value) for m in enum_cls)
        return None, Issue(
            "error",
            "bad_enum",
            f"{text!r} is not one of: {allowed}",
            row_no,
            field_name,
        )


def _check_header(rows: Sequence[Mapping[str, Any]], issues: list[Issue]) -> None:
    seen: set[str] = set()
    for row in rows:
        seen.update(row.keys())
    seen.discard(EXTRA_VALUES_COLUMN)  # reported per row by _check_row_length, not as a column
    expected = set(FIELD_NAMES)
    for missing in sorted(expected - seen):
        issues.append(
            Issue("error", "missing_column", f"template has no {missing!r} column", None, missing)
        )
    for extra in sorted(seen - expected):
        issues.append(
            Issue(
                "error",
                "unknown_column",
                f"{extra!r} is not a schema column; the template header has drifted",
                None,
                extra,
            )
        )


def _check_row_length(rows: Sequence[Mapping[str, Any]], issues: list[Issue]) -> None:
    """Report rows carrying values past the last header column.

    ``csv.DictReader`` has nowhere to put those values, and dropping them would let a file
    whose rows are wider than its header validate as clean while a transcribed value went
    missing. :func:`gosplan.transcribe.templates.read_filled` keeps them under
    :data:`~gosplan.transcribe.templates.EXTRA_VALUES_COLUMN` so they can be named here.
    """
    for i, row in enumerate(rows, start=1):
        surplus = str(row.get(EXTRA_VALUES_COLUMN, "") or "").strip()
        if surplus:
            issues.append(
                Issue(
                    "error",
                    "row_too_long",
                    f"row has more fields than the header; the surplus values are {surplus!r}",
                    i,
                )
            )


def _check_table_constancy(rows: Sequence[Mapping[str, Any]], issues: list[Issue]) -> None:
    for name in TABLE_FIELDS:
        values = {str(row.get(name, "")).strip() for row in rows}
        values.discard("")
        if len(values) > 1:
            shown = ", ".join(sorted(repr(v) for v in values)[:4])
            issues.append(
                Issue(
                    "error",
                    "table_field_varies",
                    f"{name!r} differs between rows ({shown}); one file is one printed table",
                    None,
                    name,
                )
            )


def _check_duplicates(rows: Sequence[Mapping[str, Any]], issues: list[Issue]) -> None:
    positions: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows, start=1):
        positions[cell_key(row)].append(i)
    for key, where in sorted(positions.items()):
        if len(where) > 1 and all(key):
            issues.append(
                Issue(
                    "error",
                    "duplicate_cell",
                    f"cell {key} transcribed {len(where)} times, at rows {where}",
                    where[-1],
                )
            )


def _check_currency(
    row_no: int,
    unit: str,
    basis: CurrencyBasis | None,
    edition_year: int | None,
    period: str,
    definition_note: str,
    issues: list[Issue],
) -> None:
    if basis is None:
        return
    looks_monetary = bool(MONETARY_UNIT_PATTERN.search(unit))
    if looks_monetary and basis is CurrencyBasis.NOT_MONETARY:
        issues.append(
            Issue(
                "error",
                "currency_basis_missing",
                f"unit {unit!r} looks monetary but currency_basis is {basis.value!r}; the 1961 "
                "redenomination makes an undeclared rouble series unusable",
                row_no,
                "currency_basis",
            )
        )
    if not looks_monetary and basis in {
        CurrencyBasis.OLD_ROUBLES,
        CurrencyBasis.NEW_ROUBLES,
        CurrencyBasis.FOREIGN_CURRENCY,
    }:
        issues.append(
            Issue(
                "warning",
                "currency_basis_unexpected",
                f"currency_basis {basis.value!r} declared for unit {unit!r}, which does not "
                "look monetary; confirm which of the two is wrong",
                row_no,
                "currency_basis",
            )
        )

    years = _period_years(period)
    note = definition_note.strip()
    if basis is CurrencyBasis.OLD_ROUBLES and years and min(years) >= CURRENCY_REFORM_YEAR:
        issues.append(
            Issue(
                "warning",
                "old_roubles_after_reform",
                f"period {period!r} is entirely after the {CURRENCY_REFORM_YEAR} reform but the "
                "cell is in old roubles; if the table really prints pre-reform units, say so in "
                "definition_note",
                row_no,
                "currency_basis",
            )
        )
    if (
        basis is CurrencyBasis.NEW_ROUBLES
        and years
        and max(years) < CURRENCY_REFORM_YEAR
        and not note
    ):
        issues.append(
            Issue(
                "warning",
                "new_roubles_before_reform",
                f"period {period!r} predates the {CURRENCY_REFORM_YEAR} reform and the cell is in "
                "new roubles, so the figure has been restated; record that in definition_note",
                row_no,
                "definition_note",
            )
        )
    if edition_year is not None and basis is CurrencyBasis.OLD_ROUBLES and not note:
        if edition_year > CURRENCY_REFORM_YEAR:
            issues.append(
                Issue(
                    "warning",
                    "old_roubles_late_edition",
                    f"a {edition_year} edition printing old roubles is unusual; note what the "
                    "table says about units",
                    row_no,
                    "definition_note",
                )
            )


def _check_totals(
    rows: Sequence[Mapping[str, Any]],
    parsed: Mapping[int, Any],
    roles: Mapping[int, tuple[CellRole | None, CellRole | None]],
    issues: list[Issue],
) -> None:
    """Check every printed total against the sum of the data cells in its group."""
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows, start=1):
        key = cell_key(row)
        groups[("column", key[1], key[2])].append(i)
        groups[("row", key[0], key[2])].append(i)

    for (axis, label, period), members in sorted(groups.items()):
        addends: list[int] = []
        totals: list[int] = []
        for i in members:
            row_role, col_role = roles.get(i, (None, None))
            if row_role is None or col_role is None:
                continue
            along, across = (row_role, col_role) if axis == "column" else (col_role, row_role)
            if across is not CellRole.DATA:
                continue
            if along is CellRole.DATA:
                addends.append(i)
            elif along is CellRole.TOTAL:
                totals.append(i)

        if not totals or not addends:
            continue

        numeric = [i for i in addends if getattr(parsed.get(i), "kind", "") == "number"]
        if len(numeric) != len(addends):
            issues.append(
                Issue(
                    "warning",
                    "total_unchecked",
                    f"{axis} total for {label!r} in {period!r} could not be checked: "
                    f"{len(addends) - len(numeric)} of {len(addends)} addends hold no number",
                    totals[0],
                )
            )
            continue

        decimals = max(parsed[i].decimals for i in numeric)
        total_sum = math.fsum(parsed[i].value for i in numeric)
        for t in totals:
            pt = parsed.get(t)
            if getattr(pt, "kind", "") != "number":
                continue
            decimals_here = max(decimals, pt.decimals)
            tol = rounding_tolerance(len(numeric), decimals_here)
            diff = abs(pt.value - total_sum)
            if diff > tol:
                issues.append(
                    Issue(
                        "error",
                        "total_mismatch",
                        f"{axis} total for {label!r} in {period!r}: printed {pt.value:g}, "
                        f"addends sum to {total_sum:g}, difference {diff:g} exceeds the "
                        f"rounding tolerance {tol:g} for {len(numeric)} addends at "
                        f"{decimals_here} decimal place(s)",
                        t,
                        "value_raw",
                    )
                )


def _check_decimal_shift(
    rows: Sequence[Mapping[str, Any]], parsed: Mapping[int, Any], issues: list[Issue]
) -> None:
    series: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows, start=1):
        if getattr(parsed.get(i), "kind", "") == "number":
            key = cell_key(row)
            series[(key[0], key[1])].append(i)

    for (row_label, column_label), members in sorted(series.items()):
        values = [abs(parsed[i].value) for i in members if parsed[i].value]
        if len(values) < _DECIMAL_SHIFT_MIN_SERIES:
            continue
        ordered = sorted(values)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
        if median <= 0:
            continue
        for i in members:
            v = abs(parsed[i].value)
            if v <= 0:
                continue
            ratio = v / median
            for target in _DECIMAL_SHIFT_RATIOS:
                if abs(ratio - target) <= _DECIMAL_SHIFT_SLACK * target:
                    issues.append(
                        Issue(
                            "warning",
                            "decimal_shift_suspected",
                            f"{parsed[i].value:g} is about {target:g} times the median "
                            f"{median:g} of series ({row_label!r}, {column_label!r}); check the "
                            "decimal mark and the thousands separator on the page",
                            i,
                            "value_raw",
                        )
                    )
                    break


def validate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    name: str = "transcription",
    bounds: Mapping[str, tuple[float, float]] | None = None,
) -> ValidationReport:
    """Run every check over the rows of one filled template.

    Parameters
    ----------
    rows : sequence of mapping
        As returned by :func:`gosplan.transcribe.templates.read_filled`: one dict per data
        row, values as strings exactly as typed.
    name : str, default "transcription"
        Label used in the report and its summary line.
    bounds : mapping, optional
        ``{unit: (low, high)}`` plausibility limits, matched on the unit string after
        stripping and case folding. Deliberately not defaulted: plausible bounds are a
        property of the series being transcribed, and a built-in table of them would be a
        set of numbers this project has no source for.

    Returns
    -------
    ValidationReport
        Errors and warnings, each with a stable code.
    """
    issues: list[Issue] = []
    if not rows:
        return ValidationReport(name, 0, (Issue("error", "empty_file", "no data rows"),))

    _check_header(rows, issues)
    _check_row_length(rows, issues)
    _check_table_constancy(rows, issues)
    _check_duplicates(rows, issues)

    limits = {k.strip().casefold(): v for k, v in (bounds or {}).items()}
    parsed: dict[int, Any] = {}
    roles: dict[int, tuple[CellRole | None, CellRole | None]] = {}

    for i, row in enumerate(rows, start=1):
        for name_ in REQUIRED_FIELDS:
            if not str(row.get(name_, "") or "").strip():
                issues.append(Issue("error", "missing_required", f"{name_!r} is blank", i, name_))

        edition_year: int | None = None
        for int_field, lo, hi in (("edition_year", 1900, 1995), ("page", 1, 10_000)):
            text = str(row.get(int_field, "") or "").strip()
            if not text:
                continue
            try:
                parsed_int = int(text)
            except ValueError:
                issues.append(
                    Issue("error", "bad_integer", f"{text!r} is not a whole number", i, int_field)
                )
                continue
            if not lo <= parsed_int <= hi:
                issues.append(
                    Issue(
                        "error",
                        "out_of_range",
                        f"{int_field} {parsed_int} is outside {lo}..{hi}",
                        i,
                        int_field,
                    )
                )
            elif int_field == "edition_year":
                edition_year = parsed_int

        date_text = str(row.get("transcription_date", "") or "").strip()
        if date_text and not _ISO_DATE_RE.match(date_text):
            issues.append(
                Issue(
                    "error",
                    "bad_date",
                    f"{date_text!r} is not an ISO date (YYYY-MM-DD)",
                    i,
                    "transcription_date",
                )
            )

        period = str(row.get("period", "") or "").strip()
        if period and not _PERIOD_RE.match(period):
            issues.append(
                Issue(
                    "error",
                    "bad_period",
                    f"{period!r} must be YYYY, YYYY-YYYY or YYYY/YY",
                    i,
                    "period",
                )
            )

        territorial, issue = _as_enum(
            str(row.get("territorial_basis", "")), TerritorialBasis, "territorial_basis", i
        )
        if issue:
            issues.append(issue)
        elif territorial is TerritorialBasis.UNSTATED:
            years = _period_years(period)
            touches_boundary_change = bool(years) and any(
                min(years) <= y <= max(years) for y in BOUNDARY_CHANGE_YEARS
            )
            issues.append(
                Issue(
                    "error" if touches_boundary_change else "warning",
                    "territorial_basis_unstated",
                    "territorial basis is unstated"
                    + (
                        f"; period {period!r} spans the 1939-40 boundary change, so pre-war and "
                        "post-war figures are not comparable without it"
                        if touches_boundary_change
                        else "; record what the table or its head note says"
                    ),
                    i,
                    "territorial_basis",
                )
            )

        basis, issue = _as_enum(
            str(row.get("currency_basis", "")), CurrencyBasis, "currency_basis", i
        )
        if issue:
            issues.append(issue)

        confidence, issue = _as_enum(str(row.get("confidence", "")), Confidence, "confidence", i)
        if issue:
            issues.append(issue)

        row_role, issue = _as_enum(str(row.get("row_role", "")), CellRole, "row_role", i)
        if issue:
            issues.append(issue)
        column_role, issue = _as_enum(str(row.get("column_role", "")), CellRole, "column_role", i)
        if issue:
            issues.append(issue)
        roles[i] = (row_role, column_role)

        unit = str(row.get("unit", "") or "").strip()
        _check_currency(
            i,
            unit,
            basis,
            edition_year,
            period,
            str(row.get("definition_note", "") or ""),
            issues,
        )

        raw = str(row.get("value_raw", "") or "")
        number = parse_printed_number(raw)
        parsed[i] = number

        if number.kind == "unparsable":
            issues.append(
                Issue(
                    "error",
                    "unparsable_value",
                    f"{raw!r} is neither a number nor a conventional mark; if the print is "
                    "unreadable, leave value blank and set confidence to illegible",
                    i,
                    "value_raw",
                )
            )

        if confidence is not None:
            if confidence in NUMERIC_CONFIDENCE and number.kind != "number":
                issues.append(
                    Issue(
                        "error",
                        "confidence_marker_mismatch",
                        f"confidence {confidence.value!r} says a number was read but value_raw "
                        f"{raw!r} parses as {number.kind!r}",
                        i,
                        "confidence",
                    )
                )
            if confidence is Confidence.NIL_PRINTED and number.kind != "nil":
                issues.append(
                    Issue(
                        "error",
                        "confidence_marker_mismatch",
                        f"confidence says a nil mark was printed but value_raw {raw!r} parses as "
                        f"{number.kind!r}",
                        i,
                        "confidence",
                    )
                )
            if confidence is Confidence.NO_DATA_PRINTED and number.kind != "no_data":
                issues.append(
                    Issue(
                        "error",
                        "confidence_marker_mismatch",
                        f"confidence says a no-data mark was printed but value_raw {raw!r} parses "
                        f"as {number.kind!r}",
                        i,
                        "confidence",
                    )
                )

        value_text = str(row.get("value", "") or "").strip()
        if number.kind == "number":
            if not value_text:
                issues.append(
                    Issue(
                        "error",
                        "value_missing",
                        f"value_raw {raw!r} holds a number but the value column is blank",
                        i,
                        "value",
                    )
                )
            else:
                try:
                    given = float(value_text)
                except ValueError:
                    issues.append(
                        Issue(
                            "error",
                            "value_not_numeric",
                            f"{value_text!r} is not a number",
                            i,
                            "value",
                        )
                    )
                else:
                    scale = max(1.0, abs(number.value))
                    if abs(given - number.value) > 1e-9 * scale:
                        issues.append(
                            Issue(
                                "error",
                                "value_mismatch",
                                f"value {given:g} does not match value_raw {raw!r}, which parses "
                                f"as {number.value:g}",
                                i,
                                "value",
                            )
                        )
                    if given < 0:
                        issues.append(
                            Issue(
                                "warning",
                                "negative_value",
                                f"{given:g} is negative; outside balance items a minus sign in a "
                                "printed Soviet table is unusual, so confirm it against the page",
                                i,
                                "value",
                            )
                        )
                    lo_hi = limits.get(unit.casefold())
                    if lo_hi and not lo_hi[0] <= given <= lo_hi[1]:
                        issues.append(
                            Issue(
                                "error",
                                "out_of_bounds",
                                f"{given:g} is outside the declared plausible range "
                                f"{lo_hi[0]:g}..{lo_hi[1]:g} for unit {unit!r}",
                                i,
                                "value",
                            )
                        )
        elif value_text:
            issues.append(
                Issue(
                    "error",
                    "value_present_without_number",
                    f"value {value_text!r} was entered but value_raw {raw!r} parses as "
                    f"{number.kind!r}; a mark is not a zero",
                    i,
                    "value",
                )
            )

    _check_totals(rows, parsed, roles, issues)
    _check_decimal_shift(rows, parsed, issues)

    ordered = sorted(issues, key=lambda x: (x.row if x.row is not None else 0, x.code))
    return ValidationReport(name, len(rows), tuple(ordered))


def validate_file(
    path: Path, *, bounds: Mapping[str, tuple[float, float]] | None = None
) -> ValidationReport:
    """Read a filled template from disk and validate it."""
    rows = read_filled(path)
    return validate_rows(rows, name=path.name, bounds=bounds)

"""Digit-based tests: Benford (first / second / first-two), terminal-digit uniformity, and
excess mass at integer percentages (Kobak, Shpilkin & Pshenichnikov)."""

from forensics_core.digits.benford import (
    MAD_BANDS,
    MAD_LABELS,
    POSITIONS,
    BenfordResult,
    DigitPosition,
    DigitTable,
    benford_expected,
    benford_test,
    digit_frequencies,
    digit_support,
    leading_digits,
)
from forensics_core.digits.integer_pct import (
    IntegerExcessResult,
    integer_excess,
    integer_excess_by_group,
    percentage,
    percentage_histogram,
)
from forensics_core.digits.terminal import (
    terminal_digit_pair_test,
    terminal_digit_test,
    terminal_digits,
)

__all__ = [
    "MAD_BANDS",
    "MAD_LABELS",
    "POSITIONS",
    "BenfordResult",
    "DigitPosition",
    "DigitTable",
    "IntegerExcessResult",
    "benford_expected",
    "benford_test",
    "digit_frequencies",
    "digit_support",
    "integer_excess",
    "integer_excess_by_group",
    "leading_digits",
    "percentage",
    "percentage_histogram",
    "terminal_digit_pair_test",
    "terminal_digit_test",
    "terminal_digits",
]

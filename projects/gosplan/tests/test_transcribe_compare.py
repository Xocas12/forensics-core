"""Double-transcription comparison.

The pair of fixtures was built with a known number of disagreements, worked out by hand
before the code was run:

* 3 rows x 4 periods = 12 cells, every value four digits long, so 12 x 4 = 48 digit
  positions are compared;
* three cells were read differently:

  ==================  ======  ======  ==================================================
  cell                A       B       digit positions that differ (aligned from the left)
  ==================  ======  ======  ==================================================
  Oblast 1, 1982      1222    1232    position 3
  Oblast 2, 1983      2333    333     positions 1 and 4 (a dropped leading digit shifts
                                      the string and leaves position 4 unmatched)
  Oblast 3, 1984      3444    3454    position 3
  ==================  ======  ======  ==================================================

so 4 digit positions of 48 differ, and the per-position counts are 1, 0, 2, 1.

Every one of those numbers is asserted exactly. The point of the tool is to produce a rate
that a person will use to decide whether a digit test is meaningful, and a tool that reports
an approximately right rate would be worse than none.
"""

from __future__ import annotations

import pytest
from gosplan.transcribe.compare import (
    compare_files,
    compare_transcriptions,
    digit_disagreements,
    digit_tests_permitted,
)
from gosplan.transcribe.templates import read_filled

PAIR_A = "synthetic_transcription_pair_a.csv"
PAIR_B = "synthetic_transcription_pair_b.csv"


@pytest.fixture
def report(fixtures_dir):
    return compare_files(fixtures_dir / PAIR_A, fixtures_dir / PAIR_B)


def test_the_known_cell_disagreement_rate_is_recovered_exactly(report):
    assert report.n_common == 12
    assert report.n_cell_disagreements == 3
    assert report.cell_disagreement_rate == pytest.approx(3 / 12)


def test_the_known_digit_disagreement_rate_is_recovered_exactly(report):
    assert report.n_digits_compared == 48
    assert report.n_digit_disagreements == 4
    assert report.digit_disagreement_rate == pytest.approx(4 / 48)


def test_the_per_position_breakdown_is_recovered_exactly(report):
    counts = {p.position: (p.n_compared, p.n_disagreements) for p in report.by_position}
    assert counts == {1: (12, 1), 2: (12, 0), 3: (12, 2), 4: (12, 1)}
    assert counts[3][1] / counts[3][0] == pytest.approx(2 / 12)


def test_the_disagreeing_cells_are_named_with_both_readings(report):
    by_key = {d.key: d for d in report.disagreements}
    assert set(by_key) == {
        ("Oblast 1", "Output", "1982"),
        ("Oblast 2", "Output", "1983"),
        ("Oblast 3", "Output", "1984"),
    }
    dropped = by_key[("Oblast 2", "Output", "1983")]
    assert (dropped.raw_a, dropped.raw_b) == ("2333", "333")
    assert dropped.n_digit_disagreements == 2
    assert dropped.kind == "raw_text"


def test_two_readings_of_the_same_table_are_recognised_as_such(report):
    assert report.identity_differences == ()
    assert report.same_table is True
    assert report.keys_only_in_a == () and report.keys_only_in_b == ()


def test_a_different_transcriber_is_not_a_different_table(fixtures_dir):
    """The two fixtures name different transcribers and dates; that is the point."""
    rows_a = read_filled(fixtures_dir / PAIR_A)
    rows_b = read_filled(fixtures_dir / PAIR_B)
    assert rows_a[0]["transcriber"] != rows_b[0]["transcriber"]
    assert compare_transcriptions(rows_a, rows_b).identity_differences == ()


def test_two_different_tables_are_reported_as_such(fixtures_dir):
    rows_a = read_filled(fixtures_dir / PAIR_A)
    rows_b = [dict(r, page="999") for r in read_filled(fixtures_dir / PAIR_B)]
    differences = compare_transcriptions(rows_a, rows_b).identity_differences
    assert [d[0] for d in differences] == ["page"]


def test_a_cell_present_in_only_one_reading_is_reported_not_ignored(fixtures_dir):
    rows_a = read_filled(fixtures_dir / PAIR_A)
    rows_b = read_filled(fixtures_dir / PAIR_B)[:-1]
    out = compare_transcriptions(rows_a, rows_b)
    assert out.n_common == 11
    assert len(out.keys_only_in_a) == 1
    assert out.same_table is False
    assert any(d.kind == "missing_in_b" for d in out.disagreements)


def test_identical_transcriptions_disagree_nowhere(fixtures_dir):
    rows = read_filled(fixtures_dir / PAIR_A)
    out = compare_transcriptions(rows, rows)
    assert out.n_cell_disagreements == 0
    assert out.n_digit_disagreements == 0
    assert out.digit_disagreement_rate == 0.0


# ------------------------------------------------------------------ digit alignment


@pytest.mark.parametrize(
    ("a", "b", "leading", "trailing"),
    [
        ("9221", "9231", 1, 1),
        ("9221", "9221", 0, 0),
        ("9221", "921", 2, 2),
        ("1234", "234", 4, 1),
        ("", "", 0, 0),
        ("5", "", 1, 1),
        ("123", "456", 3, 3),
    ],
)
def test_digit_alignment_counts_are_hand_checked(a, b, leading, trailing):
    assert digit_disagreements(a, b, "leading") == leading
    assert digit_disagreements(a, b, "trailing") == trailing


def test_a_dropped_digit_is_counted_conservatively():
    """Aligned from the left, dropping a leading digit displaces everything after it."""
    assert digit_disagreements("2333", "333", "leading") == 2
    assert digit_disagreements("2333", "233", "leading") == 1


# ------------------------------------------------------------------ the digit-test gate


def test_the_gate_passes_only_below_the_threshold_the_caller_states(report):
    assert digit_tests_permitted(report, max_digit_disagreement_rate=0.10) is True
    assert digit_tests_permitted(report, max_digit_disagreement_rate=0.01) is False


def test_the_gate_refuses_a_comparison_that_compared_nothing():
    empty = compare_transcriptions([], [])
    with pytest.raises(ValueError, match="no evidence"):
        digit_tests_permitted(empty, max_digit_disagreement_rate=0.5)


def test_the_gate_refuses_an_impossible_threshold(report):
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        digit_tests_permitted(report, max_digit_disagreement_rate=1.5)


def test_the_gate_fails_when_the_two_readings_do_not_cover_the_same_cells(fixtures_dir):
    rows_a = read_filled(fixtures_dir / PAIR_A)
    rows_b = read_filled(fixtures_dir / PAIR_B)[:-1]
    partial = compare_transcriptions(rows_a, rows_b)
    assert digit_tests_permitted(partial, max_digit_disagreement_rate=0.5) is False
    assert (
        digit_tests_permitted(partial, max_digit_disagreement_rate=0.5, require_full_coverage=False)
        is True
    )


def test_the_report_serialises_with_both_rates(report):
    payload = report.to_dict()
    assert payload["n_common"] == 12
    assert payload["digit_disagreement_rate"] == pytest.approx(4 / 48)
    assert len(payload["by_position"]) == 4
    assert len(payload["disagreements"]) == 3

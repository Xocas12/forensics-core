"""The catalogue must refuse entries that cannot support a claim.

The two required fields are the whole point of this module. An entry with a threshold but no
statement of what anyone gained by landing on one side of it is a round number, and scanning
enough round numbers always turns something up. These tests hold that line.
"""

from __future__ import annotations

import textwrap

import numpy as np
import pandas as pd
import pytest

from forensics_core.bunching.notch import Kink, Notch
from forensics_core.inject import inject_bunching
from forensics_core.notches import (
    SCAN_ALL_COLUMNS,
    NotchCatalogueError,
    NotchEntry,
    in_range,
    load_notches,
    parse_entry,
    scan_all,
    validate_notches,
)

GOOD = """\
- id: plan_fulfilment_100
  variable: plan_fulfilment_pct
  threshold: 100.0
  kind: notch
  side: above
  incentive: >
    A bonus is paid on reported fulfilment of 100 per cent or more, so an enterprise just
    short of plan gains by reporting just over it.
  evidence: >
    Recorded in the project's own documentation of the bonus rule.
  confounds:
    - genuine effort to reach the plan
    - rounding during aggregation
  status: verified
  notes: the programme's clearest documented incentive discontinuity
- id: growth_target
  variable: growth_pct
  threshold: 7.5
  kind: kink
  incentive: >
    A provincial growth target above which political reward changes.
  evidence: >
    unverified: no institutional source is recorded in this repository yet.
  confounds:
    - provinces manage real activity to hit targets
  status: unverified
"""


def write(tmp_path, text: str):
    p = tmp_path / "notches.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


# ---------------------------------------------------------------- the required fields


def test_an_entry_without_an_incentive_is_rejected():
    """The line between a notch and a round number."""
    with pytest.raises(NotchCatalogueError, match="incentive is required"):
        parse_entry({"id": "x", "variable": "v", "threshold": 50.0, "evidence": "somewhere"})


def test_an_entry_without_evidence_is_rejected():
    with pytest.raises(NotchCatalogueError, match="evidence is required"):
        parse_entry({"id": "x", "variable": "v", "threshold": 50.0, "incentive": "a bonus"})


def test_a_whitespace_only_incentive_does_not_count():
    with pytest.raises(NotchCatalogueError, match="incentive is required"):
        parse_entry(
            {"id": "x", "variable": "v", "threshold": 1.0, "incentive": "   ", "evidence": "e"}
        )


def test_the_rejection_message_explains_the_distinction():
    """Someone hitting this should learn why, not just that."""
    with pytest.raises(NotchCatalogueError) as exc:
        parse_entry({"id": "x", "variable": "v", "threshold": 50.0, "evidence": "e"})
    assert "round number" in str(exc.value)
    assert "digit tests" in str(exc.value)


def test_an_entry_without_a_variable_is_rejected():
    with pytest.raises(NotchCatalogueError, match="variable is required"):
        parse_entry({"id": "x", "threshold": 1.0, "incentive": "i", "evidence": "e"})


# ---------------------------------------------------------------- other validation


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", "wobble", "kind must be one of"),
        ("side", "sideways", "side must be one of"),
        ("status", "probably", "status must be one of"),
        ("threshold", "high", "threshold must be a number"),
        ("confounds", "not a list", "confounds must be a list"),
    ],
)
def test_bad_fields_are_rejected_with_a_useful_message(field, value, message):
    raw = {
        "id": "x",
        "variable": "v",
        "threshold": 1.0,
        "incentive": "i",
        "evidence": "e",
    }
    raw[field] = value
    with pytest.raises(NotchCatalogueError, match=message):
        parse_entry(raw)


def test_an_entry_that_is_not_a_mapping_is_rejected():
    with pytest.raises(NotchCatalogueError, match="not a mapping"):
        parse_entry("plan_fulfilment_100")  # type: ignore[arg-type]


def test_duplicate_ids_are_rejected(tmp_path):
    p = write(
        tmp_path,
        """\
        - id: same
          variable: v
          threshold: 1.0
          incentive: i
          evidence: e
        - id: same
          variable: v
          threshold: 2.0
          incentive: i
          evidence: e
        """,
    )
    with pytest.raises(NotchCatalogueError, match="duplicate notch id"):
        load_notches(p)


# ---------------------------------------------------------------- round trip


def test_a_valid_catalogue_round_trips(tmp_path):
    entries = load_notches(write(tmp_path, GOOD))
    assert [e.id for e in entries] == ["plan_fulfilment_100", "growth_target"]
    first = entries[0]
    assert first.threshold == 100.0
    assert first.kind == "notch"
    assert first.side == "above"
    assert first.status == "verified"
    assert len(first.confounds) == 2
    assert "bonus" in first.incentive


def test_an_empty_catalogue_is_allowed(tmp_path):
    assert load_notches(write(tmp_path, "")) == []


def test_a_non_list_catalogue_is_rejected(tmp_path):
    with pytest.raises(NotchCatalogueError, match="must be a list"):
        load_notches(write(tmp_path, "id: lonely\n"))


def test_entries_build_the_objects_the_estimators_accept(tmp_path):
    entries = load_notches(write(tmp_path, GOOD))
    notch = entries[0].to_notch()
    kink = entries[1].to_notch()
    assert isinstance(notch, Notch)
    assert notch.threshold == 100.0 and notch.side == "above"
    assert notch.label == "plan_fulfilment_100"
    assert isinstance(kink, Kink)
    assert kink.threshold == 7.5


def test_to_dict_carries_every_field(tmp_path):
    d = load_notches(write(tmp_path, GOOD))[0].to_dict()
    assert set(d) == {
        "id",
        "variable",
        "threshold",
        "kind",
        "side",
        "incentive",
        "evidence",
        "confounds",
        "status",
        "notes",
    }


# ---------------------------------------------------------------- validate_notches


def test_validate_reports_every_problem_rather_than_the_first(tmp_path):
    p = write(
        tmp_path,
        """\
        - id: a
          variable: v
          threshold: 1.0
          evidence: e
        - id: b
          variable: v
          threshold: 2.0
          incentive: i
        """,
    )
    problems = validate_notches(p)
    assert len(problems) == 2
    assert any("incentive is required" in x for x in problems)
    assert any("evidence is required" in x for x in problems)


def test_validate_flags_an_entry_with_no_confounds(tmp_path):
    p = write(
        tmp_path,
        """\
        - id: a
          variable: v
          threshold: 1.0
          incentive: i
          evidence: e
        """,
    )
    problems = validate_notches(p)
    assert any("no confounds listed" in x for x in problems)


def test_validate_is_quiet_on_a_sound_catalogue(tmp_path):
    assert validate_notches(write(tmp_path, GOOD)) == []


def test_validate_reports_a_missing_file_rather_than_raising(tmp_path):
    assert "no such file" in validate_notches(tmp_path / "absent.yaml")[0]


def test_validate_reports_bad_yaml_rather_than_raising(tmp_path):
    p = tmp_path / "notches.yaml"
    p.write_text("- id: a\n  threshold: [unclosed\n", encoding="utf-8")
    assert any("not valid YAML" in x for x in validate_notches(p))


# ---------------------------------------------------------------- scanning


def _entry(**kw) -> NotchEntry:
    base = {
        "id": "e",
        "variable": "v",
        "threshold": 100.0,
        "incentive": "i",
        "evidence": "ev",
    }
    base.update(kw)
    return NotchEntry(**base)  # type: ignore[arg-type]


def test_in_range_guards_a_threshold_the_data_never_reaches():
    values = np.linspace(0.0, 50.0, 100)
    assert in_range(_entry(threshold=25.0), values) is True
    assert in_range(_entry(threshold=100.0), values) is False
    assert in_range(_entry(threshold=25.0), np.array([np.nan, np.nan])) is False


def test_scan_all_returns_the_documented_columns_and_ranks_by_excess():
    """A bonus notch, reward above, must rank above a decoy threshold."""
    rng = np.random.default_rng(4)
    clean = rng.normal(100.0, 12.0, size=20000)
    x, _ = inject_bunching(clean, threshold=100.0, mass=0.6, window=4.0, side="above", seed=7)
    frame = pd.DataFrame({"v": x})

    catalogue = [
        _entry(id="real", threshold=100.0, side="above"),
        _entry(id="decoy", threshold=115.0, side="above"),
    ]
    out = scan_all(frame, catalogue, bin_width=1.0, exclude_below=4.0, exclude_above=4.0)
    assert list(out.columns) == SCAN_ALL_COLUMNS
    assert len(out) == 2
    assert out.iloc[0]["id"] == "real", out
    assert out.iloc[0]["normalized_excess"] > out.iloc[1]["normalized_excess"]


def test_scan_all_passes_the_side_through_so_a_bonus_notch_scores_positive():
    """The subtle one. excess_mass is summed on the BUNCHING side, so scanning a
    reward-above notch as though it were reward-below reports a large NEGATIVE excess and
    ranks the programme's flagship notch last instead of first."""
    rng = np.random.default_rng(4)
    clean = rng.normal(100.0, 12.0, size=20000)
    kw = {"bin_width": 1.0, "exclude_below": 4.0, "exclude_above": 4.0}

    above, _ = inject_bunching(clean, threshold=100.0, mass=0.6, window=4.0, side="above", seed=7)
    got = scan_all(pd.DataFrame({"v": above}), [_entry(id="bonus", side="above")], **kw)
    assert got.iloc[0]["normalized_excess"] > 1.0, "a bonus notch must score positive"

    below, _ = inject_bunching(clean, threshold=100.0, mass=0.6, window=4.0, side="below", seed=7)
    got = scan_all(pd.DataFrame({"v": below}), [_entry(id="tax", side="below")], **kw)
    assert got.iloc[0]["normalized_excess"] > 1.0, "a tax notch must score positive too"

    # and the mismatch is what would have gone unnoticed
    wrong = scan_all(pd.DataFrame({"v": above}), [_entry(id="mislabelled", side="below")], **kw)
    assert wrong.iloc[0]["normalized_excess"] < 0, "the wrong side inverts the sign"


def test_scan_all_skips_a_variable_the_frame_does_not_have():
    frame = pd.DataFrame({"v": np.random.default_rng(0).normal(100, 10, 5000)})
    out = scan_all(
        frame,
        [_entry(id="present", threshold=100.0), _entry(id="absent", variable="nope")],
        bin_width=1.0,
        exclude_below=3.0,
        exclude_above=3.0,
    )
    assert list(out["id"]) == ["present"]


def test_scan_all_skips_a_threshold_outside_the_data():
    """A threshold the data never reaches yields a number that looks like a result."""
    frame = pd.DataFrame({"v": np.random.default_rng(1).normal(50, 5, 5000)})
    out = scan_all(
        frame,
        [_entry(id="far", threshold=5000.0)],
        bin_width=1.0,
        exclude_below=3.0,
        exclude_above=3.0,
    )
    assert out.empty
    assert list(out.columns) == SCAN_ALL_COLUMNS


def test_scan_all_on_an_empty_catalogue_returns_an_empty_typed_frame():
    frame = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    out = scan_all(frame, [], bin_width=1.0, exclude_below=1.0, exclude_above=1.0)
    assert out.empty
    assert list(out.columns) == SCAN_ALL_COLUMNS

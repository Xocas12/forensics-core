"""The elections notch catalogue, and the honesty conditions on it.

This project is the programme's weakest instance of the unifying hypothesis: its thresholds are
round numbers with an inferred incentive, not a documented pay schedule. These tests hold the
catalogue to saying so, because an entry that quietly claimed `verified` would turn a round
number into an institutional fact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from forensics_core.notches import load_notches, validate_notches

PROJECT = Path(__file__).resolve().parents[1]
CATALOGUE = PROJECT / "notches.yaml"
TRAPS = PROJECT / "docs" / "known_traps.md"


@pytest.fixture(scope="module")
def entries():
    return load_notches(CATALOGUE)


def test_the_catalogue_validates():
    problems = validate_notches(CATALOGUE)
    assert problems == [], problems


def test_every_entry_names_the_small_precinct_trap(entries):
    """Trap 1 is the one that decides this project's whole analysis: at 100 registered voters
    every attainable turnout is a whole percentage, so bunching at a round number arises by
    arithmetic. An entry that does not name it is not ready to be scanned."""
    for e in entries:
        joined = " ".join(e.confounds).lower()
        assert "trap 1" in joined or "small precinct" in joined, (
            f"{e.id} does not name the small-precinct trap"
        )


def test_every_entry_names_at_least_one_confound(entries):
    for e in entries:
        assert e.confounds, f"{e.id} lists no confound"


def test_every_incentive_is_marked_unverified(entries):
    """Nothing in data/SOURCES.yaml documents an electoral target, quota or bonus. Until one is
    recorded, claiming `verified` here would dress a round number up as an institutional fact,
    which is the single failure this catalogue exists to prevent."""
    for e in entries:
        assert e.status == "unverified", (
            f"{e.id} claims status={e.status}. If a source for the incentive has been added to "
            "data/SOURCES.yaml, cite it in the entry's evidence field and update this test."
        )


def test_every_evidence_field_says_what_was_tried(entries):
    """`evidence` must record the search that failed, not merely assert absence."""
    for e in entries:
        assert "unverified" in e.evidence.lower(), f"{e.id} evidence does not admit the gap"
        assert "SOURCES.yaml" in e.evidence or "recorded" in e.evidence.lower(), (
            f"{e.id} evidence does not say what was checked"
        )


def test_the_variables_are_ones_the_clean_layer_produces(entries):
    """A threshold on a column that never exists is a silently dead entry."""
    from elections.clean import derive

    produced = set()
    source = Path(derive.__file__).read_text(encoding="utf-8")
    for name in ("turnout_boxes", "turnout_issued", "winner_share"):
        if f'"{name}"' in source:
            produced.add(name)
    for e in entries:
        assert e.variable in produced, (
            f"{e.id} scans {e.variable!r}, which elections.clean.derive does not produce"
        )


def test_the_named_traps_exist_in_known_traps(entries):
    """A confound citing a trap number that does not exist is a broken cross-reference."""
    text = TRAPS.read_text(encoding="utf-8")
    for e in entries:
        for c in e.confounds:
            low = c.lower()
            for n in ("1", "2", "3", "5", "6"):
                if low.startswith(f"trap {n}:"):
                    assert f"## {n}." in text, f"{e.id} cites trap {n}, absent from known_traps.md"


def test_the_header_records_that_no_incentive_source_exists():
    """The file's own preamble is where a reader learns how weak this instance is."""
    text = CATALOGUE.read_text(encoding="utf-8")
    assert "no such schedule" in text or "contains none" in text
    assert "weakest instance" in text


def test_entries_build_estimator_objects(entries):
    for e in entries:
        obj = e.to_notch()
        assert obj.threshold == e.threshold
        assert obj.label == e.id

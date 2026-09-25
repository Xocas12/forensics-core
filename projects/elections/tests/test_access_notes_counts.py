"""The counts quoted in the prose must match the registry they claim to summarise.

A count table that drifts from SOURCES.yaml is the cheapest possible way for this project to
start lying about its own data. These tests recompute the numbers and fail on any drift, so
the documents cannot silently go stale as sources are added or re-verified.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT / "data" / "SOURCES.yaml"
ACCESS_NOTES = PROJECT / "data" / "ACCESS_NOTES.md"
README = PROJECT / "README.md"

STATUSES = ("verified", "partial", "blocked", "unverified")


@pytest.fixture(scope="module")
def registry() -> list[dict]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def counts(registry: list[dict]) -> Counter:
    return Counter(entry["status"] for entry in registry)


def _documented_counts(text: str) -> dict[str, int]:
    """Pull "| Verified ... | 14 |" style rows out of a markdown table."""
    found: dict[str, int] = {}
    for status in STATUSES:
        m = re.search(rf"^\|\s*{status}\b[^|]*\|\s*(\d+)\s*\|", text, re.IGNORECASE | re.MULTILINE)
        if m:
            found[status] = int(m.group(1))
    return found


@pytest.mark.parametrize("doc", [ACCESS_NOTES, README], ids=["access_notes", "readme"])
def test_documented_status_counts_match_the_registry(doc: Path, counts: Counter) -> None:
    documented = _documented_counts(doc.read_text(encoding="utf-8"))
    assert documented, f"{doc.name} has no status count table to check"
    for status, n in documented.items():
        assert n == counts[status], (
            f"{doc.name} claims {n} {status} sources; the registry has {counts[status]}"
        )


@pytest.mark.parametrize("doc", [ACCESS_NOTES, README], ids=["access_notes", "readme"])
def test_documented_total_matches_the_registry(doc: Path, registry: list[dict]) -> None:
    text = doc.read_text(encoding="utf-8")
    assert re.search(rf"\b{len(registry)}\b", text), (
        f"{doc.name} never states the registry size ({len(registry)} sources)"
    )


def test_every_blocked_source_is_named_in_the_access_notes(registry: list[dict]) -> None:
    """A blocked source that no document mentions is a silently dropped problem."""
    text = ACCESS_NOTES.read_text(encoding="utf-8")
    blocked = [e["id"] for e in registry if e["status"] == "blocked"]
    missing = [sid for sid in blocked if sid not in text]
    assert not missing, f"blocked sources absent from ACCESS_NOTES.md: {missing}"


def test_registry_is_all_free_as_the_documents_claim(registry: list[dict]) -> None:
    tiers = {e["access"] for e in registry}
    assert tiers == {"free"}, f"documents claim every source is free, but found {sorted(tiers)}"


def test_blocked_sources_each_carry_a_reason(registry: list[dict]) -> None:
    for entry in registry:
        if entry["status"] == "blocked":
            assert (entry.get("blocked_reason") or "").strip(), (
                f"{entry['id']} is blocked with no recorded reason"
            )

"""CONTRACT.md exists, and its rules cannot be quietly dropped, reordered or reworded.

The frozen list below is the point of this file. A contract that a session can edit freely is
not a contract, and the specific risk is not deletion — which is visible — but a rule that
softens across a few sessions until it no longer forbids anything. Changing a title here is
allowed; doing it without noticing is not.

Rule *numbers* are load-bearing too. `gosplan/seal.py` cites rule 5 and `eval/harness.py`
cites rule 9 by number, so a renumbering silently turns those citations into references to
some other rule.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _find_contract() -> Path:
    """Walk up to the nearest CONTRACT.md.

    The same file is used in three repositories with different depths, and inside the
    vendored `packages/forensics_core` submodule, where the nearest copy is the submodule's
    own and that is the one that should be checked.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "CONTRACT.md"
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[1] / "CONTRACT.md"


CONTRACT = _find_contract()

#: The rules, in order. Position in this list is the rule number.
FROZEN_RULES = [
    "NO INVENTED SOURCES",
    "STOP AND REPORT",
    "FROZEN TESTS",
    "NO ANALYSIS BEFORE ITS PHASE",
    "THE HELD-OUT ANCHOR",
    "RAW DATA NEVER ENTERS GIT",
    "EVERY FETCH IS LOGGED",
    "BOUNDS AND FAILURES ARE RESULTS",
    "FALSE POSITIVES SHIP WITH EVERY CLAIM",
    "RANK METRICS ONLY, WITH THE BASE RATE BESIDE THEM",
    "PRE-REGISTRATION",
    "WHITELIST DISCIPLINE",
    "ACCESS POLICIES ARE OBSERVED",
]

RULE_HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


def contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def parsed_rules() -> list[tuple[int, str]]:
    return [(int(n), title.strip()) for n, title in RULE_HEADING.findall(contract_text())]


def test_the_contract_exists():
    assert CONTRACT.is_file(), (
        f"{CONTRACT} is missing. Every card in the programme cites it, and code in two "
        "repositories cites its rules by number."
    )


def test_the_rule_count_is_frozen():
    rules = parsed_rules()
    assert len(rules) == len(FROZEN_RULES), (
        f"CONTRACT.md has {len(rules)} rules but the frozen list has {len(FROZEN_RULES)}. "
        "Adding or removing a rule is allowed; doing it without updating this list is not."
    )


def test_the_rules_are_numbered_one_to_thirteen_in_order():
    numbers = [n for n, _ in parsed_rules()]
    assert numbers == list(range(1, len(FROZEN_RULES) + 1)), (
        f"rule numbers are {numbers}. They must run 1..{len(FROZEN_RULES)} in order, because "
        "seal.py cites rule 5 and eval/harness.py cites rule 9 by number."
    )


@pytest.mark.parametrize(("number", "title"), list(enumerate(FROZEN_RULES, start=1)))
def test_each_rule_keeps_its_number_and_title(number: int, title: str):
    rules = dict(parsed_rules())
    assert rules.get(number) == title, f"rule {number} is {rules.get(number)!r}, expected {title!r}"


def test_the_two_rules_cited_by_number_in_code_are_the_ones_the_code_means():
    """The failure this guards is silent: a renumbering leaves both citations pointing at a
    real rule, just the wrong one."""
    rules = dict(parsed_rules())
    assert "HELD-OUT" in rules[5], "seal.py cites rule 5 as the held-out anchor"
    assert "FALSE POSITIVES" in rules[9], "eval/harness.py cites rule 9 as the control rule"


def test_every_rule_says_what_a_violation_looks_like():
    """A rule nobody can recognise a breach of is decoration."""
    text = contract_text()
    sections = re.split(r"^## \d+\. ", text, flags=re.MULTILINE)[1:]
    missing = [s.splitlines()[0] for s in sections if "A violation looks like" not in s]
    assert not missing, f"these rules do not say what a violation looks like: {missing}"


def test_every_rule_says_what_catches_it():
    text = contract_text()
    sections = re.split(r"^## \d+\. ", text, flags=re.MULTILINE)[1:]
    missing = [s.splitlines()[0] for s in sections if "What catches it" not in s]
    assert not missing, f"these rules do not say what catches a violation: {missing}"

"""The acquisition wiring: what has an acquirer, what must not, and that the CLI runs.

These tests assert the project's hard rules rather than that code executes: no acquirer may
exist for a source the registry marks blocked or gated, every acquirer must name a real
registry id, and the shared runner's plan must reproduce those decisions. They read
``data/SOURCES.yaml`` and make no network request.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from china.acquire.__main__ import main
from china.acquire.registry import ACQUIRERS, AcquireResult, register
from china.acquire.yearbook import ANCHOR_SHA256, TOC_2023_SHA256, TOC_2024_EN_SHA256
from forensics_core.provenance.manifest import load_sources
from forensics_core.provenance.runner import NEEDS_HUMAN, plan

#: Defined here rather than imported from conftest: under pytest's importlib import
#: mode (set in the workspace pyproject) a test module cannot import its own conftest.
SOURCES_YAML = Path(__file__).resolve().parents[1] / "data" / "SOURCES.yaml"

#: Ids left without an acquirer on purpose, with the reason. Anything else missing an
#: acquirer while being free and reachable is a gap, and the test below says so.
DELIBERATELY_UNIMPLEMENTED = {
    "mcp_cnbs_repo": "third-party documentation, not a data source",
    "nbs_data_portal_new_spa": "JavaScript shell with no data in it",
}


def _sources():
    return load_sources(SOURCES_YAML)


def test_every_acquirer_names_a_real_registry_id():
    known = {s.id for s in _sources()}
    unknown = sorted(set(ACQUIRERS) - known)
    assert unknown == [], f"acquirers registered for ids not in SOURCES.yaml: {unknown}"


def test_no_acquirer_for_a_blocked_source():
    blocked = {s.id for s in _sources() if s.status == "blocked"}
    assert blocked, "the registry should still record the blocked NBS and CEC sources"
    assert sorted(blocked & set(ACQUIRERS)) == []


def test_no_acquirer_for_a_source_that_needs_a_human():
    gated = {s.id for s in _sources() if s.access in NEEDS_HUMAN}
    assert gated, "the registry should still record the paywalled and gated sources"
    assert sorted(gated & set(ACQUIRERS)) == []


def test_every_free_reachable_source_has_an_acquirer_or_a_stated_reason():
    reachable = {
        s.id for s in _sources() if s.access == "free" and s.status in {"verified", "partial"}
    }
    gaps = sorted(reachable - set(ACQUIRERS) - set(DELIBERATELY_UNIMPLEMENTED))
    assert gaps == [], f"free, reachable sources with neither an acquirer nor a reason: {gaps}"


def test_plan_attempts_exactly_the_acquirable_sources():
    attempt, skipped = plan(_sources(), ACQUIRERS)
    assert {s.id for s in attempt} == set(ACQUIRERS)
    assert len(attempt) + len(skipped) == len(_sources())
    # Every skip carries a reason a person can act on.
    assert all(reason.strip() for _s, reason in skipped)


def test_registering_a_duplicate_acquirer_is_rejected():
    existing = next(iter(ACQUIRERS))
    with pytest.raises(ValueError, match="duplicate acquirer"):
        register(existing)(lambda source, data_dir: None)


def test_acquire_result_renders_failure_and_cache_state():
    ok = AcquireResult("synthetic_id", True, "111 bytes", (), skipped_cached=True)
    bad = AcquireResult("synthetic_id", False, "HTTP 403")
    assert "ok " in str(ok) and "(cached)" in str(ok)
    assert "FAIL" in str(bad) and "(cached)" not in str(bad)


def test_list_runs_and_returns_zero(capsys):
    assert main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert f"{len(_sources())} sources" in printed
    # The mark column must flag exactly the ids that have an acquirer.
    marked = {
        line.split()[1]
        for line in printed.splitlines()
        if line.startswith("  * ") and not line.startswith("  * =")
    }
    assert marked == set(ACQUIRERS)


def test_dry_run_attempts_every_acquirable_source_and_makes_no_request(capsys):
    assert main(["--all", "--dry-run"]) == 0
    printed = capsys.readouterr().out
    dry = {
        line.split(":")[0].removeprefix("[dry] ")
        for line in printed.splitlines()
        if line.startswith("[dry] ")
    }
    assert dry == set(ACQUIRERS)
    assert f"{len(ACQUIRERS)} sources to attempt" in printed


def test_dry_run_of_a_blocked_id_skips_it_with_the_registry_reason(capsys):
    assert main(["nbs_easyquery_legacy", "--dry-run"]) == 0
    printed = capsys.readouterr().out
    assert "[skip] nbs_easyquery_legacy" in printed
    assert "UrlACL" in printed


def test_unknown_id_is_an_error(capsys):
    assert main(["synthetic_not_a_source", "--dry-run"]) == 1
    assert "is not in" in capsys.readouterr().out


def _registry_prose(source) -> str:
    """The fields ``fetch`` never rewrites: notes, evidence and download plan.

    On success ``fetch`` overwrites ``sha256``, ``bytes``, ``local_path``, ``status`` and
    ``blocked_reason`` and leaves the prose alone, so a digest quoted in the prose is a
    stable record while the ``sha256`` column is not.
    """
    return " ".join(str(x or "") for x in (source.notes, source.evidence, source.download_plan))


def test_the_pinned_anchor_digests_are_the_registry_values_as_shipped():
    """Every digest hard-coded in ``china.acquire.yearbook`` must come from ``SOURCES.yaml``.

    The constants exist because ``fetch`` rewrites an entry's ``sha256`` on every success and
    those three ids each fetch a whole family of files, so the registry value stops being the
    anchor's digest after run one. That makes the constants the only surviving copy of the
    shipped values, and a copy nobody checks is a copy that drifts into being invented.

    The check is therefore conditional on the entry still being un-fetched, which
    ``local_path is None`` says: ``fetch`` sets ``local_path`` on its first success. On a
    clean tree the constants and the registry must agree exactly. Once a real run has
    rewritten an entry, the comparison is meaningless rather than failing, and the constant
    is checked only for shape -- it must never be edited to match a post-run registry value.
    """
    recorded = {s.id: s for s in _sources()}
    compared = 0
    for source_id, digest in ANCHOR_SHA256.items():
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef"), digest
        assert source_id in recorded, f"{source_id} is pinned but not in SOURCES.yaml"
        entry = recorded[source_id]
        if entry.local_path is not None:
            continue  # the entry has been fetched; its sha256 is now a family member's
        assert entry.sha256 == digest, (
            f"{source_id}: pinned {digest} but the un-fetched registry entry holds {entry.sha256}"
        )
        compared += 1
    assert len(ANCHOR_SHA256) == 4
    assert compared == 4 or any(recorded[i].local_path for i in ANCHOR_SHA256), (
        "an anchor was neither compared against the registry nor marked as fetched"
    )


def test_the_pinned_contents_frame_digests_come_from_registry_prose():
    """The three contents-frame digests must be traceable to a field ``fetch`` cannot rewrite.

    ``TOC_2024_EN_SHA256`` is the ``csy_web_editions`` entry's recorded digest, and that
    entry's evidence field is what says the digest belongs to ``left_.htm`` (81,548 bytes)
    rather than to the 904-byte frameset its ``bytes`` column records; the evidence quotes the
    digest by its first eight characters. The two 2023 digests are written out in full in the
    ``nbs_yearbook_2023_html_tables`` evidence. Neither prose field is touched by a successful
    fetch, so unlike the ``sha256`` column these comparisons hold after a real run too.
    """
    recorded = {s.id: s for s in _sources()}
    digests = [TOC_2024_EN_SHA256, *TOC_2023_SHA256.values()]
    for digest in digests:
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef"), digest
    assert len(set(digests)) == 3, "the three contents-frame digests must differ"
    assert set(TOC_2023_SHA256) == {"en", "zh"}

    editions_prose = _registry_prose(recorded["csy_web_editions"])
    assert f"sha256 {TOC_2024_EN_SHA256[:8]}" in editions_prose, (
        "TOC_2024_EN_SHA256 must be the left_.htm digest the csy_web_editions evidence names"
    )
    tables_prose = _registry_prose(recorded["nbs_yearbook_2023_html_tables"])
    for language, digest in TOC_2023_SHA256.items():
        assert digest in tables_prose, (
            f"the 2023 {language} contents-frame digest is not recorded in "
            f"nbs_yearbook_2023_html_tables"
        )


def test_no_family_acquirer_reads_its_expected_digest_out_of_the_registry():
    """``source.sha256`` may only be read inside an acquirer whose id maps to one file.

    ``fetch`` overwrites an entry's recorded digest with each success, so for a multi-file
    family the registry value belongs to whichever member went last. Passing it as an
    expected digest on a later run compares a good file against another file's hash, renames
    the good file ``.bad`` and reports a mismatch that is pure bookkeeping. Only the two
    genuinely single-file acquirers may do it. This test names them by function, so a new
    family acquirer that copies the old pattern fails here rather than in production.
    """
    acquire_dir = SOURCES_YAML.parent.parent / "src" / "china" / "acquire"
    readers: set[str] = set()
    for path in sorted(acquire_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "sha256"
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == "source"
                ):
                    readers.add(f"{path.stem}.{node.name}")
    assert readers == {"pbc.credit_statistics", "yearbook.grp_2015"}, (
        "source.sha256 is only safe where the registry id maps to exactly one file "
        f"(pbc_credit_statistics, csy_2015_grp_vintage); found {sorted(readers)}"
    )


def test_the_two_single_file_digest_readers_really_are_single_file_sources():
    """The exemption above is only sound if those two ids do fetch exactly one file each.

    Both acquirers call ``fetch_file``, never ``fetch_files``, so ``fetch`` writes back the
    same digest it was given and the registry entry stays correct across runs.
    """
    acquire_dir = SOURCES_YAML.parent.parent / "src" / "china" / "acquire"
    for module, function in (("pbc", "credit_statistics"), ("yearbook", "grp_2015")):
        path = acquire_dir / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        node = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function
        )
        called = {
            inner.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
        }
        assert "fetch_file" in called, f"{module}.{function} must fetch exactly one file"
        assert "fetch_files" not in called, (
            f"{module}.{function} reads source.sha256 and must not fetch a family"
        )

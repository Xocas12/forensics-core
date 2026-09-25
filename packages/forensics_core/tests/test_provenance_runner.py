"""The shared acquisition runner: planning, and the console-encoding guard.

Synthetic registries only; no network, no real project directory.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from forensics_core.provenance import runner
from forensics_core.provenance.manifest import Source

BASE = {
    "name": "Synthetic ledger",
    "provider": "Synthetic Provider",
    "url": "https://example.invalid/synthetic.csv",
    "notes": "synthetic fixture",
}


def _src(sid: str, status: str, access: str, **kw) -> Source:
    payload = {**BASE, "id": sid, "status": status, "access": access, **kw}
    if status == "verified" and "http_status" not in payload:
        payload["http_status"] = 200
        payload["fetched_at"] = "2026-09-06T00:00:00Z"
    if status == "blocked":
        payload.setdefault("blocked_reason", "HTTP 403 from the synthetic host")
    return Source(**payload)


def _noop(source, data_dir, force: bool = False):
    raise AssertionError("acquirer must not run during planning")


def test_plan_attempts_only_reachable_free_sources_with_acquirers() -> None:
    sources = [
        _src("free_ok", "verified", "free"),
        _src("free_partial", "partial", "free"),
        _src("gated", "verified", "registration"),
        _src("walled", "verified", "paywalled"),
        _src("dead", "blocked", "free"),
        _src("ghost", "unverified", "free"),
    ]
    acquirers = {s.id: _noop for s in sources}
    attempt, skipped = runner.plan(sources, acquirers)

    assert [s.id for s in attempt] == ["free_ok", "free_partial"]
    reasons = {s.id: why for s, why in skipped}
    assert set(reasons) == {"gated", "walled", "dead", "ghost"}
    assert "needs a human" in reasons["gated"]
    assert "needs a human" in reasons["walled"]
    assert "HTTP 403" in reasons["dead"]
    assert "not attemptable" in reasons["ghost"]


def test_plan_reports_a_reachable_source_with_no_acquirer_rather_than_hiding_it() -> None:
    sources = [_src("orphan", "verified", "free")]
    attempt, skipped = runner.plan(sources, {})
    assert attempt == []
    assert skipped[0][1] == "no acquirer implemented for this id"


def test_explicit_id_overrides_the_status_filter_but_not_a_missing_acquirer() -> None:
    sources = [_src("dead", "blocked", "free"), _src("orphan", "verified", "free")]
    attempt, _ = runner.plan(sources, {"dead": _noop}, only=["dead"])
    assert [s.id for s in attempt] == ["dead"]

    attempt, skipped = runner.plan(sources, {"dead": _noop}, only=["orphan"])
    assert attempt == []
    assert skipped[0][0].id == "orphan"


def test_accepts_force_detects_keyword_and_var_keyword() -> None:
    assert runner._accepts_force(lambda s, d, force=False: None) is True
    assert runner._accepts_force(lambda s, d, **kw: None) is True
    assert runner._accepts_force(lambda s, d: None) is False


def test_list_does_not_die_on_a_non_ascii_source_name(tmp_path: Path) -> None:
    """A Cyrillic name must not kill --list on a legacy console code page.

    Run in a subprocess with PYTHONIOENCODING=cp1252 so the parent's UTF-8 stdout cannot mask
    the failure this guards against.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "SOURCES.yaml").write_text(
        textwrap.dedent(
            """\
            - id: synthetic_cyrillic
              name: "Синтетический источник"
              provider: Synthetic Provider
              url: https://example.invalid/synthetic.csv
              access: free
              status: partial
              notes: synthetic fixture
            """
        ),
        encoding="utf-8",
    )
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from forensics_core.provenance.runner import main
        raise SystemExit(main(project="synthetic", data_dir=Path(r"{data_dir}"),
                              acquirers={{}}, argv=["--list"]))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env={"PYTHONIOENCODING": "cp1252", "PATH": "", "SYSTEMROOT": ""},
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert b"UnicodeEncodeError" not in proc.stderr
    assert b"synthetic_cyrillic" in proc.stdout

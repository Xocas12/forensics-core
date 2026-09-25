"""Registry model, YAML round-trip, validation, checksums, fetch log and rate limiter.

All data here is synthetic (``synthetic_*`` ids, ``*.example`` / ``*.invalid`` hosts) and is
written inside pytest's ``tmp_path``. No test in this file touches the network.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest
import yaml

from forensics_core.provenance import manifest as M

# SHA-256 of b"abc", from FIPS 180-4 Appendix B.1 (a published test vector, not a value this
# code produced).
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

VALID_ENTRY = {
    "id": "synthetic_ledger",
    "name": "Synthetic Ledger Extract",
    "provider": "Synthetic Statistics Office",
    "url": "https://synthetic.example/ledger.csv",
    "access": "free",
    "status": "unverified",
    "notes": "synthetic fixture; never fetched",
}


def write_yaml(path: Path, entries: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------------------


def test_source_accepts_a_minimal_valid_entry() -> None:
    s = M.Source(**VALID_ENTRY)
    assert s.id == "synthetic_ledger"
    assert s.status == "unverified"
    assert s.sha256 is None
    assert s.bytes is None


def test_blocked_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="blocked_reason"):
        M.Source(**{**VALID_ENTRY, "status": "blocked"})
    ok = M.Source(**{**VALID_ENTRY, "status": "blocked", "blocked_reason": "HTTP 403"})
    assert ok.blocked_reason == "HTTP 403"


def test_blocked_reason_of_whitespace_is_not_a_reason() -> None:
    with pytest.raises(ValueError, match="blocked_reason"):
        M.Source(**{**VALID_ENTRY, "status": "blocked", "blocked_reason": "   "})


def test_verified_requires_evidence_of_a_successful_reach() -> None:
    """ "verified" means reached and confirmed, by a probe or by an acquisition."""
    # Neither probed nor acquired: rejected.
    with pytest.raises(ValueError, match="requires evidence"):
        M.Source(**{**VALID_ENTRY, "status": "verified"})
    # A non-200 probe is not evidence.
    with pytest.raises(ValueError, match="requires evidence"):
        M.Source(
            **{
                **VALID_ENTRY,
                "status": "verified",
                "http_status": 404,
                "fetched_at": "2026-09-06T00:00:00Z",
            }
        )
    # A 200 with no timestamp is not evidence either.
    with pytest.raises(ValueError, match="requires evidence"):
        M.Source(**{**VALID_ENTRY, "status": "verified", "http_status": 200})
    # (a) probed during research: no local copy yet, and that is legitimate.
    probed = M.Source(
        **{
            **VALID_ENTRY,
            "status": "verified",
            "http_status": 200,
            "fetched_at": "2026-09-06T00:00:00Z",
        }
    )
    assert probed.local_path is None
    # (b) acquired: the file is on disk and checksummed.
    ok = M.Source(
        **{
            **VALID_ENTRY,
            "status": "verified",
            "sha256": SHA256_ABC,
            "local_path": "data/raw/synthetic_ledger.csv",
        }
    )
    assert ok.sha256 == SHA256_ABC


def test_a_file_on_disk_must_be_checksummed_at_any_status() -> None:
    for status in ("verified", "partial", "unverified"):
        with pytest.raises(ValueError, match="must be checksummed"):
            M.Source(
                **{
                    **VALID_ENTRY,
                    "status": status,
                    "local_path": "data/raw/synthetic_ledger.csv",
                }
            )


def test_unverified_requires_notes() -> None:
    with pytest.raises(ValueError, match="notes"):
        M.Source(**{**VALID_ENTRY, "notes": "  "})


def test_access_must_be_one_of_the_five_values() -> None:
    for access in M.ACCESS_VALUES:
        entry = {**VALID_ENTRY, "access": access}
        assert M.Source(**entry).access == access
    with pytest.raises(ValueError, match="access must be one of"):
        M.Source(**{**VALID_ENTRY, "access": "open_access"})


def test_status_must_be_one_of_the_four_values() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        M.Source(**{**VALID_ENTRY, "status": "maybe"})


def test_url_may_be_none_only_for_offline_access_modes() -> None:
    with pytest.raises(ValueError, match="url may be null only when access"):
        M.Source(**{**VALID_ENTRY, "url": None})
    for access in ("archive_visit", "manual_transcription"):
        s = M.Source(**{**VALID_ENTRY, "url": None, "access": access})
        assert s.url is None


def test_malformed_sha256_and_negative_bytes_are_rejected() -> None:
    with pytest.raises(ValueError, match="64 hexadecimal"):
        M.Source(**{**VALID_ENTRY, "sha256": "deadbeef"})
    with pytest.raises(ValueError, match="bytes must be non-negative"):
        M.Source(**{**VALID_ENTRY, "bytes": -1})
    with pytest.raises(ValueError, match="http_status"):
        M.Source(**{**VALID_ENTRY, "http_status": 99})


def test_extra_keys_are_kept() -> None:
    s = M.Source(**{**VALID_ENTRY, "synthetic_project_tag": "demo"})
    assert s.model_dump()["synthetic_project_tag"] == "demo"


# --------------------------------------------------------------------------------------
# load / save / validate / update
# --------------------------------------------------------------------------------------


def test_save_then_load_round_trips_and_keeps_model_field_order(tmp_path: Path) -> None:
    src = M.Source(**VALID_ENTRY)
    path = tmp_path / "SOURCES.yaml"
    M.save_sources(path, [src])

    text = path.read_text(encoding="utf-8")
    keys = [line.split(":", 1)[0].lstrip("- ") for line in text.splitlines() if ":" in line]
    assert keys == list(M.Source.model_fields)

    back = M.load_sources(path)
    assert len(back) == 1
    assert back[0].model_dump() == src.model_dump()


def test_save_sources_writes_unicode_unescaped(tmp_path: Path) -> None:
    src = M.Source(**{**VALID_ENTRY, "name": "Sinteticá Ledger — тест"})
    path = tmp_path / "SOURCES.yaml"
    M.save_sources(path, [src])
    assert "Sinteticá" in path.read_text(encoding="utf-8")


def test_save_sources_rejects_non_source_elements(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a Source"):
        M.save_sources(tmp_path / "SOURCES.yaml", [VALID_ENTRY])  # type: ignore[list-item]


def test_load_sources_rejects_a_mapping_at_the_top_level(tmp_path: Path) -> None:
    path = tmp_path / "SOURCES.yaml"
    path.write_text("id: synthetic_ledger\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a YAML list"):
        M.load_sources(path)


def test_load_sources_reports_the_offending_index(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path / "SOURCES.yaml", [VALID_ENTRY, {**VALID_ENTRY, "id": "b", "status": "blocked"}]
    )
    with pytest.raises(ValueError, match=r"sources\[1\] \(b\)"):
        M.load_sources(path)


def test_load_sources_of_an_empty_file_is_an_empty_registry(tmp_path: Path) -> None:
    path = tmp_path / "SOURCES.yaml"
    path.write_text("", encoding="utf-8")
    assert M.load_sources(path) == []


def test_validate_sources_returns_empty_for_a_valid_file(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY])
    assert M.validate_sources(path) == []


def test_validate_sources_catches_blocked_without_reason_and_verified_without_sha(
    tmp_path: Path,
) -> None:
    entries = [
        {**VALID_ENTRY, "id": "synthetic_blocked", "status": "blocked"},
        {
            **VALID_ENTRY,
            "id": "synthetic_verified",
            "status": "verified",
            "local_path": "data/raw/x.csv",
        },
        {**VALID_ENTRY, "id": "synthetic_ok"},
    ]
    errors = M.validate_sources(write_yaml(tmp_path / "SOURCES.yaml", entries))
    assert len(errors) == 2
    assert errors[0].startswith("sources[0] (synthetic_blocked): ")
    assert "blocked_reason" in errors[0]
    assert errors[1].startswith("sources[1] (synthetic_verified): ")
    assert "sha256" in errors[1]


def test_validate_sources_reports_duplicate_ids(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY, dict(VALID_ENTRY)])
    errors = M.validate_sources(path)
    assert errors == ["sources[1] (synthetic_ledger): duplicate id (first seen at sources[0])"]


def test_validate_sources_warns_about_unknown_keys_but_does_not_fail(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [{**VALID_ENTRY, "sha_256": SHA256_ABC}])
    with pytest.warns(UserWarning, match="sha_256"):
        errors = M.validate_sources(path)
    assert errors == []


def test_update_source_read_modify_writes_one_entry(tmp_path: Path) -> None:
    other = {
        **VALID_ENTRY,
        "id": "synthetic_other",
        "notes": "untouched",
        "synthetic_extra_key": 7,
    }
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY, other])

    updated = M.update_source(
        path,
        "synthetic_ledger",
        status="verified",
        sha256=SHA256_ABC,
        local_path="data/raw/synthetic_ledger.csv",
        bytes=3,
    )
    assert updated.status == "verified"

    reread = M.load_sources(path)
    assert [s.id for s in reread] == ["synthetic_ledger", "synthetic_other"]
    assert reread[0].sha256 == SHA256_ABC
    assert reread[0].bytes == 3
    assert reread[0].name == VALID_ENTRY["name"]  # untouched fields survive
    assert reread[1].notes == "untouched"
    assert reread[1].model_dump()["synthetic_extra_key"] == 7  # extra keys survive


def test_update_source_rejects_an_unknown_id_and_leaves_the_file_alone(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY])
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="no source with id='synthetic_missing'"):
        M.update_source(path, "synthetic_missing", status="partial")
    assert path.read_text(encoding="utf-8") == before


def test_update_source_refuses_an_update_that_would_be_invalid(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY])
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="would make it invalid"):
        M.update_source(path, "synthetic_ledger", status="verified")
    assert path.read_text(encoding="utf-8") == before


def test_update_source_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "SOURCES.yaml", [VALID_ENTRY])
    M.update_source(path, "synthetic_ledger", notes="touched (synthetic)")
    assert [p.name for p in tmp_path.iterdir()] == ["SOURCES.yaml"]


# --------------------------------------------------------------------------------------
# checksums and the fetch log
# --------------------------------------------------------------------------------------


def test_sha256_file_matches_the_published_test_vector(tmp_path: Path) -> None:
    p = tmp_path / "synthetic_abc.bin"
    p.write_bytes(b"abc")
    assert M.sha256_file(p) == SHA256_ABC


def test_sha256_file_is_chunk_size_invariant(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 40
    p = tmp_path / "synthetic_payload.bin"
    p.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert M.sha256_file(p, chunk=7) == expected
    assert M.sha256_file(p, chunk=1 << 20) == expected


def test_sha256_file_rejects_a_nonpositive_chunk(tmp_path: Path) -> None:
    p = tmp_path / "synthetic_abc.bin"
    p.write_bytes(b"abc")
    with pytest.raises(ValueError, match="chunk must be a positive"):
        M.sha256_file(p, chunk=0)


def make_record(**kw) -> M.FetchRecord:
    base = {
        "source_id": "synthetic_ledger",
        "url": "https://synthetic.example/ledger.csv",
        "tool": "httpx",
        "started_at": "2026-01-01T00:00:00.000Z",
        "finished_at": "2026-01-01T00:00:01.000Z",
        "http_status": 200,
        "bytes": 3,
        "sha256": SHA256_ABC,
        "local_path": "data/raw/synthetic_ledger.csv",
        "error": None,
    }
    return M.FetchRecord(**{**base, **kw})


def test_log_fetch_creates_the_directory_and_appends_one_line_per_record(tmp_path: Path) -> None:
    data_dir = tmp_path / "projects" / "synthetic" / "data"
    assert not data_dir.exists()

    M.log_fetch(data_dir, make_record())
    M.log_fetch(data_dir, make_record(http_status=404, bytes=None, sha256=None, error="HTTP 404"))

    log = data_dir / "fetch_log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["sha256"] == SHA256_ABC
    assert first["error"] is None
    assert first["skipped_cached"] is False
    assert second["http_status"] == 404
    assert second["error"] == "HTTP 404"
    assert set(first) == {
        "source_id",
        "url",
        "tool",
        "started_at",
        "finished_at",
        "http_status",
        "bytes",
        "sha256",
        "local_path",
        "error",
        "skipped_cached",
    }


# --------------------------------------------------------------------------------------
# rate limiter
# --------------------------------------------------------------------------------------


class FakeClock:
    """Deterministic monotonic clock whose ``sleep`` simply advances the time."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self.t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.slept.append(seconds)
            self.t += seconds


def test_rate_limiter_spaces_calls_with_a_fake_clock() -> None:
    clock = FakeClock()
    lim = M.RateLimiter(4.0, monotonic=clock.monotonic, sleep=clock.sleep)
    for _ in range(5):
        lim.wait()
    # one free token, then one 1/4 s wait per call
    assert clock.slept == pytest.approx([0.25, 0.25, 0.25, 0.25])
    assert clock.t == pytest.approx(1.0)


def test_rate_limiter_credits_time_that_has_already_passed() -> None:
    clock = FakeClock()
    lim = M.RateLimiter(2.0, monotonic=clock.monotonic, sleep=clock.sleep)
    lim.wait()
    clock.t += 10.0  # a long idle gap outside the limiter
    lim.wait()
    assert clock.slept == []


def test_rate_limiter_burst_allows_a_short_run_then_paces() -> None:
    clock = FakeClock()
    lim = M.RateLimiter(1.0, burst=3.0, monotonic=clock.monotonic, sleep=clock.sleep)
    for _ in range(3):
        lim.wait()
    assert clock.slept == []
    lim.wait()
    assert clock.slept == pytest.approx([1.0])


def test_rate_limiter_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError, match="per_second must be > 0"):
        M.RateLimiter(0.0)
    with pytest.raises(ValueError, match="per_second must be > 0"):
        M.RateLimiter(-1.0)
    with pytest.raises(ValueError, match="burst must be >= 1"):
        M.RateLimiter(1.0, burst=0.5)


def test_rate_limiter_is_thread_safe_and_still_paces() -> None:
    per_second = 100.0
    n_threads, per_thread = 8, 3
    lim = M.RateLimiter(per_second)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(per_thread):
                lim.wait()
        except BaseException as exc:  # pragma: no cover - only on a locking bug
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    assert errors == []
    n_waits = n_threads * per_thread
    # the first call is free, the other n-1 are spaced by 1 / per_second
    assert elapsed >= 0.8 * (n_waits - 1) / per_second

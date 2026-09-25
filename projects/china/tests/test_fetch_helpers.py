"""The fetch helpers, tested without touching the network.

``fetch_files`` is where the project's idempotence lives: a file already on disk is skipped
without a request, which is what makes a resumed 660-file central-bank crawl free. The guard
is exercised here against an injected stand-in for ``fetch``, so that both halves are pinned:
a non-empty file is not requested, and an empty one -- what a truncated transfer leaves --
is. Asserting only that no request happens would pass for the wrong reason, and asserting
that ``ContactNotConfigured`` is raised would pin the placeholder contact string rather than
the guard. A malformed work item, by contrast, must raise rather than being skipped, because
it is a coding error.

The nightlights opt-in is here too: a gigabyte of rasters must not come down by default, and
"by default" is a property of the environment, so it is worth pinning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from china.acquire import _common
from china.acquire._common import fetch_files
from china.acquire.nightlights import OPT_IN_ENV_VAR, _opted_in, download_rasters
from forensics_core.provenance.manifest import FetchRecord, Source

SOURCE = Source(
    id="synthetic_source",
    name="SYNTHETIC source",
    provider="SYNTHETIC",
    url="https://synthetic.example/nothing",
    access="free",
    status="partial",
    notes="synthetic fixture for the tests; never fetched",
)


def test_files_already_on_disk_are_reported_without_a_request(tmp_path: Path):
    held = tmp_path / "raw" / "synthetic/held.txt"
    held.parent.mkdir(parents=True)
    held.write_text("SYNTHETIC", encoding="utf-8")

    result = fetch_files(
        SOURCE,
        tmp_path,
        [("https://synthetic.example/held.txt", "synthetic/held.txt")],
        label="synthetic files",
    )
    assert result.ok
    assert result.skipped_cached
    assert "1 already held" in result.detail
    assert "0 synthetic files fetched" in result.detail
    assert result.paths == (held,)


def _recording_fetch(calls: list[tuple[str, Path]], body: bytes = b"SYNTHETIC BODY"):
    """A stand-in for ``fetch`` that records its calls and writes ``body`` to ``dest``.

    Substituted for the real fetcher so the on-disk guard in :func:`fetch_files` can be
    exercised without a network, and without depending on the contact string being unset.
    """

    def fake_fetch(url: str, dest: Path, **kwargs: object) -> FetchRecord:
        calls.append((url, Path(dest)))
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(body)
        return FetchRecord(
            source_id=str(kwargs.get("source_id", "")),
            url=url,
            tool="synthetic",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:01Z",
            http_status=200,
            bytes=len(body),
            sha256=None,
            local_path=str(dest),
            error=None,
        )

    return fake_fetch


def test_an_empty_file_is_not_treated_as_held(tmp_path: Path, monkeypatch):
    """A zero-byte leftover must be re-requested; a non-empty file must not be.

    An empty file is what a truncated transfer leaves behind. If the guard counted it as
    already held, every family crawl would silently keep the truncated member forever.
    """
    empty = tmp_path / "raw" / "synthetic/empty.txt"
    empty.parent.mkdir(parents=True)
    empty.write_bytes(b"")
    held = tmp_path / "raw" / "synthetic/held.txt"
    held.write_bytes(b"SYNTHETIC")

    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(_common, "fetch", _recording_fetch(calls))

    result = fetch_files(
        SOURCE,
        tmp_path,
        [
            ("https://synthetic.example/empty.txt", "synthetic/empty.txt"),
            ("https://synthetic.example/held.txt", "synthetic/held.txt"),
        ],
        label="synthetic files",
    )

    assert [dest for _url, dest in calls] == [empty], "only the empty file may be requested"
    assert result.ok
    assert result.detail == "1 synthetic files fetched, 1 already held, 0 failed"
    assert empty.read_bytes() == b"SYNTHETIC BODY"
    assert held.read_bytes() == b"SYNTHETIC", "a non-empty file must not be overwritten"


def test_force_re_requests_a_file_that_is_already_held(tmp_path: Path, monkeypatch):
    """``force`` must bypass the on-disk guard, which is the only way to repair a bad file."""
    held = tmp_path / "raw" / "synthetic/held.txt"
    held.parent.mkdir(parents=True)
    held.write_bytes(b"SYNTHETIC STALE")

    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(_common, "fetch", _recording_fetch(calls))

    result = fetch_files(
        SOURCE,
        tmp_path,
        [("https://synthetic.example/held.txt", "synthetic/held.txt")],
        force=True,
        label="synthetic files",
    )

    assert [dest for _url, dest in calls] == [held]
    assert result.ok
    assert result.detail == "1 synthetic files fetched, 0 already held, 0 failed"
    assert held.read_bytes() == b"SYNTHETIC BODY"


def test_an_empty_work_list_succeeds_and_says_so(tmp_path: Path):
    result = fetch_files(SOURCE, tmp_path, [], label="synthetic files")
    assert result.ok
    assert "0 synthetic files fetched, 0 already held, 0 failed" == result.detail


@pytest.mark.parametrize("item", [("only-one",), ("a", "b", "c", "d", "e")])
def test_a_malformed_work_item_raises_rather_than_being_skipped(tmp_path: Path, item):
    with pytest.raises(ValueError, match="2-, 3- or 4-tuple"):
        fetch_files(SOURCE, tmp_path, [item])


def test_the_nightlights_rasters_are_off_by_default(monkeypatch):
    monkeypatch.delenv(OPT_IN_ENV_VAR, raising=False)
    assert _opted_in() is False
    for value in ("", "0", "false", "no", "FALSE"):
        monkeypatch.setenv(OPT_IN_ENV_VAR, value)
        assert _opted_in() is False
    for value in ("1", "yes", "true"):
        monkeypatch.setenv(OPT_IN_ENV_VAR, value)
        assert _opted_in() is True


def test_downloading_rasters_without_the_metadata_fails_with_an_explanation(tmp_path: Path):
    result = download_rasters(SOURCE, tmp_path)
    assert not result.ok
    assert "metadata not acquired yet" in result.detail

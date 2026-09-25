"""The acquisition layer: registry wiring, URL construction and offline idempotence.

Nothing here makes a network request. The tests that exercise
:func:`aaer.acquire._common.fetch_many` replace the one function that would -- the
:func:`forensics_core.provenance.manifest.fetch` name bound inside
:mod:`aaer.acquire._common` -- with :class:`RecordingFetch`, which records its arguments and
writes a synthetic body. That makes "no request was made" an assertion about a call count
rather than an inference from an exception, so the tests keep their meaning once a real
contact string is configured in ``config/forensics.toml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

# Importing every source module is what fills ACQUIRERS, as __main__ does for the CLI; those
# are unused names, hence the suppression. `_common` is imported for use, not for that side
# effect: the fetch double below is patched onto it.
from aaer.acquire import _common, bao_replication, literature, sec_edgar  # noqa: F401
from aaer.acquire import fsds as fsds_acq
from aaer.acquire._common import fetch_many
from aaer.acquire.registry import ACQUIRERS
from forensics_core.provenance.manifest import FetchRecord, load_sources
from forensics_core.provenance.runner import NEEDS_HUMAN, plan

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES = load_sources(DATA_DIR / "SOURCES.yaml")
BY_ID = {s.id: s for s in SOURCES}


@dataclass(frozen=True)
class FakeSource:
    """Stands in for a registry entry where only the id is used."""

    id: str = "synthetic_source"
    sha256: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class FetchCall:
    """One recorded call to the fetch double."""

    url: str
    dest: Path
    force: bool


class RecordingFetch:
    """Drop-in for :func:`forensics_core.provenance.manifest.fetch`; records, never calls out.

    It writes ``body`` to the destination and returns a successful
    :class:`~forensics_core.provenance.manifest.FetchRecord`, so that the caller follows the
    same branch it would after a real HTTP 200. What the tests assert on is
    :attr:`calls`: which URLs were requested, and how many times.
    """

    def __init__(self, body: bytes = b"synthetic body, written by the fetch double") -> None:
        self.calls: list[FetchCall] = []
        self.body = body

    def __call__(
        self,
        url: str,
        dest: Path,
        *,
        project_data_dir: Path,
        source_id: str,
        expected_sha256: str | None = None,
        force: bool = False,
        resume: bool = False,
        max_bytes: int | None = None,
    ) -> FetchRecord:
        dest = Path(dest)
        self.calls.append(FetchCall(url, dest, force))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.body)
        return FetchRecord(
            source_id=source_id,
            url=url,
            tool="RecordingFetch",
            started_at="1970-01-01T00:00:00Z",
            finished_at="1970-01-01T00:00:00Z",
            http_status=200,
            bytes=len(self.body),
            sha256=None,
            local_path=str(dest),
            error=None,
        )


@pytest.fixture
def recording_fetch(monkeypatch: pytest.MonkeyPatch) -> RecordingFetch:
    """Replace the fetch that :mod:`aaer.acquire._common` calls with a recording double."""
    double = RecordingFetch()
    monkeypatch.setattr(_common, "fetch", double)
    return double


# --------------------------------------------------------------------------- registry wiring


def test_every_acquirer_matches_a_registry_id():
    unknown = sorted(set(ACQUIRERS) - set(BY_ID))
    assert unknown == [], f"acquirers registered for ids absent from SOURCES.yaml: {unknown}"


def test_no_acquirer_for_a_source_that_needs_a_human():
    """A gated source must be reported by the runner, never quietly attempted."""
    gated = sorted(sid for sid in ACQUIRERS if BY_ID[sid].access in NEEDS_HUMAN)
    assert gated == []


def test_no_acquirer_for_a_blocked_source():
    blocked = sorted(sid for sid in ACQUIRERS if BY_ID[sid].status == "blocked")
    assert blocked == []


def test_plan_attempts_only_free_reachable_sources():
    attempt, skipped = plan(SOURCES, ACQUIRERS)
    assert len(attempt) + len(skipped) == len(SOURCES)
    assert {s.id for s in attempt} == set(ACQUIRERS)
    for s in attempt:
        assert s.access == "free"
        assert s.status in {"verified", "partial"}


def test_every_skipped_source_carries_a_reason():
    _attempt, skipped = plan(SOURCES, ACQUIRERS)
    assert skipped, "the registry contains gated sources; skipping none would be wrong"
    for _source, reason in skipped:
        assert reason.strip()


def test_the_four_required_families_have_acquirers():
    """The listing, the quarterly zips, the FSDS documentation and the Bao replication files."""
    for required in (
        "aaer_listing_secgov",
        "sec_fsds_quarterly_zips",
        "sec_fsds_readme",
        "bao_analysis_csv",
        "bao_labels_csv",
    ):
        assert required in ACQUIRERS


# ------------------------------------------------------------------------ AAER listing pages


def test_page_count_matches_the_scaffolded_observation():
    """34 pages of 100 rows is exactly what 3,342 items implies."""
    assert sec_edgar.page_count(sec_edgar.AAER_ITEMS_AT_SCAFFOLD) == 34
    assert (
        sec_edgar.page_count(sec_edgar.AAER_ITEMS_AT_SCAFFOLD) == sec_edgar.AAER_PAGES_AT_SCAFFOLD
    )


@pytest.mark.parametrize(
    ("n_items", "expected"), [(0, 0), (1, 1), (100, 1), (101, 2), (3300, 33), (3301, 34)]
)
def test_page_count_rounds_up(n_items, expected):
    assert sec_edgar.page_count(n_items) == expected


def test_page_count_rejects_negative():
    with pytest.raises(ValueError, match="n_items"):
        sec_edgar.page_count(-1)


def test_listing_page_zero_has_no_query_string():
    assert sec_edgar.listing_page_url(0) == sec_edgar.AAER_LISTING_URL
    assert sec_edgar.listing_page_url(7) == f"{sec_edgar.AAER_LISTING_URL}?page=7"
    with pytest.raises(ValueError, match="page"):
        sec_edgar.listing_page_url(-1)


def test_listing_page_paths_sort_in_page_order():
    paths = [sec_edgar.listing_page_path(p) for p in (0, 2, 10, 33)]
    assert paths == sorted(paths), "zero padding must make lexical order equal page order"
    assert paths[0].endswith("page_000.html")


def test_the_listing_re_reads_page_0_even_when_it_is_already_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing_html: str
):
    """The item count only adapts if page 0 is requested again, so it is forced every run.

    A stale page 0 is put on disk carrying no item count. If presence-on-disk applied to it,
    the run would keep the stale copy and fall back to the scaffolded 34 pages. Forcing it
    means the fresh count (9 items in the synthetic fixture, so one page) is what is used.
    """
    double = RecordingFetch(body=listing_html.encode("utf-8"))
    monkeypatch.setattr(_common, "fetch", double)
    raw = tmp_path / "raw" / "aaer_listing"
    raw.mkdir(parents=True)
    (raw / "page_000.html").write_text("<html>a stale copy, no count</html>", encoding="utf-8")

    result = sec_edgar.aaer_listing(FakeSource(), tmp_path)

    assert [c.url for c in double.calls] == [sec_edgar.AAER_LISTING_URL]
    assert double.calls[0].force is True, "page 0 must be forced, not served from disk"
    assert "9 items reported by page 0" in result.detail
    assert "scaffolded count" not in result.detail, "the fallback fired; page 0 was not re-read"
    assert result.ok


# ----------------------------------------------------------------- FSDS quarter arithmetic


def test_quarters_default_range_starts_after_the_empty_placeholder():
    qs = fsds_acq.quarters()
    assert qs[0] == fsds_acq.FSDS_FIRST_QUARTER_WITH_ROWS == "2009q2"
    assert fsds_acq.FSDS_FIRST_QUARTER not in qs, "2009q1 has no rows and is acquired separately"
    assert qs[-1] == fsds_acq.FSDS_LATEST_VERIFIED_QUARTER


def test_quarters_is_contiguous_and_correctly_sized():
    """2009q2 through 2026q2 inclusive is 69 quarters."""
    qs = fsds_acq.quarters()
    assert len(qs) == 69
    assert len(set(qs)) == len(qs)
    assert fsds_acq.quarters("2009q2", "2010q1") == ["2009q2", "2009q3", "2009q4", "2010q1"]
    assert fsds_acq.quarters("2015q3", "2015q3") == ["2015q3"]


def test_quarter_round_trip():
    for q in fsds_acq.quarters("2009q2", "2012q4"):
        year, quarter = fsds_acq.parse_quarter(q)
        assert fsds_acq.format_quarter(year, quarter) == q


@pytest.mark.parametrize("bad", ["2009Q2", "2009q5", "2009q0", "09q2", "", "2009"])
def test_parse_quarter_rejects_malformed_labels(bad):
    with pytest.raises(ValueError, match="quarter"):
        fsds_acq.parse_quarter(bad)


def test_quarters_rejects_a_reversed_range():
    with pytest.raises(ValueError, match="precedes"):
        fsds_acq.quarters("2015q1", "2014q4")


def test_quarter_zip_url_and_path_agree_on_the_label():
    assert fsds_acq.quarter_zip_url("2009q2").endswith("/2009q2.zip")
    assert fsds_acq.quarter_zip_path("2009q2") == "fsds/2009q2.zip"


# -------------------------------------------------------------------- offline idempotence


def test_fetch_many_requests_nothing_for_files_already_on_disk(
    tmp_path: Path, recording_fetch: RecordingFetch
):
    """Presence-based idempotence: existing, non-empty members are held, never re-requested."""
    raw = tmp_path / "raw" / "fsds"
    raw.mkdir(parents=True)
    for name in ("2009q2.zip", "2009q3.zip"):
        (raw / name).write_bytes(b"synthetic bytes, not a real zip")

    result = fetch_many(
        FakeSource(),
        tmp_path,
        [
            ("https://example.invalid/2009q2.zip", "fsds/2009q2.zip"),
            ("https://example.invalid/2009q3.zip", "fsds/2009q3.zip"),
        ],
        unit="quarterly zips",
    )
    assert recording_fetch.calls == [], "a held member must not reach fetch at all"
    assert result.ok
    assert "0 new, 2 already held, 0 failed of 2 quarterly zips" in result.detail
    assert len(result.paths) == 2
    assert (raw / "2009q2.zip").read_bytes() == b"synthetic bytes, not a real zip"


def test_fetch_many_reports_an_empty_input_without_failing(
    tmp_path: Path, recording_fetch: RecordingFetch
):
    result = fetch_many(FakeSource(), tmp_path, [], unit="pages")
    assert recording_fetch.calls == []
    assert result.ok
    assert "0 new, 0 already held, 0 failed of 0 pages" in result.detail


def test_a_zero_byte_file_is_re_fetched(tmp_path: Path, recording_fetch: RecordingFetch):
    """A truncated download is retried: a zero-byte file must not count as present.

    The zero-byte member is requested exactly once and the held member not at all, so the
    assertion is about which requests happened rather than about an exception being raised.
    """
    raw = tmp_path / "raw" / "fsds"
    raw.mkdir(parents=True)
    (raw / "2009q2.zip").write_bytes(b"")
    (raw / "2009q3.zip").write_bytes(b"synthetic bytes, not a real zip")

    truncated = "https://example.invalid/2009q2.zip"
    result = fetch_many(
        FakeSource(),
        tmp_path,
        [
            (truncated, "fsds/2009q2.zip"),
            ("https://example.invalid/2009q3.zip", "fsds/2009q3.zip"),
        ],
        unit="quarterly zips",
    )
    assert [c.url for c in recording_fetch.calls] == [truncated]
    assert recording_fetch.calls[0].dest == raw / "2009q2.zip"
    assert result.ok
    assert "1 new, 1 already held, 0 failed of 2 quarterly zips" in result.detail
    assert (raw / "2009q2.zip").stat().st_size > 0, "the truncated file must be replaced"


def test_force_re_requests_a_member_that_is_already_held(
    tmp_path: Path, recording_fetch: RecordingFetch
):
    """``--force`` is the documented way to refresh a multi-file source; it must reach fetch."""
    raw = tmp_path / "raw" / "aaer_listing"
    raw.mkdir(parents=True)
    (raw / "page_000.html").write_bytes(b"<html>an older copy of the listing</html>")

    result = fetch_many(
        FakeSource(),
        tmp_path,
        [("https://example.invalid/listing", "aaer_listing/page_000.html")],
        force=True,
        unit="pages",
    )
    assert len(recording_fetch.calls) == 1
    assert recording_fetch.calls[0].force is True
    assert result.ok
    assert "1 new, 0 already held, 0 failed of 1 pages" in result.detail


def test_a_challenge_page_served_with_http_200_is_reported_as_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """An interstitial body must not be recorded as a successful acquisition."""
    double = RecordingFetch(body=b"<html><title>Just a moment...</title></html>")
    monkeypatch.setattr(_common, "fetch", double)

    result = _common.fetch_file(
        FakeSource(),
        tmp_path,
        "https://example.invalid/policy",
        "sec_policy/webmaster-faq.html",
    )
    assert len(double.calls) == 1
    assert not result.ok, "a 200 carrying an interstitial is not an acquisition"
    assert "Just a moment" in result.detail
    assert "SOURCES.yaml" in result.detail, "the detail must say the registry entry is now wrong"


def test_a_genuine_html_body_is_not_mistaken_for_a_challenge_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    double = RecordingFetch(
        body=b"<html><body>Current max request rate: 10 requests/second.</body></html>"
    )
    monkeypatch.setattr(_common, "fetch", double)

    result = _common.fetch_file(
        FakeSource(),
        tmp_path,
        "https://example.invalid/policy",
        "sec_policy/webmaster-faq.html",
    )
    assert result.ok
    assert "sec_policy/webmaster-faq.html" in result.detail


def test_a_non_html_body_is_not_sniffed_for_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A zip whose bytes happen to spell a marker is not an interstitial; only HTML is sniffed."""
    double = RecordingFetch(body=b"PK\x03\x04 Just a moment, this is compressed data")
    monkeypatch.setattr(_common, "fetch", double)

    result = _common.fetch_file(
        FakeSource(), tmp_path, "https://example.invalid/2009q2.zip", "fsds/2009q2.zip"
    )
    assert result.ok


def test_challenge_marker_returns_none_for_a_missing_file(tmp_path: Path):
    assert _common.challenge_marker(tmp_path / "absent.html") is None

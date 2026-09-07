"""fetch(): contact policy, never-fetch-twice, resume, size limits, logging and registry.

Every request in this file is served by :class:`httpx.MockTransport`; the transport is
injected, counted, and no test can reach the network. The repository root, its
``config/forensics.toml`` and the project ``data/`` directory are synthetic and live in
pytest's ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import yaml

from forensics_core import config
from forensics_core.provenance import manifest as M

URL = "https://synthetic.example/ledger.csv"
SOURCE_ID = "synthetic_ledger"
#: Where the download lands, written the way the registry records it: POSIX-style and
#: relative to the project directory (INTERFACES.md: "local_path is relative to the project
#: directory"), never the absolute path of whichever machine ran the fetch.
DEST_RELPATH = "data/raw/synthetic_ledger.csv"
BODY = b"synthetic_col_a,synthetic_col_b\n1,2\n3,4\n" * 8
BODY_SHA256 = hashlib.sha256(BODY).hexdigest()

REAL_CONTACT = "Synthetic Test Runner tests@example.invalid"
PLACEHOLDER_CONTACT = "REPLACE_ME your.name@example.org"

CONFIG_TEMPLATE = """\
[http]
contact = "{contact}"
user_agent_prefix = "forensic-stats-test/0.0"
default_timeout_seconds = 5

[rate_limits]
default = 500.0
"synthetic.example" = 400.0

[cache]
never_refetch = {never_refetch}
"""

REGISTRY_ENTRY = {
    "id": SOURCE_ID,
    "name": "Synthetic Ledger Extract",
    "provider": "Synthetic Statistics Office",
    "url": URL,
    "access": "free",
    "status": "unverified",
    "notes": "synthetic fixture; nothing fetched yet",
}


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every request it was asked to serve."""

    def __init__(self, responder) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return responder(request)

        super().__init__(handler)


def ok_transport(status: int = 200, body: bytes = BODY) -> RecordingTransport:
    return RecordingTransport(lambda request: httpx.Response(status, content=body))


def write_config(root: Path, contact: str = REAL_CONTACT, *, never_refetch: bool = True) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "forensics.toml").write_text(
        CONFIG_TEMPLATE.format(contact=contact, never_refetch=str(never_refetch).lower()),
        encoding="utf-8",
    )
    config.load_config.cache_clear()
    M.reset_rate_limiters()


@dataclass
class Project:
    root: Path
    data: Path
    dest: Path
    registry: Path
    log: Path

    @property
    def project_dir(self) -> Path:
        """The project directory: ``local_path`` in the registry is relative to this."""
        return self.data.parent

    def resolve(self, local_path: str) -> Path:
        """What a consumer does with a registry entry: ``project_dir / entry.local_path``."""
        return self.project_dir / local_path

    def log_lines(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def entry(self) -> M.Source:
        return M.load_sources(self.registry)[0]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "synthetic_repo"
    monkeypatch.setenv("FORENSICS_ROOT", str(root))
    write_config(root)
    yield root
    config.load_config.cache_clear()
    M.reset_rate_limiters()


@pytest.fixture
def project(repo: Path) -> Project:
    data = repo / "projects" / "synthetic_project" / "data"
    data.mkdir(parents=True)
    registry = data / "SOURCES.yaml"
    registry.write_text(yaml.safe_dump([REGISTRY_ENTRY], sort_keys=False), encoding="utf-8")
    return Project(
        root=repo,
        data=data,
        dest=data / "raw" / "synthetic_ledger.csv",
        registry=registry,
        log=data / "fetch_log.jsonl",
    )


def do_fetch(project: Project, transport: RecordingTransport, **kw) -> M.FetchRecord:
    return M.fetch(
        URL,
        project.dest,
        project_data_dir=project.data,
        source_id=SOURCE_ID,
        transport=transport,
        **kw,
    )


# --------------------------------------------------------------------------------------
# HARD RULE 6: no contact, no network
# --------------------------------------------------------------------------------------


def test_placeholder_contact_blocks_the_fetch_before_any_request(project: Project) -> None:
    write_config(project.root, PLACEHOLDER_CONTACT)
    transport = ok_transport()

    with pytest.raises(config.ContactNotConfigured, match="placeholder contact"):
        do_fetch(project, transport)

    assert transport.requests == []
    assert not project.log.exists()  # nothing is logged: the attempt never started
    assert not project.dest.exists()
    assert project.entry().status == "unverified"

    # ... and with a real contact configured, the very same call goes through
    write_config(project.root, REAL_CONTACT)
    rec = do_fetch(project, transport)
    assert len(transport.requests) == 1
    assert rec.error is None
    assert project.dest.read_bytes() == BODY


def test_user_agent_carries_the_configured_contact(project: Project) -> None:
    transport = ok_transport()
    do_fetch(project, transport)
    ua = transport.requests[0].headers["user-agent"]
    assert "forensic-stats-test/0.0" in ua
    assert REAL_CONTACT in ua
    assert f"source={SOURCE_ID}" in ua


def test_explicit_headers_override_the_defaults(project: Project) -> None:
    transport = ok_transport()
    do_fetch(project, transport, headers={"User-Agent": "synthetic-agent/1.0", "X-Test": "yes"})
    headers = transport.requests[0].headers
    assert headers["user-agent"] == "synthetic-agent/1.0"
    assert headers["x-test"] == "yes"


# --------------------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------------------


def test_successful_fetch_writes_file_logs_once_and_marks_the_source_verified(
    project: Project,
) -> None:
    transport = ok_transport()
    rec = do_fetch(project, transport)

    assert rec.http_status == 200
    assert rec.error is None
    assert rec.skipped_cached is False
    assert rec.sha256 == BODY_SHA256
    assert rec.bytes == len(BODY)
    assert rec.local_path == DEST_RELPATH
    assert rec.started_at <= rec.finished_at

    assert project.dest.read_bytes() == BODY
    assert not project.dest.with_suffix(".csv.part").exists()

    lines = project.log_lines()
    assert len(lines) == 1
    assert lines[0]["sha256"] == BODY_SHA256
    assert lines[0]["source_id"] == SOURCE_ID
    assert lines[0]["skipped_cached"] is False

    entry = project.entry()
    assert entry.status == "verified"
    assert entry.sha256 == BODY_SHA256
    assert entry.bytes == len(BODY)
    assert entry.local_path == DEST_RELPATH
    assert entry.http_status == 200
    assert entry.fetched_at


def test_local_path_is_relative_to_the_project_and_resolves_back_to_the_file(
    project: Project,
) -> None:
    """The registry enters git and the raw data does not, so local_path must not be an
    absolute path from whichever machine ran the fetch: project_dir / local_path is the
    contract a consumer relies on."""
    rec = do_fetch(project, ok_transport())
    entry = project.entry()

    for recorded in (rec.local_path, entry.local_path):
        assert recorded == DEST_RELPATH
        assert not Path(recorded).is_absolute()
        assert "\\" not in recorded  # POSIX separators, so a Windows-written registry travels
        assert str(project.root) not in recorded
        assert project.resolve(recorded).read_bytes() == BODY

    # the skipped-cache record says the same thing as the completed one
    second = do_fetch(project, ok_transport())
    assert second.skipped_cached is True
    assert second.local_path == DEST_RELPATH


def test_fetch_outside_the_project_directory_records_an_absolute_path(
    project: Project, tmp_path: Path
) -> None:
    """A destination with no relative form is recorded absolutely rather than wrongly."""
    outside = tmp_path / "outside_the_project" / "synthetic_ledger.csv"
    rec = M.fetch(
        URL,
        outside,
        project_data_dir=project.data,
        source_id=SOURCE_ID,
        transport=ok_transport(),
    )
    assert rec.error is None
    assert Path(rec.local_path).is_absolute()
    assert Path(rec.local_path).read_bytes() == BODY


def test_fetch_without_a_registry_entry_raises_before_any_request(project: Project) -> None:
    """Nothing enters a pipeline without a SOURCES.yaml entry: an unregistered source is a
    caller error, not a warning issued after the bytes have landed."""
    transport = ok_transport()
    with pytest.raises(ValueError, match="no source with id='synthetic_unregistered'"):
        M.fetch(
            URL,
            project.dest,
            project_data_dir=project.data,
            source_id="synthetic_unregistered",
            transport=transport,
        )
    assert transport.requests == []
    assert not project.dest.exists()
    assert not project.log.exists()

    project.registry.unlink()  # ... and the same when there is no registry at all
    with pytest.raises(ValueError, match="does not exist"):
        do_fetch(project, transport)
    assert transport.requests == []
    assert not project.dest.exists()


def test_require_registry_false_allows_a_one_off_download(project: Project) -> None:
    project.registry.unlink()
    transport = ok_transport()
    rec = do_fetch(project, transport, require_registry=False)
    assert rec.error is None
    assert project.dest.read_bytes() == BODY
    assert len(project.log_lines()) == 1  # logged, just not registered
    assert not project.registry.exists()


# --------------------------------------------------------------------------------------
# never fetch twice
# --------------------------------------------------------------------------------------


def test_second_fetch_of_the_same_source_is_skipped_and_makes_zero_requests(
    project: Project,
) -> None:
    transport = ok_transport()
    first = do_fetch(project, transport)
    assert first.skipped_cached is False
    assert len(transport.requests) == 1

    second = do_fetch(project, transport)
    assert len(transport.requests) == 1  # no new request at all
    assert second.skipped_cached is True
    assert second.http_status is None
    assert second.error is None
    assert second.sha256 == BODY_SHA256

    lines = project.log_lines()
    assert len(lines) == 2  # every attempt is logged, skipped ones included
    assert lines[1]["skipped_cached"] is True


def test_force_refetches_even_when_the_digest_matches(project: Project) -> None:
    transport = ok_transport()
    do_fetch(project, transport)
    rec = do_fetch(project, transport, force=True)
    assert len(transport.requests) == 2
    assert rec.skipped_cached is False
    assert rec.http_status == 200


def test_a_changed_local_file_is_refetched(project: Project) -> None:
    transport = ok_transport()
    do_fetch(project, transport)
    project.dest.write_bytes(b"synthetic tampering")
    rec = do_fetch(project, transport)
    assert len(transport.requests) == 2  # digest no longer matches the registry
    assert rec.skipped_cached is False
    assert project.dest.read_bytes() == BODY


def test_never_refetch_false_disables_the_cache(project: Project) -> None:
    transport = ok_transport()
    do_fetch(project, transport)
    write_config(project.root, REAL_CONTACT, never_refetch=False)
    rec = do_fetch(project, transport)
    assert len(transport.requests) == 2
    assert rec.skipped_cached is False


# --------------------------------------------------------------------------------------
# HTTP errors: recorded, never raised
# --------------------------------------------------------------------------------------


def test_403_marks_the_source_blocked_with_a_reason(project: Project) -> None:
    transport = ok_transport(status=403, body=b"forbidden")
    rec = do_fetch(project, transport)

    assert rec.http_status == 403
    assert rec.error == "HTTP 403"
    assert rec.sha256 is None
    assert not project.dest.exists()

    assert len(project.log_lines()) == 1
    entry = project.entry()
    assert entry.status == "blocked"
    assert entry.blocked_reason == "HTTP 403"
    assert entry.http_status == 403


def test_401_marks_the_source_blocked(project: Project) -> None:
    rec = do_fetch(project, ok_transport(status=401, body=b""))
    assert rec.error == "HTTP 401"
    assert project.entry().blocked_reason == "HTTP 401"


def test_404_marks_the_source_unverified_and_keeps_the_earlier_note(project: Project) -> None:
    rec = do_fetch(project, ok_transport(status=404, body=b"missing"))

    assert rec.http_status == 404
    assert rec.error == "HTTP 404"
    entry = project.entry()
    assert entry.status == "unverified"
    assert "synthetic fixture; nothing fetched yet" in entry.notes  # earlier note kept
    assert "HTTP 404" in entry.notes
    assert URL in entry.notes
    assert len(project.log_lines()) == 1


def test_402_payment_required_marks_the_source_blocked(project: Project) -> None:
    """402 is the literal paywall status; it belongs with 401/403, not in the residual
    'partial' bucket (INTERFACES.md: 'blocked with reason on 401/403/paywall')."""
    rec = do_fetch(project, ok_transport(status=402, body=b"pay up"))
    assert rec.error == "HTTP 402"
    entry = project.entry()
    assert entry.status == "blocked"
    assert entry.blocked_reason == "HTTP 402"


def test_451_marks_the_source_blocked(project: Project) -> None:
    rec = do_fetch(project, ok_transport(status=451, body=b"unavailable for legal reasons"))
    assert rec.error == "HTTP 451"
    assert project.entry().status == "blocked"
    assert project.entry().blocked_reason == "HTTP 451"


def test_a_4xx_on_a_paywalled_entry_is_blocked_rather_than_partial(project: Project) -> None:
    M.update_source(project.registry, SOURCE_ID, access="paywalled")
    rec = do_fetch(project, ok_transport(status=429, body=b"slow down"))
    assert rec.error == "HTTP 429"
    entry = project.entry()
    assert entry.status == "blocked"
    assert entry.blocked_reason is not None
    assert "429" in entry.blocked_reason


def test_500_marks_the_source_partial(project: Project) -> None:
    rec = do_fetch(project, ok_transport(status=500, body=b"boom"))
    assert rec.error == "HTTP 500"
    entry = project.entry()
    assert entry.status == "partial"
    assert "HTTP 500" in entry.notes


def test_a_transport_exception_is_recorded_rather_than_raised(project: Project) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic transport failure")

    transport = RecordingTransport(explode)
    rec = do_fetch(project, transport)

    assert rec.http_status is None
    assert rec.error is not None
    assert "ConnectError" in rec.error
    assert "synthetic transport failure" in rec.error
    assert len(project.log_lines()) == 1
    assert project.entry().status == "partial"


# --------------------------------------------------------------------------------------
# the registry entry says what is true *now*
# --------------------------------------------------------------------------------------


def test_a_failed_refetch_does_not_un_verify_an_intact_file(project: Project) -> None:
    """A transient failure must not downgrade an entry whose file is still on disk and still
    matches the recorded digest: the never-fetch-twice cache would then freeze the wrong
    status in place forever."""
    do_fetch(project, ok_transport())
    good = project.entry()
    assert good.status == "verified"

    rec = do_fetch(project, ok_transport(status=500, body=b"boom"), force=True)
    assert rec.error == "HTTP 500"

    entry = project.entry()
    assert entry.status == "verified"  # the data on disk is unchanged and still correct
    assert entry.sha256 == good.sha256
    assert entry.bytes == good.bytes
    assert entry.local_path == good.local_path
    assert entry.http_status == 500  # ... but the failed attempt is recorded
    assert "HTTP 500" in entry.notes
    assert project.dest.read_bytes() == BODY


def test_a_failed_fetch_downgrades_when_the_recorded_file_is_gone(project: Project) -> None:
    do_fetch(project, ok_transport())
    project.dest.unlink()  # the verified file is no longer there

    rec = do_fetch(project, ok_transport(status=500, body=b"boom"))
    assert rec.error == "HTTP 500"
    assert project.entry().status == "partial"


def test_a_success_after_a_block_clears_the_stale_blocked_reason(project: Project) -> None:
    M.update_source(project.registry, SOURCE_ID, status="blocked", blocked_reason="HTTP 403")
    assert project.entry().blocked_reason == "HTTP 403"

    rec = do_fetch(project, ok_transport())
    assert rec.error is None
    entry = project.entry()
    assert entry.status == "verified"
    assert entry.blocked_reason is None  # a refusal that is no longer true is not advertised


# --------------------------------------------------------------------------------------
# resume, size limit, digest check
# --------------------------------------------------------------------------------------


def ranged_transport() -> RecordingTransport:
    """Serve byte ranges (RFC 7233): 206 with the remainder when a Range is requested."""

    def responder(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        if rng is None:
            return httpx.Response(200, content=BODY)
        start = int(rng.removeprefix("bytes=").rstrip("-"))
        return httpx.Response(
            206,
            content=BODY[start:],
            headers={"Content-Range": f"bytes {start}-{len(BODY) - 1}/{len(BODY)}"},
        )

    return RecordingTransport(responder)


def test_resume_sends_a_range_header_and_appends_the_remainder(project: Project) -> None:
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(BODY[:20])

    transport = ranged_transport()
    rec = do_fetch(project, transport, resume=True)

    assert transport.requests[0].headers["range"] == "bytes=20-"
    assert rec.http_status == 206
    assert rec.error is None
    assert project.dest.read_bytes() == BODY
    assert rec.sha256 == BODY_SHA256
    assert not part.exists()
    assert project.entry().status == "verified"


def test_resume_restarts_when_the_server_ignores_the_range(project: Project) -> None:
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"synthetic garbage from an earlier attempt")

    transport = ok_transport()  # always answers 200 with the whole body
    rec = do_fetch(project, transport, resume=True)

    assert transport.requests[0].headers.get("range") is not None
    assert rec.http_status == 200
    assert project.dest.read_bytes() == BODY  # restarted, not appended
    assert rec.sha256 == BODY_SHA256


def test_without_resume_an_existing_part_file_is_overwritten(project: Project) -> None:
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"stale synthetic bytes")

    transport = ranged_transport()
    rec = do_fetch(project, transport)

    assert transport.requests[0].headers.get("range") is None
    assert rec.http_status == 200
    assert project.dest.read_bytes() == BODY


def test_a_206_whose_content_range_disagrees_with_the_request_is_refused(
    project: Project,
) -> None:
    """RFC 7233 section 4.1: a 206 payload is placed according to its Content-Range. A server
    (or a stale .part file from another URL) that answers with a different offset must not be
    concatenated blindly and then hashed as if the result were the real file."""
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(BODY[:30])

    def responder(request: httpx.Request) -> httpx.Response:
        # asked for bytes=30-, answers with a range that starts ten bytes earlier
        return httpx.Response(
            206,
            content=BODY[10:],
            headers={"Content-Range": f"bytes 10-{len(BODY) - 1}/{len(BODY)}"},
        )

    transport = RecordingTransport(responder)
    rec = do_fetch(project, transport, resume=True)

    assert transport.requests[0].headers["range"] == "bytes=30-"
    assert rec.error is not None
    assert "Content-Range" in rec.error
    assert rec.sha256 is None
    assert not project.dest.exists()  # nothing corrupt was promoted
    assert project.entry().status == "partial"
    assert part.read_bytes() == BODY[:30]  # the good prefix is left alone


def test_a_206_without_a_content_range_is_refused(project: Project) -> None:
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(BODY[:30])

    transport = RecordingTransport(lambda request: httpx.Response(206, content=BODY[30:]))
    rec = do_fetch(project, transport, resume=True)

    assert rec.error is not None
    assert "Content-Range" in rec.error
    assert not project.dest.exists()
    assert project.entry().status != "verified"


def test_a_206_that_restarts_at_zero_overwrites_the_part_file(project: Project) -> None:
    """first == 0 means the server is sending the whole representation: restart, don't append."""
    part = project.dest.with_suffix(".csv.part")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"synthetic garbage from an earlier attempt")

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206,
            content=BODY,
            headers={"Content-Range": f"bytes 0-{len(BODY) - 1}/{len(BODY)}"},
        )

    rec = do_fetch(project, RecordingTransport(responder), resume=True)
    assert rec.error is None
    assert project.dest.read_bytes() == BODY
    assert rec.sha256 == BODY_SHA256


@pytest.mark.parametrize("status", [201, 202, 204, 205, 304])
def test_a_2xx_or_3xx_that_is_not_200_or_206_is_not_a_download(
    project: Project, status: int
) -> None:
    """A body-less or unexpected success status must never be recorded as verified: the
    empty-file digest e3b0c442... written as an integrity claim is exactly the failure this
    module exists to prevent."""
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    rec = do_fetch(project, RecordingTransport(lambda request: httpx.Response(status)))

    assert rec.http_status == status
    assert rec.error is not None
    assert f"unexpected HTTP {status}" in rec.error
    assert rec.sha256 is None
    assert not project.dest.exists()
    assert not project.dest.with_suffix(".csv.part").exists()

    entry = project.entry()
    assert entry.status == "partial"
    assert entry.sha256 != empty_sha256
    assert entry.sha256 is None
    assert len(project.log_lines()) == 1


def test_an_empty_200_body_is_refused_unless_allow_empty(project: Project) -> None:
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    rec = do_fetch(project, ok_transport(body=b""))

    assert rec.http_status == 200
    assert rec.error is not None
    assert "empty response body" in rec.error
    assert rec.sha256 is None
    assert not project.dest.exists()
    assert project.entry().status == "partial"

    # ... and the caller can still opt in for a genuinely empty resource
    rec2 = do_fetch(project, ok_transport(body=b""), allow_empty=True)
    assert rec2.error is None
    assert rec2.bytes == 0
    assert rec2.sha256 == empty_sha256
    assert project.dest.read_bytes() == b""
    assert project.entry().status == "verified"


def test_a_body_shorter_than_content_length_is_refused(project: Project) -> None:
    """A truncated transfer must not be hashed and recorded as the real file."""

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=BODY[:100], headers={"Content-Length": str(len(BODY))})

    rec = do_fetch(project, RecordingTransport(responder))
    assert rec.error is not None
    assert "Content-Length" in rec.error
    assert str(len(BODY)) in rec.error
    assert rec.sha256 is None
    assert not project.dest.exists()
    assert project.entry().status == "partial"


def test_max_bytes_aborts_the_download_and_is_logged(project: Project) -> None:
    transport = ok_transport()
    rec = do_fetch(project, transport, max_bytes=len(BODY) - 1)

    assert rec.error is not None
    assert "exceeded max_bytes" in rec.error
    assert rec.sha256 is None
    assert not project.dest.exists()
    assert not project.dest.with_suffix(".csv.part").exists()

    lines = project.log_lines()
    assert len(lines) == 1
    assert "exceeded max_bytes" in lines[0]["error"]
    entry = project.entry()
    assert entry.status == "partial"
    assert "exceeded max_bytes" in entry.notes


def test_max_bytes_large_enough_lets_the_download_through(project: Project) -> None:
    rec = do_fetch(project, ok_transport(), max_bytes=len(BODY))
    assert rec.error is None
    assert project.dest.read_bytes() == BODY


def test_a_digest_mismatch_keeps_the_file_as_bad_and_does_not_verify(project: Project) -> None:
    wrong = "0" * 64
    rec = do_fetch(project, ok_transport(), expected_sha256=wrong)

    assert rec.error is not None
    assert "sha256 mismatch" in rec.error
    assert BODY_SHA256 in rec.error
    bad = project.dest.with_suffix(".csv.bad")
    assert bad.read_bytes() == BODY
    assert not project.dest.exists()
    assert rec.local_path == DEST_RELPATH + ".bad"
    assert project.resolve(rec.local_path) == bad
    assert project.entry().status == "partial"


def test_a_malformed_expected_digest_raises_instead_of_quarantining_a_good_file(
    project: Project,
) -> None:
    """A typo'd expected digest is bad caller input, not evidence against the download."""
    transport = ok_transport()
    for wrong in ("not-a-digest", BODY_SHA256[:-1], BODY_SHA256 + "0"):
        with pytest.raises(ValueError, match="64 hexadecimal characters"):
            do_fetch(project, transport, expected_sha256=wrong)
    assert transport.requests == []
    assert not project.dest.exists()
    assert not project.dest.with_suffix(".csv.bad").exists()


def test_a_matching_expected_digest_verifies(project: Project) -> None:
    rec = do_fetch(project, ok_transport(), expected_sha256=BODY_SHA256)
    assert rec.error is None
    assert project.entry().status == "verified"


# --------------------------------------------------------------------------------------
# input validation and rate limiting
# --------------------------------------------------------------------------------------


def test_fetch_rejects_a_non_http_url(project: Project) -> None:
    transport = ok_transport()
    for bad_url in ("ftp://synthetic.example/ledger.csv", "this is not a url", "/relative/path"):
        with pytest.raises(ValueError, match="absolute http"):
            M.fetch(
                bad_url,
                project.dest,
                project_data_dir=project.data,
                source_id=SOURCE_ID,
                transport=transport,
            )
    assert transport.requests == []
    assert not project.log.exists()


def test_a_bad_url_is_rejected_even_when_a_cached_copy_exists(project: Project) -> None:
    """Validation must not sit behind the never-fetch-twice short circuit: whether a nonsense
    URL raises cannot depend on what happens to be on disk."""
    do_fetch(project, ok_transport())  # dest now exists and matches the registry digest
    assert project.entry().status == "verified"
    before = len(project.log_lines())

    with pytest.raises(ValueError, match="absolute http"):
        M.fetch(
            "this is not a url",
            project.dest,
            project_data_dir=project.data,
            source_id=SOURCE_ID,
            transport=ok_transport(),
        )
    assert len(project.log_lines()) == before  # no skipped_cached line for a nonsense URL


class CountingLimiter(M.RateLimiter):
    """RateLimiter that records every wait() instead of sleeping."""

    def __init__(self) -> None:
        super().__init__(1000.0)
        self.waits = 0

    def wait(self) -> None:
        self.waits += 1


def test_fetch_paces_every_request_through_the_rate_limiter(project: Project, monkeypatch) -> None:
    seen: list[str] = []
    counter = CountingLimiter()

    def spy(host: str, **kw) -> M.RateLimiter:
        seen.append(host)
        return counter

    monkeypatch.setattr(M, "get_rate_limiter", spy)

    do_fetch(project, ok_transport())
    assert seen == ["synthetic.example"]  # resolved for the URL's host
    assert counter.waits == 1  # and actually used to pace the request

    do_fetch(project, ok_transport(), force=True)
    assert counter.waits == 2

    # a skipped (cached) fetch makes no request, so it consumes no token
    rec = do_fetch(project, ok_transport())
    assert rec.skipped_cached is True
    assert counter.waits == 2


def test_an_injected_limiter_bypasses_the_per_host_cache(project: Project, monkeypatch) -> None:
    def boom(host: str, **kw) -> M.RateLimiter:
        raise AssertionError("get_rate_limiter must not be consulted when limiter= is given")

    monkeypatch.setattr(M, "get_rate_limiter", boom)
    limiter = CountingLimiter()
    rec = do_fetch(project, ok_transport(), limiter=limiter)
    assert rec.error is None
    assert limiter.waits == 1


def test_get_rate_limiter_reads_the_configured_rate_and_caches_per_host(repo: Path) -> None:
    a = M.get_rate_limiter("synthetic.example")
    assert a.per_second == 400.0
    assert M.get_rate_limiter("synthetic.example") is a  # cached

    other = M.get_rate_limiter("other.example")
    assert other.per_second == 500.0  # the "default" entry
    assert other is not a

    write_config(repo, REAL_CONTACT)  # clears the cache
    assert M.get_rate_limiter("synthetic.example") is not a


def test_get_rate_limiter_rejects_an_empty_host(repo: Path) -> None:
    with pytest.raises(ValueError, match="host must be a non-empty string"):
        M.get_rate_limiter("")

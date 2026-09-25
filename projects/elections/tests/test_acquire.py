"""The acquisition wiring. Nothing here touches the network.

The bug this file exists to prevent has already happened once: acquirers were registered under
ids (``dkobak_2011_csv``, ``dkobak_2018_csv``) that do not appear in ``data/SOURCES.yaml``, so
they were silently unreachable and the runner reported the real entries as having no acquirer.
:func:`test_every_registered_id_exists_in_the_registry` is the check that would have caught it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from elections.acquire import ACQUIRERS, controls
from elections.acquire.__main__ import DATA_DIR
from elections.acquire._common import CHALLENGE_MARKERS, challenge_marker, held_with_digest
from elections.acquire.registry import AcquireResult
from forensics_core.provenance.manifest import load_sources, update_source
from forensics_core.provenance.runner import NEEDS_HUMAN, plan

SOURCES_PATH = DATA_DIR / "SOURCES.yaml"


@pytest.fixture(scope="module")
def sources():
    return load_sources(SOURCES_PATH)


@pytest.fixture(scope="module")
def source_ids(sources):
    return {s.id for s in sources}


def test_the_registry_file_is_where_the_shim_looks_for_it():
    assert SOURCES_PATH.exists()
    assert DATA_DIR.name == "data"
    assert DATA_DIR.parent.name == "elections"


def test_every_registered_id_exists_in_the_registry(source_ids):
    unknown = sorted(set(ACQUIRERS) - source_ids)
    assert unknown == [], f"acquirers registered for ids not in SOURCES.yaml: {unknown}"


def test_no_acquirer_is_registered_for_a_source_a_machine_cannot_fetch(sources):
    """Blocked, unverified and human-gated entries must be reported, not attempted."""
    by_id = {s.id: s for s in sources}
    for source_id in ACQUIRERS:
        source = by_id[source_id]
        assert source.status in {"verified", "partial"}, f"{source_id} is {source.status}"
        assert source.access not in NEEDS_HUMAN, f"{source_id} needs a human"


def test_the_two_primary_files_have_acquirers(source_ids):
    """Without these the project has no data at all."""
    for source_id in ("dkobak_elections_2011", "dkobak_elections_2018"):
        assert source_id in source_ids
        assert source_id in ACQUIRERS


def test_the_false_positive_control_data_has_an_acquirer():
    """Poland 2010 and Spain 2011 are the Tier 2 check; without them there is no control."""
    assert "figshare_kobak_aoas2016_supp" in ACQUIRERS


def test_every_acquirer_accepts_the_runner_force_flag():
    from forensics_core.provenance.runner import _accepts_force

    not_forceable = sorted(name for name, fn in ACQUIRERS.items() if not _accepts_force(fn))
    assert not_forceable == []


def test_every_acquirer_documents_itself():
    undocumented = sorted(name for name, fn in ACQUIRERS.items() if not (fn.__doc__ or "").strip())
    assert undocumented == []


def test_registering_the_same_id_twice_is_an_error():
    from elections.acquire.registry import register

    with pytest.raises(ValueError, match="duplicate acquirer"):
        register("dkobak_elections_2011")(lambda source, data_dir: None)


def test_the_plan_attempts_every_acquirable_source_and_skips_the_rest(sources):
    attempt, skipped = plan(sources, ACQUIRERS, None)
    assert {s.id for s in attempt} == set(ACQUIRERS)
    assert len(attempt) + len(skipped) == len(sources)
    reasons = {s.id: reason for s, reason in skipped}
    assert "cec_vybory_izbirkom_live" in reasons
    assert reasons["cec_vybory_izbirkom_live"].startswith("blocked:")
    assert "DNS" in reasons["cec_vybory_izbirkom_live"]
    assert reasons["datahub_2011_duma"].startswith("unverified:")


def test_dry_run_makes_no_request_and_exits_clean(capsys):
    """Also the proof that the module-level wiring imports and resolves."""
    from elections.acquire.__main__ import main

    assert main(["--all", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"{len(ACQUIRERS)} sources to attempt" in out
    for source_id in ACQUIRERS:
        assert f"[dry] {source_id}:" in out


def test_list_marks_exactly_the_sources_with_acquirers(capsys, sources):
    from elections.acquire.__main__ import main

    assert main(["--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    # the last line is the legend, "  * = an acquirer is implemented for this source"
    marked = {
        line.split()[1] for line in lines if line.startswith("  * ") and line.split()[1] != "="
    }
    assert marked == set(ACQUIRERS)
    assert f"{len(sources)} sources" in lines[0]


def test_an_unknown_id_is_an_error_not_a_silent_no_op(capsys):
    from elections.acquire.__main__ import main

    assert main(["no_such_source"]) == 1
    assert "is not in" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# the two guards in _common
# --------------------------------------------------------------------------------------


def test_held_with_digest_is_true_only_for_the_matching_file(tmp_path: Path):
    target = tmp_path / "payload.bin"
    target.write_bytes(b"synthetic payload")
    # sha256 of b"synthetic payload", computed by hashlib at test time
    import hashlib

    digest = hashlib.sha256(b"synthetic payload").hexdigest()
    assert held_with_digest(target, digest)
    assert held_with_digest(target, digest.upper())
    assert not held_with_digest(target, "0" * 64)
    assert not held_with_digest(tmp_path / "absent.bin", digest)


def test_challenge_marker_finds_an_interstitial_and_ignores_real_content(tmp_path: Path):
    challenge = tmp_path / "challenge.html"
    challenge.write_text("<title>Checking your browser - reCAPTCHA</title>", encoding="utf-8")
    assert challenge_marker(challenge) in CHALLENGE_MARKERS

    article = tmp_path / "article.html"
    article.write_text("<h1>Statistical detection of systematic election irregularities</h1>")
    assert challenge_marker(article) is None


def test_challenge_marker_survives_a_binary_body(tmp_path: Path):
    binary = tmp_path / "archive.7z"
    binary.write_bytes(bytes(range(256)) * 4)
    assert challenge_marker(binary) is None


# --------------------------------------------------------------------------------------
# the two-fetch Figshare acquirer: the metadata document is not the dataset
# --------------------------------------------------------------------------------------
#
# figshare_kobak_aoas2016_supp is fetched twice under one registry id, and the first fetch is
# a 3 KB JSON document. forensics_core writes sha256, bytes, local_path and status=verified
# into the entry on any 200, so without a guard a failed payload fetch would leave the entry
# for a 9.7 MB zip describing that JSON document instead. These tests exercise the guard
# against a synthetic one-entry registry; nothing touches the network.

FIGSHARE_ID = "figshare_kobak_aoas2016_supp"

#: Stand-in for the presigned object-store link the metadata document carries. Nothing
#: requests it: the fetch step is replaced below, and ``.invalid`` never resolves (RFC 6761
#: section 6.4).
SYNTHETIC_PAYLOAD_URL = "https://synthetic.invalid/kobakEtAl_AOAS2016_suppData.zip"

SYNTHETIC_ZIP_BYTES = b"synthetic zip bytes, not the real archive"

#: The registry state the real entry is in: probed at 200 during research, nothing held yet.
SYNTHETIC_ENTRY: dict[str, object] = {
    "id": FIGSHARE_ID,
    "name": "synthetic stand-in for the AOAS 2016 supplementary zip",
    "provider": "synthetic fixture",
    "url": "https://synthetic.invalid/articles/0",
    "access": "free",
    "status": "verified",
    "fetched_at": "2026-01-01T00:00:00Z",
    "http_status": 200,
    "sha256": None,
    "bytes": 9_717_011,
    "local_path": None,
    "notes": "synthetic fixture; no bytes were ever fetched for it",
}


def _synthetic_registry(tmp_path: Path) -> Path:
    """Write the one-entry registry and return the data directory holding it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    text = yaml.safe_dump([dict(SYNTHETIC_ENTRY)], sort_keys=False)
    (data_dir / "SOURCES.yaml").write_text(text, encoding="utf-8")
    return data_dir


def _entry(registry: Path) -> dict:
    return yaml.safe_load(registry.read_text(encoding="utf-8"))[0]


def _record_success(registry: Path, source_id: str, dest: Path, project_dir: Path) -> None:
    """What forensics_core writes on a 200: the fetched file's own digest, size and path.

    Mirrors ``manifest._registry_fields`` for ``rec.error is None``.
    """
    update_source(
        registry,
        source_id,
        fetched_at="2026-02-02T00:00:00Z",
        http_status=200,
        sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        bytes=dest.stat().st_size,
        local_path=str(dest.relative_to(project_dir)),
        status="verified",
        blocked_reason=None,
    )


def _record_failure(registry: Path, source_id: str) -> None:
    """What forensics_core writes when a fetch fails and the entry's file is still intact.

    Mirrors ``manifest._registry_fields`` for ``intact=True``: the attempt's stamp and a dated
    note, with the integrity fields left exactly as the previous success wrote them. That is
    the branch the metadata step's own success puts the payload failure into, and the reason
    the false record would otherwise survive.
    """
    notes = str(_entry(registry)["notes"])
    update_source(
        registry,
        source_id,
        fetched_at="2026-02-02T00:00:01Z",
        http_status=500,
        notes=f"{notes}\n2026-02-02T00:00:01Z {SYNTHETIC_PAYLOAD_URL}: HTTP 500",
    )


def _fake_fetch_file(registry: Path, *, payload: str, seen: dict, meta_body: str | None = None):
    """A stand-in for ``fetch_file`` that records what the real one would record.

    ``payload`` is ``"ok"``, ``"fail"`` (HTTP 500) or ``"raise"`` (what
    :func:`forensics_core.provenance.manifest.fetch` does when handed a URL it will not
    request). ``seen`` collects the registry entry as it stood when the payload step began.
    """
    body = json.dumps({"files": [{"download_url": SYNTHETIC_PAYLOAD_URL}]})

    def fake(source, data_dir, *, url, dest_rel, **kwargs):
        dest = data_dir / "raw" / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if url == controls.FIGSHARE_API_URL:
            dest.write_text(body if meta_body is None else meta_body, encoding="utf-8")
            _record_success(registry, source.id, dest, data_dir.parent)
            return AcquireResult(source.id, True, f"raw/{dest_rel}", (dest,))
        seen["at_payload_time"] = _entry(registry)
        if payload == "raise":
            raise ValueError(f"fetch() needs an absolute http(s) URL with a host; got {url!r}")
        if payload == "fail":
            _record_failure(registry, source.id)
            return AcquireResult(source.id, False, f"{url}: HTTP 500")
        dest.write_bytes(SYNTHETIC_ZIP_BYTES)
        _record_success(registry, source.id, dest, data_dir.parent)
        return AcquireResult(source.id, True, f"raw/{dest_rel}", (dest,))

    return fake


def _run_acquirer(tmp_path: Path, monkeypatch, **fake_kwargs):
    """Set up a synthetic registry and replace the acquirer's fetch step."""
    data_dir = _synthetic_registry(tmp_path)
    registry = data_dir / "SOURCES.yaml"
    source = load_sources(registry)[0]
    monkeypatch.setattr(controls, "fetch_file", _fake_fetch_file(registry, **fake_kwargs))
    return registry, source, data_dir


def test_the_metadata_step_alone_would_claim_the_json_document_is_the_dataset(
    tmp_path: Path, monkeypatch
):
    """The hazard the guard exists for, asserted so the tests below cannot pass vacuously."""
    seen: dict = {}
    _registry, source, data_dir = _run_acquirer(tmp_path, monkeypatch, payload="fail", seen=seen)

    controls.kobak_aoas_supplement(source, data_dir)

    mid = seen["at_payload_time"]
    assert mid["local_path"].endswith("figshare_article_3126883.json")
    assert mid["status"] == "verified"
    assert mid["bytes"] != SYNTHETIC_ENTRY["bytes"]


@pytest.mark.parametrize("payload", ["fail", "raise"])
def test_a_failed_payload_fetch_leaves_no_record_claiming_the_dataset_is_held(
    tmp_path: Path, monkeypatch, payload: str
):
    seen: dict = {}
    registry, source, data_dir = _run_acquirer(tmp_path, monkeypatch, payload=payload, seen=seen)

    if payload == "raise":
        with pytest.raises(ValueError, match="absolute http"):
            controls.kobak_aoas_supplement(source, data_dir)
    else:
        assert not controls.kobak_aoas_supplement(source, data_dir).ok

    after = _entry(registry)
    assert after["local_path"] is None, "the entry still names a file it does not hold"
    assert after["sha256"] is None, "the entry still carries the metadata document's digest"
    assert after["bytes"] == SYNTHETIC_ENTRY["bytes"]
    assert after["status"] == SYNTHETIC_ENTRY["status"]
    assert after["http_status"] == SYNTHETIC_ENTRY["http_status"]
    assert after["fetched_at"] == SYNTHETIC_ENTRY["fetched_at"]


def test_the_failed_attempt_is_still_recorded_in_the_entry_notes(tmp_path: Path, monkeypatch):
    """Restoring the integrity fields must not erase the library's dated failure note."""
    seen: dict = {}
    registry, source, data_dir = _run_acquirer(tmp_path, monkeypatch, payload="fail", seen=seen)

    controls.kobak_aoas_supplement(source, data_dir)

    notes = str(_entry(registry)["notes"])
    assert str(SYNTHETIC_ENTRY["notes"]) in notes
    assert "HTTP 500" in notes
    assert SYNTHETIC_PAYLOAD_URL in notes


def test_a_successful_payload_fetch_keeps_the_payload_record(tmp_path: Path, monkeypatch):
    """The guard must not fire on success: the archive's own digest is what stays recorded."""
    seen: dict = {}
    registry, source, data_dir = _run_acquirer(tmp_path, monkeypatch, payload="ok", seen=seen)

    assert controls.kobak_aoas_supplement(source, data_dir).ok

    after = _entry(registry)
    assert after["local_path"].endswith("kobakEtAl_AOAS2016_suppData.zip")
    assert after["sha256"] == hashlib.sha256(SYNTHETIC_ZIP_BYTES).hexdigest()
    assert after["bytes"] == len(SYNTHETIC_ZIP_BYTES)
    assert after["status"] == "verified"


def test_an_unreadable_metadata_document_also_leaves_no_false_record(tmp_path: Path, monkeypatch):
    """The download_url cannot be read, so the payload is never attempted at all."""
    seen: dict = {}
    registry, source, data_dir = _run_acquirer(
        tmp_path, monkeypatch, payload="ok", seen=seen, meta_body="{not json"
    )

    result = controls.kobak_aoas_supplement(source, data_dir)

    assert not result.ok
    assert "download_url" in result.detail
    assert "at_payload_time" not in seen
    after = _entry(registry)
    assert after["local_path"] is None
    assert after["sha256"] is None
    assert after["status"] == SYNTHETIC_ENTRY["status"]

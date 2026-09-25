"""The ``forensics-manifest`` command line: validate / status / sha256.

Synthetic registries written into pytest's ``tmp_path``; no network, no repository state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from forensics_core.provenance import manifest as M

SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

GOOD = {
    "id": "synthetic_ledger",
    "name": "Synthetic Ledger Extract",
    "provider": "Synthetic Statistics Office",
    "url": "https://synthetic.example/ledger.csv",
    "access": "free",
    "status": "verified",
    "sha256": SHA256_ABC,
    "bytes": 4096,
    "local_path": "data/raw/synthetic_ledger.csv",
}
BLOCKED = {
    "id": "synthetic_paywalled",
    "name": "Synthetic Paywalled Series",
    "provider": "Synthetic Vendor",
    "url": "https://synthetic.example/premium.zip",
    "access": "paywalled",
    "status": "blocked",
    "blocked_reason": "HTTP 403",
}


def write_registry(path: Path, entries: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    return write_registry(
        tmp_path / "projects" / "synthetic_project" / "data" / "SOURCES.yaml", [GOOD, BLOCKED]
    )


# --------------------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------------------


def test_validate_exits_zero_on_a_valid_registry(registry: Path, capsys) -> None:
    assert M.main(["validate", str(registry)]) == 0
    assert "OK (2 sources)" in capsys.readouterr().out


def test_validate_exits_one_and_prints_every_error(tmp_path: Path, capsys) -> None:
    path = write_registry(
        tmp_path / "SOURCES.yaml",
        [
            {**BLOCKED, "blocked_reason": None},
            {**GOOD, "id": "synthetic_no_hash", "sha256": None},
        ],
    )
    assert M.main(["validate", str(path)]) == 1
    out = capsys.readouterr().out
    assert "sources[0] (synthetic_paywalled)" in out
    assert "blocked_reason" in out
    assert "sources[1] (synthetic_no_hash)" in out
    assert "sha256" in out


def test_validate_exits_one_on_a_missing_file(tmp_path: Path, capsys) -> None:
    assert M.main(["validate", str(tmp_path / "absent.yaml")]) == 1
    assert "absent.yaml" in capsys.readouterr().out


def test_validate_checks_every_path_given(registry: Path, tmp_path: Path, capsys) -> None:
    bad = write_registry(tmp_path / "other" / "SOURCES.yaml", [{**BLOCKED, "blocked_reason": ""}])
    assert M.main(["validate", str(registry), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "OK (2 sources)" in out
    assert "sources[0] (synthetic_paywalled)" in out


# --------------------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------------------


def test_status_prints_a_fixed_width_table(registry: Path, capsys) -> None:
    assert M.main(["status", str(registry)]) == 0
    lines = capsys.readouterr().out.splitlines()
    header, separator, *rows = lines

    assert header.split() == ["project", "id", "access", "status", "bytes", "blocked_reason"]
    assert set(separator) <= {"-", " "}
    assert len(rows) == 2

    # every column starts at the same offset on every line
    for name, value in (("id", "synthetic_ledger"), ("status", "verified")):
        start = header.index(name)
        assert rows[0][start : start + len(value)] == value

    assert "synthetic_project" in rows[0]  # project name from projects/<name>/data/
    assert "HTTP 403" in rows[1]
    assert "4096" in rows[0]


def test_status_reports_unreadable_files_and_exits_one(tmp_path: Path, capsys) -> None:
    assert M.main(["status", str(tmp_path / "absent.yaml")]) == 1
    assert "absent.yaml" in capsys.readouterr().out


def test_status_covers_several_registries(registry: Path, tmp_path: Path, capsys) -> None:
    second = write_registry(
        tmp_path / "projects" / "other_project" / "data" / "SOURCES.yaml", [GOOD]
    )
    assert M.main(["status", str(registry), str(second)]) == 0
    out = capsys.readouterr().out
    assert out.count("synthetic_ledger") == 2
    assert "other_project" in out


# --------------------------------------------------------------------------------------
# sha256
# --------------------------------------------------------------------------------------


def test_sha256_prints_the_digest_of_each_file(tmp_path: Path, capsys) -> None:
    a = tmp_path / "synthetic_abc.bin"
    a.write_bytes(b"abc")
    b = tmp_path / "synthetic_empty.bin"
    b.write_bytes(b"")

    assert M.main(["sha256", str(a), str(b)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(SHA256_ABC + "  ")
    assert lines[1].startswith("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ")


def test_sha256_exits_one_on_a_missing_file(tmp_path: Path, capsys) -> None:
    assert M.main(["sha256", str(tmp_path / "absent.bin")]) == 1
    assert "absent.bin" in capsys.readouterr().out


def test_an_unknown_subcommand_is_a_usage_error(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        M.main(["frobnicate"])
    assert excinfo.value.code == 2

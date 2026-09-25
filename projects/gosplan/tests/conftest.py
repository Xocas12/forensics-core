"""Shared paths for the gosplan tests.

Every fixture is synthetic and named ``synthetic_*``. Nothing here reads ``data/raw``, and
nothing in this suite makes a network request: the acquisition tests exercise the pure
parsing helpers and the registry wiring, never the fetcher.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCES_YAML = PROJECT_DIR / "data" / "SOURCES.yaml"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def sources_yaml() -> Path:
    return SOURCES_YAML

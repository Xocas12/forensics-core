"""Shared paths for the china tests.

Every fixture under ``tests/fixtures`` is synthetic and named ``synthetic_*``. None of them
came from a real fetch, and none of them is allowed to look as though it did: the years are
2097 to 2099, the identifiers are spelled SYNTHETIC, and the values are things like 9.9 and
888.8. Nothing in the test suite touches ``data/raw``, ``data/interim`` or ``data/processed``,
and nothing touches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: projects/china
PROJECT_DIR = Path(__file__).resolve().parents[1]

#: projects/china/tests/fixtures
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: projects/china/data/SOURCES.yaml
SOURCES_YAML = PROJECT_DIR / "data" / "SOURCES.yaml"


@pytest.fixture(scope="session")
def fixtures() -> Path:
    """Directory holding the synthetic fixtures."""
    return FIXTURES

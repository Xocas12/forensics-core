"""Shared fixtures for forensics_core tests.

All synthetic data used in tests lives here or under tests/fixtures/ with a ``synthetic_``
prefix and obviously artificial values (HARD RULE 3). Nothing generated here may be written
under any project's data/ directory.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260903)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def synthetic_benford_sample(rng) -> np.ndarray:
    """Log-uniform positive numbers: conform to Benford by construction."""
    return 10 ** rng.uniform(0, 6, size=20_000)


@pytest.fixture
def synthetic_uniform_digits_sample(rng) -> np.ndarray:
    """Uniform on [1000, 9999]: first digits are NOT Benford, last digits ARE uniform."""
    return rng.integers(1000, 10_000, size=20_000).astype(float)

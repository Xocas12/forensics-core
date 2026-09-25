"""Shared fixtures. Everything the suite touches is synthetic; see ``fixtures/README.md``.

The real precinct files are not in this repository and no test reads them. Where a check is
anchored to a published total that only the real file can satisfy, the test monkeypatches the
anchor to the synthetic file's own value to exercise the passing branch, and asserts the
unpatched anchor separately as a constant.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from elections.clean import read_raw

FIXTURES = Path(__file__).parent / "fixtures"

#: Values worked out by hand from the fixture files; see fixtures/README.md.
SYNTHETIC_ROWS = 6
SYNTHETIC_REGISTERED_TOTAL = {"2011-duma": 3850, "2018-presidential": 3680}
SYNTHETIC_WINNER_TOTAL = {"2011-duma": 1095, "2018-presidential": 1080}


@pytest.fixture(scope="session")
def hand_computed() -> dict[str, object]:
    """Values worked out by hand from the fixtures, so tests assert numbers, not behaviour."""
    return {
        "rows": SYNTHETIC_ROWS,
        "registered_total": dict(SYNTHETIC_REGISTERED_TOTAL),
        "winner_total": dict(SYNTHETIC_WINNER_TOTAL),
    }


@pytest.fixture(scope="session")
def fixture_paths() -> dict[str, Path]:
    """Raw-shaped synthetic CSVs, keyed by election."""
    return {
        "2011-duma": FIXTURES / "synthetic_2011_duma.csv",
        "2018-presidential": FIXTURES / "synthetic_2018_presidential.csv",
    }


@pytest.fixture
def duma_2011(fixture_paths: dict[str, Path]) -> pd.DataFrame:
    """The synthetic 2011 file, mapped onto the canonical schema."""
    return read_raw(fixture_paths["2011-duma"], "2011-duma")


@pytest.fixture
def presidential_2018(fixture_paths: dict[str, Path]) -> pd.DataFrame:
    """The synthetic 2018 file, mapped onto the canonical schema."""
    return read_raw(fixture_paths["2018-presidential"], "2018-presidential")


@pytest.fixture
def tidy(duma_2011: pd.DataFrame, presidential_2018: pd.DataFrame) -> pd.DataFrame:
    """Both synthetic elections stacked, as ``build_tidy`` would stack the real ones."""
    return pd.concat([duma_2011, presidential_2018], ignore_index=True)

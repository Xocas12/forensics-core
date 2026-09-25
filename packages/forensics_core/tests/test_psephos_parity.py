"""Cross-implementation parity between forensics_core and psephos (WO-112).

psephos and this library implement the same two method families independently: excess of
integer percentages (Kobak, Shpilkin and Pshenichnikov 2016) and last-digit uniformity
(Beber and Scacco 2012). These tests run both on the same synthetic data and assert that they
agree to the tolerances stated in each test, so that drift in either one is caught. The
decision, the known differences and the reasons for each tolerance are in
``docs/psephos_relationship.md``.

psephos is not a dependency of this workspace. The psephos tests run when ``psephos`` is
importable, either because it is installed or because the environment variable
``PSEPHOS_SRC`` points at the ``src/`` directory of a psephos checkout; otherwise they are
skipped with a reason that says so. A skipped parity test catches no drift: see the document
for why that is a weakness and how it could be closed.

Synthetic data only; nothing here reads a file.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from forensics_core.digits import integer_pct, terminal

PSEPHOS_SRC_ENV = "PSEPHOS_SRC"

# Both implementations are run with the same, explicit settings, so that the comparison is
# about the method and not about the defaults, which differ on purpose (see the document).
N_MC = 500
SEED = 20260925
TOLERANCE = 0.05
MIN_DENOMINATOR = 250
MIN_COUNT = 100


def _psephos_methods():
    """Import psephos's method modules, or skip with the reason they are unavailable."""
    src = os.environ.get(PSEPHOS_SRC_ENV)
    if src:
        path = Path(src)
        if not (path / "psephos" / "methods" / "integer_pct.py").is_file():
            pytest.skip(
                f"{PSEPHOS_SRC_ENV}={src} does not contain psephos/methods/integer_pct.py; "
                "point it at the src/ directory of a psephos checkout"
            )
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    reason = (
        "psephos is not importable: install it or set "
        f"{PSEPHOS_SRC_ENV} to the src/ directory of a psephos checkout. "
        "The parity test is not running, so drift between the two implementations is not "
        "being checked."
    )
    pi = pytest.importorskip("psephos.methods.integer_pct", reason=reason)
    pd_ = pytest.importorskip("psephos.methods.digits", reason=reason)
    return pi, pd_


@pytest.fixture
def synthetic_rounded_election() -> tuple[np.ndarray, np.ndarray]:
    """Synthetic precincts, a fifth of them reporting a whole-number turnout percentage.

    Denominators run from 50 to 2999 so that some fall below the size threshold and the two
    exclusion rules are exercised; numerators never exceed denominators, so both
    implementations see exactly the same usable units.
    """
    rng = np.random.default_rng(SEED)
    d = rng.integers(50, 3000, size=4000)
    k = rng.binomial(d, rng.uniform(0.3, 0.9, size=d.size))
    rounded = rng.random(d.size) < 0.2
    target = rng.integers(40, 91, size=d.size)
    k = np.where(rounded, np.round(d * target / 100.0).astype(np.int64), k)
    return k.astype(float), d.astype(float)


@pytest.fixture
def synthetic_vote_counts() -> np.ndarray:
    """Synthetic vote counts with a mild last-digit distortion, some below ``MIN_COUNT``."""
    rng = np.random.default_rng(SEED + 1)
    counts = rng.integers(20, 5000, size=6000)
    nudged = rng.random(counts.size) < 0.05
    counts = np.where(nudged, counts - counts % 10 + 7, counts)
    return counts.astype(float)


def test_last_digit_chi_square_agrees(synthetic_vote_counts):
    """The last-digit chi-square is deterministic, so the two must agree to rounding error.

    Tolerance: relative 1e-9 on the statistic and on the p-value. Both are the Pearson
    chi-square against a uniform 10-cell table with 9 degrees of freedom; the only
    difference is floating-point summation order.
    """
    _, ps_digits = _psephos_methods()
    x = synthetic_vote_counts
    ps = ps_digits.last_digit_uniformity(x, min_count=MIN_COUNT)
    # psephos drops counts below min_count; the library has no such filter, so apply it here.
    fc = terminal.terminal_digit_test(x[x >= MIN_COUNT], k=1)

    assert ps.n_used == fc.n
    np.testing.assert_allclose(ps.details["observed"], fc.details["observed"], rtol=0, atol=0)
    np.testing.assert_allclose(ps.statistic, fc.statistic, rtol=1e-9)
    np.testing.assert_allclose(ps.pvalue, fc.pvalue, rtol=1e-9)


def test_integer_percentage_excess_agrees(synthetic_rounded_election):
    """Integer-percentage excess: deterministic parts exactly, Monte Carlo parts within noise.

    Tolerances:

    * units used, units excluded and the observed integer count: exact. These involve no
      randomness.
    * null mean: within ``4 * sd * sqrt(2 / n_mc)``, four standard errors of the difference
      between two independent Monte Carlo means. The two streams are seeded identically and
      are usually far closer than that, but they are not guaranteed identical: the library
      computes the binomial share as ``(100 * k / d) / 100`` and psephos as ``k / d``, which
      can differ in the last bit and change an individual draw.
    * effect as a share of units tested: the same tolerance divided by the number of units.
    """
    ps_int, _ = _psephos_methods()
    k, d = synthetic_rounded_election
    ps = ps_int.integer_excess(
        k, d, tolerance=TOLERANCE, min_denominator=MIN_DENOMINATOR, n_mc=N_MC, seed=SEED
    )
    fc = integer_pct.integer_excess(
        integer_pct.percentage(k, d),
        d,
        tolerance=TOLERANCE,
        min_denominator=MIN_DENOMINATOR,
        n_mc=N_MC,
        seed=SEED,
    )

    assert ps.n_used == fc.test.n
    assert ps.n_excluded == fc.n_excluded_small + fc.test.details["n_dropped"]
    assert ps.details["observed"] == fc.observed

    sd = max(ps.details["null_sd"], fc.expected_sd)
    mean_tol = 4.0 * sd * np.sqrt(2.0 / N_MC)
    assert abs(ps.details["null_mean"] - fc.expected_mean) <= mean_tol
    assert abs(ps.effect - fc.test.details["excess_share_of_units"]) <= mean_tol / fc.test.n


def test_documented_library_defaults():
    """The library defaults the document compares against psephos's are the ones in the code.

    Runs without psephos, so that at least the library side of the recorded differences is
    checked in every environment.
    """
    params = inspect.signature(integer_pct.integer_excess).parameters
    assert params["n_mc"].default == 200
    assert params["min_denominator"].default == 100
    assert params["tolerance"].default == 0.05


def test_documented_psephos_defaults():
    """The psephos defaults the document records are the ones in the psephos code."""
    ps_int, ps_digits = _psephos_methods()
    params = inspect.signature(ps_int.integer_excess).parameters
    assert params["n_mc"].default == 500
    assert params["min_denominator"].default == 250
    assert params["tolerance"].default == 0.05
    assert ps_int.DEFAULT_MIN_DENOMINATOR == 250
    assert inspect.signature(ps_digits.last_digit_uniformity).parameters["min_count"].default == 100

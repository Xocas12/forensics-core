"""Every registered detector must round-trip through the harness and orient the same way.

The orientation tests matter most. A detector whose sign is inverted still runs, still produces
numbers, and still ranks units confidently in exactly the wrong order, which no amount of
downstream care would catch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.detectors import DETECTOR_NAMES
from forensics_core.eval.harness import DETECTOR_REGISTRY, Dataset, make_detector

BUNCH_KW = {
    "threshold": 100.0,
    "bin_width": 1.0,
    "exclude_below": 4.0,
    "exclude_above": 4.0,
}


def _kwargs(name: str) -> dict:
    return dict(BUNCH_KW) if name == "notch_bunching" else {}


def panel(n_units: int = 12, per_unit: int = 400, seed: int = 0) -> Dataset:
    """Units whose cells are arrays, the shape idiom B expects."""
    rng = np.random.default_rng(seed)
    den = [rng.integers(400, 3000, size=per_unit).astype(float) for _ in range(n_units)]
    vals = [rng.normal(100.0, 12.0, size=per_unit) for _ in range(n_units)]
    pct = [100.0 * rng.binomial(d.astype(int), 0.55) / d for d in den]
    X = pd.DataFrame(
        {
            "values": pd.Series(vals, dtype=object),
            "denominators": pd.Series(den, dtype=object),
        }
    )
    # integer_excess needs percentages; give it its own frame slot by overwriting for that test
    X["pct"] = pd.Series(pct, dtype=object)
    return Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(n_units)]),
        X=X,
        y=pd.Series([np.nan] * n_units),
    )


# ---------------------------------------------------------------- registration


def test_every_named_detector_is_registered():
    for name in DETECTOR_NAMES:
        assert name in DETECTOR_REGISTRY, f"{name} is not in DETECTOR_REGISTRY"


def test_every_detector_round_trips_through_make_detector():
    for name in DETECTOR_NAMES:
        det = make_detector(name, **_kwargs(name))
        assert det.name == name
        assert hasattr(det, "fit") and hasattr(det, "score")


@pytest.mark.parametrize("name", DETECTOR_NAMES)
def test_each_detector_returns_one_finite_score_per_row(name):
    ds = panel()
    kw = _kwargs(name)
    if name == "integer_excess":
        kw["column"] = "pct"
    det = make_detector(name, **kw).fit(ds)
    scores = np.asarray(det.score(ds), dtype=float)
    assert scores.shape == (len(ds.unit_id),)
    assert np.isfinite(scores).all(), f"{name} produced non-finite scores"


# ---------------------------------------------------------------- orientation


def test_benford_scores_a_distorted_unit_above_a_clean_one():
    rng = np.random.default_rng(1)
    clean = [10 ** rng.uniform(0, 5, size=800) for _ in range(6)]
    # a unit whose leading digits are uniform rather than Benford
    dirty = [rng.integers(10_000, 99_999, size=800).astype(float) for _ in range(6)]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(12)]),
        X=pd.DataFrame({"values": pd.Series(clean + dirty, dtype=object)}),
        y=pd.Series([0] * 6 + [1] * 6),
    )
    s = np.asarray(make_detector("benford_first_two").score(ds), dtype=float)
    assert s[6:].mean() > s[:6].mean(), "the non-Benford units must score higher"


def test_terminal_digit_scores_an_invented_unit_above_a_clean_one():
    rng = np.random.default_rng(2)
    clean = [rng.integers(1000, 9999, size=600).astype(float) for _ in range(6)]
    weights = np.array([0.22, 0.03, 0.10, 0.11, 0.10, 0.20, 0.09, 0.08, 0.04, 0.03])
    dirty = [
        ((rng.integers(100, 999, size=600) * 10) + rng.choice(10, size=600, p=weights)).astype(
            float
        )
        for _ in range(6)
    ]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(12)]),
        X=pd.DataFrame({"values": pd.Series(clean + dirty, dtype=object)}),
        y=pd.Series([0] * 6 + [1] * 6),
    )
    s = np.asarray(make_detector("terminal_digit").score(ds), dtype=float)
    assert s[6:].mean() > s[:6].mean(), "units with invented last digits must score higher"


def test_underdispersion_scores_a_TOO_SMOOTH_unit_higher_not_lower():
    """The inverted one. A low dispersion index is the signal, so the detector must flip it."""
    rng = np.random.default_rng(3)
    noisy = [rng.normal(100.0, 20.0, size=200) for _ in range(6)]
    smooth = [rng.normal(100.0, 0.5, size=200) for _ in range(6)]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(12)]),
        X=pd.DataFrame({"values": pd.Series(noisy + smooth, dtype=object)}),
        y=pd.Series([0] * 6 + [1] * 6),
    )
    s = np.asarray(make_detector("underdispersion").score(ds), dtype=float)
    assert s[6:].mean() > s[:6].mean(), (
        "the low-variance units must score HIGHER; the sign flip is missing"
    )


def test_too_smooth_scores_a_smooth_series_higher_not_lower():
    """The other inverted one: a LOW p-value means implausibly smooth.

    The smoothed units come from inject_smoothing rather than a linear ramp. A ramp is smooth
    in level but its first differences are near-constant plus noise, and the test detrends by
    differencing, so a ramp reads as white noise and discriminates nothing. Shrinking the
    deviations around a local trend is the mechanism the test is actually built to catch.
    """
    from forensics_core.inject import inject_smoothing

    rng = np.random.default_rng(4)
    noisy = [rng.normal(100.0, 5.0, size=120) for _ in range(6)]
    smooth = [
        inject_smoothing(rng.normal(100.0, 5.0, size=120), retain=0.02, seed=i)[0] for i in range(6)
    ]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(12)]),
        X=pd.DataFrame({"values": pd.Series(noisy + smooth, dtype=object)}),
        y=pd.Series([0] * 6 + [1] * 6),
    )
    s = np.asarray(make_detector("too_smooth").score(ds), dtype=float)
    assert s[6:].mean() > s[:6].mean(), "smooth series must score higher"


def test_notch_bunching_scores_a_bunched_unit_above_a_clean_one():
    from forensics_core.inject import inject_bunching

    rng = np.random.default_rng(5)
    clean = [rng.normal(100.0, 12.0, size=4000) for _ in range(5)]
    dirty = [
        inject_bunching(a, threshold=100.0, mass=0.6, window=4.0, side="below", seed=7)[0]
        for a in (rng.normal(100.0, 12.0, size=4000) for _ in range(5))
    ]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(10)]),
        X=pd.DataFrame({"values": pd.Series(clean + dirty, dtype=object)}),
        y=pd.Series([0] * 5 + [1] * 5),
    )
    s = np.asarray(make_detector("notch_bunching", **BUNCH_KW).score(ds), dtype=float)
    assert s[5:].mean() > s[:5].mean(), "bunched units must score higher"


# ---------------------------------------------------------------- failure handling


def test_a_missing_column_says_which_idiom_is_expected():
    ds = Dataset(
        unit_id=pd.Series(["a"]),
        X=pd.DataFrame({"wrong": [1.0]}),
        y=pd.Series([np.nan]),
    )
    with pytest.raises(ValueError, match="idiom B"):
        make_detector("terminal_digit").score(ds)


def test_a_unit_with_too_few_values_makes_the_detector_refuse():
    """A unit that could not be tested has not been found innocent, and there is no honest
    finite score for it: zero would rank it least suspicious, a maximum most. The harness and
    the rank metrics both reject non-finite scores, so nan is not available either. The only
    honest option left is to refuse and say which units, which is a decision about the sample
    and belongs to the caller."""
    ds = Dataset(
        unit_id=pd.Series(["short", "long"]),
        X=pd.DataFrame(
            {
                "values": pd.Series(
                    [np.array([1.0, 2.0]), np.random.default_rng(0).normal(100, 20, 200)],
                    dtype=object,
                )
            }
        ),
        y=pd.Series([np.nan, np.nan]),
    )
    with pytest.raises(ValueError, match="could not score 1 of 2 units"):
        make_detector("underdispersion").score(ds)


def test_the_refusal_says_how_to_proceed():
    ds = Dataset(
        unit_id=pd.Series(["bad", "good"]),
        X=pd.DataFrame(
            {
                "values": pd.Series(
                    [np.array([np.nan] * 50), np.random.default_rng(1).normal(100, 20, 200)],
                    dtype=object,
                )
            }
        ),
        y=pd.Series([np.nan, np.nan]),
    )
    with pytest.raises(ValueError) as exc:
        make_detector("underdispersion").score(ds)
    message = str(exc.value)
    assert "min_len" in message, "the refusal must name the knob that would change it"
    assert "Filter those" in message, "the refusal must say what the caller can do"


def test_reconcile_gross_error_is_deliberately_absent():
    """Its input is a constraint system, not a per-unit collection. Neither documented idiom
    fits it, and a detector reporting a misleading per-row score would be worse than none."""
    assert "reconcile_gross_error" not in DETECTOR_REGISTRY
    from forensics_core import detectors

    source = __import__("pathlib").Path(detectors.__file__).read_text(encoding="utf-8")
    assert "reconcile_gross_error is deliberately NOT registered" in source

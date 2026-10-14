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
    counts = [rng.poisson(100.0, size=per_unit).astype(float) for _ in range(n_units)]
    X = pd.DataFrame(
        {
            "values": pd.Series(vals, dtype=object),
            "denominators": pd.Series(den, dtype=object),
        }
    )
    # integer_excess needs percentages; give it its own frame slot by overwriting for that test
    X["pct"] = pd.Series(pct, dtype=object)
    # the dispersion index is defined on counts only; the default underdispersion detector
    # refuses the normal values above
    X["counts"] = pd.Series(counts, dtype=object)
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
    if name == "underdispersion":
        kw["column"] = "counts"
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
    """The inverted one. A low dispersion index is the signal, so the detector must flip it.

    Counts, because the default statistic refuses anything else: Poisson units against units
    that never stray more than one from 100.
    """
    rng = np.random.default_rng(3)
    noisy = [rng.poisson(100.0, size=200).astype(float) for _ in range(6)]
    smooth = [(100 + rng.integers(-1, 2, size=200)).astype(float) for _ in range(6)]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(12)]),
        X=pd.DataFrame({"values": pd.Series(noisy + smooth, dtype=object)}),
        y=pd.Series([0] * 6 + [1] * 6),
    )
    s = np.asarray(make_detector("underdispersion").score(ds), dtype=float)
    assert s[6:].mean() > s[:6].mean(), (
        "the low-variance units must score HIGHER; the sign flip is missing"
    )


def _equal_cv_panel(seed: int = 0, n_units: int = 300, periods: int = 30, cv: float = 0.10):
    """Non-count series with the same CV and levels log-uniform from 10 to 10^4.

    Noise proportional to the level, as for sector output or revenue: no unit is smoother than
    another, so an honest smoothness score must not depend on the level. 15% of units have half
    their variance removed.
    """
    rng = np.random.default_rng(seed)
    level = 10 ** rng.uniform(1, 4, size=n_units)
    fabricated = rng.random(n_units) < 0.15
    vals = []
    for lv, fab in zip(level, fabricated, strict=True):
        a = rng.normal(lv, cv * lv, size=periods)
        if fab:
            a = lv + (a - lv) * np.sqrt(0.5)
        vals.append(a)
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(n_units)]),
        X=pd.DataFrame({"values": pd.Series(vals, dtype=object)}),
        y=pd.Series(fabricated.astype(int)),
    )
    return ds, level


def test_underdispersion_refuses_non_count_series_by_default():
    """var/mean on a non-count series is CV^2 * mean, which ranks units by size. Units with
    equal CV at levels 10 to 10^4 scored that way correlate with log level at about -0.98, so
    the default statistic must refuse them rather than return that ranking."""
    ds, _ = _equal_cv_panel()
    with pytest.raises(ValueError, match="statistic='cv'"):
        make_detector("underdispersion").score(ds)


def test_underdispersion_refuses_negative_or_fractional_values():
    rng = np.random.default_rng(5)
    for bad in (np.array([3.0, 4.0, -1.0, 5.0, 2.0, 4.0]), rng.poisson(50, 40) + 0.5):
        ds = Dataset(
            unit_id=pd.Series(["bad", "good"]),
            X=pd.DataFrame(
                {"values": pd.Series([bad, rng.poisson(50, 40).astype(float)], dtype=object)}
            ),
            y=pd.Series([np.nan, np.nan]),
        )
        with pytest.raises(ValueError, match="could not score 1 of 2 units"):
            make_detector("underdispersion").score(ds)


def test_underdispersion_cv_scores_do_not_follow_the_level():
    """Equal CV, levels spanning three orders of magnitude: the scale-free statistic must be
    essentially uncorrelated with log level, and still separate the fabricated units."""
    from scipy.stats import spearmanr

    from forensics_core.eval.metrics import roc_auc

    ds, level = _equal_cv_panel()
    s = np.asarray(make_detector("underdispersion", statistic="cv").score(ds), dtype=float)
    rho = spearmanr(s, np.log(level)).statistic
    assert abs(rho) < 0.2, f"cv scores follow the level (Spearman {rho:.2f} with log level)"
    assert roc_auc(ds.y.to_numpy(), s) > 0.85


def test_underdispersion_cv_rank_is_unchanged_when_a_unit_is_rescaled():
    """Re-expressing one honest unit in thousands must not move it in the ranking; under
    var/mean the same rescale moved a mid-ranked unit to rank 1 of 300."""
    ds, _ = _equal_cv_panel()
    det = make_detector("underdispersion", statistic="cv")
    before = np.asarray(det.score(ds), dtype=float)
    i = int(np.flatnonzero(ds.y.to_numpy() == 0)[0])
    vals = list(ds.X["values"])
    vals[i] = vals[i] / 1000.0
    rescaled = Dataset(
        unit_id=ds.unit_id,
        X=pd.DataFrame({"values": pd.Series(vals, dtype=object)}),
        y=ds.y,
    )
    after = np.asarray(det.score(rescaled), dtype=float)
    np.testing.assert_allclose(after, before, rtol=1e-12)


def test_underdispersion_index_on_poisson_counts_does_not_follow_the_level():
    """The control: on counts the default statistic is the scale-free one."""
    from scipy.stats import spearmanr

    rng = np.random.default_rng(7)
    level = 10 ** rng.uniform(1, 4, size=300)
    counts = [rng.poisson(lv, size=30).astype(float) for lv in level]
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(300)]),
        X=pd.DataFrame({"values": pd.Series(counts, dtype=object)}),
        y=pd.Series([np.nan] * 300),
    )
    s = np.asarray(make_detector("underdispersion").score(ds), dtype=float)
    rho = spearmanr(s, np.log(level)).statistic
    assert abs(rho) < 0.2, f"Spearman {rho:.2f} with log level on Poisson counts"


def test_underdispersion_rejects_an_unknown_statistic():
    with pytest.raises(ValueError, match="unknown statistic"):
        make_detector("underdispersion", statistic="variance")


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
                    [
                        np.array([1.0, 2.0]),
                        np.random.default_rng(0).poisson(100, 200).astype(float),
                    ],
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
                    [
                        np.array([np.nan] * 50),
                        np.random.default_rng(1).poisson(100, 200).astype(float),
                    ],
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

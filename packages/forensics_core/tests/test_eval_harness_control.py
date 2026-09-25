"""transfer must return the object that made the claim, and score controls with it.

CONTRACT rule 9 requires every detection result to ship with the same detector's behaviour on
data where nothing should be found. Until now `transfer` fitted a deep copy it never returned,
so a caller could only score a control with a *refitted sibling* of the detector that produced
the scores. That answers a different question, and quietly: the two objects are not the same
fit, and a false-positive rate belongs to the object that made the claim.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from forensics_core.eval.harness import Dataset, FunctionDetector, transfer


def labelled_source(n: int = 400, seed: int = 0) -> Dataset:
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.3).astype(float)
    x = np.where(y == 1.0, rng.normal(3.0, 1.0, n), rng.normal(0.0, 1.0, n))
    return Dataset(
        unit_id=pd.Series([f"s{i}" for i in range(n)]),
        X=pd.DataFrame({"x": x}),
        y=pd.Series(y),
        meta={"name": "source"},
    )


def unlabelled(name: str, loc: float, n: int = 300, seed: int = 1) -> Dataset:
    rng = np.random.default_rng(seed)
    return Dataset(
        unit_id=pd.Series([f"{name}{i}" for i in range(n)]),
        X=pd.DataFrame({"x": rng.normal(loc, 1.0, n)}),
        y=pd.Series([np.nan] * n),
        meta={"name": name},
    )


def detector() -> FunctionDetector:
    return FunctionDetector(lambda X: X["x"].to_numpy(dtype=float), name="x_score")


def test_transfer_returns_the_instance_that_produced_the_scores():
    result = transfer(detector(), labelled_source(), unlabelled("target", 2.0))
    assert result.fitted_detector is not None
    # scoring the target again with the returned instance reproduces the same numbers
    target = unlabelled("target", 2.0)
    again = np.asarray(result.fitted_detector.score(target), dtype=float)
    assert np.allclose(np.sort(again), np.sort(result.scores["score"].to_numpy()))


def test_no_controls_gives_an_empty_report_rather_than_a_missing_field():
    result = transfer(detector(), labelled_source(), unlabelled("target", 2.0))
    assert result.control_reports == []


def test_a_control_is_scored_by_the_same_fitted_instance():
    control = unlabelled("clean", 0.0, seed=5)
    result = transfer(detector(), labelled_source(), unlabelled("target", 2.0), controls=[control])
    assert len(result.control_reports) == 1
    entry = result.control_reports[0]
    assert entry["control"] == "clean"
    assert entry["n"] == len(control)
    assert entry["rates"], "a control report with no thresholds says nothing"


def test_a_clean_control_flags_less_than_a_distorted_one():
    """The number the rule exists for: how often the detector fires where nothing is wrong."""
    clean = unlabelled("clean", 0.0, seed=5)
    dirty = unlabelled("dirty", 3.0, seed=6)
    result = transfer(
        detector(), labelled_source(), unlabelled("target", 2.0), controls=[clean, dirty]
    )
    by_name = {e["control"]: e for e in result.control_reports}
    # compare at the strictest threshold the calibration curve carries
    strict_clean = by_name["clean"]["rates"][-1]["flagged_share"]
    strict_dirty = by_name["dirty"]["rates"][-1]["flagged_share"]
    assert strict_clean < strict_dirty, (
        f"a clean control flagged {strict_clean:.3f} and a distorted one {strict_dirty:.3f}; "
        "the control is not discriminating"
    )
    assert strict_clean < 0.2, f"clean control flagged {strict_clean:.3f} at the strictest cut"


def test_the_flagged_share_falls_as_the_threshold_rises():
    control = unlabelled("clean", 0.0, seed=5)
    result = transfer(detector(), labelled_source(), unlabelled("target", 2.0), controls=[control])
    rates = result.control_reports[0]["rates"]
    shares = [r["flagged_share"] for r in rates]
    assert shares == sorted(shares, reverse=True), (
        "flagged share must be non-increasing as the score threshold rises"
    )


def test_control_thresholds_match_the_calibration_curve():
    """So a reader can put the two side by side: 'at the score where source precision was p,
    this control flagged q of its rows'."""
    control = unlabelled("clean", 0.0, seed=5)
    result = transfer(detector(), labelled_source(), unlabelled("target", 2.0), controls=[control])
    from_control = [r["score_threshold"] for r in result.control_reports[0]["rates"]]
    from_calibration = list(result.calibration["score_threshold"].to_numpy(dtype=float))
    assert from_control == from_calibration

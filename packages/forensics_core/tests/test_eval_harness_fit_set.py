"""What a detector sees at fit time, and that both entry points agree about it.

Two bugs live here, and neither raises anything. A positive-unlabelled estimator handed only
the labelled rows silently stops being a PU estimator, because the pool it estimates its label
frequency against has been removed. And if `evaluate` and `transfer` choose differently, a
`source_report` is not a report on the object that scored the target, which is the comparison
the whole transfer design rests on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.eval.harness import (
    Dataset,
    EvalSpec,
    FunctionDetector,
    PUDetector,
    evaluate,
    fit_set,
    transfer,
)


def pu_dataset(n: int = 600, *, labelled_fraction: float = 0.3, seed: int = 0) -> Dataset:
    """Two Gaussians. Some true positives are labelled 1, some non-positives are labelled 0 as
    presumed clean, and the rest are NaN.

    The 0s matter. In a pure positive-unlabelled dataset every labelled row is a positive, and
    fitting a PU estimator on the labelled rows alone RAISES, which is a loud failure. It is
    when some rows carry a 0 that the old default failed silently: the estimator fitted happily
    on a pool that was not the unlabelled pool at all. That is the case worth testing.
    """
    rng = np.random.default_rng(seed)
    truth = rng.random(n) < 0.4
    x = np.where(truth, rng.normal(2.0, 1.0, n), rng.normal(0.0, 1.0, n))
    y = np.full(n, np.nan)
    known = truth & (rng.random(n) < labelled_fraction)
    y[known] = 1.0
    presumed_clean = (~truth) & (rng.random(n) < labelled_fraction)
    y[presumed_clean] = 0.0
    return Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(n)]),
        X=pd.DataFrame({"x": x}),
        y=pd.Series(y),
        meta={"name": "pu"},
    )


class Recorder:
    """A detector that records how many rows it was fitted on.

    The record lives on the CLASS, not the instance, because `evaluate` deep-copies the
    detector for each fold: anything written to `self` inside `fit` is written to a copy and
    thrown away, and reading it back off the original silently sees nothing.
    """

    name = "recorder"
    SEEN: list[int] = []

    def __init__(self, wants_unlabeled: bool = False) -> None:
        self.wants_unlabeled = wants_unlabeled

    def fit(self, ds: Dataset) -> Recorder:
        Recorder.SEEN.append(len(ds))
        return self

    def score(self, ds: Dataset) -> np.ndarray:
        return ds.X["x"].to_numpy(dtype=float)


@pytest.fixture(autouse=True)
def _clear_recorder():
    Recorder.SEEN.clear()
    yield
    Recorder.SEEN.clear()


# ---------------------------------------------------------------- the declaration


def test_a_pu_detector_declares_that_it_wants_the_unlabelled_pool():
    assert PUDetector.wants_unlabeled is True
    assert FunctionDetector.wants_unlabeled is False


def test_fit_set_gives_a_pu_detector_every_row():
    ds = pu_dataset()
    n_labelled = len(ds.labeled())
    assert n_labelled < len(ds), "the fixture must have unlabelled rows to be meaningful"
    assert len(fit_set(Recorder(wants_unlabeled=True), ds)) == len(ds)


def test_fit_set_gives_a_supervised_detector_only_the_labelled_rows():
    ds = pu_dataset()
    assert len(fit_set(Recorder(wants_unlabeled=False), ds)) == len(ds.labeled())


def test_fit_set_falls_back_to_every_row_when_nothing_is_labelled():
    """A dataset with no labels at all would otherwise hand an empty frame to fit."""
    ds = Dataset(
        unit_id=pd.Series(["a", "b"]),
        X=pd.DataFrame({"x": [1.0, 2.0]}),
        y=pd.Series([np.nan, np.nan]),
    )
    assert len(fit_set(Recorder(), ds)) == 2


# ---------------------------------------------------------------- the two entry points agree


def test_evaluate_and_transfer_show_a_detector_the_same_rows():
    """The parity bug. Same detector, same dataset: the fit sets must match."""
    ds = pu_dataset()

    target = Dataset(
        unit_id=pd.Series(["t0", "t1"]),
        X=pd.DataFrame({"x": [0.0, 1.0]}),
        y=pd.Series([np.nan, np.nan]),
    )

    evaluate(Recorder(wants_unlabeled=True), ds, EvalSpec(split="none"))
    from_evaluate = list(Recorder.SEEN)
    Recorder.SEEN.clear()

    transfer(Recorder(wants_unlabeled=True), ds, target)
    from_transfer = list(Recorder.SEEN)

    assert from_evaluate and from_transfer, "one of the two never fitted"
    assert from_evaluate[0] == from_transfer[0] == len(ds), (
        f"evaluate fitted on {from_evaluate[0]} rows and transfer on {from_transfer[0]}, "
        f"of {len(ds)}. They must agree, or a source_report is not a report on the object "
        "that scored the target."
    )


def test_a_supervised_detector_sees_only_labelled_rows_in_both():
    ds = pu_dataset()
    target = Dataset(
        unit_id=pd.Series(["t0"]),
        X=pd.DataFrame({"x": [0.0]}),
        y=pd.Series([np.nan]),
    )
    evaluate(Recorder(wants_unlabeled=False), ds, EvalSpec(split="none"))
    from_evaluate = list(Recorder.SEEN)
    Recorder.SEEN.clear()
    transfer(Recorder(wants_unlabeled=False), ds, target)
    from_transfer = list(Recorder.SEEN)
    assert from_evaluate[0] == from_transfer[0] == len(ds.labeled())


# ---------------------------------------------------------------- the semantic consequence


def test_a_pu_detector_recovers_the_label_frequency_only_with_the_pool():
    """The bug that raises nothing. Fitting a PU estimator on the labelled rows alone leaves it
    with no unlabelled pool, so its label-frequency estimate is computed against nothing like
    the right sample and comes out badly wrong."""
    ds = pu_dataset(n=3000, labelled_fraction=0.3, seed=3)
    assert len(ds.labeled()) < len(ds), "the fixture must retain an unlabelled pool"

    with_pool = PUDetector(kind="elkan_noto", random_state=0)
    with_pool.fit(fit_set(with_pool, ds))
    c_with = float(with_pool.estimator_.c_)

    labelled_only = PUDetector(kind="elkan_noto", random_state=0)
    labelled_only.fit(ds.labeled())
    c_without = float(labelled_only.estimator_.c_)

    # The label frequency is 0.3 by construction. Fitting on the labelled rows alone does not
    # raise here, because the 0s give it something to call unlabelled; it just estimates the
    # wrong quantity, which is the silent failure this change removes.
    assert abs(c_with - 0.3) < abs(c_without - 0.3), (
        f"the pool must improve the label-frequency estimate: with={c_with:.3f} "
        f"without={c_without:.3f}, truth=0.30"
    )


def test_transfer_defaults_to_the_detectors_own_declaration():
    ds = pu_dataset()
    target = Dataset(
        unit_id=pd.Series(["t0", "t1"]),
        X=pd.DataFrame({"x": [0.0, 3.0]}),
        y=pd.Series([np.nan, np.nan]),
    )
    det = PUDetector(kind="elkan_noto", random_state=0)
    result = transfer(det, ds, target)
    assert len(result.scores) == 2


def test_fit_on_can_still_be_forced_and_rejects_nonsense():
    ds = pu_dataset()
    target = Dataset(
        unit_id=pd.Series(["t0"]),
        X=pd.DataFrame({"x": [0.0]}),
        y=pd.Series([np.nan]),
    )
    det = FunctionDetector(lambda X: X["x"].to_numpy(), name="f")
    transfer(det, ds, target, fit_on="all")
    transfer(det, ds, target, fit_on="labeled")
    with pytest.raises(ValueError, match="fit_on must be"):
        transfer(det, ds, target, fit_on="whatever")

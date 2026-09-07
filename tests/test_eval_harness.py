"""Tests for :mod:`forensics_core.eval.harness`.

Every dataset here is synthetic and generated in the test from a seeded generator: an
obviously artificial panel of 200 rows over five years, with one informative feature built
as ``2 * y + noise`` so that an injected effect can be recovered, and one pure-noise feature.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from forensics_core.eval.harness import (
    DETECTOR_REGISTRY,
    Dataset,
    Detector,
    EvalReport,
    EvalSpec,
    FunctionDetector,
    PUDetector,
    SklearnDetector,
    TransferResult,
    evaluate,
    make_detector,
    register_detector,
    transfer,
)

YEARS = (2000, 2001, 2002, 2003, 2004)
N_PER_YEAR = 40


def synthetic_panel(
    seed: int = 20260906,
    n_per_year: int = N_PER_YEAR,
    years: tuple[int, ...] = YEARS,
    base_rate: float = 0.25,
    n_groups: int = 8,
    effect: float = 2.0,
    name: str = "synthetic_panel",
) -> Dataset:
    """A synthetic labeled panel: ``signal = effect * y + N(0, 1)``, ``noise = N(0, 1)``."""
    rng = np.random.default_rng(seed)
    n = n_per_year * len(years)
    y = (rng.random(n) < base_rate).astype(float)
    frame = pd.DataFrame({"signal": effect * y + rng.normal(size=n), "noise": rng.normal(size=n)})
    return Dataset(
        unit_id=pd.Series([f"unit_{i:04d}" for i in range(n)]),
        X=frame,
        y=pd.Series(y),
        groups=pd.Series([f"group_{i % n_groups}" for i in range(n)]),
        time=pd.Series(np.repeat(np.asarray(years), n_per_year)),
        meta={"name": name},
    )


def signal_detector() -> FunctionDetector:
    return FunctionDetector(lambda X: X["signal"].to_numpy(), name="signal_column")


# ---------------------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------------------


def test_dataset_validation_rejects_misaligned_or_impossible_input():
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    ids = pd.Series(["a", "b", "c"])

    with pytest.raises(ValueError, match=r"X must be a pandas\.DataFrame"):
        Dataset(unit_id=ids, X={"a": [1, 2, 3]})
    with pytest.raises(ValueError, match="length"):
        Dataset(unit_id=pd.Series(["a", "b"]), X=frame)
    with pytest.raises(ValueError, match="unique"):
        Dataset(unit_id=pd.Series(["a", "a", "c"]), X=frame)
    with pytest.raises(ValueError, match="only 1"):
        Dataset(unit_id=ids, X=frame, y=pd.Series([1.0, 2.0, 0.0]))
    with pytest.raises(ValueError, match="index"):
        Dataset(unit_id=ids, X=frame, y=pd.Series([1.0, 0.0, 1.0], index=[7, 8, 9]))
    with pytest.raises(ValueError, match="meta must be a dict"):
        Dataset(unit_id=ids, X=frame, meta=["not", "a", "dict"])
    with pytest.raises(ValueError, match="1-D"):
        Dataset(unit_id=ids, X=frame, groups=pd.DataFrame({"g": [1, 2, 3]}))

    # y = 1 / 0 / NaN is the only accepted alphabet, and lists are wrapped for convenience
    ds = Dataset(unit_id=["a", "b", "c"], X=frame, y=[1.0, 0.0, np.nan])
    assert isinstance(ds.unit_id, pd.Series)
    assert len(ds) == 3
    assert ds.name == "dataset"


def test_dataset_labeled_and_positives_subsets():
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    ds = Dataset(
        unit_id=pd.Series(["w", "x", "y", "z"]),
        X=frame,
        y=pd.Series([1.0, 0.0, np.nan, 1.0]),
        meta={"name": "tiny"},
    )
    labeled = ds.labeled()
    assert labeled.unit_id.tolist() == ["w", "x", "z"]
    assert len(labeled) == 3
    assert labeled.name == "tiny"
    positives = ds.positives()
    assert positives.unit_id.tolist() == ["w", "z"]
    assert np.all(positives.y_values() == 1.0)
    # subsetting keeps every field aligned
    assert positives.X["a"].tolist() == [1.0, 4.0]

    unlabeled_ds = Dataset(unit_id=pd.Series(["w"]), X=pd.DataFrame({"a": [1.0]}))
    with pytest.raises(ValueError, match="no labels"):
        unlabeled_ds.labeled()


# ---------------------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------------------


def test_temporal_split_counts_and_in_sample_flag():
    ds = synthetic_panel()
    spec = EvalSpec(split="temporal", train_end=2002, ks=(0.1,), metrics=("roc_auc",))
    report = evaluate(signal_detector(), ds, spec)

    # 5 years x 40 rows: 2000-2002 train (120 rows), 2003-2004 test (80 rows)
    assert report.n_train == 120
    assert report.n_test == 80
    assert len(report.per_fold) == 1
    assert report.per_fold[0]["n_train"] == 120
    assert report.per_fold[0]["n_test_rows"] == 80
    expected_pos = int(ds.y_values()[120:].sum())
    assert report.n_pos_test == expected_pos
    assert 0 < expected_pos < 80
    assert report.in_sample is False
    assert report.detector == "signal_column"
    assert report.dataset == "synthetic_panel"
    # the injected effect must be recovered out of sample
    assert report.metrics["roc_auc"] > 0.8


def test_temporal_split_scores_all_test_rows_but_grades_only_labeled_ones():
    ds = synthetic_panel()
    y = ds.y_values().copy()
    y[120:130] = np.nan  # ten unlabeled rows land in the test period
    ds = Dataset(
        unit_id=ds.unit_id, X=ds.X, y=pd.Series(y), groups=ds.groups, time=ds.time, meta=ds.meta
    )
    spec = EvalSpec(split="temporal", train_end=2002, ks=(0.1,), metrics=("roc_auc",))
    report = evaluate(signal_detector(), ds, spec)
    assert report.per_fold[0]["n_test_rows"] == 80  # all test rows are scored
    assert report.n_test == 70  # only the labeled ones are graded
    assert len(report.per_fold[0]["test_unit_ids"]) == 70


def test_temporal_split_input_errors():
    ds = synthetic_panel()
    with pytest.raises(ValueError, match="train_end"):
        evaluate(signal_detector(), ds, EvalSpec(split="temporal"))
    with pytest.raises(ValueError, match="nothing to test on"):
        evaluate(signal_detector(), ds, EvalSpec(split="temporal", train_end=2099))
    with pytest.raises(ValueError, match="nothing to train on"):
        evaluate(signal_detector(), ds, EvalSpec(split="temporal", train_end=1900))

    no_time = Dataset(unit_id=ds.unit_id, X=ds.X, y=ds.y)
    with pytest.raises(ValueError, match=r"needs Dataset\.time"):
        evaluate(signal_detector(), no_time, EvalSpec(split="temporal", train_end=2002))
    with pytest.raises(ValueError, match="needs labels"):
        evaluate(
            signal_detector(),
            Dataset(unit_id=ds.unit_id, X=ds.X, time=ds.time),
            EvalSpec(split="temporal", train_end=2002),
        )


def test_anchor_holdout_tests_exactly_the_anchor_rows():
    ds = synthetic_panel()
    anchor = pd.Series(ds.time.to_numpy() == 2004)  # the anchor event is the last year
    spec = EvalSpec(split="anchor_holdout", anchor_mask=anchor, ks=(5,), metrics=("roc_auc",))
    report = evaluate(signal_detector(), ds, spec)

    anchor_ids = ds.unit_id[anchor.to_numpy()].tolist()
    assert report.per_fold[0]["test_unit_ids"] == anchor_ids
    assert report.n_test == N_PER_YEAR == 40
    assert report.n_train == 160
    assert set(report.per_fold[0]["test_unit_ids"]).isdisjoint(
        set(ds.unit_id[~anchor.to_numpy()].tolist())
    )

    with pytest.raises(ValueError, match="anchor_mask"):
        evaluate(signal_detector(), ds, EvalSpec(split="anchor_holdout"))
    with pytest.raises(ValueError, match="no rows"):
        evaluate(
            signal_detector(),
            ds,
            EvalSpec(split="anchor_holdout", anchor_mask=pd.Series(np.zeros(len(ds), dtype=bool))),
        )
    with pytest.raises(ValueError, match="length"):
        evaluate(
            signal_detector(),
            ds,
            EvalSpec(split="anchor_holdout", anchor_mask=pd.Series([True, False])),
        )


def test_group_kfold_puts_each_group_in_exactly_one_test_fold():
    ds = synthetic_panel()
    spec = EvalSpec(split="group_kfold", n_splits=4, ks=(0.1,), metrics=("roc_auc",))
    report = evaluate(signal_detector(), ds, spec)

    assert len(report.per_fold) == 4
    assert report.n_test == len(ds)  # every labeled row is tested exactly once
    group_of = dict(zip(ds.unit_id.tolist(), ds.groups.tolist(), strict=True))
    seen: dict[str, int] = {}
    for entry in report.per_fold:
        for unit in entry["test_unit_ids"]:
            group = group_of[unit]
            assert seen.setdefault(group, entry["fold"]) == entry["fold"]
    assert len(seen) == 8  # all eight groups appear
    assert report.metrics["roc_auc"] > 0.8

    with pytest.raises(ValueError, match="distinct groups"):
        evaluate(signal_detector(), ds, EvalSpec(split="group_kfold", n_splits=9))
    no_groups = Dataset(unit_id=ds.unit_id, X=ds.X, y=ds.y, time=ds.time)
    with pytest.raises(ValueError, match=r"needs Dataset\.groups"):
        evaluate(signal_detector(), no_groups, EvalSpec(split="group_kfold", n_splits=3))


def test_split_none_is_flagged_as_in_sample():
    ds = synthetic_panel()
    spec = EvalSpec(split="none", ks=(0.05,), metrics=("roc_auc", "precision_at_k"))
    report = evaluate(signal_detector(), ds, spec)
    assert report.in_sample is True
    assert any("IN-SAMPLE" in note for note in report.notes)
    assert report.n_train == report.n_test == len(ds)
    assert set(report.metrics) == {"roc_auc", "precision@5%"}


def test_evaluate_reports_and_then_refuses_folds_without_both_classes():
    """A test side with only positives is unscoreable; the report must say so, not guess."""
    n = 20
    y = np.concatenate([np.zeros(10), np.ones(10)])  # positives only after the split
    ds = Dataset(
        unit_id=pd.Series([f"u{i}" for i in range(n)]),
        X=pd.DataFrame({"signal": np.arange(float(n))}),
        y=pd.Series(y),
        time=pd.Series(np.repeat([2000, 2001], 10)),
        meta={"name": "degenerate"},
    )
    with pytest.raises(ValueError, match="no fold had both"):
        evaluate(signal_detector(), ds, EvalSpec(split="temporal", train_end=2000, ks=(2,)))


# ---------------------------------------------------------------------------------------
# detectors
# ---------------------------------------------------------------------------------------


def test_function_detector_respects_the_higher_is_suspicious_convention():
    ds = synthetic_panel()
    flipped = FunctionDetector(
        lambda X: -X["signal"].to_numpy(), name="flipped", higher_is_suspicious=False
    )
    assert np.allclose(flipped.fit(ds).score(ds), ds.X["signal"].to_numpy())

    with pytest.raises(ValueError, match="callable"):
        FunctionDetector("not a function")
    wrong_length = FunctionDetector(lambda X: np.zeros(3), name="short")
    with pytest.raises(ValueError, match="returned 3 values"):
        wrong_length.score(ds)
    non_finite = FunctionDetector(lambda X: np.full(len(X), np.nan), name="nan")
    with pytest.raises(ValueError, match="non-finite"):
        non_finite.score(ds)


def test_sklearn_detector_recovers_the_injected_effect_out_of_sample():
    ds = synthetic_panel()
    detector = SklearnDetector(LogisticRegression(max_iter=1000), name="logit")
    spec = EvalSpec(
        split="temporal",
        train_end=2002,
        ks=(0.1,),
        metrics=("roc_auc", "average_precision", "precision_at_k", "ndcg_at_k"),
    )
    report = evaluate(detector, ds, spec)
    assert report.metrics["roc_auc"] > 0.85
    assert report.metrics["average_precision"] > 0.6
    assert report.metrics["precision@10%"] > 0.7
    assert 0.0 <= report.metrics["ndcg@10%"] <= 1.0

    # the detector handed in is never fitted: evaluate deep-copies it per fold
    assert detector.estimator_ is None
    with pytest.raises(RuntimeError, match="before fit"):
        detector.score(ds)

    # unlabeled rows are dropped by fit; a single class is an error
    one_class = ds.positives()
    with pytest.raises(ValueError, match="both classes"):
        SklearnDetector(LogisticRegression(), name="logit").fit(one_class)
    with pytest.raises(ValueError, match="must have a fit method"):
        SklearnDetector(object())

    class _FitOnly:
        def fit(self, X, y):
            return self

    with pytest.raises(ValueError, match="decision_function or predict_proba"):
        SklearnDetector(_FitOnly())


def test_pu_detector_label_mapping_and_optional_dependency():
    """y == 0 is *unlabeled* for PU, not a negative; skip until labels.pu lands."""
    ds = synthetic_panel()
    y = ds.y_values().copy()
    y[:20] = np.nan
    ds = Dataset(
        unit_id=ds.unit_id, X=ds.X, y=pd.Series(y), groups=ds.groups, time=ds.time, meta=ds.meta
    )
    detector = PUDetector(kind="elkan_noto", base_estimator=LogisticRegression(max_iter=1000))
    s = detector.pu_labels(ds)
    assert set(np.unique(s)) <= {0, 1}
    assert s.sum() == int(np.nansum(y == 1.0))
    assert s[:20].sum() == 0  # NaN -> unlabeled
    assert np.all(s[np.where(y == 0.0)[0]] == 0)  # presumed clean -> unlabeled too

    with pytest.raises(ValueError, match="kind must be one of"):
        PUDetector(kind="nope")

    pu = pytest.importorskip(
        "forensics_core.labels.pu", reason="labels.pu is written by another agent"
    )
    if not hasattr(pu, "ElkanNotoPU"):
        pytest.skip("forensics_core.labels.pu has no ElkanNotoPU yet")
    fitted = detector.fit(ds)
    scores = fitted.score(ds)
    assert scores.shape == (len(ds),)
    assert np.all(np.isfinite(scores))
    labeled = ds.labeled()
    from forensics_core.eval.metrics import roc_auc

    assert roc_auc(labeled.y_values(), fitted.score(labeled)) > 0.7

    # ... and the PU detectors go through evaluate() like any other detector
    spec = EvalSpec(split="temporal", train_end=2002, ks=(0.1,), metrics=("roc_auc",))
    assert evaluate(detector, ds, spec).metrics["roc_auc"] > 0.7
    if hasattr(pu, "BaggingPU"):
        bagging = PUDetector(
            kind="bagging",
            base_estimator=LogisticRegression(max_iter=1000),
            n_estimators=10,
            random_state=0,
        )
        assert evaluate(bagging, ds, spec).metrics["roc_auc"] > 0.7

    all_positive = ds.positives()
    with pytest.raises(ValueError, match="needs unlabeled rows"):
        detector.fit(all_positive)


# ---------------------------------------------------------------------------------------
# transfer
# ---------------------------------------------------------------------------------------


def test_transfer_ranks_every_target_unit_and_calibrates_on_the_source():
    source = synthetic_panel(seed=1, name="source_project")
    target = synthetic_panel(seed=2, name="target_project", n_per_year=20)
    detector = SklearnDetector(LogisticRegression(max_iter=1000), name="logit")
    spec = EvalSpec(split="temporal", train_end=2002, ks=(0.1,), metrics=("roc_auc",))

    result = transfer(detector, source, target, source_spec=spec)
    assert isinstance(result, TransferResult)

    scores = result.scores
    assert list(scores.columns) == ["unit_id", "score", "rank"]
    assert len(scores) == len(target)
    assert set(scores["unit_id"]) == set(target.unit_id)
    assert scores["rank"].tolist() == list(range(1, len(target) + 1))
    assert scores["score"].is_monotonic_decreasing  # rank 1 = most suspicious

    # the transferred ranking still separates the target labels
    merged = scores.merge(
        pd.DataFrame({"unit_id": target.unit_id, "y": target.y_values()}), on="unit_id"
    )
    from forensics_core.eval.metrics import roc_auc

    assert roc_auc(merged["y"].to_numpy(), merged["score"].to_numpy()) > 0.8

    calibration = result.calibration
    assert set(["score_threshold", "precision", "recall"]).issubset(calibration.columns)
    assert calibration["score_threshold"].is_monotonic_increasing
    assert calibration["recall"].is_monotonic_decreasing  # fewer selected as t rises
    assert calibration["recall"].iloc[0] == pytest.approx(1.0)  # lowest threshold takes all
    assert calibration["precision"].iloc[0] == pytest.approx(source.y_values().mean())
    assert ((calibration["precision"] >= 0.0) & (calibration["precision"] <= 1.0)).all()
    assert calibration["precision"].iloc[-1] > calibration["precision"].iloc[0]

    payload = result.to_dict()
    assert payload["source"] == "source_project"
    assert len(payload["scores"]) == len(target)
    assert payload["calibration"][0]["recall"] == pytest.approx(1.0)

    assert isinstance(result.source_report, EvalReport)
    assert result.source_report.metrics["roc_auc"] > 0.8
    assert result.source == "source_project"
    assert result.target == "target_project"
    assert result.n_source_fit == len(source)

    # without a source_spec there is no source report, and nothing else changes
    plain = transfer(detector, source, target)
    assert plain.source_report is None
    assert plain.scores["unit_id"].tolist() == scores["unit_id"].tolist()

    with pytest.raises(ValueError, match="fit_on"):
        transfer(detector, source, target, fit_on="everything")
    with pytest.raises(ValueError, match="labels on the source"):
        transfer(
            detector,
            Dataset(unit_id=source.unit_id, X=source.X),
            target,
        )


# ---------------------------------------------------------------------------------------
# registry and reports
# ---------------------------------------------------------------------------------------


def test_registry_round_trip():
    assert {"function", "sklearn", "pu_elkan_noto", "pu_bagging"} <= set(DETECTOR_REGISTRY)

    built = make_detector("function", func=lambda X: X["signal"].to_numpy(), name="from_registry")
    assert isinstance(built, FunctionDetector)
    assert isinstance(built, Detector)
    assert built.name == "from_registry"

    pu = make_detector("pu_bagging")
    assert isinstance(pu, PUDetector)
    assert pu.kind == "bagging"

    class _Custom:
        name = "custom"

        def fit(self, ds):
            return self

        def score(self, ds):
            return np.zeros(len(ds))

    try:
        register_detector("test_custom_detector")(_Custom)
        assert isinstance(make_detector("test_custom_detector"), _Custom)
        with pytest.raises(ValueError, match="already registered"):
            register_detector("test_custom_detector")(_Custom)
        register_detector("test_custom_detector", overwrite=True)(_Custom)

        register_detector("test_bad_factory", overwrite=True)(lambda: "not a detector")
        with pytest.raises(ValueError, match="does not implement the Detector protocol"):
            make_detector("test_bad_factory")
    finally:
        DETECTOR_REGISTRY.pop("test_custom_detector", None)
        DETECTOR_REGISTRY.pop("test_bad_factory", None)

    with pytest.raises(ValueError, match="unknown detector"):
        make_detector("no_such_detector")
    with pytest.raises(ValueError, match="non-empty string"):
        register_detector("")


def test_evalspec_validation():
    with pytest.raises(ValueError, match="split must be"):
        EvalSpec(split="random")
    with pytest.raises(ValueError, match="n_splits"):
        EvalSpec(split="group_kfold", n_splits=1)
    with pytest.raises(ValueError, match="unknown metric"):
        EvalSpec(metrics=("accuracy",))
    with pytest.raises(ValueError, match="ks must not be empty"):
        EvalSpec(ks=())
    with pytest.raises(ValueError, match="fraction"):
        EvalSpec(ks=(2.5,))
    assert EvalSpec(ks=[1, 0.05]).ks == (1, 0.05)


def test_report_serialises_and_tabulates():
    ds = synthetic_panel()
    spec = EvalSpec(
        split="temporal", train_end=2002, ks=(0.05, 10), metrics=("roc_auc", "precision_at_k")
    )
    report = evaluate(signal_detector(), ds, spec)
    assert set(report.metrics) == {"roc_auc", "precision@5%", "precision@10"}

    payload = report.to_dict()
    assert payload["detector"] == "signal_column"
    assert payload["spec"]["split"] == "temporal"
    assert payload["spec"]["train_end"] == 2002
    assert payload["n_test"] == 80
    assert isinstance(payload["per_fold"], list)

    table = report.summary_table()
    assert len(table) == len(report.metrics)
    assert set(table["metric"]) == set(report.metrics)
    assert table["detector"].unique().tolist() == ["signal_column"]
    combined = pd.concat([table, report.summary_table()], ignore_index=True)
    assert len(combined) == 2 * len(report.metrics)

    # an anchor mask is summarised, not dumped, so the payload stays JSON-serialisable
    anchor_spec = EvalSpec(
        split="anchor_holdout",
        anchor_mask=pd.Series(ds.time.to_numpy() == 2004),
        ks=(5,),
        metrics=("roc_auc",),
    )
    anchor_payload = evaluate(signal_detector(), ds, anchor_spec).to_dict()
    assert anchor_payload["spec"]["anchor_mask"] == {"n_rows": 200, "n_anchor": 40}
    assert json.loads(json.dumps(anchor_payload))["n_test"] == 40


def test_evaluate_rejects_objects_that_are_not_detectors_or_datasets():
    ds = synthetic_panel()
    spec = EvalSpec(split="temporal", train_end=2002, ks=(0.1,), metrics=("roc_auc",))
    with pytest.raises(ValueError, match="Detector protocol"):
        evaluate(object(), ds, spec)
    with pytest.raises(ValueError, match="must be a Dataset"):
        evaluate(signal_detector(), ds.X, spec)
    with pytest.raises(ValueError, match="must be an EvalSpec"):
        evaluate(signal_detector(), ds, {"split": "temporal"})

"""One evaluation harness for every project: a :class:`Dataset`, a :class:`Detector`
protocol, split policies that respect time and grouping, and a transfer path that carries a
detector calibrated on one project onto another.

The point of the harness is that a method developed on (say) audited financial statements
can be re-scored on election precincts without rewriting the evaluation, and that the two
runs are comparable because the split policy, the metric bundle and the report shape are
fixed here rather than in each project.

Design notes and sources
------------------------
- Split policies. ``"temporal"`` trains on rows at or before ``train_end`` and tests on
  everything later, the design used by Bao, Y., Ke, B., Li, B., Yu, Y. J. and Zhang, J.
  (2020), "Detecting accounting fraud in publicly traded U.S. firms using a machine
  learning approach", *Journal of Accounting Research* 58(1): 199-235, precisely because a
  random split leaks the future into the past. ``"group_kfold"`` wraps
  :class:`sklearn.model_selection.GroupKFold` so that a whole firm / province / year sits on
  one side of the split. ``"anchor_holdout"`` holds out an *anchor event* -- a period or set
  of units where the ground truth is known from outside the data -- and trains on the rest.
  ``"none"`` fits and scores the same labeled rows; its metrics are in-sample and the report
  says so (:attr:`EvalReport.in_sample`).
- Positive-unlabeled labels. Enforcement data marks some positives and nothing else; a 0 in
  ``Dataset.y`` means *presumed* clean, not verified clean. :class:`PUDetector` therefore
  treats both ``NaN`` and ``0`` as unlabeled (Elkan, C. and Noto, K. (2008), "Learning
  classifiers from only positive and unlabeled data", *KDD*; Mordelet, F. and Vert, J.-P.
  (2014), "A bagging SVM to learn from positive and unlabeled examples", *Pattern
  Recognition Letters* 37: 201-209), while :class:`SklearnDetector` takes the 0s at face
  value as negatives.
- Metrics come from :mod:`forensics_core.eval.metrics`; the tie-breaking rule documented
  there (stable descending sort on the score) applies to every ranking produced here.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from sklearn.base import clone
from sklearn.model_selection import GroupKFold

from forensics_core._types import jsonable
from forensics_core.eval.metrics import (
    _as_float_1d,
    _k_label,
    _rank_order,
    _resolve_k,
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    roc_auc,
)

__all__ = [
    "DETECTOR_REGISTRY",
    "Dataset",
    "Detector",
    "EvalReport",
    "EvalSpec",
    "FunctionDetector",
    "PUDetector",
    "SklearnDetector",
    "TransferResult",
    "evaluate",
    "make_detector",
    "register_detector",
    "transfer",
]

SplitKind = Literal["temporal", "group_kfold", "anchor_holdout", "none"]

#: Metric names accepted in :attr:`EvalSpec.metrics` that return a single number.
_SCALAR_METRICS: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
    "roc_auc": roc_auc,
    "average_precision": average_precision,
}
#: Metric names that are evaluated at every cut-off in :attr:`EvalSpec.ks`.
_AT_K_METRICS: dict[str, tuple[str, Callable[..., float]]] = {
    "ndcg_at_k": ("ndcg", ndcg_at_k),
    "precision_at_k": ("precision", precision_at_k),
    "recall_at_k": ("recall", recall_at_k),
}


# --------------------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------------------


def _to_series(value: Any, name: str, n: int, index: pd.Index) -> pd.Series:
    """Coerce ``value`` to a length-``n`` Series carrying ``index``, or raise ValueError."""
    if isinstance(value, pd.Series):
        ser = value
    elif isinstance(value, pd.DataFrame):
        raise ValueError(f"{name} must be 1-D (a Series); got a DataFrame with {value.shape}")
    else:
        arr = np.asarray(value)
        if arr.ndim != 1:
            raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
        ser = pd.Series(arr, index=index)
    if len(ser) != n:
        raise ValueError(f"{name} has length {len(ser)} but X has {n} rows")
    if not ser.index.equals(index):
        raise ValueError(
            f"{name}.index does not match X.index; pandas would silently misalign them. "
            "Reset both indexes (.reset_index(drop=True)) or pass matching indexes."
        )
    return ser


@dataclass
class Dataset:
    """Rows to be scored, with whatever labels, groups and timestamps exist.

    Parameters
    ----------
    unit_id : pandas.Series
        Identifier of the scored unit (firm-year, precinct, region-year). Must be unique.
    X : pandas.DataFrame
        Features; rows align *positionally and by index* with every other field.
    y : pandas.Series or None
        1 = confirmed distortion, 0 = presumed clean, ``NaN`` = unlabeled. No other value is
        accepted. ``None`` means the dataset carries no labels at all (scoring only).
    groups : pandas.Series or None
        Grouping key for ``split="group_kfold"`` (year, province, firm).
    time : pandas.Series or None
        Period key for ``split="temporal"``. Anything comparable with ``<=`` works:
        integers, dates, ``pandas.Timestamp``.
    meta : dict
        Free-form provenance: ``{"name": ..., "project": ..., "anchor_events": [...]}``.
        ``meta["name"]`` (else ``meta["project"]``) names the dataset in reports.

    Raises
    ------
    ValueError
        If ``X`` is not a DataFrame, any companion series has the wrong length or a
        different index, ``unit_id`` has duplicates, or ``y`` holds a value other than
        0, 1 or NaN.

    Notes
    -----
    A list or array passed where a Series is expected is wrapped in a Series carrying
    ``X.index`` -- that is a convenience, not a coercion of values. Index *mismatches* are
    an error rather than something pandas resolves silently, because silent alignment is
    how labels end up attached to the wrong rows.
    """

    unit_id: pd.Series
    X: pd.DataFrame
    y: pd.Series | None = None
    groups: pd.Series | None = None
    time: pd.Series | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.X, pd.DataFrame):
            raise ValueError(f"X must be a pandas.DataFrame; got {type(self.X).__name__}")
        if not isinstance(self.meta, dict):
            raise ValueError(f"meta must be a dict; got {type(self.meta).__name__}")
        n = len(self.X)
        index = self.X.index
        self.unit_id = _to_series(self.unit_id, "unit_id", n, index)
        duplicated = self.unit_id.duplicated()
        if bool(duplicated.any()):
            examples = self.unit_id[duplicated].unique()[:5].tolist()
            raise ValueError(
                f"unit_id must be unique; {int(duplicated.sum())} duplicate rows, e.g. {examples}"
            )
        for name in ("y", "groups", "time"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, _to_series(value, name, n, index))
        if self.y is not None:
            values = _as_float_1d(self.y, "y")
            finite = values[~np.isnan(values)]
            if not np.all((finite == 0.0) | (finite == 1.0)):
                bad = np.unique(finite[(finite != 0.0) & (finite != 1.0)])[:5]
                raise ValueError(
                    f"y must contain only 1 (confirmed), 0 (presumed clean) or NaN "
                    f"(unlabeled); found e.g. {bad.tolist()}"
                )

    def __len__(self) -> int:
        return len(self.X)

    @property
    def n(self) -> int:
        """Number of rows."""
        return len(self.X)

    @property
    def name(self) -> str:
        """``meta["name"]``, else ``meta["project"]``, else ``"dataset"``."""
        return str(self.meta.get("name", self.meta.get("project", "dataset")))

    def y_values(self) -> np.ndarray:
        """Labels as a float array with ``NaN`` for unlabeled rows.

        Raises
        ------
        ValueError
            If the dataset has no labels at all (``y is None``).
        """
        if self.y is None:
            raise ValueError("this Dataset has no labels (y is None)")
        return _as_float_1d(self.y, "y")

    def take(self, positions: ArrayLike) -> Dataset:
        """Positional subset (like ``.iloc``) of every aligned field; ``meta`` is copied."""
        idx = np.asarray(positions, dtype=int)
        return Dataset(
            unit_id=self.unit_id.iloc[idx],
            X=self.X.iloc[idx],
            y=None if self.y is None else self.y.iloc[idx],
            groups=None if self.groups is None else self.groups.iloc[idx],
            time=None if self.time is None else self.time.iloc[idx],
            meta=dict(self.meta),
        )

    def labeled(self) -> Dataset:
        """Rows whose label is not NaN (both confirmed positives and presumed-clean 0s)."""
        return self.take(np.flatnonzero(~np.isnan(self.y_values())))

    def positives(self) -> Dataset:
        """Rows with ``y == 1`` (confirmed distortion)."""
        return self.take(np.flatnonzero(self.y_values() == 1.0))


# --------------------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------------------


@runtime_checkable
class Detector(Protocol):
    """Anything that can be fit on a :class:`Dataset` and score one.

    ``score`` returns one float per row, higher = more suspicious. ``fit`` may ignore the
    labels entirely (unsupervised detectors) and should return ``self``.

    The protocol is ``runtime_checkable``, so ``isinstance(obj, Detector)`` checks that the
    object has ``name``, ``fit`` and ``score`` (attribute presence only -- Python cannot
    check signatures at runtime). ``issubclass`` is *not* available, because the protocol
    has a non-method member (``name``).
    """

    name: str

    def fit(self, ds: Dataset) -> Detector: ...

    def score(self, ds: Dataset) -> np.ndarray: ...


def _check_scores(values: ArrayLike, ds: Dataset, who: str) -> np.ndarray:
    scores = _as_float_1d(values, f"{who} scores")
    if scores.size != len(ds):
        raise ValueError(
            f"{who}.score returned {scores.size} values for a Dataset of {len(ds)} rows"
        )
    if not np.all(np.isfinite(scores)):
        n_bad = int(np.count_nonzero(~np.isfinite(scores)))
        raise ValueError(f"{who}.score returned {n_bad} non-finite values")
    return scores


class FunctionDetector:
    """Wrap a plain ``f(X: DataFrame) -> scores`` function; ``fit`` is a no-op.

    This is how an unsupervised statistic (a Benford chi-square per unit, a bunching
    z-score) enters the harness without pretending to be an estimator.

    Parameters
    ----------
    func : callable
        Takes ``ds.X`` and returns one number per row.
    name : str
        Name used in reports.
    higher_is_suspicious : bool
        If False the returned scores are negated, so that the harness convention (higher =
        more suspicious) holds regardless of the sign the statistic naturally has.
    """

    #: fit is a no-op, so the fit set is irrelevant; declared for the protocol.
    wants_unlabeled = False

    def __init__(
        self,
        func: Callable[[pd.DataFrame], ArrayLike],
        name: str = "function",
        *,
        higher_is_suspicious: bool = True,
    ) -> None:
        if not callable(func):
            raise ValueError(f"func must be callable; got {type(func).__name__}")
        self.func = func
        self.name = str(name)
        self.higher_is_suspicious = bool(higher_is_suspicious)

    def fit(self, ds: Dataset) -> FunctionDetector:
        """No-op: the wrapped function has no parameters to learn (``ds`` is ignored)."""
        return self

    def score(self, ds: Dataset) -> np.ndarray:
        scores = _check_scores(self.func(ds.X), ds, self.name)
        return scores if self.higher_is_suspicious else -scores


class SklearnDetector:
    """Wrap any scikit-learn estimator with ``decision_function`` or ``predict_proba``.

    Fitting uses the *labeled* rows only (``y`` in {0, 1}); unlabeled rows are dropped. The
    0s are taken at face value as negatives -- use :class:`PUDetector` when they are merely
    presumed clean.

    Parameters
    ----------
    estimator : sklearn estimator
        Cloned before fitting, so the instance handed in is never mutated and folds cannot
        leak into each other.
    name : str or None
        Defaults to ``"sklearn:<EstimatorClass>"``.
    score_method : {"auto", "decision_function", "predict_proba"}
        ``"auto"`` prefers ``decision_function`` and falls back to ``predict_proba``
        (column of class 1).
    """

    #: A supervised estimator takes the 0s at face value as negatives and has no use for
    #: rows with no label.
    wants_unlabeled = False

    def __init__(
        self,
        estimator: Any,
        name: str | None = None,
        *,
        score_method: Literal["auto", "decision_function", "predict_proba"] = "auto",
    ) -> None:
        if not hasattr(estimator, "fit"):
            raise ValueError("estimator must have a fit method")
        if score_method not in ("auto", "decision_function", "predict_proba"):
            raise ValueError(
                "score_method must be 'auto', 'decision_function' or 'predict_proba'; "
                f"got {score_method!r}"
            )
        if score_method == "auto":
            if not (hasattr(estimator, "decision_function") or hasattr(estimator, "predict_proba")):
                raise ValueError(
                    "estimator must expose decision_function or predict_proba to produce "
                    "continuous scores"
                )
        elif not hasattr(estimator, score_method):
            raise ValueError(f"estimator has no {score_method}")
        self.estimator = estimator
        self.score_method = score_method
        self.name = str(name) if name is not None else f"sklearn:{type(estimator).__name__}"
        self.estimator_: Any = None

    def fit(self, ds: Dataset) -> SklearnDetector:
        labeled = ds.labeled()
        if len(labeled) == 0:
            raise ValueError(
                f"{self.name}.fit needs labeled rows; none of the {len(ds)} rows carry a 0/1 label"
            )
        y = labeled.y_values()
        classes = np.unique(y)
        if classes.size < 2:
            raise ValueError(
                f"{self.name}.fit needs both classes among the labeled rows; got only "
                f"{classes.tolist()}"
            )
        self.estimator_ = clone(self.estimator)
        self.estimator_.fit(labeled.X, y.astype(int))
        return self

    def _score_matrix(self, X: pd.DataFrame) -> np.ndarray:
        method = self.score_method
        if method == "auto":
            method = (
                "decision_function"
                if hasattr(self.estimator_, "decision_function")
                else "predict_proba"
            )
        raw = getattr(self.estimator_, method)(X)
        raw = np.asarray(raw, dtype=float)
        if method == "predict_proba" or raw.ndim == 2:
            if raw.ndim != 2:
                raise ValueError(f"{method} returned shape {raw.shape}; expected 2-D")
            classes = list(getattr(self.estimator_, "classes_", [0, 1]))
            if 1 not in classes:
                raise ValueError(f"fitted estimator has no class 1; classes_={classes}")
            raw = raw[:, classes.index(1)]
        return raw

    def score(self, ds: Dataset) -> np.ndarray:
        if self.estimator_ is None:
            raise RuntimeError(f"{self.name}.score called before fit")
        return _check_scores(self._score_matrix(ds.X), ds, self.name)


class PUDetector:
    """Wrap a positive-unlabeled estimator from :mod:`forensics_core.labels.pu`.

    Label handling (important, and deliberately different from :class:`SklearnDetector`)
    -----------------------------------------------------------------------------------
    The PU estimators take ``s`` in {1 = labeled positive, 0 = unlabeled}. This wrapper
    builds ``s`` as::

        y == 1   -> s = 1   (confirmed distortion)
        y == 0   -> s = 0   (presumed clean: treated as UNLABELED, not as a negative)
        y is NaN -> s = 0   (unlabeled)

    Treating the 0s as unlabeled is the whole point of PU learning with enforcement data:
    "not prosecuted" is not "clean" (Elkan and Noto 2008; Mordelet and Vert 2014). Every
    row of the dataset is used for fitting, labeled or not.

    Parameters
    ----------
    kind : {"elkan_noto", "bagging"}
        Selects ``ElkanNotoPU`` or ``BaggingPU`` from ``forensics_core.labels.pu``, imported
        lazily inside :meth:`fit` so that this module imports even while that subpackage is
        still being written.
    base_estimator : sklearn estimator or None
        Passed straight through; ``None`` lets the PU class pick its own default.
    name : str or None
        Defaults to ``"pu:<kind>"``.
    **estimator_kwargs
        Forwarded to the PU class constructor (``hold_out_ratio``, ``n_estimators``,
        ``random_state``, ...).
    """

    #: PU estimation needs the unlabeled pool: the label-frequency estimate is computed
    #: against it, so fitting on the labeled rows alone silently changes the method.
    wants_unlabeled = True

    _CLASS_FOR_KIND = {"elkan_noto": "ElkanNotoPU", "bagging": "BaggingPU"}

    def __init__(
        self,
        kind: Literal["elkan_noto", "bagging"] = "elkan_noto",
        base_estimator: Any = None,
        name: str | None = None,
        **estimator_kwargs: Any,
    ) -> None:
        if kind not in self._CLASS_FOR_KIND:
            raise ValueError(f"kind must be one of {sorted(self._CLASS_FOR_KIND)}; got {kind!r}")
        self.kind = kind
        self.base_estimator = base_estimator
        self.estimator_kwargs = dict(estimator_kwargs)
        self.name = str(name) if name is not None else f"pu:{kind}"
        self.estimator_: Any = None

    def _pu_class(self) -> Any:
        try:
            from forensics_core.labels import pu as pu_module
        except ImportError as exc:  # pragma: no cover - depends on install state
            raise ImportError(
                "PUDetector needs forensics_core.labels.pu (ElkanNotoPU / BaggingPU); "
                "that module is not importable"
            ) from exc
        class_name = self._CLASS_FOR_KIND[self.kind]
        cls = getattr(pu_module, class_name, None)
        if cls is None:
            raise ImportError(f"forensics_core.labels.pu does not define {class_name}")
        return cls

    def pu_labels(self, ds: Dataset) -> np.ndarray:
        """The ``s`` vector handed to the PU estimator: 1 for ``y == 1``, else 0."""
        if ds.y is None:
            return np.zeros(len(ds), dtype=int)
        y = ds.y_values()
        return (y == 1.0).astype(int)

    def fit(self, ds: Dataset) -> PUDetector:
        s = self.pu_labels(ds)
        n_pos = int(s.sum())
        if n_pos == 0:
            raise ValueError(f"{self.name}.fit needs at least one positive (y == 1); found none")
        if n_pos == s.size:
            raise ValueError(
                f"{self.name}.fit needs unlabeled rows as well; all {s.size} rows are positive"
            )
        cls = self._pu_class()
        self.estimator_ = cls(base_estimator=self.base_estimator, **self.estimator_kwargs)
        self.estimator_.fit(_numeric_matrix(ds.X), s)
        return self

    def score(self, ds: Dataset) -> np.ndarray:
        if self.estimator_ is None:
            raise RuntimeError(f"{self.name}.score called before fit")
        X = _numeric_matrix(ds.X)
        if hasattr(self.estimator_, "decision_function"):
            raw = np.asarray(self.estimator_.decision_function(X), dtype=float)
        else:
            proba = np.asarray(self.estimator_.predict_proba(X), dtype=float)
            raw = proba[:, 1] if proba.ndim == 2 else proba
        return _check_scores(raw, ds, self.name)


def _numeric_matrix(X: pd.DataFrame) -> np.ndarray:
    """``X`` as a float matrix, raising ValueError on non-numeric columns."""
    try:
        return X.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "X must be entirely numeric for this detector; encode or drop the non-numeric "
            f"columns first ({exc})"
        ) from exc


# --------------------------------------------------------------------------------------
# Specification and report
# --------------------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """Scalars pass through; anything else (Timestamp, Period, ...) becomes its ``str``."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


@dataclass
class EvalSpec:
    """How a detector is to be evaluated.

    Parameters
    ----------
    split : {"temporal", "group_kfold", "anchor_holdout", "none"}
        See the module docstring. ``"none"`` produces in-sample metrics.
    train_end : Any
        ``split="temporal"``: last training period, inclusive (rows with
        ``time <= train_end`` train, the rest test).
    n_splits : int
        ``split="group_kfold"``: number of folds; at least 2.
    anchor_mask : pandas.Series or None
        ``split="anchor_holdout"``: boolean, True for the rows that *are* the anchor. Those
        rows are the test set; training uses everything else.
    ks : tuple
        Cut-offs for the ``@k`` metrics. Ints are counts, floats in (0, 1) are fractions of
        the test set.
    metrics : tuple
        Any of ``"roc_auc"``, ``"average_precision"``, ``"ndcg_at_k"``,
        ``"precision_at_k"``, ``"recall_at_k"``.

    Raises
    ------
    ValueError
        On an unknown split or metric name, ``n_splits < 2``, an empty or invalid ``ks``.
    """

    split: SplitKind = "temporal"
    train_end: Any = None
    n_splits: int = 5
    anchor_mask: pd.Series | None = None
    ks: tuple[int | float, ...] = (0.01, 0.05, 0.10)
    metrics: tuple[str, ...] = ("roc_auc", "average_precision", "ndcg_at_k", "precision_at_k")

    def __post_init__(self) -> None:
        if self.split not in ("temporal", "group_kfold", "anchor_holdout", "none"):
            raise ValueError(
                "split must be 'temporal', 'group_kfold', 'anchor_holdout' or 'none'; "
                f"got {self.split!r}"
            )
        if not isinstance(self.n_splits, int | np.integer) or int(self.n_splits) < 2:
            raise ValueError(f"n_splits must be an int >= 2; got {self.n_splits!r}")
        self.n_splits = int(self.n_splits)
        if isinstance(self.ks, int | float | str):
            raise ValueError(f"ks must be a sequence of cut-offs; got {self.ks!r}")
        self.ks = tuple(self.ks)
        if not self.ks:
            raise ValueError("ks must not be empty")
        for k in self.ks:
            _resolve_k(k, 10**9)  # validates type and range; n is irrelevant here
        if isinstance(self.metrics, str):
            raise ValueError("metrics must be a sequence of names, not a single string")
        self.metrics = tuple(self.metrics)
        if not self.metrics:
            raise ValueError("metrics must not be empty")
        known = set(_SCALAR_METRICS) | set(_AT_K_METRICS)
        unknown = [m for m in self.metrics if m not in known]
        if unknown:
            raise ValueError(f"unknown metric(s) {unknown}; known: {sorted(known)}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly view; ``anchor_mask`` is summarised by its size, not copied."""
        mask = None
        if self.anchor_mask is not None:
            values = _as_bool_mask(self.anchor_mask, len(self.anchor_mask), "anchor_mask")
            mask = {"n_rows": int(values.size), "n_anchor": int(values.sum())}
        return {
            "split": self.split,
            "train_end": _plain(self.train_end),
            "n_splits": self.n_splits,
            "anchor_mask": mask,
            "ks": [_plain(k) for k in self.ks],
            "metrics": list(self.metrics),
        }


@dataclass
class EvalReport:
    """Result of :func:`evaluate`.

    Attributes
    ----------
    detector, dataset : str
        Names, for tabulating several runs together.
    spec : EvalSpec
        The specification that produced this report.
    metrics : dict of str to float
        Mean over usable folds (a single fold for every split except ``group_kfold``).
        Keys are ``"roc_auc"``, ``"average_precision"``, ``"ndcg@1%"``, ``"precision@5"``...
    per_fold : list of dict
        One entry per fold: ``fold``, ``n_train`` (rows given to ``fit``), ``n_test``
        (labeled test rows scored), ``n_test_rows`` (all test rows scored), ``n_pos_test``,
        ``metrics``, ``test_unit_ids``, ``skipped`` and ``reason``.
    n_train, n_test, n_pos_test : int
        Summed over folds: training rows, labeled test rows, positives among them.
    in_sample : bool
        True when ``spec.split == "none"``: the same rows were used to fit and to score, so
        every number here is optimistic.
    notes : tuple of str
        Warnings worth carrying with the numbers (skipped folds, in-sample scoring).
    """

    detector: str
    dataset: str
    spec: EvalSpec
    metrics: dict[str, float]
    per_fold: list[dict]
    n_train: int
    n_test: int
    n_pos_test: int
    in_sample: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return jsonable(
            {
                "detector": self.detector,
                "dataset": self.dataset,
                "spec": self.spec.to_dict(),
                "metrics": self.metrics,
                "per_fold": self.per_fold,
                "n_train": self.n_train,
                "n_test": self.n_test,
                "n_pos_test": self.n_pos_test,
                "in_sample": self.in_sample,
                "notes": list(self.notes),
            }
        )

    def summary_table(self) -> pd.DataFrame:
        """Tidy one-row-per-metric table; ``pandas.concat`` several to compare detectors."""
        rows = [
            {
                "detector": self.detector,
                "dataset": self.dataset,
                "split": self.spec.split,
                "in_sample": self.in_sample,
                "n_train": self.n_train,
                "n_test": self.n_test,
                "n_pos_test": self.n_pos_test,
                "metric": name,
                "value": float(value),
            }
            for name, value in self.metrics.items()
        ]
        return pd.DataFrame(
            rows,
            columns=[
                "detector",
                "dataset",
                "split",
                "in_sample",
                "n_train",
                "n_test",
                "n_pos_test",
                "metric",
                "value",
            ],
        )


@dataclass(frozen=True)
class TransferResult:
    """Result of :func:`transfer`: target ranking plus the source-calibrated reading of it.

    Attributes
    ----------
    scores : pandas.DataFrame
        Columns ``unit_id``, ``score``, ``rank`` -- one row per target unit, sorted by score
        descending (rank 1 = most suspicious).
    source_report : EvalReport or None
        Present when ``source_spec`` was given: how the detector performed on its home
        project.
    calibration : pandas.DataFrame
        Columns ``score_threshold``, ``precision``, ``recall``, ``n_selected``, computed on
        the **source** labels, thresholds ascending. Read a target score against it: "on the
        source project, taking everything scoring at least this had precision p". ``recall``
        is non-increasing in the threshold by construction; ``precision`` is not monotone in
        general -- it is an empirical curve, and it is noisy in the top few rows.
    detector, source, target : str
        Names carried through for tabulation.
    n_source_fit : int
        Number of source rows the detector was fitted on.
    """

    scores: pd.DataFrame
    source_report: EvalReport | None
    calibration: pd.DataFrame
    detector: str = ""
    source: str = ""
    target: str = ""
    n_source_fit: int = 0

    def to_dict(self) -> dict[str, Any]:
        return jsonable(
            {
                "detector": self.detector,
                "source": self.source,
                "target": self.target,
                "n_source_fit": self.n_source_fit,
                "scores": self.scores.to_dict(orient="records"),
                "calibration": self.calibration.to_dict(orient="records"),
                "source_report": None
                if self.source_report is None
                else self.source_report.to_dict(),
            }
        )


# --------------------------------------------------------------------------------------
# splits and evaluation
# --------------------------------------------------------------------------------------


def _as_bool_mask(mask: Any, n: int, name: str) -> np.ndarray:
    if isinstance(mask, pd.Series):
        values = mask.to_numpy()
    else:
        values = np.asarray(mask)
    if values.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {values.shape}")
    if values.size != n:
        raise ValueError(f"{name} has length {values.size} but the dataset has {n} rows")
    if values.dtype == bool:
        return values.astype(bool)
    if values.dtype.kind in "iuf":
        if not np.all(np.isin(values, (0, 1))):
            raise ValueError(f"{name} must be boolean (or 0/1) with no missing values")
        return values.astype(bool)
    raise ValueError(f"{name} must be boolean; got dtype {values.dtype}")


def _temporal_folds(ds: Dataset, spec: EvalSpec) -> list[tuple[np.ndarray, np.ndarray]]:
    if ds.time is None:
        raise ValueError("split='temporal' needs Dataset.time")
    if spec.train_end is None:
        raise ValueError("split='temporal' needs EvalSpec.train_end (last training period)")
    if bool(ds.time.isna().any()):
        raise ValueError("Dataset.time has missing values; a row with no period cannot be split")
    try:
        is_train = (ds.time <= spec.train_end).to_numpy(dtype=bool)
    except TypeError as exc:
        raise ValueError(
            f"cannot compare Dataset.time (dtype {ds.time.dtype}) with train_end={spec.train_end!r}"
        ) from exc
    train = np.flatnonzero(is_train)
    test = np.flatnonzero(~is_train)
    if train.size == 0:
        raise ValueError(f"no rows with time <= train_end={spec.train_end!r}; nothing to train on")
    if test.size == 0:
        raise ValueError(f"every row has time <= train_end={spec.train_end!r}; nothing to test on")
    return [(train, test)]


def _group_folds(ds: Dataset, spec: EvalSpec) -> list[tuple[np.ndarray, np.ndarray]]:
    if ds.groups is None:
        raise ValueError("split='group_kfold' needs Dataset.groups")
    groups = ds.groups.to_numpy()
    n_groups = int(pd.unique(ds.groups).size)
    if n_groups < spec.n_splits:
        raise ValueError(
            f"GroupKFold needs at least n_splits={spec.n_splits} distinct groups; got {n_groups}"
        )
    splitter = GroupKFold(n_splits=spec.n_splits)
    placeholder = np.zeros((len(ds), 1))
    return [
        (np.asarray(tr, dtype=int), np.asarray(te, dtype=int))
        for tr, te in splitter.split(placeholder, groups=groups)
    ]


def _anchor_folds(ds: Dataset, spec: EvalSpec) -> list[tuple[np.ndarray, np.ndarray]]:
    if spec.anchor_mask is None:
        raise ValueError("split='anchor_holdout' needs EvalSpec.anchor_mask")
    mask = _as_bool_mask(spec.anchor_mask, len(ds), "anchor_mask")
    test = np.flatnonzero(mask)
    train = np.flatnonzero(~mask)
    if test.size == 0:
        raise ValueError("anchor_mask selects no rows; there is no anchor to hold out")
    if train.size == 0:
        raise ValueError("anchor_mask selects every row; nothing is left to train on")
    return [(train, test)]


def _make_folds(ds: Dataset, spec: EvalSpec) -> list[tuple[np.ndarray, np.ndarray]]:
    if spec.split == "temporal":
        return _temporal_folds(ds, spec)
    if spec.split == "group_kfold":
        return _group_folds(ds, spec)
    if spec.split == "anchor_holdout":
        return _anchor_folds(ds, spec)
    labeled = np.flatnonzero(~np.isnan(ds.y_values()))
    if labeled.size == 0:
        raise ValueError("split='none' needs labeled rows; every y is NaN")
    return [(labeled, labeled)]


def _compute_metrics(y: np.ndarray, scores: np.ndarray, spec: EvalSpec) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in spec.metrics:
        if name in _SCALAR_METRICS:
            out[name] = float(_SCALAR_METRICS[name](y, scores))
        else:
            label, func = _AT_K_METRICS[name]
            for k in spec.ks:
                out[f"{label}@{_k_label(k)}"] = float(func(y, scores, k))
    return out


def fit_indices(detector: Detector, ds: Dataset, train_idx: np.ndarray) -> np.ndarray:
    """The rows a detector should be fitted on, given a fold's training indices.

    A detector that wants the unlabeled pool gets every unlabeled row added to its training
    set, on top of the fold's own training rows.

    This cannot leak. Test folds are built from labeled rows only, so an unlabeled row is never
    in a test set, and adding all of them to every training fold tells the detector nothing
    about the rows it will be scored on. What it does do is give a positive-unlabeled estimator
    the pool its label-frequency estimate is computed against, without which it is a different
    method wearing the same name.
    """
    if not getattr(detector, "wants_unlabeled", False):
        return train_idx
    unlabeled = np.flatnonzero(np.isnan(ds.y_values()))
    return np.union1d(np.asarray(train_idx), unlabeled)


def fit_set(detector: Detector, ds: Dataset) -> Dataset:
    """The rows a detector should see at fit time.

    A detector declares its own need through ``wants_unlabeled``; the caller does not guess.
    A positive-unlabeled estimator needs the unlabeled pool, because that pool is what its
    label-frequency estimate is computed against, and handing it only the labeled rows turns it
    into something else without any error being raised.

    :func:`evaluate` and :func:`transfer` both route through here. They used to choose
    differently, so a ``source_report`` was not strictly a report on the object that scored the
    target, which is the comparison the whole transfer design rests on.
    """
    if getattr(detector, "wants_unlabeled", False):
        return ds
    labeled = ds.labeled()
    return labeled if len(labeled) else ds


def evaluate(detector: Detector, ds: Dataset, spec: EvalSpec) -> EvalReport:
    """Fit and score ``detector`` on ``ds`` under ``spec``, and report rank metrics.

    The detector is deep-copied per fold, fitted on the training rows (*all* of them,
    labeled or not, so PU detectors keep their unlabeled pool) and asked to score the test
    rows. Metrics are then computed on the labeled test rows only. A fold whose labeled test
    rows do not contain both a positive and a negative is skipped, recorded in ``per_fold``
    with a reason, and left out of the averages.

    Parameters
    ----------
    detector : Detector
        Must expose ``name``, ``fit`` and ``score``.
    ds : Dataset
        Must carry labels.
    spec : EvalSpec

    Returns
    -------
    EvalReport
        ``metrics`` are unweighted means over the usable folds; ``n_train``/``n_test``/
        ``n_pos_test`` are sums over folds (so for ``group_kfold`` ``n_test`` is the whole
        labeled sample, and ``n_train`` counts each row several times, once per fold that
        trained on it).

    Raises
    ------
    ValueError
        If the detector does not satisfy the protocol, the dataset has no labels, the split
        cannot be built (missing ``time``/``groups``/``anchor_mask``, empty side), or no
        fold was usable.
    """
    if not isinstance(ds, Dataset):
        raise ValueError(f"ds must be a Dataset; got {type(ds).__name__}")
    if not isinstance(spec, EvalSpec):
        raise ValueError(f"spec must be an EvalSpec; got {type(spec).__name__}")
    if not isinstance(detector, Detector):
        raise ValueError(
            "detector must implement the Detector protocol (name, fit, score); got "
            f"{type(detector).__name__}"
        )
    if ds.y is None:
        raise ValueError("evaluate needs labels; Dataset.y is None")

    y_all = ds.y_values()
    folds = _make_folds(ds, spec)
    notes: list[str] = []
    in_sample = spec.split == "none"
    if in_sample:
        notes.append(
            "split='none': the detector was fit and scored on the same labeled rows, so "
            "these metrics are IN-SAMPLE and optimistic; they are not evidence of transfer."
        )

    per_fold: list[dict] = []
    for i, (train_idx, test_idx) in enumerate(folds):
        fold_detector = copy.deepcopy(detector)
        fold_detector.fit(ds.take(fit_indices(fold_detector, ds, train_idx)))
        test_ds = ds.take(test_idx)
        scores = _check_scores(fold_detector.score(test_ds), test_ds, getattr(detector, "name", ""))
        y_test = y_all[test_idx]
        labeled = ~np.isnan(y_test)
        y_lab = y_test[labeled]
        s_lab = scores[labeled]
        n_pos = int(np.count_nonzero(y_lab == 1.0))
        n_neg = int(y_lab.size - n_pos)
        entry: dict[str, Any] = {
            "fold": i,
            "n_train": int(train_idx.size),
            "n_test": int(y_lab.size),
            "n_test_rows": int(test_idx.size),
            "n_pos_test": n_pos,
            "test_unit_ids": ds.unit_id.iloc[test_idx[labeled]].tolist(),
            "skipped": False,
            "reason": None,
            "metrics": {},
        }
        if n_pos == 0 or n_neg == 0:
            entry["skipped"] = True
            entry["reason"] = (
                f"fold {i} has n_pos={n_pos}, n_neg={n_neg} among its labeled test rows; "
                "rank metrics are undefined there"
            )
            notes.append(str(entry["reason"]))
        else:
            entry["metrics"] = _compute_metrics(y_lab, s_lab, spec)
        per_fold.append(entry)

    usable = [entry for entry in per_fold if not entry["skipped"]]
    if not usable:
        raise ValueError(
            "no fold had both a positive and a negative among its labeled test rows; "
            "nothing could be scored"
        )
    names: list[str] = []
    for entry in usable:
        for key in entry["metrics"]:
            if key not in names:
                names.append(key)
    metrics = {
        key: float(np.mean([entry["metrics"][key] for entry in usable if key in entry["metrics"]]))
        for key in names
    }
    return EvalReport(
        detector=str(getattr(detector, "name", type(detector).__name__)),
        dataset=ds.name,
        spec=spec,
        metrics=metrics,
        per_fold=per_fold,
        n_train=int(sum(entry["n_train"] for entry in per_fold)),
        n_test=int(sum(entry["n_test"] for entry in per_fold)),
        n_pos_test=int(sum(entry["n_pos_test"] for entry in per_fold)),
        in_sample=in_sample,
        notes=tuple(notes),
    )


def _calibration_curve(y: np.ndarray, scores: np.ndarray, max_points: int = 100) -> pd.DataFrame:
    """Precision and recall of "select everything scoring >= t", for a grid of ``t``.

    Thresholds are the distinct observed scores (so a threshold always selects whole tie
    groups), thinned to at most ``max_points`` evenly spaced values and returned ascending.
    """
    order = _rank_order(scores)
    y_sorted = y[order]
    s_sorted = scores[order]
    true_positives = np.cumsum(y_sorted == 1.0)
    n_selected = np.arange(1, y_sorted.size + 1)
    n_pos = int(true_positives[-1])
    if n_pos == 0:
        raise ValueError("cannot calibrate a score without positives in the source labels")
    last_of_run = np.flatnonzero(np.append(np.diff(s_sorted) != 0.0, True))
    if last_of_run.size > max_points:
        keep = np.unique(np.round(np.linspace(0, last_of_run.size - 1, max_points)).astype(int))
        last_of_run = last_of_run[keep]
    frame = pd.DataFrame(
        {
            "score_threshold": s_sorted[last_of_run],
            "precision": true_positives[last_of_run] / n_selected[last_of_run],
            "recall": true_positives[last_of_run] / n_pos,
            "n_selected": n_selected[last_of_run],
        }
    )
    return frame.iloc[::-1].reset_index(drop=True)


def transfer(
    detector: Detector,
    source: Dataset,
    target: Dataset,
    source_spec: EvalSpec | None = None,
    *,
    fit_on: Literal["auto", "labeled", "all"] = "auto",
    max_calibration_points: int = 100,
) -> TransferResult:
    """Fit a detector on its home project and score another one with it.

    Parameters
    ----------
    detector : Detector
        Deep-copied first; the instance handed in is not fitted or mutated.
    source : Dataset
        The project the detector was developed on. Must carry labels with at least one
        positive.
    target : Dataset
        The project to score. Labels are not needed (and are ignored here).
    source_spec : EvalSpec or None
        If given, :func:`evaluate` is run on the source first and the report is carried in
        the result, so the transferred ranking travels with an honest out-of-sample record
        of what the detector did at home.
    fit_on : {"labeled", "all"}
        ``"labeled"`` (default, and what the interface contract specifies) fits on the
        labeled source rows. ``"all"`` fits on every source row, which is what a
        :class:`PUDetector` wants when the unlabeled pool is informative.
    max_calibration_points : int
        Maximum number of rows in the calibration curve.

    Returns
    -------
    TransferResult

    Notes
    -----
    The calibration curve is computed on the *training* rows of the source, so it is
    in-sample and optimistic: it says how the fitted detector orders the source, not how it
    would order fresh source data. Use ``source_spec`` for the honest number and read the
    curve as a translation table for score levels, not as a performance claim.
    """
    if not isinstance(source, Dataset) or not isinstance(target, Dataset):
        raise ValueError("source and target must both be Dataset instances")
    if not isinstance(detector, Detector):
        raise ValueError(
            "detector must implement the Detector protocol (name, fit, score); got "
            f"{type(detector).__name__}"
        )
    if fit_on not in ("labeled", "all", "auto"):
        raise ValueError(f"fit_on must be 'auto', 'labeled' or 'all'; got {fit_on!r}")
    if source.y is None:
        raise ValueError("transfer needs labels on the source dataset")
    if len(target) == 0:
        raise ValueError("target dataset is empty; nothing to score")

    source_report = evaluate(detector, source, source_spec) if source_spec is not None else None

    labeled_source = source.labeled()
    if len(labeled_source) == 0:
        raise ValueError("source dataset has no labeled rows to fit on")
    if fit_on == "auto":
        fit_ds = fit_set(detector, source)
    else:
        fit_ds = labeled_source if fit_on == "labeled" else source

    fitted = copy.deepcopy(detector)
    fitted.fit(fit_ds)

    target_scores = _check_scores(
        fitted.score(target), target, str(getattr(detector, "name", "detector"))
    )
    order = _rank_order(target_scores)
    scores_frame = pd.DataFrame(
        {
            "unit_id": target.unit_id.to_numpy()[order],
            "score": target_scores[order],
            "rank": np.arange(1, target_scores.size + 1),
        }
    )

    source_scores = _check_scores(
        fitted.score(labeled_source), labeled_source, str(getattr(detector, "name", "detector"))
    )
    calibration = _calibration_curve(
        labeled_source.y_values(), source_scores, max_points=max_calibration_points
    )
    return TransferResult(
        scores=scores_frame,
        source_report=source_report,
        calibration=calibration,
        detector=str(getattr(detector, "name", type(detector).__name__)),
        source=source.name,
        target=target.name,
        n_source_fit=len(fit_ds),
    )


# --------------------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------------------

#: name -> factory. The factory is called with the keyword arguments given to
#: :func:`make_detector`, so entries are usually the detector classes themselves.
DETECTOR_REGISTRY: dict[str, Callable[..., Detector]] = {}


def register_detector(name: str, *, overwrite: bool = False) -> Callable[[Any], Any]:
    """Decorator registering a detector factory (usually the class) under ``name``.

    Parameters
    ----------
    name : str
        Registry key, e.g. ``"benford_chi2"``.
    overwrite : bool
        Re-registering a name is an error unless this is True, so two projects cannot
        silently claim the same key.

    Returns
    -------
    callable
        The decorator; it returns the factory unchanged.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("detector name must be a non-empty string")

    def decorator(factory: Any) -> Any:
        if not callable(factory):
            raise ValueError(f"detector factory for {name!r} must be callable")
        if name in DETECTOR_REGISTRY and not overwrite:
            raise ValueError(
                f"detector {name!r} is already registered "
                f"({DETECTOR_REGISTRY[name]!r}); pass overwrite=True to replace it"
            )
        DETECTOR_REGISTRY[name] = factory
        return factory

    return decorator


def make_detector(name: str, /, **kw: Any) -> Detector:
    """Build a registered detector by name.

    ``name`` is positional-only so that ``**kw`` can carry a detector's own ``name=``
    argument (``make_detector("function", func=f, name="benford")``) without colliding with
    the registry key.

    Raises
    ------
    ValueError
        If ``name`` is not registered, or the factory returns something that does not
        satisfy the :class:`Detector` protocol.
    """
    if name not in DETECTOR_REGISTRY:
        raise ValueError(f"unknown detector {name!r}; registered: {sorted(DETECTOR_REGISTRY)}")
    detector = DETECTOR_REGISTRY[name](**kw)
    if not isinstance(detector, Detector):
        raise ValueError(
            f"factory for {name!r} returned {type(detector).__name__}, which does not "
            "implement the Detector protocol (name, fit, score)"
        )
    return detector


def _register_builtins() -> None:
    """Register the detectors shipped with the library (idempotent)."""
    register_detector("function", overwrite=True)(FunctionDetector)
    register_detector("sklearn", overwrite=True)(SklearnDetector)

    def elkan_noto(**kw: Any) -> PUDetector:
        return PUDetector(kind="elkan_noto", **kw)

    def bagging(**kw: Any) -> PUDetector:
        return PUDetector(kind="bagging", **kw)

    register_detector("pu_elkan_noto", overwrite=True)(elkan_noto)
    register_detector("pu_bagging", overwrite=True)(bagging)


_register_builtins()

"""Rank metrics for detectors whose positive base rate is tiny.

Accuracy is meaningless when 0.3% of firm-years are fraudulent: a detector that flags
nothing scores 99.7%. Everything here therefore scores a *ranking* -- how much of the
positive mass the detector concentrates at the top of the list.

Sources
-------
- Hanley, J. A. and McNeil, B. J. (1982). "The meaning and use of the area under a
  receiver operating characteristic (ROC) curve." *Radiology* 143(1): 29-36.
- Manning, C. D., Raghavan, P. and Schuetze, H. (2008). *Introduction to Information
  Retrieval*, Cambridge University Press, ch. 8 (precision@k, recall@k, average precision).
- Jaervelin, K. and Kekaelaeinen, J. (2002). "Cumulated gain-based evaluation of IR
  techniques." *ACM Transactions on Information Systems* 20(4): 422-446 (DCG / nDCG).
- Bao, Y., Ke, B., Li, B., Yu, Y. J. and Zhang, J. (2020). "Detecting accounting fraud in
  publicly traded U.S. firms using a machine learning approach." *Journal of Accounting
  Research* 58(1): 199-235. They report NDCG@k with k = 1% of the test firm-years, which is
  why fractional ``k`` is supported here.
- Efron, B. (1979). "Bootstrap methods: another look at the jackknife." *Annals of
  Statistics* 7(1): 1-26; percentile intervals as in Efron, B. and Tibshirani, R. J. (1993),
  *An Introduction to the Bootstrap*, Chapman & Hall, ch. 13.

Tie handling (applies to every ``*_at_k`` function and to :func:`rank_metrics`)
-------------------------------------------------------------------------------
Units are ordered by a **stable descending sort on ``scores``**: equal scores keep their
input order, so the row that appears first in ``y_true``/``scores`` is ranked first. This
makes the ``@k`` metrics deterministic but *input-order dependent* when many scores tie
(e.g. a detector that emits integer counts). If that matters, break ties yourself before
calling -- add a tiny deterministic jitter, or de-duplicate -- rather than relying on row
order. ``roc_auc`` and ``average_precision`` are delegated to scikit-learn, which handles
ties as mid-ranks (ROC AUC) / step-wise (AP) and is therefore order independent.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike
from sklearn.metrics import average_precision_score, roc_auc_score

from forensics_core._types import jsonable

__all__ = [
    "BootstrapResult",
    "average_precision",
    "bootstrap_metric",
    "ndcg_at_k",
    "precision_at_k",
    "rank_metrics",
    "recall_at_k",
    "roc_auc",
]

Gains = Literal["binary", "exponential"]


@dataclass(frozen=True)
class BootstrapResult:
    """Percentile-bootstrap summary of a single scalar metric.

    This is ``forensics_core.eval``'s own result type; it deliberately does not import the
    bunching subpackage so the two can evolve independently, but it carries the same field
    names so results tabulate together.

    Attributes
    ----------
    point : float
        The metric computed once on the full sample (not the mean of the draws).
    se : float
        Standard deviation of the bootstrap draws (``ddof=1``) -- the bootstrap standard
        error.
    ci_low, ci_high : float
        Percentile interval at ``alpha`` (the ``alpha/2`` and ``1 - alpha/2`` quantiles of
        the draws). Percentile intervals are not bias corrected; with fewer than a few
        dozen positives they are optimistic (Efron and Tibshirani 1993, ch. 13-14).
    draws : numpy.ndarray
        The successful bootstrap replicates, in draw order.
    method : str
        Resampling scheme; ``"pairs"`` means (y, score) pairs are resampled together.
    n_boot : int
        Number of replicates *requested*.
    alpha : float
        Interval level used.
    n_failed : int
        Replicates discarded because the metric was undefined on that resample (e.g. a draw
        with no positives). Large values mean the interval is unreliable.
    """

    point: float
    se: float
    ci_low: float
    ci_high: float
    draws: np.ndarray
    method: str
    n_boot: int
    alpha: float = 0.05
    n_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


# --------------------------------------------------------------------------------------
# private helpers (shared with eval.harness; not part of the public contract)
# --------------------------------------------------------------------------------------


def _as_float_1d(x: ArrayLike, name: str) -> np.ndarray:
    """Coerce ``x`` to a 1-D float64 array or raise ``ValueError``."""
    if hasattr(x, "to_numpy"):  # pandas Series / Index, incl. nullable dtypes
        try:
            arr = x.to_numpy(dtype=float, na_value=np.nan)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    else:
        arr = np.asarray(x)
        if arr.dtype.kind not in "biuf":
            raise ValueError(f"{name} must be numeric; got dtype {arr.dtype}")
    arr = np.asarray(arr, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
    return arr


def _validate_pair(
    y_true: ArrayLike, scores: ArrayLike, *, graded: bool = False
) -> tuple[np.ndarray, np.ndarray]:
    """Validate a (labels, scores) pair and return them as float arrays.

    Raises
    ------
    ValueError
        If lengths differ, the sample is empty, either array holds non-finite values, or
        ``y_true`` is not binary (0/1) -- or, when ``graded``, is negative.
    """
    y = _as_float_1d(y_true, "y_true")
    s = _as_float_1d(scores, "scores")
    if y.size != s.size:
        raise ValueError(f"y_true and scores must have the same length; got {y.size} and {s.size}")
    if y.size == 0:
        raise ValueError("y_true and scores are empty; nothing to score")
    if not np.all(np.isfinite(y)):
        raise ValueError(
            "y_true contains NaN/inf; drop unlabeled rows (Dataset.labeled()) before scoring"
        )
    if not np.all(np.isfinite(s)):
        raise ValueError("scores must all be finite (no NaN/inf)")
    if graded:
        if np.any(y < 0):
            raise ValueError("y_true (relevance grades) must be non-negative")
    elif not np.all((y == 0.0) | (y == 1.0)):
        bad = np.unique(y[(y != 0.0) & (y != 1.0)])[:5]
        raise ValueError(f"y_true must be binary 0/1; found other values, e.g. {bad.tolist()}")
    return y, s


def _require_both_classes(y: np.ndarray, metric: str) -> None:
    n_pos = int(np.count_nonzero(y == 1.0))
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        raise ValueError(
            f"{metric} needs at least one positive and one negative; got n_pos={n_pos}, "
            f"n_neg={n_neg} out of {y.size} rows"
        )


def _rank_order(scores: np.ndarray) -> np.ndarray:
    """Indices that sort ``scores`` descending, ties keeping input order (stable sort)."""
    return np.argsort(-scores, kind="stable")


def _resolve_k(k: int | float, n: int) -> int:
    """Turn ``k`` into a positive integer count of top-ranked units.

    ``k`` is a count when it is an integer, and a *fraction of n* when it is a float
    strictly between 0 and 1 (``ceil(k * n)``, floored at 1, as in Bao et al. 2020 where
    k = 1% of the test set). A float that is not in ``(0, 1)`` -- ``5.0``, say -- is
    rejected rather than silently read as a count, because the two meanings are not
    interchangeable.
    """
    if isinstance(k, bool):
        raise ValueError("k must be an int count or a float fraction in (0, 1); got a bool")
    if isinstance(k, int | np.integer):
        k_int = int(k)
        if k_int < 1:
            raise ValueError(f"k must be at least 1; got {k_int}")
        if k_int > n:
            raise ValueError(f"k={k_int} exceeds the number of scored units (n={n})")
        return k_int
    if isinstance(k, float | np.floating):
        k_float = float(k)
        if not math.isfinite(k_float):
            raise ValueError(f"k must be finite; got {k_float}")
        if not (0.0 < k_float < 1.0):
            raise ValueError(
                f"a float k is a fraction and must lie strictly in (0, 1); got {k_float}. "
                "Pass an int if you meant a count."
            )
        return max(1, math.ceil(k_float * n))
    raise ValueError(
        f"k must be an int count or a float fraction in (0, 1); got {type(k).__name__}"
    )


def _k_label(k: int | float) -> str:
    """Suffix used in :func:`rank_metrics` keys: ``5`` -> ``"5"``, ``0.01`` -> ``"1%"``."""
    if isinstance(k, int | np.integer) and not isinstance(k, bool):
        return str(int(k))
    return f"{float(k) * 100:g}%"


def _gain(y: np.ndarray, gains: Gains) -> np.ndarray:
    if gains == "binary":
        return y
    if gains == "exponential":
        return np.exp2(y) - 1.0
    raise ValueError(f"gains must be 'binary' or 'exponential'; got {gains!r}")


# --------------------------------------------------------------------------------------
# public metrics
# --------------------------------------------------------------------------------------


def roc_auc(y_true: ArrayLike, scores: ArrayLike) -> float:
    """Area under the ROC curve (Hanley and McNeil 1982).

    Thin wrapper around :func:`sklearn.metrics.roc_auc_score` that validates its inputs
    first. Equal to the probability that a randomly chosen positive outranks a randomly
    chosen negative (ties counted as half).

    Parameters
    ----------
    y_true : array-like of {0, 1}
        Binary labels; 1 = confirmed distortion.
    scores : array-like of float
        Higher = more suspicious.

    Returns
    -------
    float
        AUC in [0, 1]; 0.5 is chance.

    Raises
    ------
    ValueError
        On length mismatch, empty input, non-finite values, non-binary labels, or a sample
        that does not contain at least one positive *and* one negative (AUC is undefined).
    """
    y, s = _validate_pair(y_true, scores)
    _require_both_classes(y, "roc_auc")
    return float(roc_auc_score(y, s))


def average_precision(y_true: ArrayLike, scores: ArrayLike) -> float:
    """Average precision: the step-wise area under the precision-recall curve.

    ``AP = sum_n (R_n - R_{n-1}) * P_n`` over the ranked list (Manning et al. 2008, ch. 8;
    computed by :func:`sklearn.metrics.average_precision_score`, which does *not*
    interpolate). Its chance level is the positive base rate, so unlike AUC it is a fair
    summary when positives are rare.

    Raises
    ------
    ValueError
        Same conditions as :func:`roc_auc`.
    """
    y, s = _validate_pair(y_true, scores)
    _require_both_classes(y, "average_precision")
    return float(average_precision_score(y, s))


def precision_at_k(y_true: ArrayLike, scores: ArrayLike, k: int | float) -> float:
    """Share of the top-``k`` ranked units that are positive.

    Parameters
    ----------
    y_true : array-like of {0, 1}
        Binary labels.
    scores : array-like of float
        Higher = more suspicious; ties keep input order (see the module docstring).
    k : int or float
        Count if int, fraction of ``n`` (``ceil``, at least 1) if a float in (0, 1).

    Returns
    -------
    float
        ``(# positives in the top k) / k``. The denominator is ``k``, never
        ``min(k, n_pos)``, so a list with fewer than ``k`` positives cannot reach 1.0.

    Notes
    -----
    Defined (and equal to 0.0) when there are no positives at all; ``recall_at_k`` and
    ``ndcg_at_k`` raise in that case because they are not.
    """
    y, s = _validate_pair(y_true, scores)
    kk = _resolve_k(k, y.size)
    top = y[_rank_order(s)[:kk]]
    return float(np.count_nonzero(top == 1.0) / kk)


def recall_at_k(y_true: ArrayLike, scores: ArrayLike, k: int | float) -> float:
    """Share of all positives that are captured in the top ``k`` ranked units.

    Also called "hit rate" or "sensitivity at k" (Manning et al. 2008, ch. 8).

    Raises
    ------
    ValueError
        If ``y_true`` has no positives (recall would divide by zero), or on the usual
        input-validation failures.
    """
    y, s = _validate_pair(y_true, scores)
    n_pos = int(np.count_nonzero(y == 1.0))
    if n_pos == 0:
        raise ValueError("recall_at_k is undefined without positives; y_true has none")
    kk = _resolve_k(k, y.size)
    top = y[_rank_order(s)[:kk]]
    return float(np.count_nonzero(top == 1.0) / n_pos)


def ndcg_at_k(
    y_true: ArrayLike,
    scores: ArrayLike,
    k: int | float,
    gains: Gains = "binary",
) -> float:
    """Normalised discounted cumulative gain at ``k`` (Jaervelin and Kekaelaeinen 2002).

    ``DCG@k = sum_{i=1..k} g_i / log2(i + 1)`` where ``g_i`` is the gain of the unit at rank
    ``i``; ``IDCG@k`` is the same sum over the ideal ordering (labels sorted descending);
    ``NDCG@k = DCG@k / IDCG@k``.

    Parameters
    ----------
    y_true : array-like
        Binary labels with ``gains="binary"``. Non-negative graded relevance is also
        accepted (validated as such), which is what ``gains="exponential"`` is for.
    scores : array-like of float
        Higher = more suspicious; ties keep input order.
    k : int or float
        Count, or fraction of ``n`` if a float in (0, 1). Bao et al. (2020) report NDCG@k
        with k = 1% of the test firm-years.
    gains : {"binary", "exponential"}
        ``"binary"`` uses ``g = rel``; ``"exponential"`` uses ``g = 2**rel - 1``. For 0/1
        labels the two coincide (``2**1 - 1 == 1``), so the choice only matters for graded
        relevance. The exponential gain is the industry-standard variant popularised by
        Burges et al. (2005), "Learning to rank using gradient descent", ICML -- that
        attribution is taken from secondary sources (IR textbooks and the scikit-learn
        documentation); confirm against the primary text before quoting it.

    Returns
    -------
    float
        NDCG@k in [0, 1]; 1.0 iff the top ``k`` slots are filled with the highest-gain
        units in non-increasing order of gain.

    Raises
    ------
    ValueError
        If all gains are zero (IDCG = 0, so NDCG is undefined), or on the usual
        input-validation failures.
    """
    y, s = _validate_pair(y_true, scores, graded=True)
    kk = _resolve_k(k, y.size)
    g = _gain(y, gains)
    discount = 1.0 / np.log2(np.arange(1, kk + 1) + 1.0)
    dcg = float(np.sum(g[_rank_order(s)[:kk]] * discount))
    ideal = np.sort(g)[::-1][:kk]
    idcg = float(np.sum(ideal * discount))
    if idcg <= 0.0:
        raise ValueError(
            "ndcg_at_k is undefined when every gain is zero (IDCG = 0); y_true has no positives"
        )
    return dcg / idcg


def rank_metrics(
    y_true: ArrayLike,
    scores: ArrayLike,
    ks: Sequence[int | float] = (0.01, 0.05, 0.10),
    *,
    gains: Gains = "binary",
    include_global: bool = True,
) -> dict[str, float]:
    """Compute the standard bundle of rank metrics in one pass.

    Parameters
    ----------
    y_true, scores : array-like
        As elsewhere; higher score = more suspicious.
    ks : sequence of int or float
        Cut-offs. Floats in (0, 1) are fractions of ``n``.
    gains : {"binary", "exponential"}
        Passed to :func:`ndcg_at_k`.
    include_global : bool
        If True (default) also compute ``roc_auc`` and ``average_precision``, which require
        both classes to be present. Set False to score a sample that is all-positive or
        all-negative on the ``@k`` metrics alone.

    Returns
    -------
    dict of str to float
        Keys are ``"roc_auc"``, ``"average_precision"`` and, per cut-off,
        ``"precision@<k>"``, ``"recall@<k>"``, ``"ndcg@<k>"`` where ``<k>`` is the integer
        count (``"5"``) or the percentage for a fractional k (``"1%"``, ``"10%"``). So
        ``rank_metrics(y, s, ks=(0.01, 0.05))`` yields ``"ndcg@1%"``, ``"precision@5%"``,
        and so on.

    Raises
    ------
    ValueError
        On duplicate cut-off labels, or from any of the underlying metrics.
    """
    y, s = _validate_pair(y_true, scores, graded=True)
    out: dict[str, float] = {}
    if include_global:
        out["roc_auc"] = roc_auc(y, s)
        out["average_precision"] = average_precision(y, s)
    seen: set[str] = set()
    for k in ks:
        label = _k_label(k)
        if label in seen:
            raise ValueError(f"duplicate cut-off label {label!r} in ks={tuple(ks)!r}")
        seen.add(label)
        out[f"precision@{label}"] = precision_at_k(y, s, k)
        out[f"recall@{label}"] = recall_at_k(y, s, k)
        out[f"ndcg@{label}"] = ndcg_at_k(y, s, k, gains=gains)
    return out


def bootstrap_metric(
    metric: Callable[[np.ndarray, np.ndarray], float],
    y_true: ArrayLike,
    scores: ArrayLike,
    n_boot: int = 499,
    alpha: float = 0.05,
    seed: int | None = None,
    *,
    stratified: bool = False,
) -> BootstrapResult:
    """Percentile bootstrap of any ``metric(y_true, scores) -> float``.

    Resamples (label, score) *pairs* with replacement (the "pairs" scheme: Efron 1979;
    Efron and Tibshirani 1993, ch. 6), recomputes the metric, and reports the percentile
    interval. The point estimate is the metric on the full sample, not the mean of draws.

    Parameters
    ----------
    metric : callable
        Takes ``(y_true, scores)`` and returns a float. Metrics that need extra arguments
        are bound first, e.g.
        ``bootstrap_metric(functools.partial(precision_at_k, k=0.01), y, s)``.
    y_true, scores : array-like
        As elsewhere.
    n_boot : int
        Number of replicates; must be at least 2.
    alpha : float
        Interval level in (0, 1): the interval spans the ``alpha/2`` and ``1 - alpha/2``
        quantiles of the draws.
    seed : int or None
        Seeds ``numpy.random.default_rng``.
    stratified : bool
        If True, resample positives and negatives separately, keeping the number of each
        fixed. This holds the base rate constant across replicates -- it removes the
        sampling variance of the base rate, so intervals are narrower and answer a
        different question; the default (False) is the ordinary pairs bootstrap.

    Returns
    -------
    BootstrapResult

    Raises
    ------
    ValueError
        On invalid ``n_boot``/``alpha``, on the usual input-validation failures, or if
        fewer than two replicates produced a finite value (metric undefined too often --
        typically too few positives).
    """
    y, s = _validate_pair(y_true, scores, graded=True)
    if not isinstance(n_boot, int | np.integer) or isinstance(n_boot, bool) or int(n_boot) < 2:
        raise ValueError(f"n_boot must be an int >= 2; got {n_boot!r}")
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError(f"alpha must lie strictly in (0, 1); got {alpha!r}")
    n_boot = int(n_boot)
    rng = np.random.default_rng(seed)
    point = float(metric(y, s))

    n = y.size
    pos_idx = np.flatnonzero(y > 0.0)
    neg_idx = np.flatnonzero(y <= 0.0)
    if stratified and (pos_idx.size == 0 or neg_idx.size == 0):
        raise ValueError("stratified bootstrap needs at least one positive and one negative")

    draws: list[float] = []
    n_failed = 0
    for _ in range(n_boot):
        if stratified:
            idx = np.concatenate(
                [
                    pos_idx[rng.integers(0, pos_idx.size, size=pos_idx.size)],
                    neg_idx[rng.integers(0, neg_idx.size, size=neg_idx.size)],
                ]
            )
        else:
            idx = rng.integers(0, n, size=n)
        try:
            value = float(metric(y[idx], s[idx]))
        except ValueError:  # degenerate resample: metric undefined there
            n_failed += 1
            continue
        if not math.isfinite(value):
            n_failed += 1
            continue
        draws.append(value)

    if len(draws) < 2:
        raise ValueError(
            f"only {len(draws)} of {n_boot} bootstrap replicates produced a finite value "
            "(the metric is undefined on most resamples -- too few positives?)"
        )
    arr = np.asarray(draws, dtype=float)
    lo, hi = np.quantile(arr, [alpha / 2.0, 1.0 - alpha / 2.0])
    return BootstrapResult(
        point=point,
        se=float(np.std(arr, ddof=1)),
        ci_low=float(lo),
        ci_high=float(hi),
        draws=arr,
        method="stratified_pairs" if stratified else "pairs",
        n_boot=n_boot,
        alpha=float(alpha),
        n_failed=n_failed,
    )

"""Positive-unlabeled (PU) learning.

Enforcement-based labels identify *some* positives (an SEC AAER, an admitted falsification,
an annulled precinct); everything else is **unlabeled**, not negative. Training an ordinary
classifier on "labeled positive vs. everything else" therefore estimates the wrong quantity.

Two standard corrections are implemented here.

``ElkanNotoPU``
    Elkan, C., & Noto, K. (2008). "Learning classifiers from only positive and unlabeled
    data." *Proceedings of the 14th ACM SIGKDD International Conference on Knowledge
    Discovery and Data Mining (KDD '08)*, 213-220. Under the SCAR assumption (labeled
    positives are Selected Completely At Random among the true positives) the classifier
    ``g(x) = P(s=1|x)`` trained on the *observed* labels satisfies ``g(x) = c * P(y=1|x)``
    with the constant ``c = P(s=1|y=1)``, so dividing by an estimate of ``c`` recovers the
    calibrated posterior.

``BaggingPU``
    Mordelet, F., & Vert, J.-P. (2014). "A bagging SVM to learn from positive and unlabeled
    examples." *Pattern Recognition Letters* 37:201-209. Aggregate many classifiers, each
    trained on all positives against a small random subsample of the unlabeled set, and
    score each unlabeled point with the estimators that did *not* see it (out-of-bag).

Both are pure estimators: no I/O, no global state, no plotting. Randomness flows through
``random_state`` into :func:`numpy.random.default_rng`.

Notes
-----
Section and algorithm numbers quoted in the docstrings below are recalled from secondary
summaries of the two papers; the mathematics is standard, but the exact numbering should be
confirmed against the primary texts before being cited in writing.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.linear_model import LogisticRegression
from sklearn.utils.validation import check_array, check_is_fitted, column_or_1d

__all__ = ["BaggingPU", "ElkanNotoPU", "estimate_class_prior"]


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------


def _make_rng(random_state: Any) -> np.random.Generator:
    """Return a :class:`numpy.random.Generator` from an sklearn-style ``random_state``.

    Accepts ``None``, an integer seed, a :class:`numpy.random.Generator` (returned as is),
    a :class:`numpy.random.SeedSequence`, or a legacy :class:`numpy.random.RandomState`
    (spawned from). Anything else raises ``ValueError`` rather than being coerced silently.
    Booleans are rejected even though ``bool`` is a subclass of ``int``: ``random_state=True``
    almost certainly means "yes, randomise", not "seed 1".
    """
    if isinstance(random_state, np.random.Generator):
        return random_state
    if isinstance(random_state, np.random.RandomState):
        return np.random.default_rng(int(random_state.randint(0, 2**31 - 1)))
    if isinstance(random_state, np.random.SeedSequence):
        return np.random.default_rng(random_state)
    if isinstance(random_state, bool | np.bool_):
        raise ValueError(
            f"random_state must not be a bool; got {random_state!r}. Pass None for an "
            "unseeded generator or an explicit integer seed."
        )
    if random_state is None or isinstance(random_state, int | np.integer):
        return np.random.default_rng(random_state)
    raise ValueError(
        "random_state must be None, an int, a numpy Generator/SeedSequence or a legacy "
        f"RandomState; got {type(random_state).__name__}."
    )


def _check_pu_inputs(X: ArrayLike, s: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    """Validate a PU training set.

    Parameters
    ----------
    X : array-like of shape (n_samples, n_features)
    s : array-like of shape (n_samples,)

    Returns
    -------
    X : ndarray of shape (n_samples, n_features), dtype float64
    s : ndarray of shape (n_samples,), dtype int64, values in {0, 1}

    Raises
    ------
    ValueError
        If ``X`` is not a finite numeric 2-D array, if ``s`` is not 1-D of the same length,
        if ``s`` holds any value other than 0 or 1, or if either group is empty. Nothing is
        coerced silently: a label vector of ``{-1, 1}`` or ``{1, 2}`` is an error, not a
        relabelling opportunity.
    """
    X = check_array(X, dtype=np.float64, ensure_2d=True)
    s_arr = np.asarray(s)
    if s_arr.dtype.kind not in "biuf":
        raise ValueError(
            f"s must be a numeric or boolean array of 0/1 labels; got dtype {s_arr.dtype!r}."
        )
    s_arr = column_or_1d(s_arr, warn=False)
    if s_arr.shape[0] != X.shape[0]:
        raise ValueError(
            f"X and s must have the same number of rows; got {X.shape[0]} and {s_arr.shape[0]}."
        )
    s_float = s_arr.astype(np.float64, copy=False)
    if not np.all(np.isfinite(s_float)):
        raise ValueError("s contains non-finite values; PU labels must be exactly 0 or 1.")
    bad = np.unique(s_float[(s_float != 0.0) & (s_float != 1.0)])
    if bad.size:
        raise ValueError(
            "s must contain only 0 (unlabeled) and 1 (labeled positive); found "
            f"{bad.tolist()}. Negatives are never observed in a PU problem - encode them as 0."
        )
    s_int = s_float.astype(np.int64)
    n_pos = int((s_int == 1).sum())
    n_unl = int((s_int == 0).sum())
    if n_pos == 0:
        raise ValueError("s contains no labeled positives (no entry equal to 1).")
    if n_unl == 0:
        raise ValueError("s contains no unlabeled points (no entry equal to 0).")
    return X, s_int


def _positive_column(estimator: Any) -> int:
    """Index of the ``1`` column in ``estimator.classes_``."""
    classes = np.asarray(getattr(estimator, "classes_", np.array([0, 1])))
    hits = np.flatnonzero(classes == 1)
    if hits.size != 1:
        raise ValueError(
            f"base estimator was not fitted on binary 0/1 labels; classes_ = {classes.tolist()}."
        )
    return int(hits[0])


def _proba_positive(estimator: Any, X: np.ndarray) -> np.ndarray:
    """``P(label = 1 | x)`` from a fitted estimator that exposes ``predict_proba``."""
    if not hasattr(estimator, "predict_proba"):
        raise ValueError(
            f"{type(estimator).__name__} has no predict_proba, which this step needs. Wrap it "
            "in sklearn.calibration.CalibratedClassifierCV, or pass a probabilistic model."
        )
    proba = np.asarray(estimator.predict_proba(X), dtype=np.float64)
    if proba.ndim != 2:
        raise ValueError("predict_proba must return a 2-D array of class probabilities.")
    return proba[:, _positive_column(estimator)]


def _rank_score(estimator: Any, X: np.ndarray) -> np.ndarray:
    """Ranking score of a fitted estimator.

    ``decision_function`` when the estimator has one (Mordelet & Vert's bagging SVM
    aggregates SVM margins), otherwise ``predict_proba[:, 1]``. Higher = more positive.
    """
    if hasattr(estimator, "decision_function"):
        d = np.asarray(estimator.decision_function(X), dtype=np.float64)
        if d.ndim == 2 and d.shape[1] == 1:
            d = d.ravel()
        if d.ndim != 1:
            raise ValueError(
                f"decision_function must return a 1-D score for a binary problem; got {d.shape}."
            )
        return d
    return _proba_positive(estimator, X)


def _classifier_tags(tags: Any) -> Any:
    """Mark sklearn >= 1.6 ``tags`` as belonging to a classifier."""
    tags.estimator_type = "classifier"
    try:  # pragma: no cover - depends on the installed sklearn
        from sklearn.utils import ClassifierTags

        tags.classifier_tags = ClassifierTags()
    except ImportError:  # pragma: no cover
        pass
    return tags


# ---------------------------------------------------------------------------------------
# Elkan & Noto (2008)
# ---------------------------------------------------------------------------------------


class ElkanNotoPU(BaseEstimator, ClassifierMixin):
    """Elkan-Noto constant-``c`` correction for positive-unlabeled data.

    Fit a non-traditional classifier ``g(x) ~ P(s=1|x)`` on the observed labels ``s``,
    estimate the labelling frequency ``c = P(s=1|y=1)`` on positives held out of that fit,
    and report ``P(y=1|x) = g(x)/c``.

    Under SCAR (labeled positives are Selected Completely At Random among the positives,
    independently of ``x``), ``P(s=1|x) = P(s=1|y=1) P(y=1|x) = c P(y=1|x)`` -- Lemma 1 of
    Elkan & Noto (2008). Their estimator ``e1``, used here, is the average of ``g(x)`` over
    a validation set of labeled positives that the classifier never saw.

    Parameters
    ----------
    base_estimator : estimator or None, default=None
        Probabilistic binary classifier implementing ``fit`` and ``predict_proba``. It is
        cloned before fitting, so the instance passed in is never modified. ``None`` means
        ``sklearn.linear_model.LogisticRegression(max_iter=1000)``.
    hold_out_ratio : float, default=0.2
        Fraction of the labeled positives held out to estimate ``c``. Must lie strictly
        between 0 and 1. At least one positive is always held out and at least one always
        stays in the training split, so tiny positive sets still work.
    hold_out_unlabeled : bool, default=True
        Also hold out the same fraction of the *unlabeled* rows, i.e. split the whole
        dataset rather than only the positives. This keeps the labelled share of the
        training set equal to ``c`` and so removes the hold-out **dilution** bias (Notes,
        item 2); the residual **overlap** bias of ``e1`` (Notes, item 1) is unaffected, so
        ``c_`` is still biased downwards whenever the classes overlap. ``False`` reproduces
        the positives-only hold-out of the widely copied reference implementations, adding a
        further downward factor of roughly ``1 - hold_out_ratio`` on top of that.
    random_state : int, Generator, RandomState or None, default=None
        Controls the hold-out split.

    Attributes
    ----------
    c_ : float
        Estimated label frequency ``P(s=1|y=1)``: the mean of ``g`` over the held-out
        positives (estimator ``e1``).
    prior_ : float
        Estimated class prior ``P(y=1)``: the mean of ``g(x)/c_`` over all training rows,
        clipped to ``[0, 1]``. **A value of exactly 1.0 or 0.0 is a failure signal, not an
        estimate**: it means the raw ratio left the unit interval and was clipped, which
        happens when ``c_`` is badly underestimated (few held-out positives, heavy class
        overlap) or SCAR is violated. Compare with ``prior_unclipped_`` before using it.
    prior_unclipped_ : float
        The same ratio ``mean(g) / c_`` *without* the clip. ``prior_unclipped_ > 1`` (or
        ``< 0``, impossible for probabilistic ``g``) says the estimate is out of bounds and
        the class prior is not identified from this fit.
    estimator_ : estimator
        The fitted non-traditional classifier ``g``. It is trained *without* the held-out
        positives, which is what makes ``c_`` an out-of-sample estimate.
    hold_out_indices_ : ndarray
        Row indices of the held-out positives, into the ``X`` passed to :meth:`fit`.
    hold_out_unlabeled_indices_ : ndarray
        Row indices of the held-out unlabeled rows (empty when
        ``hold_out_unlabeled=False``).
    classes_ : ndarray
        Always ``array([0, 1])``.
    n_features_in_ : int
    n_positive_, n_unlabeled_ : int

    Notes
    -----
    Two distinct sources of bias in ``c_``:

    1. *Overlap.* ``E[g(x) | y=1] = c E[P(y=1|x) | y=1] <= c``, so ``c_`` is biased
       downwards whenever the classes overlap. This is intrinsic to ``e1`` and vanishes as
       the classes separate.
    2. *Hold-out dilution.* If the held-out positives are simply deleted from the training
       set, the labelled share of that training set drops from ``c`` to about
       ``c (1 - hold_out_ratio)``, and ``g`` - hence ``c_`` - shrinks by the same factor.
       Elkan & Noto avoid this by splitting the *whole* dataset into an estimation and a
       validation part and averaging ``g`` over the validation part's labeled positives.
       ``hold_out_unlabeled=True`` (the default) does that; ``False`` reproduces the
       positives-only split used by the common reference implementations, which carries the
       bias. See the note on this in the module's project documentation.

    Elkan & Noto give three estimators of ``c`` (``e1``, ``e2``, ``e3``); only ``e1`` is
    implemented here, as it is the one they recommend. The ``e1``/``e2``/``e3`` naming is
    recalled from secondary summaries of the paper; confirm against the primary text
    (KDD '08, pp. 213-220) before quoting it.

    References
    ----------
    Elkan, C., & Noto, K. (2008). Learning classifiers from only positive and unlabeled
    data. *KDD '08*, 213-220.

    Examples
    --------
    >>> import numpy as np
    >>> rng = np.random.default_rng(0)
    >>> X = np.vstack([rng.normal(3.0, 1.0, (200, 2)), rng.normal(0.0, 1.0, (200, 2))])
    >>> s = np.zeros(400, dtype=int)
    >>> s[:60] = 1                       # 60 of the 200 positives are labeled
    >>> pu = ElkanNotoPU(random_state=0).fit(X, s)
    >>> bool(0.0 < pu.c_ <= 1.0)
    True
    """

    def __init__(
        self,
        base_estimator: Any = None,
        hold_out_ratio: float = 0.2,
        random_state: Any = None,
        hold_out_unlabeled: bool = True,
    ) -> None:
        self.base_estimator = base_estimator
        self.hold_out_ratio = hold_out_ratio
        self.random_state = random_state
        self.hold_out_unlabeled = hold_out_unlabeled

    # -- sklearn plumbing --------------------------------------------------------------

    def __sklearn_tags__(self):  # pragma: no cover - metadata only
        # INTERFACES.md fixes the base order (BaseEstimator, ClassifierMixin), which puts
        # BaseEstimator's tags first in the MRO and would otherwise leave estimator_type
        # unset, so is_classifier() would return False.
        return _classifier_tags(super().__sklearn_tags__())

    def _make_base(self) -> Any:
        if self.base_estimator is None:
            return LogisticRegression(max_iter=1000)
        return clone(self.base_estimator)

    # -- fitting -----------------------------------------------------------------------

    def fit(self, X: ArrayLike, s: ArrayLike) -> ElkanNotoPU:
        """Fit ``g`` on the observed labels, then estimate ``c_`` and ``prior_``.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        s : array-like of shape (n_samples,)
            1 = labeled positive, 0 = unlabeled. Any other value raises ``ValueError``.

        Returns
        -------
        self : ElkanNotoPU

        Raises
        ------
        ValueError
            On invalid ``s``, ``hold_out_ratio`` outside ``(0, 1)``, fewer than two labeled
            positives, a base estimator without ``predict_proba``, or a non-positive ``c_``.
        """
        X, s = _check_pu_inputs(X, s)
        try:
            ratio = float(self.hold_out_ratio)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"hold_out_ratio must be a float in (0, 1); got {self.hold_out_ratio!r}."
            ) from exc
        if not np.isfinite(ratio) or not 0.0 < ratio < 1.0:
            raise ValueError(
                f"hold_out_ratio must lie strictly in (0, 1); got {self.hold_out_ratio!r}."
            )

        pos_idx = np.flatnonzero(s == 1)
        n_pos = int(pos_idx.size)
        if n_pos < 2:
            raise ValueError(
                "need at least 2 labeled positives to hold one out and still train on one; "
                f"got {n_pos}."
            )
        n_hold = int(np.ceil(ratio * n_pos))
        n_hold = min(max(n_hold, 1), n_pos - 1)

        rng = _make_rng(self.random_state)
        hold_idx = np.sort(pos_idx[rng.permutation(n_pos)[:n_hold]])

        # Hold out the same share of the unlabeled rows, so the training set keeps the same
        # labelled share as the full sample and c_ is not deflated by the split itself.
        unl_idx = np.flatnonzero(s == 0)
        n_unl = int(unl_idx.size)
        if self.hold_out_unlabeled:
            n_hold_unl = int(np.ceil(ratio * n_unl))
            n_hold_unl = min(max(n_hold_unl, 0), n_unl - 1)
            hold_unl_idx = np.sort(unl_idx[rng.permutation(n_unl)[:n_hold_unl]])
        else:
            hold_unl_idx = np.empty(0, dtype=np.int64)

        train_mask = np.ones(X.shape[0], dtype=bool)
        train_mask[hold_idx] = False
        train_mask[hold_unl_idx] = False

        estimator = self._make_base()
        if not hasattr(estimator, "predict_proba"):
            raise ValueError(
                f"base_estimator {type(estimator).__name__} has no predict_proba; the "
                "Elkan-Noto correction divides a probability by c and so needs one."
            )
        estimator.fit(X[train_mask], s[train_mask])

        c = float(np.mean(_proba_positive(estimator, X[hold_idx])))
        if not np.isfinite(c) or c <= 0.0:
            raise ValueError(
                f"estimated label frequency c_ = {c!r} is not positive: the fitted classifier "
                "gives the held-out positives zero probability, so g(x)/c is undefined. Use a "
                "less aggressively separating base estimator, more positives, or a smaller "
                "hold_out_ratio."
            )

        g_all = _proba_positive(estimator, X)
        self.estimator_ = estimator
        self.hold_out_indices_ = hold_idx
        self.hold_out_unlabeled_indices_ = hold_unl_idx
        self.c_ = c
        # Keep the raw ratio: prior_ == 1.0 is ambiguous (a genuine prior of 1, or a clipped
        # out-of-range ratio), and the difference is exactly what tells a caller the fit is
        # untrustworthy. See the Attributes section.
        self.prior_unclipped_ = float(np.mean(g_all)) / c
        self.prior_ = float(np.clip(self.prior_unclipped_, 0.0, 1.0))
        self.classes_ = np.array([0, 1])
        self.n_features_in_ = int(X.shape[1])
        self.n_positive_ = n_pos
        self.n_unlabeled_ = n_unl
        return self

    # -- prediction --------------------------------------------------------------------

    def _check_X(self, X: ArrayLike) -> np.ndarray:
        check_is_fitted(self, "c_")
        X = check_array(X, dtype=np.float64, ensure_2d=True)
        if X.shape[1] != self.n_features_in_:
            raise ValueError(
                f"X has {X.shape[1]} features, but this {type(self).__name__} was fitted with "
                f"{self.n_features_in_}."
            )
        return X

    def decision_function(self, X: ArrayLike) -> np.ndarray:
        """``g(x) / c_``, unclipped. Higher = more likely to be a true positive."""
        X = self._check_X(X)
        return _proba_positive(self.estimator_, X) / self.c_

    def predict_proba(self, X: ArrayLike) -> np.ndarray:
        """``[[1 - p, p]]`` with ``p = clip(g(x)/c_, 0, 1)``."""
        p = np.clip(self.decision_function(X), 0.0, 1.0)
        return np.column_stack([1.0 - p, p])

    def predict(self, X: ArrayLike) -> np.ndarray:
        """Hard labels at the 0.5 threshold on the corrected posterior."""
        p = self.predict_proba(X)[:, 1]
        return self.classes_[(p >= 0.5).astype(int)]


# ---------------------------------------------------------------------------------------
# Mordelet & Vert (2014)
# ---------------------------------------------------------------------------------------


class BaggingPU(BaseEstimator, ClassifierMixin):
    """Bagging PU classifier: the bagging-SVM scheme of Mordelet & Vert, any base estimator.

    Each of ``n_estimators`` rounds trains the base estimator on *all* labeled positives
    (class 1) against ``k`` points drawn from the unlabeled pool (class 0). The unlabeled
    points left out of a round are scored by that round's estimator; averaging those
    out-of-bag scores gives every unlabeled training point a score uncontaminated by its own
    (wrong) training label.

    Parameters
    ----------
    base_estimator : estimator or None, default=None
        Cloned each round, so the instance passed in is never modified. ``None`` means
        ``sklearn.linear_model.LogisticRegression(max_iter=1000)``.
    n_estimators : int, default=50
        Number of bagging rounds.
    k : int or None, default=None
        Unlabeled points drawn per round. ``None`` means "as many as there are labeled
        positives", making each round's training set balanced.
    random_state : int, Generator, RandomState or None, default=None
        Controls the per-round subsampling.
    bootstrap : bool, default=True
        Draw the ``k`` unlabeled points with replacement. Mordelet & Vert describe drawing
        a subsample of size ``K`` from the unlabeled set; whether their experiments sample
        with or without replacement is recalled from a secondary summary and should be
        confirmed against the primary text. With ``False`` the draw is without replacement
        and ``k`` may not exceed the number of unlabeled points.

    Attributes
    ----------
    oob_scores_ : ndarray of shape (n_samples,)
        Mean out-of-bag score per training row: ``nan`` at labeled positives (they are in
        every round's training set, so they are never out of bag) and at any unlabeled row
        that happened to be sampled in every round. Higher = more suspicious.
    oob_counts_ : ndarray of shape (n_samples,)
        How many rounds each row was out of bag for.
    X_train_ : ndarray of shape (n_samples, n_features)
        The validated training matrix, kept so that ``decision_function(X, use_oob=True)``
        can recognise training rows. Not copied: mutating the array passed to :meth:`fit`
        in place invalidates the match.
    estimators_ : list
        The fitted per-round estimators.
    score_kind_ : {"decision_function", "predict_proba"}
        Which base-estimator output was aggregated.
    k_ : int
        The ``k`` actually used.
    classes_ : ndarray
        Always ``array([0, 1])``.
    n_features_in_ : int
    n_positive_, n_unlabeled_ : int

    Notes
    -----
    Scores are averaged on the base estimator's own scale (``decision_function`` where it
    exists, else ``predict_proba[:, 1]``), so :meth:`decision_function` output is a ranking
    score and not a probability. Use :meth:`predict_proba` for an averaged probability when
    the base estimator provides one.

    The unlabeled pool contains the unlabeled *positives*, so every round trains against
    partly mislabeled negatives; the aggregation is what averages that noise away
    (Mordelet & Vert 2014, Algorithm 1 - the algorithm number is recalled from a secondary
    summary; confirm against Pattern Recognit. Lett. 37:201-209).

    References
    ----------
    Mordelet, F., & Vert, J.-P. (2014). A bagging SVM to learn from positive and unlabeled
    examples. *Pattern Recognition Letters* 37:201-209.

    Examples
    --------
    >>> import numpy as np
    >>> rng = np.random.default_rng(0)
    >>> X = np.vstack([rng.normal(3.0, 1.0, (100, 2)), rng.normal(0.0, 1.0, (300, 2))])
    >>> s = np.zeros(400, dtype=int)
    >>> s[:30] = 1
    >>> pu = BaggingPU(n_estimators=10, random_state=0).fit(X, s)
    >>> bool(np.isnan(pu.oob_scores_[:30]).all())
    True
    """

    def __init__(
        self,
        base_estimator: Any = None,
        n_estimators: int = 50,
        k: int | None = None,
        random_state: Any = None,
        bootstrap: bool = True,
    ) -> None:
        self.base_estimator = base_estimator
        self.n_estimators = n_estimators
        self.k = k
        self.random_state = random_state
        self.bootstrap = bootstrap

    # -- sklearn plumbing --------------------------------------------------------------

    def __sklearn_tags__(self):  # pragma: no cover - metadata only
        return _classifier_tags(super().__sklearn_tags__())

    def _make_base(self) -> Any:
        if self.base_estimator is None:
            return LogisticRegression(max_iter=1000)
        return clone(self.base_estimator)

    # -- fitting -----------------------------------------------------------------------

    def fit(self, X: ArrayLike, s: ArrayLike) -> BaggingPU:
        """Run the bagging rounds and accumulate out-of-bag scores.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        s : array-like of shape (n_samples,)
            1 = labeled positive, 0 = unlabeled. Any other value raises ``ValueError``.

        Returns
        -------
        self : BaggingPU

        Raises
        ------
        ValueError
            On invalid ``s``, a non-positive ``n_estimators`` or ``k``, or a ``k`` so large
            that no out-of-bag scores could be produced.
        """
        X, s = _check_pu_inputs(X, s)
        # bool is a subclass of int; True would silently become "one round", so reject it.
        if (
            isinstance(self.n_estimators, bool | np.bool_)
            or not isinstance(self.n_estimators, int | np.integer)
            or int(self.n_estimators) < 1
        ):
            raise ValueError(f"n_estimators must be a positive int; got {self.n_estimators!r}.")
        n_estimators = int(self.n_estimators)

        pos_idx = np.flatnonzero(s == 1)
        unl_idx = np.flatnonzero(s == 0)
        n_unl = int(unl_idx.size)

        if self.k is None:
            k = int(pos_idx.size)
        elif (
            isinstance(self.k, bool | np.bool_)
            or not isinstance(self.k, int | np.integer)
            or int(self.k) < 1
        ):
            # bool is a subclass of int; k=True would silently mean "one unlabeled draw".
            raise ValueError(f"k must be a positive int or None; got {self.k!r}.")
        else:
            k = int(self.k)
        # When k was derived from the positives, telling the caller to "lower k" is useless
        # advice about a number they never chose, so the two cases get different messages.
        remedy = (
            f"k defaults to the number of labeled positives ({k}), so pass an explicit "
            "smaller k (or reduce the positives fed in)."
            if self.k is None
            else "Lower k."
        )
        if not self.bootstrap and k > n_unl:
            raise ValueError(
                f"k={k} exceeds the {n_unl} unlabeled points available and bootstrap=False, so "
                f"a draw without replacement is impossible and no out-of-bag scores exist. "
                f"{remedy} Or sample with replacement."
            )
        if self.bootstrap and k >= n_unl:
            # Legal but useless: say so rather than returning an all-nan oob_scores_.
            raise ValueError(
                f"k={k} is not smaller than the number of unlabeled points ({n_unl}); every "
                "round would train on (almost) the whole unlabeled pool and essentially no "
                f"out-of-bag scores would remain. {remedy}"
            )

        rng = _make_rng(self.random_state)
        X_pos = X[pos_idx]
        y_round = np.concatenate(
            [np.ones(pos_idx.size, dtype=np.int64), np.zeros(k, dtype=np.int64)]
        )

        oob_sum = np.zeros(X.shape[0], dtype=np.float64)
        oob_count = np.zeros(X.shape[0], dtype=np.int64)
        estimators: list[Any] = []
        score_kind: str | None = None

        for _ in range(n_estimators):
            draw = (
                rng.integers(0, n_unl, size=k)
                if self.bootstrap
                else rng.choice(n_unl, size=k, replace=False)
            )
            sampled = unl_idx[draw]
            estimator = self._make_base()
            estimator.fit(np.vstack([X_pos, X[sampled]]), y_round)
            estimators.append(estimator)
            if score_kind is None:
                score_kind = (
                    "decision_function"
                    if hasattr(estimator, "decision_function")
                    else "predict_proba"
                )

            in_bag = np.zeros(n_unl, dtype=bool)
            in_bag[draw] = True
            oob = unl_idx[~in_bag]
            if oob.size:
                oob_sum[oob] += _rank_score(estimator, X[oob])
                oob_count[oob] += 1

        scores = np.full(X.shape[0], np.nan, dtype=np.float64)
        seen = oob_count > 0
        scores[seen] = oob_sum[seen] / oob_count[seen]

        self.estimators_ = estimators
        self.oob_scores_ = scores
        self.oob_counts_ = oob_count
        self.X_train_ = X
        self._oob_lookup_cache_ = None  # invalidated on every refit
        self.score_kind_ = score_kind
        self.k_ = k
        self.classes_ = np.array([0, 1])
        self.n_features_in_ = int(X.shape[1])
        self.n_positive_ = int(pos_idx.size)
        self.n_unlabeled_ = n_unl
        return self

    # -- prediction --------------------------------------------------------------------

    def _check_X(self, X: ArrayLike) -> np.ndarray:
        check_is_fitted(self, "estimators_")
        X = check_array(X, dtype=np.float64, ensure_2d=True)
        if X.shape[1] != self.n_features_in_:
            raise ValueError(
                f"X has {X.shape[1]} features, but this {type(self).__name__} was fitted with "
                f"{self.n_features_in_}."
            )
        return X

    def _oob_lookup(self) -> dict[bytes, float]:
        """Map the byte pattern of each training row to its finite out-of-bag score.

        Rows that repeat in the training set share one entry holding the mean of their
        out-of-bag scores; rows that were never out of bag (every labeled positive, and any
        unlabeled row sampled in every round) are absent, because they have no OOB score.
        Built once and cached, since it is only needed by ``decision_function(use_oob=True)``.
        """
        cached = getattr(self, "_oob_lookup_cache_", None)
        if cached is not None:
            return cached
        sums: dict[bytes, float] = {}
        counts: dict[bytes, int] = {}
        # +0.0 normalises -0.0 to 0.0 so that two numerically equal rows hash alike.
        for row, score in zip(self.X_train_ + 0.0, self.oob_scores_, strict=True):
            if not np.isfinite(score):
                continue
            key = row.tobytes()
            sums[key] = sums.get(key, 0.0) + float(score)
            counts[key] = counts.get(key, 0) + 1
        lookup = {key: total / counts[key] for key, total in sums.items()}
        self._oob_lookup_cache_ = lookup
        return lookup

    def decision_function(self, X: ArrayLike, *, use_oob: bool = False) -> np.ndarray:
        """Mean score over the bagged estimators. Higher = more likely to be positive.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        use_oob : bool, default=False
            Substitute the stored out-of-bag score for every row of ``X`` that is
            byte-identical to a training row which was out of bag at least once (i.e. the
            unlabeled training rows). Rows with no out-of-bag score -- new rows, the labeled
            positives, and any unlabeled row that was sampled in every round -- keep the
            full bagged mean. Requires holding the training matrix, which :meth:`fit`
            stores as ``X_train_``.

        Returns
        -------
        ndarray of shape (n_samples,)

        Notes
        -----
        **Deviation from INTERFACES.md.** The contract annotates this method "mean
        out-of-bag score for unlabeled; mean score for new X". The default here is the
        plain bagged mean for *every* row, and the contract's behaviour is available only
        via ``use_oob=True``. The reason is that ``X`` carries no row identity: an
        estimator cannot know that a row it is asked to score is the same observation it
        trained on, so making the split automatic would mean matching on feature values on
        every call, and it would make the score of a row depend on whether an identical row
        happened to be in the training set. :attr:`oob_scores_` is the primary, unambiguous
        out-of-bag surface -- indexed by training row, ``nan`` where no out-of-bag score
        exists -- and is what the unlabeled training pool should be ranked by.

        For the unlabeled rows of the *training* set, then, prefer :attr:`oob_scores_` (or
        ``use_oob=True``): those averages use only the rounds in which the point was out of
        bag, so they are not inflated by the point's own (wrong) negative label.
        """
        X = self._check_X(X)
        total = np.zeros(X.shape[0], dtype=np.float64)
        for estimator in self.estimators_:
            total += _rank_score(estimator, X)
        scores = total / len(self.estimators_)
        if use_oob:
            lookup = self._oob_lookup()
            for i, row in enumerate(X + 0.0):
                hit = lookup.get(row.tobytes())
                if hit is not None:
                    scores[i] = hit
        return scores

    def predict_proba(self, X: ArrayLike) -> np.ndarray:
        """Mean of the base estimators' ``predict_proba``, as ``[[1 - p, p]]``.

        Note that each round is trained on a balanced positives-vs-subsample set, so ``p``
        is calibrated to that artificial mix, not to the population prior. Use it for
        ranking, or recalibrate.
        """
        X = self._check_X(X)
        total = np.zeros(X.shape[0], dtype=np.float64)
        for estimator in self.estimators_:
            total += _proba_positive(estimator, X)
        p = total / len(self.estimators_)
        return np.column_stack([1.0 - p, p])

    def predict(self, X: ArrayLike) -> np.ndarray:
        """Hard labels: mean probability >= 0.5 for a probabilistic base estimator,
        otherwise mean decision function >= 0."""
        check_is_fitted(self, "estimators_")
        if hasattr(self.estimators_[0], "predict_proba"):
            hits = self.predict_proba(X)[:, 1] >= 0.5
        else:
            hits = self.decision_function(X) >= 0.0
        return self.classes_[hits.astype(int)]


# ---------------------------------------------------------------------------------------
# class prior
# ---------------------------------------------------------------------------------------


def estimate_class_prior(
    scores_labeled: ArrayLike,
    scores_unlabeled: ArrayLike,
    method: Literal["elkan_noto"] = "elkan_noto",
    *,
    clip: bool = True,
) -> float:
    """Estimate the class prior ``P(y=1)`` from PU classifier scores.

    With ``g(x) = P(s=1|x) = c P(y=1|x)`` (Elkan & Noto 2008, Lemma 1), the mean of ``g``
    over held-out *labeled positives* estimates ``c = P(s=1|y=1)``, and the mean of ``g``
    over the unlabeled pool divided by ``c`` estimates the prior on that pool.

    Parameters
    ----------
    scores_labeled : array-like, 1-D
        ``g(x)`` at labeled positives, ideally ones the classifier was not trained on.
    scores_unlabeled : array-like, 1-D
        ``g(x)`` at the points whose prior is wanted.
    method : {"elkan_noto"}, default="elkan_noto"
        Only the Elkan-Noto ``e1`` ratio is implemented.
    clip : bool, default=True
        Clip the ratio into ``[0, 1]``. Pass ``False`` to see the raw ratio, which is the
        only way to tell a clipped estimate from a genuine one (see Notes).

    Returns
    -------
    float
        ``mean(scores_unlabeled) / mean(scores_labeled)``, clipped to ``[0, 1]`` unless
        ``clip=False``. **A returned 1.0 (or 0.0) may be a clipped out-of-range ratio rather
        than an estimate** -- re-run with ``clip=False`` to find out.

    Raises
    ------
    ValueError
        On an unknown ``method``, on non-1-D or empty input, if no finite values survive,
        or if the estimated ``c`` is not strictly positive.

    Notes
    -----
    Non-finite values are dropped before averaging, per the package-wide convention; because
    the return type is a bare float there is nowhere to report the dropped count, so it is
    stated here instead. The estimate inherits the SCAR assumption and, like ``c_`` itself,
    is biased when the classes overlap.

    The ratio is a prior only under SCAR and only when ``mean(scores_labeled)`` is a decent
    estimate of ``c``; it leaves ``[0, 1]`` when it is not (too few held-out positives,
    heavy class overlap, a violated SCAR assumption). Clipping keeps the return value
    interpretable as a probability but hides that failure, so a result of exactly ``1.0``
    or ``0.0`` should be treated as "not identified", not as a confident answer.

    The prior returned is the prior *of whichever pool* ``scores_unlabeled`` describes.
    Passing the scores of the unlabeled rows alone estimates ``P(y=1 | s=0)``, which is
    strictly below the whole-sample ``P(y=1)`` estimated by
    :attr:`ElkanNotoPU.prior_` (that one averages ``g`` over *all* training rows, labeled
    positives included).

    References
    ----------
    Elkan, C., & Noto, K. (2008). Learning classifiers from only positive and unlabeled
    data. *KDD '08*, 213-220.

    Examples
    --------
    >>> estimate_class_prior([0.25, 0.75], [0.125, 0.375])   # c = 0.5, mean g = 0.25
    0.5
    """
    if method != "elkan_noto":
        raise ValueError(f"unknown method {method!r}; only 'elkan_noto' is implemented.")
    if np.ndim(scores_labeled) > 1 or np.ndim(scores_unlabeled) > 1:
        raise ValueError("scores_labeled and scores_unlabeled must be 1-D arrays of scores.")
    labeled = np.asarray(scores_labeled, dtype=np.float64).ravel()
    unlabeled = np.asarray(scores_unlabeled, dtype=np.float64).ravel()
    if labeled.size == 0 or unlabeled.size == 0:
        raise ValueError("scores_labeled and scores_unlabeled must both be non-empty.")
    labeled = labeled[np.isfinite(labeled)]
    unlabeled = unlabeled[np.isfinite(unlabeled)]
    if labeled.size == 0 or unlabeled.size == 0:
        raise ValueError("no finite scores left after dropping non-finite values.")
    c = float(np.mean(labeled))
    if c <= 0.0:
        raise ValueError(
            f"estimated label frequency c = {c!r} is not positive, so the prior g(x)/c is "
            "undefined. Check that scores_labeled holds P(s=1|x) at labeled positives."
        )
    ratio = float(np.mean(unlabeled)) / c
    return float(np.clip(ratio, 0.0, 1.0)) if clip else ratio

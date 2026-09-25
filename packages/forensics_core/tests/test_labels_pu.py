"""Tests for forensics_core.labels.pu.

All data is synthetic and generated in the test (HARD RULE 3): two 2-D Gaussian blobs whose
true labels are known, from which a known fraction ``c`` of the positives is revealed. The
tests check that the estimators recover the injected quantities (``c``, the class prior, the
ranking of the hidden positives), that hand-computable cases come out exactly right, and
that invalid input raises.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin, clone, is_classifier
from sklearn.exceptions import NotFittedError
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.svm import LinearSVC

from forensics_core.labels import BaggingPU, ElkanNotoPU, estimate_class_prior

TRUE_C = 0.3
TRUE_PRIOR = 0.4


# ---------------------------------------------------------------------------------------
# synthetic data
# ---------------------------------------------------------------------------------------


def make_pu_data(
    seed: int,
    n: int = 4000,
    prior: float = TRUE_PRIOR,
    c: float = TRUE_C,
    separation: float = 4.0,
    n_labeled: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic PU problem: two unit-variance 2-D Gaussians ``separation`` apart.

    ``y`` is the hidden truth (1 with probability ``prior``); ``s`` reveals each positive
    independently with probability ``c``, which is exactly the SCAR assumption Elkan & Noto
    (2008) require. Pass ``n_labeled`` to reveal an exact number of positives instead.
    """
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < prior).astype(int)
    X = rng.normal(0.0, 1.0, size=(n, 2))
    X[y == 1] += separation / np.sqrt(2.0)  # shift both coordinates
    if n_labeled is None:
        s = ((y == 1) & (rng.random(n) < c)).astype(int)
    else:
        positives = np.flatnonzero(y == 1)
        if n_labeled > positives.size:
            raise ValueError("n_labeled exceeds the number of true positives generated")
        s = np.zeros(n, dtype=int)
        s[rng.choice(positives, size=n_labeled, replace=False)] = 1
    return X, y, s


class ProbaFromFeature(BaseEstimator, ClassifierMixin):
    """Stub classifier whose ``P(class 1|x)`` is literally the first feature of ``x``.

    Used to make ``c_`` and ``prior_`` hand-computable: no fitting happens, so the answer
    does not depend on which rows landed in the hold-out.
    """

    def fit(self, X, y):
        self.classes_ = np.unique(np.asarray(y))
        self.fit_shapes_ = np.asarray(X).shape
        return self

    def predict_proba(self, X):
        p = np.asarray(X, dtype=float)[:, 0]
        return np.column_stack([1.0 - p, p])


class ScoreFromFeature(BaseEstimator, ClassifierMixin):
    """Stub classifier whose ``decision_function`` is the first feature of ``x``.

    Records the number of training rows it saw, so the bagging round size can be asserted.
    """

    def fit(self, X, y):
        X = np.asarray(X)
        self.classes_ = np.unique(np.asarray(y))
        self.n_train_rows_ = X.shape[0]
        self.n_train_positive_ = int(np.sum(np.asarray(y) == 1))
        return self

    def decision_function(self, X):
        return np.asarray(X, dtype=float)[:, 0]


# ---------------------------------------------------------------------------------------
# ElkanNotoPU: recovery of the injected constants
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_elkan_noto_recovers_c_and_prior(seed):
    """c_ recovers the injected label frequency and prior_ the injected class prior."""
    X, _, s = make_pu_data(seed)
    pu = ElkanNotoPU(random_state=seed).fit(X, s)
    assert abs(pu.c_ - TRUE_C) < 0.1, f"c_ = {pu.c_}"
    assert abs(pu.prior_ - TRUE_PRIOR) < 0.15, f"prior_ = {pu.prior_}"


def _fit_over_seeds(injected_c: float, seeds=(0, 1, 2)) -> list[ElkanNotoPU]:
    fits = []
    for seed in seeds:
        X, _, s = make_pu_data(seed, c=injected_c)
        fits.append(ElkanNotoPU(random_state=seed).fit(X, s))
    return fits


@pytest.mark.parametrize("injected_c", [0.1, 0.2, 0.3, 0.5, 0.8])
def test_elkan_noto_tracks_the_injected_label_frequency(injected_c):
    """c_ follows the label frequency actually injected, across the whole range, while
    prior_ stays put: changing c changes only how many positives are revealed."""
    fits = _fit_over_seeds(injected_c)
    estimated_c = [f.c_ for f in fits]
    estimated_prior = [f.prior_ for f in fits]
    assert abs(float(np.mean(estimated_c)) - injected_c) < 0.1, f"c_ = {estimated_c}"
    assert abs(float(np.mean(estimated_prior)) - TRUE_PRIOR) < 0.15, f"prior_ = {estimated_prior}"


def test_elkan_noto_c_is_monotone_in_the_injected_label_frequency():
    means = [
        float(np.mean([f.c_ for f in _fit_over_seeds(c, seeds=(0, 1))]))
        for c in (0.1, 0.3, 0.6, 0.9)
    ]
    assert means == sorted(means), means


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_elkan_noto_ranks_hidden_positives(seed):
    """decision_function ranks the hidden true positives above the true negatives, even
    though it never saw a single negative label. Overlapping blobs (separation 3)."""
    X, y, s = make_pu_data(seed, separation=3.0)
    pu = ElkanNotoPU(random_state=seed).fit(X, s)
    auc = roc_auc_score(y, pu.decision_function(X))
    assert auc > 0.85, f"AUC vs hidden labels = {auc}"
    # the score must beat the raw observed labels' own base rate: unlabeled positives are
    # scored above unlabeled negatives too.
    unlabeled = s == 0
    assert roc_auc_score(y[unlabeled], pu.decision_function(X[unlabeled])) > 0.85


def test_elkan_noto_hold_out_dilution_biases_c_downwards():
    """Deleting the held-out positives without holding out matching unlabeled rows deflates
    the labelled share of the training set, and with it c_ (see the Notes in the class)."""
    corrected, naive = [], []
    for seed in range(5):
        X, _, s = make_pu_data(seed)
        corrected.append(ElkanNotoPU(random_state=seed, hold_out_unlabeled=True).fit(X, s).c_)
        naive.append(ElkanNotoPU(random_state=seed, hold_out_unlabeled=False).fit(X, s).c_)
    corrected_arr, naive_arr = np.asarray(corrected), np.asarray(naive)
    assert np.all(naive_arr < corrected_arr)
    # the deflation is about the factor (1 - hold_out_ratio) = 0.8
    assert 0.7 < float(np.mean(naive_arr / corrected_arr)) < 0.95
    assert abs(float(np.mean(naive_arr)) - TRUE_C) > abs(float(np.mean(corrected_arr)) - TRUE_C)


def test_elkan_noto_c_and_prior_are_hand_computable():
    """With a stub g(x) = x[:, 0] the estimator's arithmetic is exact.

    4 positives at g = 0.5 and 6 unlabeled at g = 0.1:
        c_     = 0.5                      (mean g over the held-out positives)
        mean g = (4*0.5 + 6*0.1) / 10 = 0.26
        prior_ = 0.26 / 0.5 = 0.52
    """
    x0 = np.array([0.5, 0.5, 0.5, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    pu = ElkanNotoPU(base_estimator=ProbaFromFeature(), random_state=0).fit(X, s)
    assert pu.c_ == pytest.approx(0.5)
    assert pu.prior_ == pytest.approx(0.52)
    assert pu.prior_unclipped_ == pytest.approx(0.52)  # in range, so the clip does nothing
    assert pu.decision_function(X) == pytest.approx(np.where(x0 == 0.5, 1.0, 0.2))
    assert pu.n_positive_ == 4
    assert pu.n_unlabeled_ == 6


def test_elkan_noto_prior_unclipped_exposes_a_clipped_prior():
    """prior_ == 1.0 is the library's failure signal; prior_unclipped_ says it is one.

    4 positives at g = 0.2 and 6 unlabeled at g = 0.9 (a c_ far below the mean score, which
    is what an underestimated c_ looks like):
        c_     = 0.2
        mean g = (4*0.2 + 6*0.9) / 10 = 0.62
        ratio  = 0.62 / 0.2 = 3.1  ->  clipped to 1.0
    """
    x0 = np.array([0.2, 0.2, 0.2, 0.2, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9])
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    pu = ElkanNotoPU(base_estimator=ProbaFromFeature(), random_state=0).fit(X, s)
    assert pu.c_ == pytest.approx(0.2)
    assert pu.prior_unclipped_ == pytest.approx(3.1)
    assert pu.prior_ == 1.0
    assert pu.prior_unclipped_ > 1.0, "a clipped prior_ must be detectable after the fact"


def test_elkan_noto_predict_proba_is_clipped_and_decision_function_is_not():
    """g/c above 1 is reported unclipped by decision_function and clipped by predict_proba."""
    x0 = np.array([0.4, 0.4, 0.4, 0.4, 0.1, 0.1, 0.1, 0.1])
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    pu = ElkanNotoPU(base_estimator=ProbaFromFeature(), random_state=0).fit(X, s)
    assert pu.c_ == pytest.approx(0.4)

    hot = np.array([[0.8, 0.0]])  # g = 0.8, so g/c = 2.0
    assert pu.decision_function(hot) == pytest.approx([2.0])
    proba = pu.predict_proba(hot)
    assert proba.shape == (1, 2)
    assert proba[0, 1] == pytest.approx(1.0)
    assert proba[0, 0] == pytest.approx(0.0)

    proba_all = pu.predict_proba(X)
    assert np.all(proba_all >= 0.0) and np.all(proba_all <= 1.0)
    assert proba_all.sum(axis=1) == pytest.approx(np.ones(len(X)))
    assert np.array_equal(pu.predict(hot), np.array([1]))


def test_elkan_noto_holds_out_the_requested_share_of_positives():
    X, _, s = make_pu_data(0, n=1000)
    n_pos = int(s.sum())
    pu = ElkanNotoPU(hold_out_ratio=0.25, random_state=3).fit(X, s)
    assert len(pu.hold_out_indices_) == int(np.ceil(0.25 * n_pos))
    assert np.all(s[pu.hold_out_indices_] == 1)
    assert np.all(s[pu.hold_out_unlabeled_indices_] == 0)
    assert len(np.unique(pu.hold_out_indices_)) == len(pu.hold_out_indices_)


def test_elkan_noto_is_deterministic_given_random_state():
    X, _, s = make_pu_data(1, n=1500)
    a = ElkanNotoPU(random_state=7).fit(X, s)
    b = ElkanNotoPU(random_state=7).fit(X, s)
    c = ElkanNotoPU(random_state=8).fit(X, s)
    assert a.c_ == b.c_
    assert np.array_equal(a.hold_out_indices_, b.hold_out_indices_)
    assert not np.array_equal(a.hold_out_indices_, c.hold_out_indices_)


def test_elkan_noto_does_not_mutate_the_passed_base_estimator():
    X, _, s = make_pu_data(0, n=800)
    base = LogisticRegression(max_iter=1000)
    ElkanNotoPU(base_estimator=base, random_state=0).fit(X, s)
    assert not hasattr(base, "coef_"), "base_estimator must be cloned, not fitted in place"


# ---------------------------------------------------------------------------------------
# BaggingPU
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_bagging_pu_ranks_hidden_positives(seed):
    X, y, s = make_pu_data(seed, separation=3.0)
    bag = BaggingPU(n_estimators=25, random_state=seed).fit(X, s)
    assert roc_auc_score(y, bag.decision_function(X)) > 0.85
    unlabeled = s == 0
    oob_auc = roc_auc_score(y[unlabeled], bag.oob_scores_[unlabeled])
    assert oob_auc > 0.85, f"out-of-bag AUC vs hidden labels = {oob_auc}"


def test_bagging_pu_oob_scores_are_nan_exactly_at_the_positives():
    X, _, s = make_pu_data(0, n=3000, separation=3.0)
    bag = BaggingPU(n_estimators=25, random_state=0).fit(X, s)
    oob = bag.oob_scores_
    assert oob.shape == (len(s),)
    assert np.all(np.isnan(oob[s == 1])), "labeled positives are never out of bag"
    assert np.all(np.isfinite(oob[s == 0])), "every unlabeled point was out of bag at least once"
    assert int(np.isnan(oob).sum()) == int(s.sum())
    assert np.all(bag.oob_counts_[s == 1] == 0)
    assert np.all(bag.oob_counts_[s == 0] > 0)


def test_bagging_pu_round_composition_and_oob_bookkeeping_are_exact():
    """A stub whose score is the first feature makes the OOB average exactly that feature.

    Each round must train on every positive plus exactly k unlabeled draws.
    """
    x0 = np.arange(30, dtype=float) / 30.0
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.zeros(30, dtype=int)
    s[:5] = 1
    bag = BaggingPU(base_estimator=ScoreFromFeature(), n_estimators=8, k=4, random_state=0).fit(
        X, s
    )

    assert bag.k_ == 4
    assert bag.score_kind_ == "decision_function"
    assert len(bag.estimators_) == 8
    for est in bag.estimators_:
        assert est.n_train_rows_ == 5 + 4
        assert est.n_train_positive_ == 5

    # every estimator returns x0, so an out-of-bag average is x0 itself
    unlabeled = s == 0
    assert bag.oob_scores_[unlabeled] == pytest.approx(x0[unlabeled])
    assert np.all(np.isnan(bag.oob_scores_[s == 1]))
    assert bag.decision_function(X) == pytest.approx(x0)
    # Each round draws k = 4 unlabeled points, so it marks at most 4 distinct rows in bag
    # (fewer when the bootstrap repeats a draw). Summed over the 8 rounds that bounds the
    # total in-bag count -- it does NOT bound any single row's count, since one row can be
    # drawn in many rounds.
    n_rounds = 8
    assert np.all(bag.oob_counts_[unlabeled] <= n_rounds)
    assert np.all(bag.oob_counts_[unlabeled] > 0)
    assert int(np.sum(n_rounds - bag.oob_counts_[unlabeled])) <= n_rounds * 4


def test_bagging_pu_default_k_is_the_number_of_positives():
    x0 = np.arange(40, dtype=float)
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.zeros(40, dtype=int)
    s[:7] = 1
    bag = BaggingPU(base_estimator=ScoreFromFeature(), n_estimators=3, random_state=0).fit(X, s)
    assert bag.k_ == 7
    for est in bag.estimators_:
        assert est.n_train_rows_ == 14  # 7 positives + 7 unlabeled draws


def test_bagging_pu_works_with_a_decision_function_only_estimator():
    X, y, s = make_pu_data(0, n=1200, separation=3.0)
    bag = BaggingPU(base_estimator=LinearSVC(), n_estimators=10, random_state=0).fit(X, s)
    assert bag.score_kind_ == "decision_function"
    assert roc_auc_score(y, bag.decision_function(X)) > 0.85
    with pytest.raises(ValueError, match="predict_proba"):
        bag.predict_proba(X)


def test_bagging_pu_is_deterministic_given_random_state():
    X, _, s = make_pu_data(2, n=1200, separation=3.0)
    a = BaggingPU(n_estimators=6, random_state=11).fit(X, s)
    b = BaggingPU(n_estimators=6, random_state=11).fit(X, s)
    c = BaggingPU(n_estimators=6, random_state=12).fit(X, s)
    assert a.decision_function(X) == pytest.approx(b.decision_function(X))
    assert not np.allclose(a.oob_scores_[s == 0], c.oob_scores_[s == 0])


def test_bagging_pu_predict_proba_averages_and_is_a_proper_distribution():
    X, _, s = make_pu_data(0, n=900, separation=3.0)
    bag = BaggingPU(n_estimators=8, random_state=0).fit(X, s)
    proba = bag.predict_proba(X)
    assert proba.shape == (len(X), 2)
    assert proba.sum(axis=1) == pytest.approx(np.ones(len(X)))
    assert np.all(proba >= 0.0) and np.all(proba <= 1.0)
    manual = np.mean([e.predict_proba(X)[:, 1] for e in bag.estimators_], axis=0)
    assert proba[:, 1] == pytest.approx(manual)


def test_bagging_pu_use_oob_substitutes_the_stored_out_of_bag_scores():
    """decision_function(use_oob=True) is the contract's 'OOB for unlabeled, mean for new X'.

    The default is the plain bagged mean for every row (see the method's Notes), so this
    also pins that the flag is opt-in and changes nothing when left off.
    """
    X, y, s = make_pu_data(0, n=600, separation=3.0)
    bag = BaggingPU(n_estimators=15, random_state=0).fit(X, s)
    plain = bag.decision_function(X)
    oob = bag.decision_function(X, use_oob=True)
    unlabeled = s == 0

    # unlabeled training rows get exactly their stored out-of-bag average ...
    assert np.all(np.isfinite(bag.oob_scores_[unlabeled]))
    assert oob[unlabeled] == pytest.approx(bag.oob_scores_[unlabeled])
    # ... which is a different number from the in-bag-contaminated bagged mean
    assert not np.allclose(oob[unlabeled], plain[unlabeled])
    assert roc_auc_score(y[unlabeled], oob[unlabeled]) > 0.85
    # labeled positives are never out of bag, so they keep the bagged mean
    assert oob[s == 1] == pytest.approx(plain[s == 1])
    # rows the estimator never trained on keep the bagged mean too
    new_X = X[:20] + 100.0
    assert bag.decision_function(new_X, use_oob=True) == pytest.approx(bag.decision_function(new_X))
    # the default is untouched
    assert bag.decision_function(X) == pytest.approx(plain)


def test_bagging_pu_use_oob_averages_byte_identical_training_rows():
    """Two identical training rows share one out-of-bag entry: the mean of the two."""
    X, _, s = make_pu_data(0, n=300, separation=3.0)
    dup = np.flatnonzero(s == 0)[:2]
    X[dup[1]] = X[dup[0]]  # byte-identical unlabeled rows with different OOB histories
    bag = BaggingPU(n_estimators=12, random_state=0).fit(X, s)
    pair = bag.oob_scores_[dup]
    assert np.all(np.isfinite(pair))
    assert pair[0] != pair[1], "the two rows must have been out of bag in different rounds"
    scored = bag.decision_function(X, use_oob=True)
    assert scored[dup[0]] == pytest.approx(float(np.mean(pair)))
    assert scored[dup[1]] == pytest.approx(float(np.mean(pair)))


def test_bagging_pu_does_not_mutate_the_passed_base_estimator():
    X, _, s = make_pu_data(0, n=800)
    base = LogisticRegression(max_iter=1000)
    BaggingPU(base_estimator=base, n_estimators=3, random_state=0).fit(X, s)
    assert not hasattr(base, "coef_")


# ---------------------------------------------------------------------------------------
# the tiny-n_positive regime (SEC AAER base rates: a handful of positives, thousands of rows)
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_both_estimators_survive_20_positives_and_5000_unlabeled(seed):
    X, y, s = make_pu_data(seed, n=5020, separation=3.0, n_labeled=20)
    assert int(s.sum()) == 20
    assert int((s == 0).sum()) == 5000

    pu = ElkanNotoPU(random_state=seed).fit(X, s)
    assert np.isfinite(pu.c_) and 0.0 < pu.c_ <= 1.0
    assert 0.0 <= pu.prior_ <= 1.0
    assert roc_auc_score(y, pu.decision_function(X)) > 0.85
    assert len(pu.hold_out_indices_) == 4  # ceil(0.2 * 20)

    bag = BaggingPU(n_estimators=25, random_state=seed).fit(X, s)
    assert bag.k_ == 20
    assert roc_auc_score(y, bag.decision_function(X)) > 0.85
    assert np.all(np.isnan(bag.oob_scores_[s == 1]))
    assert np.all(np.isfinite(bag.oob_scores_[s == 0]))
    unlabeled = s == 0
    assert roc_auc_score(y[unlabeled], bag.oob_scores_[unlabeled]) > 0.85


def test_elkan_noto_works_with_only_two_labeled_positives():
    X, _, s = make_pu_data(0, n=2000, separation=3.0, n_labeled=2)
    pu = ElkanNotoPU(random_state=0).fit(X, s)
    assert len(pu.hold_out_indices_) == 1  # one held out, one left to train on
    assert 0.0 < pu.c_ <= 1.0


# ---------------------------------------------------------------------------------------
# estimate_class_prior
# ---------------------------------------------------------------------------------------


def test_estimate_class_prior_matches_hand_computation():
    # c = mean([0.25, 0.75]) = 0.5; mean unlabeled = 0.25; prior = 0.25 / 0.5 = 0.5
    assert estimate_class_prior([0.25, 0.75], [0.125, 0.375]) == pytest.approx(0.5)
    # c = 0.4, mean unlabeled = 0.08 -> 0.2
    assert estimate_class_prior([0.4], [0.04, 0.12]) == pytest.approx(0.2)


def test_estimate_class_prior_clips_to_the_unit_interval():
    # mean unlabeled (0.5) exceeds c (0.25): the ratio is 2.0 and must be reported as 1.0
    assert estimate_class_prior([0.25], [0.5]) == 1.0
    assert 0.0 <= estimate_class_prior([0.5], [0.0, 0.0]) <= 1.0
    assert estimate_class_prior([0.5], [0.0, 0.0]) == 0.0


def test_estimate_class_prior_clip_false_exposes_the_out_of_range_ratio():
    """A returned 1.0 is ambiguous; clip=False is what distinguishes the two cases."""
    clipped_failure = estimate_class_prior([0.25], [0.5])
    genuine = estimate_class_prior([0.5], [0.5])
    assert clipped_failure == genuine == 1.0  # indistinguishable with the clip on
    assert estimate_class_prior([0.25], [0.5], clip=False) == pytest.approx(2.0)
    assert estimate_class_prior([0.5], [0.5], clip=False) == pytest.approx(1.0)
    # the clip never changes an in-range ratio
    assert estimate_class_prior([0.4], [0.04, 0.12], clip=False) == pytest.approx(0.2)


def test_estimate_class_prior_drops_non_finite_values():
    assert estimate_class_prior([0.5, np.nan], [0.25, np.inf]) == pytest.approx(0.5)


def test_estimate_class_prior_agrees_with_the_fitted_estimator():
    """The free function reproduces ElkanNotoPU.prior_ from the same scores."""
    X, y, s = make_pu_data(0, n=2000)
    pu = ElkanNotoPU(random_state=0).fit(X, s)
    g = pu.decision_function(X) * pu.c_  # recover g(x) itself
    prior = estimate_class_prior(g[pu.hold_out_indices_], g)
    assert prior == pytest.approx(pu.prior_, abs=1e-12)

    # ... but only because prior_ averages g over ALL rows. The free function estimates the
    # prior of whatever pool it is given: hand it the unlabeled rows and it estimates
    # P(y=1 | s=0), which is strictly smaller because every labeled positive (g large, y=1
    # for certain) has been removed from the pool.
    unlabeled_pool = estimate_class_prior(g[pu.hold_out_indices_], g[s == 0])
    assert unlabeled_pool < prior
    assert float(np.mean(y[s == 0])) < float(np.mean(y))  # the truth moves the same way
    # and the gap is not a rounding artefact: it is of the order of the removed mass
    assert prior - unlabeled_pool > 0.01


@pytest.mark.parametrize(
    ("labeled", "unlabeled", "match"),
    [
        ([], [0.1], "non-empty"),
        ([0.1], [], "non-empty"),
        ([np.nan], [0.1], "finite"),
        ([0.0, 0.0], [0.1], "not positive"),
        ([-0.5], [0.1], "not positive"),
        ([[0.1, 0.2]], [0.1], "1-D"),
    ],
)
def test_estimate_class_prior_rejects_bad_input(labeled, unlabeled, match):
    with pytest.raises(ValueError, match=match):
        estimate_class_prior(labeled, unlabeled)


def test_estimate_class_prior_rejects_unknown_method():
    with pytest.raises(ValueError, match="unknown method"):
        estimate_class_prior([0.5], [0.25], method="du_plessis")


# ---------------------------------------------------------------------------------------
# validation: loud failures
# ---------------------------------------------------------------------------------------


@pytest.fixture
def small_problem():
    X, _, s = make_pu_data(0, n=200, separation=3.0)
    return X, s


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
@pytest.mark.parametrize(
    ("bad_labels", "match"),
    [
        ([0, 1, 2, 0, 1], "only 0"),
        ([-1, 1, 0, 1, 0], "only 0"),
        ([1, 1, 0.5, 0, 1], "only 0"),
        ([0, 0, 0, 0, 0], "no labeled positives"),
        ([1, 1, 1, 1, 1], "no unlabeled points"),
        ([np.nan, 1, 0, 1, 0], "non-finite"),
    ],
)
def test_fit_rejects_invalid_s(estimator_cls, bad_labels, match):
    X = np.arange(10, dtype=float).reshape(5, 2)
    with pytest.raises(ValueError, match=match):
        estimator_cls().fit(X, bad_labels)


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_fit_rejects_string_labels(estimator_cls):
    X = np.arange(10, dtype=float).reshape(5, 2)
    with pytest.raises(ValueError, match="numeric or boolean"):
        estimator_cls().fit(X, np.array(["1", "0", "1", "0", "1"]))


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_fit_rejects_length_mismatch(estimator_cls):
    X = np.arange(10, dtype=float).reshape(5, 2)
    with pytest.raises(ValueError, match="same number of rows"):
        estimator_cls().fit(X, [1, 0, 1])


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_fit_rejects_non_finite_features(estimator_cls, small_problem):
    X, s = small_problem
    X = X.copy()
    X[3, 0] = np.nan
    with pytest.raises(ValueError):
        estimator_cls().fit(X, s)


@pytest.mark.parametrize("ratio", [0.0, 1.0, -0.2, 1.5, np.nan, None, "a lot", True, False])
def test_elkan_noto_rejects_bad_hold_out_ratio(ratio, small_problem):
    X, s = small_problem
    with pytest.raises(ValueError, match="hold_out_ratio"):
        ElkanNotoPU(hold_out_ratio=ratio).fit(X, s)


def test_elkan_noto_needs_at_least_two_positives():
    X, _, s = make_pu_data(0, n=500, separation=3.0, n_labeled=1)
    with pytest.raises(ValueError, match="at least 2 labeled positives"):
        ElkanNotoPU().fit(X, s)


def test_elkan_noto_rejects_a_base_estimator_without_predict_proba(small_problem):
    X, s = small_problem
    with pytest.raises(ValueError, match="predict_proba"):
        ElkanNotoPU(base_estimator=LinearSVC()).fit(X, s)


@pytest.mark.parametrize("n_estimators", [0, -3, 2.5])
def test_bagging_pu_rejects_bad_n_estimators(n_estimators, small_problem):
    X, s = small_problem
    with pytest.raises(ValueError, match="n_estimators"):
        BaggingPU(n_estimators=n_estimators).fit(X, s)


@pytest.mark.parametrize("k", [0, -1, 1.5])
def test_bagging_pu_rejects_bad_k(k, small_problem):
    X, s = small_problem
    with pytest.raises(ValueError, match="k must be"):
        BaggingPU(k=k).fit(X, s)


def test_bagging_pu_rejects_k_that_leaves_nothing_out_of_bag(small_problem):
    X, s = small_problem
    n_unlabeled = int((s == 0).sum())
    with pytest.raises(ValueError, match="out-of-bag"):
        BaggingPU(k=n_unlabeled).fit(X, s)
    with pytest.raises(ValueError, match="bootstrap=False"):
        BaggingPU(k=n_unlabeled + 1, bootstrap=False).fit(X, s)


@pytest.mark.parametrize("bootstrap", [True, False])
def test_bagging_pu_k_error_does_not_blame_a_k_the_caller_never_passed(bootstrap):
    """With k=None the value comes from the positives, so 'lower k' is not the fix."""
    x0 = np.arange(200, dtype=float)
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.zeros(200, dtype=int)
    s[:160] = 1  # derived k = 160, against only 40 unlabeled rows
    with pytest.raises(ValueError, match="k defaults to the number of labeled positives"):
        BaggingPU(bootstrap=bootstrap, random_state=0).fit(X, s)
    # an explicit k gets the short advice instead
    with pytest.raises(ValueError, match="Lower k"):
        BaggingPU(k=41, bootstrap=bootstrap, random_state=0).fit(X, s)


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
@pytest.mark.parametrize("flag", [True, False])
def test_rejects_a_boolean_random_state(estimator_cls, flag, small_problem):
    """bool is a subclass of int: random_state=True must not quietly become seed 1."""
    X, s = small_problem
    with pytest.raises(ValueError, match="random_state must not be a bool"):
        estimator_cls(random_state=flag).fit(X, s)


@pytest.mark.parametrize("flag", [True, False])
def test_bagging_pu_rejects_boolean_n_estimators_and_k(flag, small_problem):
    """Likewise n_estimators=True must not mean 'one round' nor k=True 'one draw'."""
    X, s = small_problem
    with pytest.raises(ValueError, match="n_estimators must be a positive int"):
        BaggingPU(n_estimators=flag, random_state=0).fit(X, s)
    with pytest.raises(ValueError, match="k must be a positive int"):
        BaggingPU(k=flag, n_estimators=2, random_state=0).fit(X, s)


def test_bagging_pu_without_bootstrap_never_repeats_a_draw():
    x0 = np.arange(50, dtype=float)
    X = np.column_stack([x0, np.zeros_like(x0)])
    s = np.zeros(50, dtype=int)
    s[:6] = 1
    bag = BaggingPU(
        base_estimator=ScoreFromFeature(), n_estimators=5, k=10, bootstrap=False, random_state=0
    ).fit(X, s)
    # sampling without replacement leaves exactly len(U) - k rows out of bag every round
    assert int(np.sum(bag.oob_counts_)) == 5 * (44 - 10)


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_predicting_before_fitting_raises(estimator_cls):
    with pytest.raises(NotFittedError):
        estimator_cls().decision_function(np.zeros((3, 2)))


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_predicting_with_the_wrong_number_of_features_raises(estimator_cls, small_problem):
    X, s = small_problem
    fitted = estimator_cls().fit(X, s)
    with pytest.raises(ValueError, match="features"):
        fitted.decision_function(np.zeros((3, 5)))


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_rejects_an_uninterpretable_random_state(estimator_cls, small_problem):
    X, s = small_problem
    with pytest.raises(ValueError, match="random_state"):
        estimator_cls(random_state="lucky").fit(X, s)


# ---------------------------------------------------------------------------------------
# sklearn compatibility
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_get_set_params_round_trip_and_clone(estimator_cls, small_problem):
    X, s = small_problem
    est = estimator_cls()
    params = est.get_params()
    assert "base_estimator" in params
    assert "random_state" in params
    est.set_params(random_state=5)
    assert est.get_params()["random_state"] == 5

    fresh = clone(est)
    assert fresh.get_params() == est.get_params()
    assert not hasattr(fresh, "classes_")
    assert is_classifier(est)

    fitted = est.fit(X, s)
    assert np.array_equal(fitted.classes_, np.array([0, 1]))
    assert fitted.n_features_in_ == 2
    assert set(np.unique(fitted.predict(X))) <= {0, 1}
    assert fitted.predict(X).shape == (len(X),)


@pytest.mark.parametrize("estimator_cls", [ElkanNotoPU, BaggingPU])
def test_accepts_list_input_and_a_generator_random_state(estimator_cls):
    """Lists and arrays must give identical scores, and default_rng(seed) must match seed."""
    X, y, s = make_pu_data(0, n=300, separation=3.0)
    from_lists = estimator_cls(random_state=np.random.default_rng(0)).fit(X.tolist(), s.tolist())
    from_arrays = estimator_cls(random_state=np.random.default_rng(0)).fit(X, s)
    from_seed = estimator_cls(random_state=0).fit(X, s)

    scores = from_lists.decision_function(X)
    assert scores.shape == (len(X),)
    assert np.all(np.isfinite(scores))
    assert float(np.std(scores)) > 0.0, "a constant score would pass a shape-only check"
    assert roc_auc_score(y, scores) > 0.85
    # list input, array input and an int seed are the same fit, not merely the same shape
    assert scores == pytest.approx(from_arrays.decision_function(X))
    assert scores == pytest.approx(from_seed.decision_function(X))
    # and scoring accepts lists too
    assert scores == pytest.approx(from_lists.decision_function(X.tolist()))

"""Tests for :mod:`forensics_core.eval.metrics`.

All data here is synthetic: either the ten-row worked example below (hand-computed
expectations, arithmetic in the comments) or draws from a seeded generator.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from forensics_core.eval.metrics import (
    BootstrapResult,
    average_precision,
    bootstrap_metric,
    ndcg_at_k,
    precision_at_k,
    rank_metrics,
    recall_at_k,
    roc_auc,
)

# ---------------------------------------------------------------------------------------
# The worked example. Scores are already in descending order, so rank i = position i.
#
#   rank i :   1     2     3     4     5     6     7     8     9    10
#   score  : 0.90  0.80  0.70  0.60  0.50  0.40  0.30  0.20  0.10  0.00
#   label  :   1     0     1     0     0     1     0     0     0     0
#
# Three positives, at ranks 1, 3 and 6.
# ---------------------------------------------------------------------------------------
Y10 = [1, 0, 1, 0, 0, 1, 0, 0, 0, 0]
S10 = [0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.00]


def test_precision_at_k_hand_computed():
    # positives in the top k, divided by k:
    #   k=1  -> 1/1  = 1.0
    #   k=3  -> 2/3  = 0.6666666666666666   (ranks 1 and 3)
    #   k=5  -> 2/5  = 0.4
    #   k=10 -> 3/10 = 0.3
    assert precision_at_k(Y10, S10, 1) == pytest.approx(1.0)
    assert precision_at_k(Y10, S10, 3) == pytest.approx(2 / 3)
    assert precision_at_k(Y10, S10, 5) == pytest.approx(0.4)
    assert precision_at_k(Y10, S10, 10) == pytest.approx(0.3)


def test_recall_at_k_hand_computed():
    # positives in the top k, divided by the 3 positives overall:
    #   k=1  -> 1/3, k=3 -> 2/3, k=5 -> 2/3 (no new positive at ranks 4-5), k=10 -> 3/3
    assert recall_at_k(Y10, S10, 1) == pytest.approx(1 / 3)
    assert recall_at_k(Y10, S10, 3) == pytest.approx(2 / 3)
    assert recall_at_k(Y10, S10, 5) == pytest.approx(2 / 3)
    assert recall_at_k(Y10, S10, 10) == pytest.approx(1.0)


def test_ndcg_at_k_hand_computed():
    # DCG@5  = 1/log2(2) + 0 + 1/log2(4) + 0 + 0        = 1 + 0.5            = 1.5
    # IDCG@5 = 1/log2(2) + 1/log2(3) + 1/log2(4)        = 1 + 0.63092975 + 0.5
    #                                                    = 2.1309297535714578
    # NDCG@5 = 1.5 / 2.1309297535714578                 = 0.7039180890341347
    idcg = 1.0 + 1.0 / np.log2(3.0) + 0.5
    assert idcg == pytest.approx(2.1309297535714578)
    assert ndcg_at_k(Y10, S10, 5) == pytest.approx(1.5 / idcg)
    assert ndcg_at_k(Y10, S10, 5) == pytest.approx(0.7039180890341347)

    # k=3 has the same DCG and the same IDCG (the ideal top-3 is 1,1,1), so same value.
    assert ndcg_at_k(Y10, S10, 3) == pytest.approx(0.7039180890341347)

    # DCG@10 = 1 + 1/log2(4) + 1/log2(7) = 1 + 0.5 + 0.35620718710802196 = 1.8562071871080221
    # NDCG@10 = 1.8562071871080221 / 2.1309297535714578 = 0.8710785440003369
    dcg10 = 1.0 + 0.5 + 1.0 / np.log2(7.0)
    assert dcg10 == pytest.approx(1.8562071871080221)
    assert ndcg_at_k(Y10, S10, 10) == pytest.approx(dcg10 / idcg)
    assert ndcg_at_k(Y10, S10, 10) == pytest.approx(0.8710785440003369)

    # k=1: the top slot holds a positive, so the ranking is ideal down to rank 1.
    assert ndcg_at_k(Y10, S10, 1) == pytest.approx(1.0)


def test_ndcg_binary_and_exponential_agree_on_binary_labels():
    # 2**1 - 1 == 1 and 2**0 - 1 == 0, so the two gain schemes coincide for 0/1 labels.
    for k in (1, 3, 5, 10):
        assert ndcg_at_k(Y10, S10, k, gains="binary") == pytest.approx(
            ndcg_at_k(Y10, S10, k, gains="exponential")
        )


def test_ndcg_exponential_gains_hand_computed_on_graded_relevance():
    # graded relevance, already ranked: rel = [2, 0, 1, 0]
    # exponential gains g = 2**rel - 1 = [3, 0, 1, 0]
    #   DCG@4  = 3/log2(2) + 0/log2(3) + 1/log2(4) + 0/log2(5) = 3 + 0.5 = 3.5
    #   ideal  = [3, 1, 0, 0]
    #   IDCG@4 = 3 + 1/log2(3) = 3.6309297535714578
    #   NDCG@4 = 3.5 / 3.6309297535714578 = 0.9639404333166532
    rel = [2, 0, 1, 0]
    scores = [4.0, 3.0, 2.0, 1.0]
    idcg = 3.0 + 1.0 / np.log2(3.0)
    assert ndcg_at_k(rel, scores, 4, gains="exponential") == pytest.approx(3.5 / idcg)
    assert ndcg_at_k(rel, scores, 4, gains="exponential") == pytest.approx(0.9639404333166532)

    # linear gains on the same grades: DCG = 2 + 0.5 = 2.5, IDCG = 2 + 1/log2(3)
    assert ndcg_at_k(rel, scores, 4, gains="binary") == pytest.approx(
        2.5 / (2.0 + 1.0 / np.log2(3.0))
    )


def test_fractional_k_is_a_ceiled_fraction_of_n():
    # n = 10:  0.25 -> ceil(2.5) = 3;  0.5 -> ceil(5.0) = 5;  0.01 -> ceil(0.1) = 1 (floor of 1)
    assert precision_at_k(Y10, S10, 0.25) == pytest.approx(precision_at_k(Y10, S10, 3))
    assert precision_at_k(Y10, S10, 0.5) == pytest.approx(precision_at_k(Y10, S10, 5))
    assert precision_at_k(Y10, S10, 0.01) == pytest.approx(precision_at_k(Y10, S10, 1))
    assert recall_at_k(Y10, S10, 0.25) == pytest.approx(2 / 3)
    assert ndcg_at_k(Y10, S10, 0.25) == pytest.approx(ndcg_at_k(Y10, S10, 3))

    # 1% of a 250-row list is 2.5 -> 3 rows.
    rng = np.random.default_rng(11)
    y = np.zeros(250, dtype=int)
    y[:5] = 1
    s = rng.permutation(np.arange(250.0))
    assert precision_at_k(y, s, 0.01) == pytest.approx(precision_at_k(y, s, 3))


def test_bad_k_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        precision_at_k(Y10, S10, 0)
    with pytest.raises(ValueError, match="exceeds"):
        precision_at_k(Y10, S10, 11)
    with pytest.raises(ValueError, match="fraction"):
        precision_at_k(Y10, S10, 5.0)  # a float is a fraction, never a count
    with pytest.raises(ValueError, match="fraction"):
        precision_at_k(Y10, S10, 1.0)
    with pytest.raises(ValueError, match="bool"):
        precision_at_k(Y10, S10, True)
    with pytest.raises(ValueError):
        precision_at_k(Y10, S10, "5")


def test_roc_auc_hand_computed():
    # Mann-Whitney: concordant (positive above negative) pairs out of 3 * 7 = 21.
    #   positive at rank 1 beats all 7 negatives
    #   positive at rank 3 beats the 6 negatives below it (ranks 4,5,7,8,9,10)
    #   positive at rank 6 beats the 4 negatives at ranks 7,8,9,10
    #   (7 + 6 + 4) / 21 = 17/21 = 0.8095238095238095
    assert roc_auc(Y10, S10) == pytest.approx(17 / 21)


def test_average_precision_hand_computed():
    # AP = mean precision at the ranks of the positives (no ties here):
    #   rank 1 -> 1/1, rank 3 -> 2/3, rank 6 -> 3/6
    #   (1 + 0.6666666666666666 + 0.5) / 3 = 0.7222222222222222
    assert average_precision(Y10, S10) == pytest.approx((1.0 + 2 / 3 + 0.5) / 3)


def test_perfect_and_inverted_rankings():
    y = [1, 1, 0, 0, 0]
    perfect = [5.0, 4.0, 3.0, 2.0, 1.0]
    inverted = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert roc_auc(y, perfect) == pytest.approx(1.0)
    assert roc_auc(y, inverted) == pytest.approx(0.0)
    assert ndcg_at_k(y, perfect, 2) == pytest.approx(1.0)
    assert precision_at_k(y, perfect, 2) == pytest.approx(1.0)
    assert precision_at_k(y, inverted, 2) == pytest.approx(0.0)
    assert recall_at_k(y, inverted, 2) == pytest.approx(0.0)


def test_ties_are_broken_by_input_order_stably():
    # Both units score 1.0; the stable descending sort keeps the input order, so the row
    # listed first is ranked first.
    assert precision_at_k([0, 1], [1.0, 1.0], 1) == pytest.approx(0.0)
    assert precision_at_k([1, 0], [1.0, 1.0], 1) == pytest.approx(1.0)
    # AUC is tie-aware and gives half credit, regardless of order.
    assert roc_auc([0, 1], [1.0, 1.0]) == pytest.approx(0.5)
    assert roc_auc([1, 0], [1.0, 1.0]) == pytest.approx(0.5)


def test_single_class_inputs_raise():
    ones = [1, 1, 1]
    zeros = [0, 0, 0]
    s = [3.0, 2.0, 1.0]
    with pytest.raises(ValueError, match="at least one positive and one negative"):
        roc_auc(ones, s)
    with pytest.raises(ValueError, match="at least one positive and one negative"):
        average_precision(zeros, s)
    with pytest.raises(ValueError, match="undefined without positives"):
        recall_at_k(zeros, s, 2)
    with pytest.raises(ValueError, match="IDCG"):
        ndcg_at_k(zeros, s, 2)
    # precision is still defined without positives: nothing in the top k is a hit.
    assert precision_at_k(zeros, s, 2) == pytest.approx(0.0)


def test_input_validation():
    with pytest.raises(ValueError, match="same length"):
        roc_auc([1, 0, 1], [1.0, 2.0])
    with pytest.raises(ValueError, match="empty"):
        roc_auc([], [])
    with pytest.raises(ValueError, match="NaN"):
        roc_auc([1, np.nan, 0], [3.0, 2.0, 1.0])
    with pytest.raises(ValueError, match="finite"):
        roc_auc([1, 0, 1], [3.0, np.nan, 1.0])
    with pytest.raises(ValueError, match="binary"):
        roc_auc([1, 2, 0], [3.0, 2.0, 1.0])
    with pytest.raises(ValueError, match="non-negative"):
        ndcg_at_k([1, -1, 0], [3.0, 2.0, 1.0], 2)
    with pytest.raises(ValueError, match="gains"):
        ndcg_at_k(Y10, S10, 3, gains="linear")
    with pytest.raises(ValueError, match="1-D"):
        roc_auc(np.zeros((2, 2)), np.zeros((2, 2)))


def test_metrics_recover_an_injected_signal():
    """A score built from the labels plus noise must rank far above chance."""
    rng = np.random.default_rng(20260906)
    n = 2000
    y = (rng.random(n) < 0.05).astype(int)  # 5% base rate
    scores = y * 2.0 + rng.normal(0.0, 1.0, size=n)  # injected effect of 2 sd
    assert roc_auc(y, scores) > 0.85
    assert average_precision(y, scores) > 0.4
    # the top 1% should be far richer in positives than the 5% base rate
    assert precision_at_k(y, scores, 0.01) > 0.5
    assert ndcg_at_k(y, scores, 0.01) > 0.5

    # a pure-noise score is at chance and cannot beat the informative one
    noise = rng.normal(size=n)
    assert abs(roc_auc(y, noise) - 0.5) < 0.05
    assert roc_auc(y, scores) > roc_auc(y, noise)


def test_rank_metrics_keys_and_values():
    out = rank_metrics(Y10, S10, ks=(0.01, 0.05, 0.10))
    assert set(out) == {
        "roc_auc",
        "average_precision",
        "precision@1%",
        "recall@1%",
        "ndcg@1%",
        "precision@5%",
        "recall@5%",
        "ndcg@5%",
        "precision@10%",
        "recall@10%",
        "ndcg@10%",
    }
    # n = 10, so 1%, 5% and 10% all resolve to ceil(<= 1.0) = 1 row.
    assert out["precision@1%"] == pytest.approx(1.0)
    assert out["recall@10%"] == pytest.approx(1 / 3)
    assert out["roc_auc"] == pytest.approx(17 / 21)

    # integer cut-offs get bare-number keys
    out_int = rank_metrics(Y10, S10, ks=(3, 5))
    assert "precision@3" in out_int
    assert out_int["precision@5"] == pytest.approx(0.4)

    with pytest.raises(ValueError, match="duplicate"):
        rank_metrics(Y10, S10, ks=(3, 3))

    # a one-class sample can still be scored on the @k metrics alone
    out_pos = rank_metrics([1, 1, 1], [3.0, 2.0, 1.0], ks=(2,), include_global=False)
    assert out_pos["precision@2"] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="at least one positive and one negative"):
        rank_metrics([1, 1, 1], [3.0, 2.0, 1.0], ks=(2,))


def test_bootstrap_metric_brackets_the_point_estimate():
    rng = np.random.default_rng(7)
    n = 400
    y = (rng.random(n) < 0.25).astype(int)
    scores = y * 1.5 + rng.normal(size=n)
    res = bootstrap_metric(roc_auc, y, scores, n_boot=200, alpha=0.05, seed=42)

    assert isinstance(res, BootstrapResult)
    assert res.point == pytest.approx(roc_auc(y, scores))
    assert res.n_boot == 200
    assert res.draws.size == 200 - res.n_failed
    assert res.se > 0.0
    assert res.ci_low < res.point < res.ci_high
    assert 0.0 <= res.ci_low <= res.ci_high <= 1.0
    assert res.method == "pairs"
    assert res.to_dict()["point"] == pytest.approx(res.point)

    # same seed -> same draws; different seed -> different draws
    again = bootstrap_metric(roc_auc, y, scores, n_boot=200, seed=42)
    assert np.allclose(again.draws, res.draws)
    other = bootstrap_metric(roc_auc, y, scores, n_boot=200, seed=43)
    assert not np.allclose(other.draws, res.draws)

    # a wider alpha gives a narrower interval
    narrow = bootstrap_metric(roc_auc, y, scores, n_boot=200, alpha=0.5, seed=42)
    assert (narrow.ci_high - narrow.ci_low) < (res.ci_high - res.ci_low)


def test_bootstrap_metric_accepts_bound_at_k_metrics_and_validates_arguments():
    rng = np.random.default_rng(3)
    n = 300
    y = (rng.random(n) < 0.2).astype(int)
    scores = y * 1.0 + rng.normal(size=n)
    metric = functools.partial(precision_at_k, k=0.05)
    res = bootstrap_metric(metric, y, scores, n_boot=100, seed=1)
    assert res.point == pytest.approx(precision_at_k(y, scores, 0.05))
    assert res.ci_low <= res.point <= res.ci_high

    strat = bootstrap_metric(roc_auc, y, scores, n_boot=100, seed=1, stratified=True)
    assert strat.method == "stratified_pairs"

    with pytest.raises(ValueError, match="n_boot"):
        bootstrap_metric(roc_auc, y, scores, n_boot=1)
    with pytest.raises(ValueError, match="alpha"):
        bootstrap_metric(roc_auc, y, scores, n_boot=10, alpha=1.5)


def test_bootstrap_metric_reports_undefined_resamples():
    """With a single positive, most resamples lose it and the metric is undefined."""
    y = [1] + [0] * 40
    scores = list(np.linspace(1.0, 0.0, 41))
    res = bootstrap_metric(roc_auc, y, scores, n_boot=200, seed=5)
    assert res.n_failed > 0
    assert res.draws.size == 200 - res.n_failed

    with pytest.raises(ValueError, match="undefined on most resamples"):
        bootstrap_metric(roc_auc, [1, 0], [1.0, 0.0], n_boot=2, seed=0)

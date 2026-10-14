"""Confirming the winner of a notch scan: forensics_core.bunching.inference.scan_placebo_test.

``scan_candidate_notches`` puts the largest of k estimates in row 0. A placebo comparison
that treats that winner as if it had been named in advance confirms it far too often when
there is no bunching anywhere, because the best of k tends to beat most placebos. These
tests pin the size of the confirmation the scan documents, exactly where the null can be
enumerated and by simulation through the public API where it cannot.

Synthetic data only (HARD RULE 3): uniform densities, with and without units moved onto a
known threshold. Fixed seeds throughout.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from forensics_core.bunching import (
    bunching_estimator,
    placebo_test,
    scan_candidate_notches,
    scan_placebo_test,
)

ALPHA = 0.05
WINDOW = {"bin_width": 1.0, "exclude_below": 2.0, "exclude_above": 2.0, "poly_degree": 7}
CANDIDATES = [60.0, 80.0, 100.0, 120.0, 140.0]
#: 40, 45, ..., 160 without the candidates: 20 placebos interleaved with the five candidates.
PLACEBOS = [float(t) for t in range(40, 161, 5) if float(t) not in CANDIDATES]
N_REPLICATES = 200


def synthetic_uniform(seed: int, n: int = 40_000, hi: float = 200.0) -> np.ndarray:
    """Uniform on ``[0, hi]``: no threshold carries any bunching."""
    return np.random.default_rng(seed).uniform(0.0, hi, size=n)


def synthetic_uniform_with_notch(
    seed: int, threshold: float, n: int = 120_000, hi: float = 600.0, n_moved: int = 300
) -> np.ndarray:
    """Uniform on ``[0, hi]`` with ``n_moved`` units moved from just below ``threshold`` to
    just above it (a bonus notch: the reward lies above)."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(0.0, hi, size=n)
    pool = np.flatnonzero((x >= threshold - 2.0) & (x < threshold))
    chosen = rng.choice(pool, size=n_moved, replace=False)
    x[chosen] = rng.uniform(threshold, threshold + 1.0, size=n_moved)
    return x


def cached_factory(cache: dict[float, object]):
    """An estimator factory with the scan's settings that fits each threshold once.

    Every call within one replicate sees the same sample, so a fit can be reused between
    the scan test and the placebo tests run on the same replicate.
    """

    def factory(threshold: float):
        def _estimate(x: np.ndarray):
            if threshold not in cache:
                cache[threshold] = bunching_estimator(x, threshold, bunching_side="above", **WINDOW)
            return cache[threshold]

        return _estimate

    return factory


# -------------------------------------------------------------- the acceptance scenario


def test_the_documented_confirmation_rejects_a_null_scan_winner_at_most_alpha():
    """No bunching anywhere, five scanned candidates, 20 placebos: the confirmation the scan
    documents rejects the winner at 0.05 in at most 5% of replicates plus Monte Carlo error,
    and so does placebo_test's default p-value for a threshold named in advance."""
    doc = " ".join((scan_candidate_notches.__doc__ or "").split())
    assert "scan_placebo_test" in doc, "the scan must document the selection-aware test"
    assert "exploratory" in doc

    k, m = len(CANDIDATES), len(PLACEBOS)
    mc_error = 2.0 * math.sqrt(ALPHA * (1.0 - ALPHA) / N_REPLICATES)
    confirmed = prenamed = selection_blind = 0
    for rep in range(N_REPLICATES):
        x = synthetic_uniform(seed=20261014 + rep)
        table = scan_candidate_notches(x, CANDIDATES, side="above", **WINDOW)
        factory = cached_factory({})

        result = scan_placebo_test(x, CANDIDATES, factory, PLACEBOS)
        assert result.details["winner"] == table.loc[0, "threshold"]
        assert result.pvalue >= k / (k + m)
        confirmed += result.pvalue <= ALPHA

        prenamed += placebo_test(x, 100.0, factory, PLACEBOS).pvalue <= ALPHA
        winner = result.details["winner"]
        selection_blind += placebo_test(x, winner, factory, PLACEBOS).pvalue <= ALPHA

    assert confirmed / N_REPLICATES <= ALPHA + mc_error
    assert prenamed / N_REPLICATES <= ALPHA + mc_error
    # The scenario is one a selection-blind check fails: the winner beats every placebo in
    # about k / (k + m) = 0.20 of null replicates, and placebo_test then reports p = 1/21.
    assert selection_blind / N_REPLICATES > 0.10


# ------------------------------------------------------------------- exact validity


def _ranked_inputs(n_thresholds: int):
    """A null sample, one real fit per threshold, and a statistic read from a rank table.

    The statistic ignores the fit and returns the rank assigned to its threshold, so the
    test can put the candidates at any set of ranks among the pooled thresholds. Under the
    null every assignment of ranks is equally likely, which is what makes the enumeration
    below an exact size computation.
    """
    x = synthetic_uniform(seed=7, n=20_000)
    thresholds = 10.0 + 4.0 * np.arange(n_thresholds)
    factory = cached_factory({})
    for t in thresholds:
        factory(float(t))(x)
    rank: dict[float, float] = {}

    def statistic(result) -> float:
        return rank[float(result.threshold)]

    return x, thresholds, factory, rank, statistic


def _scan_pvalues(k: int, m: int):
    """Yield (candidate ranks, p-value) for every k-set of ranks among k + m thresholds."""
    x, thresholds, factory, rank, statistic = _ranked_inputs(k + m)
    candidates, placebos = thresholds[:k], thresholds[k:]
    for chosen in itertools.combinations(range(k + m), k):
        others = [r for r in range(k + m) if r not in chosen]
        rank.clear()
        rank.update({float(t): float(r) for t, r in zip(candidates, chosen, strict=True)})
        rank.update({float(t): float(r) for t, r in zip(placebos, others, strict=True)})
        result = scan_placebo_test(x, candidates, factory, placebos, statistic=statistic)
        yield chosen, result


@pytest.mark.parametrize(("k", "m"), [(1, 20), (2, 40), (3, 20)])
def test_scan_placebo_test_has_size_at_most_alpha_over_every_assignment_of_ranks(k, m):
    pvalues = np.array([result.pvalue for _, result in _scan_pvalues(k, m)])
    assert pvalues.size == math.comb(k + m, k)
    for alpha in (0.05, 0.10, 0.20):
        size = float(np.mean(pvalues <= alpha))
        assert size <= alpha
        # Not vacuous: wherever the floor k / (k + m) is at or below alpha, it can reject.
        if k / (k + m) <= alpha:
            assert size > 0.0
        else:
            assert size == 0.0


def test_scan_placebo_pvalue_is_the_share_of_k_sets_whose_maximum_reaches_the_winner():
    k, m = 2, 10
    for chosen, result in _scan_pvalues(k, m):
        winner_rank = max(chosen)
        reaching = sum(max(s) >= winner_rank for s in itertools.combinations(range(k + m), k))
        assert result.pvalue == pytest.approx(reaching / math.comb(k + m, k), rel=1e-12)
        assert result.details["min_attainable_pvalue"] == pytest.approx(k / (k + m))


def test_with_one_candidate_it_is_the_add_one_placebo_test():
    x = synthetic_uniform_with_notch(seed=3, threshold=300.0)
    factory = cached_factory({})
    placebos = [float(t) for t in range(200, 420, 10) if t != 300]
    scan = scan_placebo_test(x, [300.0], factory, placebos)
    single = placebo_test(x, 300.0, factory, placebos, add_one=True)
    assert scan.statistic == single.statistic
    assert scan.pvalue == pytest.approx(single.pvalue, rel=1e-12)
    assert scan.details["n_at_least_observed"] == single.details["n_at_least_observed"]


# ------------------------------------------------------------------- power and floor


def _placebos_away_from(candidates: list[float], start: float, stop: float, step: float):
    grid = np.arange(start, stop, step)
    keep = [t for t in grid if all(abs(t - c) >= 6.0 for c in candidates)]
    return [float(t) for t in keep]


def test_a_real_notch_is_confirmed_given_enough_placebos():
    candidates = [100.0, 200.0, 300.0, 400.0, 500.0]
    x = synthetic_uniform_with_notch(seed=11, threshold=300.0)
    placebos = _placebos_away_from(candidates, 15.0, 590.0, 5.0)
    assert len(placebos) >= 95  # m >= k * (1 - alpha) / alpha for k = 5 at 0.05

    result = scan_placebo_test(x, candidates, cached_factory({}), placebos)
    assert result.details["winner"] == 300.0
    assert result.details["n_at_least_observed"] == 0
    assert result.pvalue == pytest.approx(5.0 / (5.0 + len(placebos)))
    assert result.pvalue <= ALPHA


def test_with_too_few_placebos_the_floor_is_reported_and_nothing_is_confirmed():
    candidates = [100.0, 200.0, 300.0, 400.0, 500.0]
    x = synthetic_uniform_with_notch(seed=11, threshold=300.0)
    placebos = _placebos_away_from(candidates, 15.0, 590.0, 5.0)[::5][:20]
    assert len(placebos) == 20

    result = scan_placebo_test(x, candidates, cached_factory({}), placebos)
    assert result.details["winner"] == 300.0
    assert result.details["min_attainable_pvalue"] == pytest.approx(5.0 / 25.0)
    assert result.pvalue == pytest.approx(5.0 / 25.0)
    assert result.pvalue > ALPHA


def test_result_carries_the_scan_and_the_placebos():
    x = synthetic_uniform(seed=5)
    result = scan_placebo_test(x, CANDIDATES, cached_factory({}), PLACEBOS)
    details = result.details
    assert result.method == "bunching_scan_placebo"
    assert details["alternative"] == "greater"
    assert details["n_candidates"] == len(CANDIDATES)
    assert details["n_placebo"] == len(PLACEBOS)
    assert details["statistic_name"] == "normalized_excess"
    np.testing.assert_array_equal(details["candidates"], CANDIDATES)
    np.testing.assert_array_equal(details["placebo_thresholds"], PLACEBOS)
    assert result.statistic == pytest.approx(float(np.max(details["candidate_values"])))
    assert details["n_pooled_at_least_observed"] == 1 + details["n_at_least_observed"]
    assert result.n == x.size
    assert result.to_dict()["details"]["winner"] == details["winner"]


# ---------------------------------------------------------------------- bad arguments


@pytest.mark.parametrize(
    ("candidates", "placebos", "match"),
    [
        ([], PLACEBOS, "candidates must be a non-empty"),
        ([60.0, 60.0], PLACEBOS, "candidates must not contain duplicates"),
        ([60.0, np.nan], PLACEBOS, "candidates must all be finite"),
        (CANDIDATES, [], "placebo_thresholds must be a non-empty"),
        (CANDIDATES, [45.0, 45.0], "placebo_thresholds must not contain duplicates"),
        (CANDIDATES, [45.0, np.inf], "placebo_thresholds must all be finite"),
        (CANDIDATES, [45.0, 100.0], "must not contain any of the candidates"),
    ],
)
def test_scan_placebo_test_rejects_bad_thresholds(candidates, placebos, match):
    x = synthetic_uniform(seed=5, n=5_000)
    with pytest.raises(ValueError, match=match):
        scan_placebo_test(x, candidates, cached_factory({}), placebos)


def test_scan_placebo_test_rejects_a_statistic_that_is_not_finite():
    x = synthetic_uniform(seed=5, n=5_000)
    with pytest.raises(ValueError, match="not finite at threshold"):
        scan_placebo_test(
            x, CANDIDATES, cached_factory({}), PLACEBOS, statistic=lambda r: float("nan")
        )


def test_scan_placebo_test_rejects_a_factory_that_is_not_one():
    x = synthetic_uniform(seed=5, n=5_000)
    with pytest.raises(ValueError, match="estimator_factory must be callable"):
        scan_placebo_test(x, CANDIDATES, None, PLACEBOS)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="BunchingResult"):
        scan_placebo_test(x, CANDIDATES, lambda t: lambda a: 1.0, PLACEBOS)

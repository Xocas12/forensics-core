"""Tests for forensics_core.bunching.notch: notch/kink specifications and the notch scan.

Synthetic data only (HARD RULE 3): a lognormal density with a known number of units moved
across a known threshold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.bunching.density import bunching_estimator
from forensics_core.bunching.notch import (
    SCAN_COLUMNS,
    Kink,
    Notch,
    estimate_kink,
    estimate_notch,
    scan_candidate_notches,
)

THRESHOLD = 100.0
SIGMA = 0.35
WINDOW = {
    "bin_width": 1.0,
    "exclude_below": 2.0,
    "exclude_above": 2.0,
    "lo": 60.0,
    "hi": 160.0,
    "poly_degree": 7,
}


def lognormal_with_bunching(
    seed: int, n: int = 200_000, n_moved: int = 2_000, side: str = "below"
) -> np.ndarray:
    """Lognormal density with ``n_moved`` units moved to the ``side`` of ``THRESHOLD``.

    ``side="below"`` moves units from just above the threshold to just below it (the tax
    notch pattern, reward below); ``side="above"`` does the reverse (the bonus notch: a
    payment is made iff the reported value reaches the threshold).
    """
    rng = np.random.default_rng(seed)
    x = rng.lognormal(np.log(THRESHOLD), SIGMA, size=n)
    if side == "below":
        pool = np.flatnonzero((x >= THRESHOLD) & (x < THRESHOLD + 2.0))
        target_lo, target_hi = THRESHOLD - 1.0, THRESHOLD
    else:
        pool = np.flatnonzero((x >= THRESHOLD - 2.0) & (x < THRESHOLD))
        target_lo, target_hi = THRESHOLD, THRESHOLD + 1.0
    chosen = rng.choice(pool, size=n_moved, replace=False)
    x[chosen] = rng.uniform(target_lo, target_hi, size=n_moved)
    return x


# ------------------------------------------------------------------- specifications


def test_notch_defaults_and_dominated_side():
    notch = Notch(100.0)
    assert notch.side == "above"
    assert notch.label == ""
    assert notch.dominated_side == "below"
    assert Notch(100.0, side="below").dominated_side == "above"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"threshold": np.nan}, "threshold"),
        ({"threshold": np.inf}, "threshold"),
        ({"threshold": 100.0, "side": "sideways"}, "side"),
        ({"threshold": "a hundred"}, "threshold"),
    ],
)
def test_notch_rejects_bad_arguments(kwargs, match):
    with pytest.raises(ValueError, match=match):
        Notch(**kwargs)


def test_kink_rejects_a_nonfinite_threshold():
    with pytest.raises(ValueError, match="threshold"):
        Kink(np.nan)


def test_estimate_notch_requires_a_notch():
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match="must be a Notch"):
        estimate_notch(x, 100.0, **WINDOW)  # type: ignore[arg-type]


def test_estimate_kink_requires_a_kink():
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match="must be a Kink"):
        estimate_kink(x, 100.0, bin_width=1.0, exclude_halfwidth=2.0)  # type: ignore[arg-type]


def test_estimate_kink_rejects_a_bad_halfwidth():
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match="exclude_halfwidth"):
        estimate_kink(x, Kink(THRESHOLD), bin_width=1.0, exclude_halfwidth=0.0)


# ---------------------------------------------------------------------- estimate_notch


def test_estimate_notch_recovers_a_bonus_notch_above_the_threshold():
    injected = 2_000
    x = lognormal_with_bunching(seed=7, n_moved=injected, side="above")
    result = estimate_notch(x, Notch(THRESHOLD, side="above", label="plan >= 100%"), **WINDOW)

    assert result.excess_mass == pytest.approx(injected, rel=0.12)
    assert result.missing_mass == pytest.approx(injected, rel=0.12)
    assert result.settings["side"] == "above"
    assert result.settings["notch_label"] == "plan >= 100%"
    assert result.settings["specification"] == "notch"
    # the hole is just below the threshold when the reward lies above it
    assert result.settings["dominated_region"] == (98.0, 100.0)
    assert result.settings["dominated_side"] == "below"


def test_estimate_notch_recovers_a_tax_notch_below_the_threshold():
    injected = 2_000
    x = lognormal_with_bunching(seed=20260903, n_moved=injected, side="below")
    result = estimate_notch(x, Notch(THRESHOLD, side="below"), **WINDOW)

    assert result.excess_mass == pytest.approx(injected, rel=0.12)
    assert result.settings["dominated_region"] == (100.0, 102.0)
    assert result.settings["dominated_side"] == "above"
    # identical to calling the estimator directly with the matching bunching side
    direct = bunching_estimator(x, THRESHOLD, bunching_side="below", **WINDOW)
    assert result.excess_mass == pytest.approx(direct.excess_mass, rel=1e-12)
    assert result.normalized_excess == pytest.approx(direct.normalized_excess, rel=1e-12)


def test_estimate_notch_forwards_extra_keywords():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000, side="below")
    result = estimate_notch(
        x, Notch(THRESHOLD, side="below"), integration_constraint=True, max_iter=25, **WINDOW
    )
    assert result.settings["integration_constraint"] is True
    assert result.settings["max_iter"] == 25
    assert result.settings["n_iter"] >= 1


# ----------------------------------------------------------------------- estimate_kink


def test_estimate_kink_uses_a_symmetric_window():
    injected = 2_000
    x = lognormal_with_bunching(seed=20260903, n_moved=injected, side="below")
    result = estimate_kink(
        x,
        Kink(THRESHOLD, label="marginal bonus rate"),
        bin_width=1.0,
        exclude_halfwidth=2.0,
        poly_degree=7,
        lo=60.0,
        hi=160.0,
    )
    assert result.settings["n_excluded_below"] == result.settings["n_excluded_above"] == 2
    assert result.settings["specification"] == "kink"
    assert result.settings["kink_label"] == "marginal bonus rate"
    assert result.settings["exclude_halfwidth"] == 2.0
    assert "dominated_region" not in result.settings
    assert result.excess_mass == pytest.approx(injected, rel=0.12)


# ------------------------------------------------------------------ scan for the notch


def test_scan_ranks_the_true_notch_first():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000, side="below")
    candidates = [85.0, 90.0, 95.0, THRESHOLD, 105.0, 110.0, 115.0]
    table = scan_candidate_notches(
        x,
        candidates,
        bin_width=1.0,
        exclude_below=2.0,
        exclude_above=2.0,
        poly_degree=7,
        side="below",
        lo=60.0,
        hi=160.0,
    )

    assert isinstance(table, pd.DataFrame)
    assert list(table.columns) == SCAN_COLUMNS
    assert len(table) == len(candidates)
    assert sorted(table["threshold"].tolist()) == sorted(candidates)
    assert table.loc[0, "threshold"] == THRESHOLD
    # and it wins by a wide margin, not by a hair
    assert table.loc[0, "normalized_excess"] > 10.0 * table.loc[1, "normalized_excess"]
    assert table["normalized_excess"].is_monotonic_decreasing
    assert (table["side"] == "below").all()
    assert (table["n_in_window"] > 0).all()
    assert table.index.tolist() == list(range(len(candidates)))


def test_scan_finds_a_bonus_notch_when_the_reward_lies_above():
    x = lognormal_with_bunching(seed=7, n_moved=2_000, side="above")
    table = scan_candidate_notches(
        x,
        [90.0, 95.0, THRESHOLD, 105.0, 110.0],
        bin_width=1.0,
        exclude_below=2.0,
        exclude_above=2.0,
        poly_degree=7,
        side="above",
        lo=60.0,
        hi=160.0,
    )
    assert table.loc[0, "threshold"] == THRESHOLD
    assert (table["side"] == "above").all()


def test_scan_finds_nothing_in_a_smooth_density():
    x = np.random.default_rng(4).lognormal(np.log(THRESHOLD), SIGMA, size=200_000)
    table = scan_candidate_notches(
        x,
        [90.0, 95.0, THRESHOLD, 105.0, 110.0],
        bin_width=1.0,
        exclude_below=2.0,
        exclude_above=2.0,
        poly_degree=7,
        side="below",
        lo=60.0,
        hi=160.0,
    )
    assert table["normalized_excess"].abs().max() < 0.15


def test_scan_supports_weights():
    x = lognormal_with_bunching(seed=20260903, n_moved=2_000, side="below")
    weights = np.full(x.size, 3.0)
    plain = scan_candidate_notches(
        x,
        [95.0, THRESHOLD, 105.0],
        bin_width=1.0,
        exclude_below=2.0,
        exclude_above=2.0,
        poly_degree=7,
        side="below",
        lo=60.0,
        hi=160.0,
    )
    weighted = scan_candidate_notches(
        x,
        [95.0, THRESHOLD, 105.0],
        bin_width=1.0,
        exclude_below=2.0,
        exclude_above=2.0,
        poly_degree=7,
        side="below",
        lo=60.0,
        hi=160.0,
        weights=weights,
    )
    assert weighted.loc[0, "threshold"] == plain.loc[0, "threshold"] == THRESHOLD
    np.testing.assert_allclose(
        weighted["excess_mass"].to_numpy(), 3.0 * plain["excess_mass"].to_numpy(), rtol=1e-10
    )
    np.testing.assert_allclose(
        weighted["normalized_excess"].to_numpy(),
        plain["normalized_excess"].to_numpy(),
        rtol=1e-10,
    )
    np.testing.assert_allclose(
        weighted["n_in_window"].to_numpy(), 3.0 * plain["n_in_window"].to_numpy(), rtol=1e-10
    )


@pytest.mark.parametrize(
    ("candidates", "match"),
    [
        ([], "non-empty"),
        ([100.0, 100.0], "duplicates"),
        ([100.0, np.nan], "finite"),
    ],
)
def test_scan_rejects_bad_candidates(candidates, match):
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match=match):
        scan_candidate_notches(
            x,
            candidates,
            bin_width=1.0,
            exclude_below=2.0,
            exclude_above=2.0,
            poly_degree=3,
            side="below",
            lo=60.0,
            hi=160.0,
        )


def test_scan_rejects_a_bad_side():
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match="side"):
        scan_candidate_notches(
            x,
            [100.0],
            bin_width=1.0,
            exclude_below=2.0,
            exclude_above=2.0,
            side="sideways",  # type: ignore[arg-type]
        )


def test_scan_names_the_candidate_that_failed():
    x = lognormal_with_bunching(seed=1, n=20_000, n_moved=200)
    with pytest.raises(ValueError, match=r"candidate threshold 1000\.0"):
        scan_candidate_notches(
            x,
            [1000.0],
            bin_width=1.0,
            exclude_below=2.0,
            exclude_above=2.0,
            poly_degree=3,
            side="below",
            lo=60.0,
            hi=160.0,
        )

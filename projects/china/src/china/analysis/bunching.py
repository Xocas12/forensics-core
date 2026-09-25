"""Bunching at the provincial growth target. **Stubs only: every function raises.**

The programme's unifying hypothesis is that distortion concentrates at discontinuities in the
incentive function: the plan-fulfilment threshold, the analyst consensus, the growth target.
For this project the candidate discontinuity is the annual growth target a province sets for
itself, and the prediction is excess mass in reported growth just at or above it and a hole
just below.

Method: Chetty, Friedman, Olsen and Pistaferri (2011) for the polynomial counterfactual and
the normalised excess mass; Kleven and Waseem (2013) for the notch case, where the payoff and
not just its slope changes at the threshold. Both are implemented in
:mod:`forensics_core.bunching`, and
:func:`forensics_core.bunching.notch.scan_candidate_notches` makes "find the notch" a
first-class operation, which matters here because round numbers are candidate thresholds in
their own right.

**Two problems that have to be solved before any of this runs, and neither is a coding
problem.**

1. *There is no source for provincial growth targets in this project's registry.* They are
   announced in provincial government work reports, one province a year. Until a source is
   registered, ``targets`` is a required argument with no default, and
   :func:`scan_growth_notches` is the honest fallback: it looks for excess mass at round
   numbers without claiming to know what the target was.
2. *The sample is tiny.* Bunching estimators are built for tens of thousands of tax filers.
   Here there are 31 provinces times roughly ten years, so about 310 observations spread over
   the whole growth distribution. Whether excess mass is even estimable at that size has to
   be established first, by simulation, and reported alongside anything else.

Honest bunching exists too, and ``docs/known_traps.md`` says so: provinces manage credit and
infrastructure to hit their targets. Excess mass at the target is consistent with both
misreporting and genuine target-hitting, and the physical-proxy residual
(:mod:`china.analysis.proxies`) is what distinguishes them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

__all__ = [
    "growth_target_bunching",
    "round_number_candidates",
    "scan_growth_notches",
    "terminal_digit_screen",
]


def round_number_candidates(lo: float = 4.0, hi: float = 12.0, step: float = 0.5) -> list[float]:
    """Candidate thresholds for a scan when the real targets are unknown.

    Round growth rates are focal in their own right: an announced target is nearly always a
    round or half-round number, so a scan over them is a usable substitute for a target list
    and does not pretend to be one.

    Parameters
    ----------
    lo, hi : float
        Range of growth rates in percentage points.
    step : float, default 0.5
        Spacing.

    Returns
    -------
    list of float
        The candidate thresholds.

    Raises
    ------
    ValueError
        If ``step`` is not positive or ``hi`` is not above ``lo``.

    Examples
    --------
    >>> round_number_candidates(6.0, 7.0, 0.5)
    [6.0, 6.5, 7.0]
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    if hi <= lo:
        raise ValueError(f"hi must exceed lo, got lo={lo} hi={hi}")
    out: list[float] = []
    value = lo
    while value <= hi + 1e-9:
        out.append(round(value, 10))
        value += step
    return out


def growth_target_bunching(
    growth: pd.Series,
    targets: pd.Series,
    *,
    bin_width: float = 0.1,
    exclude_below: float = 0.3,
    exclude_above: float = 0.3,
    poly_degree: int = 5,
) -> Any:
    """Excess mass in reported growth at each province-year's own growth target.

    Because the target differs by province and year, growth is re-centred on the target and
    the estimator is run once on the pooled, re-centred distribution. That is the standard
    device for a heterogeneous threshold and it assumes the response has the same shape at
    every target, which should be stated.

    Parameters
    ----------
    growth : pandas.Series
        Reported growth, indexed by province and year.
    targets : pandas.Series
        The announced target for the same province and year. **Required, no default**: the
        registry has no source for provincial growth targets, so passing them is the caller's
        way of saying where they came from.
    bin_width : float, default 0.1
        Histogram bin width in percentage points, matching the precision growth is published
        at.
    exclude_below, exclude_above : float, default 0.3
        Half-widths of the excluded window either side of the threshold.
    poly_degree : int, default 5
        Degree of the counterfactual polynomial. Lower than the usual 7 because the sample is
        two orders of magnitude smaller than in the tax-bunching literature.

    Returns
    -------
    forensics_core.bunching.density.BunchingResult
        With ``normalized_excess`` as the headline quantity.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: a source for ``targets``, and a power simulation. With about 310
    province-year observations, establish by simulation what size of excess mass is
    detectable at all before interpreting any estimate.
    """
    raise NotImplementedError(
        "no source for provincial growth targets is registered in data/SOURCES.yaml, and "
        "the estimator's power at about 310 observations is unestablished"
    )


def scan_growth_notches(
    growth: pd.Series,
    candidates: Sequence[float] | None = None,
    *,
    bin_width: float = 0.1,
    exclude_below: float = 0.3,
    exclude_above: float = 0.3,
    poly_degree: int = 5,
) -> pd.DataFrame:
    """Scan round growth rates for excess mass, without assuming a target.

    Wraps :func:`forensics_core.bunching.notch.scan_candidate_notches`. This is the version of
    the test that can actually be run with what the project has: it needs no target list, and
    it answers "is reported growth piling up anywhere in particular" rather than "is it piling
    up at the target".

    Parameters
    ----------
    growth : pandas.Series
        Reported growth for all provinces and years.
    candidates : sequence of float, optional
        Thresholds to try; defaults to :func:`round_number_candidates`.
    bin_width, exclude_below, exclude_above, poly_degree
        As :func:`growth_target_bunching`.

    Returns
    -------
    pandas.DataFrame
        One row per candidate threshold with excess mass, missing mass, normalised excess and
        the number of observations in the window, sorted by normalised excess descending.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the panel, and a multiple-comparison policy. Scanning seventeen candidate
    thresholds and reporting the largest is a maximum, not an estimate, and needs the
    placebo treatment in :func:`forensics_core.bunching.inference.placebo_test`.
    """
    raise NotImplementedError(
        "needs an extracted growth series, and a placebo or multiple-comparison policy for "
        "reporting the maximum over a scan"
    )


def terminal_digit_screen(
    panel: pd.DataFrame,
    *,
    vintage: str,
    series: str = "grp_nominal",
) -> Any:
    """Terminal-digit uniformity on published provincial levels.

    A cheap screen that needs no proxy and no target, testing whether the last digit of
    published levels is uniform. Wraps
    :func:`forensics_core.digits.terminal.terminal_digit_test`.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage to screen.
    series : str, default "grp_nominal"
        Series to screen.

    Returns
    -------
    forensics_core.TestResult
        Chi-square against uniform over the ten terminal digits.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains, and this one is a real obstacle rather than a to-do: the yearbook publishes
    provincial product to one decimal place in units of 100 million yuan, so the terminal
    digit is a rounding artefact of a quantity that was itself aggregated and rounded, and the
    test's null is not obviously uniform. Establish the null on an uncontested vintage before
    reading anything into a rejection. Note also that once extraction is by optical character
    recognition, a digit test is partly a test of the recogniser.
    """
    raise NotImplementedError(
        "needs an extracted panel; and the uniform null for a rounded, aggregated level "
        "series has to be established before a rejection means anything"
    )

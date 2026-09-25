"""Terminal-digit (last-digit) uniformity tests.

Unlike the leading digits, the trailing digits of a count carry no information about its
magnitude: for counts large enough that the last digit is not itself the quantity of
interest, the last digit is uniform on 0-9 and the last two digits are uniform on 00-99.
Humans inventing numbers are poor uniform generators, so the last digits of fabricated
counts are not uniform - they under-produce repeated digits such as 33 and over-produce
adjacent digits such as 34 (Beber, B. and Scacco, A. 2012, "What the numbers say: a
digit-based test for election fraud", *Political Analysis* 20(2): 211-234).

Assumption behind the null (Beber and Scacco 2012, section 2): the counts must be large
enough and spread over enough orders of magnitude that the last digit is effectively a
uniform draw. For counts concentrated below roughly 100 the uniform null is wrong for
reasons that have nothing to do with fraud, and these tests should not be used.

All functions here are pure: no I/O, no globals, no plotting.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats

from forensics_core._types import TestResult
from forensics_core.digits._common import (
    INTEGER_TOL,
    as_float_array,
    chi2_goodness_of_fit,
    kish_effective_n,
    validate_weights,
    weighted_counts,
)

#: Largest magnitude for which a float64 represents every integer exactly.
_MAX_EXACT_INT = 2.0**53

_BEBER_SCACCO_CITATION = (
    "Beber, B. and Scacco, A. (2012), 'What the numbers say: a digit-based test for election "
    "fraud', Political Analysis 20(2): 211-234."
)


def _check_k(k: int) -> int:
    if isinstance(k, bool) or not isinstance(k, int | np.integer):
        raise ValueError(f"k must be an integer; got {type(k).__name__}")
    k = int(k)
    if k < 1 or k > 9:
        raise ValueError(f"k must be between 1 and 9 (10**k cells); got {k}")
    return k


def _terminal_digits_with_mask(values: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(digits, mask)``; ``mask`` marks the finite elements that were used."""
    finite = np.isfinite(values)
    v = values[finite]
    if v.size:
        if np.any(np.abs(v) >= _MAX_EXACT_INT):
            raise ValueError(
                "terminal digits are undefined for magnitudes at or above 2**53, where "
                "float64 no longer represents every integer exactly"
            )
        rounded = np.round(v)
        bad = np.abs(v - rounded) > INTEGER_TOL
        if np.any(bad):
            offenders = np.unique(v[bad])[:5]
            raise ValueError(
                "terminal digit tests require integer-valued input (tolerance "
                f"{INTEGER_TOL:g}); {int(bad.sum())} value(s) are not integers, "
                f"e.g. {offenders.tolist()}"
            )
        digits = (np.abs(rounded).astype(np.int64)) % (10**k)
    else:
        digits = np.zeros(0, dtype=np.int64)
    return digits, finite


def terminal_digits(x: ArrayLike, k: int = 1) -> np.ndarray:
    """Last ``k`` decimal digits of integer-valued input.

    Parameters
    ----------
    x : array-like
        1-D numeric input. Values must be integer-valued to within 1e-9
        (:data:`forensics_core.digits._common.INTEGER_TOL`); non-finite entries are dropped,
        anything else that is not an integer raises. The magnitude is used, so ``-123`` and
        ``123`` share the terminal digits ``23``.
    k : int, default 1
        Number of trailing digits, 1 to 9.

    Returns
    -------
    numpy.ndarray
        ``int64`` values in ``0 .. 10**k - 1``, one per finite element of ``x``.

    Raises
    ------
    ValueError
        If ``k`` is out of range, if a finite value is not integer-valued, or if a magnitude
        is at or above ``2**53``.

    Examples
    --------
    >>> terminal_digits([123, 4560, 7.0]).tolist()
    [3, 0, 7]
    >>> terminal_digits([123, 4560, 7.0], k=2).tolist()
    [23, 60, 7]
    """
    k = _check_k(k)
    values = as_float_array(x, "x")
    digits, _ = _terminal_digits_with_mask(values, k)
    return digits


def _uniform_digit_table(
    values: np.ndarray, k: int, w: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float, int]:
    """Shared machinery: ``(observed, observed_prop, expected_prop, n, effective_n, n_dropped)``."""
    digits, finite = _terminal_digits_with_mask(values, k)
    n = int(digits.size)
    if n == 0:
        raise ValueError("no finite values: cannot test terminal digits of an empty sample")
    n_cells = 10**k
    kept_w = None if w is None else w[finite]
    if kept_w is not None and not np.any(kept_w > 0):
        raise ValueError("every finite value has zero weight")
    observed = weighted_counts(digits, kept_w, n_cells)
    total = float(observed.sum())
    observed_prop = observed / total
    expected_prop = np.full(n_cells, 1.0 / n_cells)
    effective_n = float(n) if kept_w is None else kish_effective_n(kept_w)
    return observed, observed_prop, expected_prop, n, effective_n, int(values.size - n)


def terminal_digit_test(x: ArrayLike, k: int = 1, weights: ArrayLike | None = None) -> TestResult:
    """Chi-square test that the last ``k`` digits are uniform.

    The null of uniform terminal digits is the standard election-forensics benchmark (Beber
    and Scacco 2012); the same test is used on reported counts in other settings where the
    trailing digits should carry no signal.

    Parameters
    ----------
    x : array-like
        1-D integer-valued input; see :func:`terminal_digits`.
    k : int, default 1
        Number of trailing digits; the test has ``10**k`` cells and ``10**k - 1`` degrees of
        freedom.
    weights : array-like, optional
        Observation weights. Cell counts become weighted sums and the chi-square is evaluated
        at the Kish effective sample size, which makes the weighted p-value APPROXIMATE
        (it ignores the cell-by-cell design effect a Rao-Scott correction would carry).

    Returns
    -------
    TestResult
        ``method = f"terminal_digit_{k}_chi2"``, ``statistic`` the Pearson chi-square,
        ``pvalue`` its upper-tail probability, ``n`` the unweighted count used. ``details``
        carries ``observed``, ``expected``, ``max_abs_dev`` (largest absolute deviation
        between an observed and expected cell proportion), ``max_excess_cell`` (the digit
        with the largest positive excess) and ``df``.

    Raises
    ------
    ValueError
        If ``k`` is out of range, the input is not integer-valued, the sample is empty, or
        the weights are mis-shaped.
    """
    k = _check_k(k)
    values = as_float_array(x, "x")
    w = validate_weights(weights, values.size)
    observed, observed_prop, expected_prop, n, effective_n, n_dropped = _uniform_digit_table(
        values, k, w
    )
    stat, pvalue, df = chi2_goodness_of_fit(observed_prop, expected_prop, effective_n)
    deviation = observed_prop - expected_prop
    return TestResult(
        method=f"terminal_digit_{k}_chi2",
        statistic=stat,
        pvalue=pvalue,
        n=n,
        details={
            "k": k,
            "digits": np.arange(10**k, dtype=np.int64),
            "observed": observed,
            "expected": expected_prop * float(observed.sum()),
            "observed_prop": observed_prop,
            "expected_prop": expected_prop,
            "max_abs_dev": float(np.max(np.abs(deviation))),
            "max_excess_cell": int(np.argmax(deviation)),
            "max_excess": float(np.max(deviation)),
            "df": df,
            "n_dropped": n_dropped,
            "effective_n": effective_n,
            "weighted": w is not None,
            "weighted_pvalue_is_approximate": w is not None,
            "alternative": "greater",
            "citation": _BEBER_SCACCO_CITATION,
        },
    )


def _pair_masks() -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks over the 100 last-two-digit cells: repeated pairs, adjacent pairs."""
    cells = np.arange(100)
    tens, units = cells // 10, cells % 10
    repeated = tens == units
    adjacent = np.abs(tens - units) == 1
    return repeated, adjacent


def _proportion_z(
    observed_prop: float, expected_prop: float, effective_n: float
) -> tuple[float, float]:
    """Two-sided normal test for a single proportion. Returns ``(z, pvalue)``."""
    se = np.sqrt(expected_prop * (1.0 - expected_prop) / effective_n)
    z = float((observed_prop - expected_prop) / se)
    return z, float(2.0 * stats.norm.sf(abs(z)))


def terminal_digit_pair_test(x: ArrayLike, weights: ArrayLike | None = None) -> TestResult:
    """Test that the last two digits are jointly uniform (Beber and Scacco 2012).

    Under the null the 100 last-two-digit combinations are equally likely, so 10 of the 100
    cells are repeated digits (00, 11, ..., 99), giving an expected proportion of 0.10, and
    18 are adjacent digits (01, 10, 12, 21, ..., 89, 98), giving 0.18. Beber and Scacco
    (2012) report that numbers invented by people show *too few* repeats and *too many*
    adjacent pairs, so the sign of each excess matters as much as the chi-square.

    Parameters
    ----------
    x : array-like
        1-D integer-valued input; see :func:`terminal_digits`. Values below 10 contribute a
        leading zero (7 counts as 07), which is correct only if such counts really can occur;
        filter them out beforehand when they cannot.
    weights : array-like, optional
        Observation weights; see :func:`terminal_digit_test` for the approximation this
        introduces into the p-value.

    Returns
    -------
    TestResult
        ``method = "terminal_digit_pair_chi2"``, the 100-cell chi-square statistic and its
        p-value (99 degrees of freedom). ``details["adjacent_pair_excess"]`` holds, for both
        the repeated-digit and the adjacent-digit families, the observed and expected
        proportions, the excess (observed minus expected; negative means a deficit), a
        normal-approximation z and its two-sided p-value.

    Raises
    ------
    ValueError
        If the input is not integer-valued, the sample is empty, or the weights are
        mis-shaped.
    """
    values = as_float_array(x, "x")
    w = validate_weights(weights, values.size)
    observed, observed_prop, expected_prop, n, effective_n, n_dropped = _uniform_digit_table(
        values, 2, w
    )
    stat, pvalue, df = chi2_goodness_of_fit(observed_prop, expected_prop, effective_n)
    repeated_mask, adjacent_mask = _pair_masks()
    excess: dict[str, dict[str, Any]] = {}
    for name, mask, direction in (
        ("repeated", repeated_mask, "fabricated data show a deficit (Beber and Scacco 2012)"),
        ("adjacent", adjacent_mask, "fabricated data show an excess (Beber and Scacco 2012)"),
    ):
        obs_p = float(observed_prop[mask].sum())
        exp_p = float(expected_prop[mask].sum())
        z, p_two_sided = _proportion_z(obs_p, exp_p, effective_n)
        excess[name] = {
            "cells": np.flatnonzero(mask).tolist(),
            "observed_prop": obs_p,
            "expected_prop": exp_p,
            "excess": obs_p - exp_p,
            "z": z,
            "pvalue": p_two_sided,
            "fraud_direction": direction,
        }
    deviation = observed_prop - expected_prop
    return TestResult(
        method="terminal_digit_pair_chi2",
        statistic=stat,
        pvalue=pvalue,
        n=n,
        details={
            "k": 2,
            "digits": np.arange(100, dtype=np.int64),
            "observed": observed,
            "expected": expected_prop * float(observed.sum()),
            "observed_prop": observed_prop,
            "expected_prop": expected_prop,
            "max_abs_dev": float(np.max(np.abs(deviation))),
            "max_excess_cell": int(np.argmax(deviation)),
            "df": df,
            "n_dropped": n_dropped,
            "effective_n": effective_n,
            "weighted": w is not None,
            "weighted_pvalue_is_approximate": w is not None,
            "alternative": "greater",
            "adjacent_pair_excess": excess,
            "citation": _BEBER_SCACCO_CITATION,
        },
    )

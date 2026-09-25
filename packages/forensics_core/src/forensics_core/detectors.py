"""The library's unsupervised methods, wrapped as named detectors.

The estimators in this library are unsupervised: they take a collection of numbers and return
one result. The harness is built around :class:`~forensics_core.eval.harness.Detector` objects
whose ``score`` returns one number per row. Until each method is a registered detector, every
project wires it up by hand, the pre-registration cannot name it, and the power atlas cannot
iterate over method families. This module is that wiring, and nothing else: no estimator's
numerical behaviour changes here.

The shape problem
-----------------
``docs/method_transfer.md`` documents two idioms for turning a collection statistic into a
per-row score, and every detector below says which it uses.

**Idiom A, precompute and read a column.** The project's feature builder calls the routine once
per unit and writes the statistic into a column of ``X``; the detector reads it. Cheap, because
``evaluate`` calls ``score`` once per fold, but it moves the method definition into the project.

**Idiom B, loop inside the function.** ``X`` carries one array-valued column per unit, and the
wrapped function calls the routine per row. Keeps the method in one place, and costs a
recomputation per fold.

Everything here is idiom B, because that is what a *library* detector can offer: idiom A by
definition lives in a project. Each detector therefore expects one object column whose cells
are the arrays a unit contributes, and says so in its docstring. A project that has already
precomputed a statistic does not need this module at all, and should wrap its column with
``FunctionDetector`` directly.

The sign convention
-------------------
Higher means more suspicious, everywhere. Where a statistic is naturally the other way round
the detector passes ``higher_is_suspicious=False`` rather than negating by hand, so the choice
is visible at the call site:

* a chi-square or an integer-excess statistic is already higher-is-worse;
* a p-value is lower-is-worse;
* :func:`~forensics_core.dispersion.underdispersion.dispersion_index` is suspicious when
  **low**, because too little noise is the signal.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import numpy as np

from forensics_core.bunching.density import bunching_estimator
from forensics_core.digits.benford import benford_test
from forensics_core.digits.integer_pct import integer_excess
from forensics_core.digits.terminal import terminal_digit_test
from forensics_core.dispersion.underdispersion import dispersion_index, too_smooth_test
from forensics_core.eval.harness import FunctionDetector, register_detector

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

#: The detectors this module registers.
DETECTOR_NAMES = (
    "benford_first_two",
    "terminal_digit",
    "integer_excess",
    "notch_bunching",
    "underdispersion",
    "too_smooth",
)

#: Default column holding each unit's array of values.
VALUES_COLUMN = "values"

#: Default column holding each unit's array of denominators, for rate-based methods.
DENOMINATORS_COLUMN = "denominators"


def _cells(frame: pd.DataFrame, column: str, detector: str) -> list[np.ndarray]:
    """Pull one array per row out of an object column, with a message that says what is wrong.

    A detector handed a float column rather than a column of arrays is the commonest mistake
    here, and the resulting error deep inside an estimator is unreadable.
    """
    if column not in frame.columns:
        raise ValueError(
            f"{detector}: no {column!r} column. This detector uses idiom B, so X must carry "
            f"one array per unit in {column!r}. If the statistic is already precomputed per "
            "unit, wrap that column with FunctionDetector directly instead."
        )
    out: list[np.ndarray] = []
    for i, cell in enumerate(frame[column]):
        arr = np.asarray(cell, dtype=float).ravel()
        if arr.ndim != 1:
            raise ValueError(f"{detector}: row {i} of {column!r} is not one-dimensional")
        out.append(arr)
    return out


def _scored(
    frame: pd.DataFrame,
    detector: str,
    per_unit: Callable[..., float],
    *,
    column: str = VALUES_COLUMN,
    extra_column: str | None = None,
    min_len: int = 1,
) -> np.ndarray:
    """Apply ``per_unit`` to each unit's array, refusing rather than guessing a missing score.

    A unit that could not be scored has not been found innocent, and there is no honest finite
    value to give it: zero or a minimum would rank it as the least suspicious thing in the
    dataset, and a maximum as the most. The harness and the rank metrics both reject non-finite
    scores, so ``nan`` is not available either.

    So this raises, naming the units and what to do. Filtering untestable units is a decision
    about the sample, and it belongs to the caller who knows why those units are short.
    """
    values = _cells(frame, column, detector)
    extras: Sequence[np.ndarray] | None = (
        _cells(frame, extra_column, detector) if extra_column else None
    )
    scores = np.full(len(values), np.nan, dtype=float)
    too_short: list[int] = []
    failed: list[tuple[int, str]] = []
    for i, arr in enumerate(values):
        finite = arr[np.isfinite(arr)]
        if finite.size < min_len:
            too_short.append(i)
            continue
        try:
            if extras is None:
                scores[i] = float(per_unit(finite))
            else:
                other = np.asarray(extras[i], dtype=float)
                scores[i] = float(per_unit(arr, other))
        except (ValueError, ZeroDivisionError, FloatingPointError) as exc:
            failed.append((i, f"{type(exc).__name__}: {exc}"))

    bad = np.flatnonzero(~np.isfinite(scores))
    if bad.size:
        detail = []
        if too_short:
            detail.append(
                f"{len(too_short)} unit(s) had fewer than min_len={min_len} finite values "
                f"(first at row {too_short[0]})"
            )
        if failed:
            detail.append(
                f"{len(failed)} unit(s) raised, first at row {failed[0][0]}: {failed[0][1]}"
            )
        raise ValueError(
            f"{detector}: could not score {bad.size} of {len(values)} units. "
            + "; ".join(detail)
            + ". A unit that cannot be tested has not been found innocent, and there is no "
            "honest score to give it, so this refuses rather than guessing. Filter those "
            "units from the Dataset, or lower min_len if the threshold is wrong for this "
            "data. The harness and the rank metrics both reject non-finite scores."
        )
    return scores


# ------------------------------------------------------------------------------ digit family


@register_detector("benford_first_two")
def benford_first_two_detector(
    *, column: str = VALUES_COLUMN, min_len: int = 30, **kw: Any
) -> FunctionDetector:
    """First-two-digit Benford chi-square per unit. Idiom B.

    Cost of the idiom: the digit table is rebuilt on every ``score`` call, so on a large panel
    inside a cross-validated ``evaluate`` this is the expensive detector. Precompute the
    statistic in the project and use ``FunctionDetector`` if that matters.

    ``min_len`` guards the chi-square: with too few values the statistic is unstable and the
    unit scores ``nan`` rather than an arbitrary number.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "benford_first_two",
            lambda a: benford_test(a, position="first_two", **kw).chi2.statistic,
            column=column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="benford_first_two", higher_is_suspicious=True)


@register_detector("terminal_digit")
def terminal_digit_detector(
    *, column: str = VALUES_COLUMN, k: int = 1, min_len: int = 30, **kw: Any
) -> FunctionDetector:
    """Last-digit uniformity chi-square per unit. Idiom B.

    Same recomputation cost as the Benford detector. The statistic is higher-is-worse, so no
    sign flip.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "terminal_digit",
            lambda a: terminal_digit_test(np.rint(a), k=k, **kw).statistic,
            column=column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="terminal_digit", higher_is_suspicious=True)


@register_detector("integer_excess")
def integer_excess_detector(
    *,
    column: str = VALUES_COLUMN,
    denominators_column: str = DENOMINATORS_COLUMN,
    min_len: int = 50,
    n_mc: int = 100,
    seed: int | None = 0,
    **kw: Any,
) -> FunctionDetector:
    """Excess mass at integer percentages per unit, as a z-statistic. Idiom B.

    Needs two columns: percentages in ``column`` and their denominators in
    ``denominators_column``, because the null redraws each observation as binomial noise around
    its own rate and cannot be computed from percentages alone.

    The most expensive detector here by a wide margin: the null is a Monte Carlo, so a
    ``score`` call runs ``n_mc`` resamples per unit. ``n_mc`` defaults to 100 rather than the
    estimator's own default for that reason, and the p-value floor moves with it.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "integer_excess",
            lambda pct, den: integer_excess(pct, den, n_mc=n_mc, seed=seed, **kw).test.statistic,
            column=column,
            extra_column=denominators_column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="integer_excess", higher_is_suspicious=True)


# ---------------------------------------------------------------------------------- bunching


@register_detector("notch_bunching")
def notch_bunching_detector(
    *,
    threshold: float,
    bin_width: float,
    exclude_below: float,
    exclude_above: float,
    column: str = VALUES_COLUMN,
    side: str = "below",
    min_len: int = 200,
    **kw: Any,
) -> FunctionDetector:
    """Normalised excess mass at one notch, per unit. Idiom B.

    ``side`` must match where the reward lies, and getting it wrong inverts the sign: a
    reward-above notch scanned as ``"below"`` reports a large negative excess. See
    ``docs/notches.md``.

    ``min_len`` is high because the estimator fits a polynomial counterfactual over binned
    counts; a unit with a few dozen values cannot support one, and would otherwise produce a
    confident number from noise.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "notch_bunching",
            lambda a: (
                bunching_estimator(
                    a,
                    threshold,
                    bin_width=bin_width,
                    exclude_below=exclude_below,
                    exclude_above=exclude_above,
                    bunching_side=side,
                    **kw,
                ).normalized_excess
            ),
            column=column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="notch_bunching", higher_is_suspicious=True)


# -------------------------------------------------------------------------------- dispersion


@register_detector("underdispersion")
def underdispersion_detector(
    *, column: str = VALUES_COLUMN, min_len: int = 5, **kw: Any
) -> FunctionDetector:
    """Dispersion index per unit, oriented so that too little noise scores high. Idiom B.

    The one detector whose natural direction is inverted: fabricated series contain too little
    variance, so a LOW dispersion index is the signal. ``higher_is_suspicious=False`` makes
    that visible here rather than hiding a minus sign inside the function.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "underdispersion",
            lambda a: dispersion_index(a, **kw),
            column=column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="underdispersion", higher_is_suspicious=False)


@register_detector("too_smooth")
def too_smooth_detector(
    *,
    column: str = VALUES_COLUMN,
    min_len: int = 8,
    n_perm: int = 199,
    seed: int | None = 0,
    **kw: Any,
) -> FunctionDetector:
    """Von Neumann smoothness test per unit, scored on its p-value. Idiom B.

    A low p-value means the series is implausibly smooth, so this is the second inverted
    detector: ``higher_is_suspicious=False``.

    ``n_perm`` defaults below the estimator's own default because this runs a permutation test
    per unit; raise it when the ranking near the top matters more than the runtime.
    """

    def score(X: pd.DataFrame) -> np.ndarray:
        return _scored(
            X,
            "too_smooth",
            lambda a: too_smooth_test(a, n_perm=n_perm, seed=seed, **kw).pvalue,
            column=column,
            min_len=min_len,
        )

    return FunctionDetector(score, name="too_smooth", higher_is_suspicious=False)


# ------------------------------------------------------------------------------------- notes
#
# reconcile_gross_error is deliberately NOT registered. Its input is a reconciliation over a
# constraint system, not a collection of numbers per unit: it needs an incidence matrix, a
# measurement vector and a covariance, and the "unit" it scores is a measurement inside one
# system rather than a row of a Dataset. Neither documented idiom fits it without inventing a
# convention for how a Dataset carries a graph, and a detector that silently reported a
# misleading per-row score would be worse than its absence. A project that wants it should
# reconcile explicitly and wrap the resulting per-measurement z with FunctionDetector under
# idiom A.

"""Inference for bunching estimates: bootstrap standard errors, placebo thresholds and a
generic label-permutation test.

The bunching estimator is a regression on *binned counts*, so its sampling variability comes
from two places: the counts are noisy around the polynomial (bin-level residuals) and the
sample of units is itself a draw (unit-level resampling). Chetty, Friedman, Olsen and
Pistaferri (2011, *Quarterly Journal of Economics* 126(2): 749-804) use the first — they
resample the estimated residual vector of the bin-count regression, rebuild a set of bin
counts, and re-run the estimator — and report the standard deviation of the resulting
distribution as the standard error. The unit-level ("pairs") bootstrap is the standard
alternative (Efron and Tibshirani 1993, *An Introduction to the Bootstrap*, ch. 6 and 13);
it is slower but propagates uncertainty in the binning itself.

Placebo thresholds are the field's standard falsification: re-run the estimator at
thresholds where the incentive function does *not* jump and check that the measured excess
is unremarkable there (Kleven 2016, *Annual Review of Economics* 8: 435-464).

All functions here are pure; randomness flows through ``seed`` -> ``np.random.default_rng``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from forensics_core._types import TestResult, jsonable
from forensics_core.bunching._common import as_float_array, drop_nonfinite
from forensics_core.bunching.density import BunchingResult, _refit_result

__all__ = [
    "BootstrapResult",
    "bootstrap_bunching",
    "permutation_test",
    "placebo_test",
]

BootstrapMethod = Literal["residual", "pairs"]

#: Statistics of a :class:`~forensics_core.bunching.density.BunchingResult` that can be
#: bootstrapped by name.
_STATISTICS = ("excess_mass", "missing_mass", "normalized_excess")


@dataclass(frozen=True)
class BootstrapResult:
    """Bootstrap distribution of a scalar estimate.

    Attributes
    ----------
    point : float
        The full-sample estimate (not the bootstrap mean).
    se : float
        Standard deviation of the bootstrap draws, ``ddof=1``.
    ci_low, ci_high : float
        Percentile interval at level ``1 - alpha`` (Efron and Tibshirani 1993, ch. 13).
    draws : numpy.ndarray
        The bootstrap replicates, in the order they were drawn.
    method : str
        ``"residual"`` or ``"pairs"``.
    n_boot : int
        Number of replicates.
    """

    point: float
    se: float
    ci_low: float
    ci_high: float
    draws: np.ndarray
    method: str
    n_boot: int

    @property
    def bias(self) -> float:
        """Bootstrap estimate of bias: ``mean(draws) - point``."""
        return float(np.mean(self.draws)) - float(self.point)

    def covers(self, value: float) -> bool:
        """Whether the percentile interval contains ``value``."""
        return bool(self.ci_low <= float(value) <= self.ci_high)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))

    def to_test_result(self, method_name: str = "bunching_bootstrap") -> TestResult:
        """Wrap as a :class:`~forensics_core._types.TestResult` (no p-value)."""
        return TestResult(
            method=method_name,
            statistic=float(self.point),
            pvalue=None,
            n=int(self.n_boot),
            details={
                "se": float(self.se),
                "ci_low": float(self.ci_low),
                "ci_high": float(self.ci_high),
                "bootstrap_method": self.method,
                "n_boot": int(self.n_boot),
            },
        )


def _check_alpha(alpha: float) -> float:
    a = float(alpha)
    if not np.isfinite(a) or not (0.0 < a < 1.0):
        raise ValueError(f"alpha must lie strictly between 0 and 1; got {alpha!r}")
    return a


def _extract(result: BunchingResult, statistic: str | Callable[[BunchingResult], float]) -> float:
    if callable(statistic):
        return float(statistic(result))
    if statistic not in _STATISTICS:
        raise ValueError(f"statistic must be a callable or one of {_STATISTICS}; got {statistic!r}")
    return float(getattr(result, statistic))


def _result_from_fit(
    base: BunchingResult, counts: np.ndarray, fit: dict[str, Any]
) -> BunchingResult:
    """Rebuild a :class:`BunchingResult` from a bin-level refit of ``base``."""
    settings = {
        **base.settings,
        "n_iter": fit["n_iter"],
        "converged": fit["converged"],
        "stop_reason": fit["stop_reason"],
        "shift_factor": fit["shift_factor"],
        "mean_counterfactual_excluded": fit["mean_counterfactual_excluded"],
        "imbalance": abs(fit["excess_mass"] - fit["missing_mass"]),
        "n_in_window": float(np.sum(counts[base.excluded_mask])),
        "resampled": True,
    }
    return replace(
        base,
        counts=counts,
        counterfactual=fit["counterfactual"],
        excess_mass=fit["excess_mass"],
        missing_mass=fit["missing_mass"],
        normalized_excess=fit["normalized_excess"],
        coefficients=fit["coefficients"],
        settings=settings,
    )


def bootstrap_bunching(
    x: ArrayLike,
    estimator: Callable[[np.ndarray], BunchingResult],
    *,
    n_boot: int = 499,
    alpha: float = 0.05,
    seed: int | None = None,
    method: BootstrapMethod = "residual",
    statistic: str | Callable[[BunchingResult], float] = "excess_mass",
) -> BootstrapResult:
    """Bootstrap standard error and percentile interval for a bunching estimate.

    Parameters
    ----------
    x : array-like
        The sample the estimator is applied to. Non-finite values are dropped first, so the
        residual and pairs bootstraps see the same data.
    estimator : callable
        ``estimator(x) -> BunchingResult``. Typically
        ``functools.partial`` or a lambda closing over ``threshold``, ``bin_width`` and the
        window widths.
    n_boot : int, default 499
        Number of replicates. 499/999 keep percentile ranks exact-ish for the usual alphas.
    alpha : float, default 0.05
        Percentile interval level: the interval spans the ``alpha/2`` and ``1 - alpha/2``
        quantiles of the draws.
    seed : int, optional
        Seed for ``numpy.random.default_rng``.
    method : {"residual", "pairs"}, default "residual"
        ``"residual"`` — Chetty et al. (2011): fit once, form the bin-level residuals
        ``c_j - hat c_j`` of the *full* regression (polynomial **and** excluded-bin dummies,
        so residuals in the excluded window are exactly zero), resample them with
        replacement across bins, add them back to the fitted values and re-run the bin-level
        estimator. The unit sample and the binning are held fixed. ``"pairs"`` — resample
        units with replacement and re-run ``estimator`` on each resample.
    statistic : str or callable, default "excess_mass"
        Which scalar to bootstrap: ``"excess_mass"``, ``"missing_mass"``,
        ``"normalized_excess"``, or any callable mapping a ``BunchingResult`` to a float.

    Returns
    -------
    BootstrapResult

    Raises
    ------
    ValueError
        If ``n_boot < 2``, ``alpha`` is out of range, ``method`` is unknown, ``estimator``
        does not return a ``BunchingResult``, or the statistic name is unknown.

    Notes
    -----
    The residual pool includes the zero residuals of the excluded bins, following the
    reference implementation of Chetty et al. (2011) (whose regression is saturated there).
    This makes the residual bootstrap mildly conservative in the sense of understating
    variance in the excluded window; the pairs bootstrap does not have that property and is
    the safer default when the bin counts are small.

    The pairs bootstrap resamples ``x`` only. If the estimator uses observation weights,
    close over weights that are a function of the value (or use ``method="residual"``),
    because the resampled units cannot be matched back to positions in the weight vector.
    """
    if int(n_boot) < 2:
        raise ValueError(f"n_boot must be >= 2; got {n_boot!r}")
    a = _check_alpha(alpha)
    if method not in ("residual", "pairs"):
        raise ValueError(f"method must be 'residual' or 'pairs'; got {method!r}")
    if not callable(estimator):
        raise ValueError("estimator must be callable: estimator(x) -> BunchingResult")

    arr = as_float_array(x, "x")
    arr, _, _ = drop_nonfinite(arr, None)
    if arr.size == 0:
        raise ValueError("x contains no finite values")

    base = estimator(arr)
    if not isinstance(base, BunchingResult):
        raise ValueError(f"estimator must return a BunchingResult; got {type(base).__name__}")
    point = _extract(base, statistic)

    rng = np.random.default_rng(seed)
    n_draws = int(n_boot)
    draws = np.empty(n_draws, dtype=float)

    if method == "residual":
        counts = np.asarray(base.counts, dtype=float)
        excluded = np.asarray(base.excluded_mask, dtype=bool)
        fitted = np.where(excluded, counts, np.asarray(base.counterfactual, dtype=float))
        residuals = counts - fitted
        n_bins = counts.size
        for b in range(n_draws):
            resampled = fitted + rng.choice(residuals, size=n_bins, replace=True)
            fit = _refit_result(base, resampled)
            draws[b] = _extract(_result_from_fit(base, resampled, fit), statistic)
    else:
        n = arr.size
        for b in range(n_draws):
            idx = rng.integers(0, n, size=n)
            result = estimator(arr[idx])
            if not isinstance(result, BunchingResult):
                raise ValueError(
                    f"estimator must return a BunchingResult; got {type(result).__name__}"
                )
            draws[b] = _extract(result, statistic)

    lo, hi = np.quantile(draws, [a / 2.0, 1.0 - a / 2.0])
    return BootstrapResult(
        point=float(point),
        se=float(np.std(draws, ddof=1)),
        ci_low=float(lo),
        ci_high=float(hi),
        draws=draws,
        method=str(method),
        n_boot=n_draws,
    )


def placebo_test(
    x: ArrayLike,
    threshold: float,
    estimator_factory: Callable[[float], Callable[[np.ndarray], BunchingResult]],
    placebo_thresholds: Sequence[float],
    *,
    statistic: str | Callable[[BunchingResult], float] = "normalized_excess",
    add_one: bool = False,
) -> TestResult:
    """Compare the excess mass at ``threshold`` with the excess at placebo thresholds.

    The identifying assumption of a bunching design is that the counterfactual density is
    smooth, so the *same* estimator applied where the incentive function does not jump
    should find nothing. This test makes that check quantitative: the p-value is the share
    of placebo thresholds whose excess is at least as large as the real one (Kleven 2016,
    *Annual Review of Economics*, on placebo/robustness practice; the permutation logic is
    the usual one).

    Parameters
    ----------
    x : array-like
        Running variable.
    threshold : float
        The real threshold.
    estimator_factory : callable
        ``estimator_factory(threshold) -> (estimator(x) -> BunchingResult)``. It must build
        an estimator that differs *only* in the threshold, otherwise the placebos are not
        comparable.
    placebo_thresholds : sequence of float
        Thresholds at which nothing should happen. Choose them far enough from the real
        threshold that the excluded windows do not overlap it, and inside the support.
    statistic : str or callable, default "normalized_excess"
        Which scalar to compare. The normalised excess is the right default because the
        counterfactual level differs between thresholds.
    add_one : bool, default False
        If ``True`` use ``(1 + #{placebo >= observed}) / (1 + n_placebo)``, the
        never-zero permutation p-value of Phipson and Smyth (2010, *Statistical Applications
        in Genetics and Molecular Biology* 9(1), Article 39). The default ``False`` is the
        plain share fixed by INTERFACES.md, which can return exactly 0.

    Returns
    -------
    TestResult
        ``statistic`` is the observed value at the real threshold; ``pvalue`` is one-sided
        (``details["alternative"] = "greater"``); ``details`` carries the placebo thresholds
        and their values, the number of placebos, and the placebo mean/sd.

    Raises
    ------
    ValueError
        If ``placebo_thresholds`` is empty, contains ``threshold`` itself, or if the factory
        does not produce estimators returning ``BunchingResult``.
    """
    thr = float(threshold)
    if not np.isfinite(thr):
        raise ValueError(f"threshold must be finite; got {threshold!r}")
    if not callable(estimator_factory):
        raise ValueError("estimator_factory must be callable: factory(threshold) -> estimator")
    placebos = np.asarray(list(placebo_thresholds), dtype=float)
    if placebos.size == 0:
        raise ValueError("placebo_thresholds must not be empty")
    if not np.all(np.isfinite(placebos)):
        raise ValueError("placebo_thresholds must all be finite")
    if np.any(placebos == thr):
        raise ValueError("placebo_thresholds must not contain the real threshold")

    arr = as_float_array(x, "x")
    arr, _, n_dropped = drop_nonfinite(arr, None)
    if arr.size == 0:
        raise ValueError("x contains no finite values")

    def _run(t: float) -> float:
        estimator = estimator_factory(float(t))
        if not callable(estimator):
            raise ValueError("estimator_factory must return a callable estimator")
        result = estimator(arr)
        if not isinstance(result, BunchingResult):
            raise ValueError(f"estimator must return a BunchingResult; got {type(result).__name__}")
        return _extract(result, statistic)

    observed = _run(thr)
    values = np.array([_run(t) for t in placebos], dtype=float)
    n_ge = int(np.sum(values >= observed))
    if add_one:
        pvalue = (1.0 + n_ge) / (1.0 + values.size)
    else:
        pvalue = n_ge / values.size

    stat_name = (
        statistic if isinstance(statistic, str) else getattr(statistic, "__name__", "custom")
    )
    return TestResult(
        method="bunching_placebo",
        statistic=float(observed),
        pvalue=float(pvalue),
        n=int(arr.size),
        details={
            "alternative": "greater",
            "threshold": thr,
            "statistic_name": stat_name,
            "placebo_thresholds": placebos,
            "placebo_values": values,
            "n_placebo": int(values.size),
            "n_at_least_observed": n_ge,
            "placebo_mean": float(np.mean(values)),
            "placebo_sd": float(np.std(values, ddof=1)) if values.size > 1 else float("nan"),
            "add_one": bool(add_one),
            "n_dropped": int(n_dropped),
        },
    )


def permutation_test(
    x: ArrayLike,
    groups: ArrayLike,
    statistic: Callable[[np.ndarray], float],
    n_perm: int = 999,
    seed: int | None = None,
) -> TestResult:
    """Label-permutation test for a group difference in any scalar statistic.

    Under the null the group labels are exchangeable, so the observed contrast is compared
    with the distribution of contrasts obtained by shuffling the labels (Fisher 1935, *The
    Design of Experiments*; Phipson and Smyth 2010, *Statistical Applications in Genetics
    and Molecular Biology* 9(1), Article 39, for the ``(1 + count) / (1 + n_perm)``
    p-value used here, which is never exactly zero).

    The contrast is

    * two groups: ``statistic(x[g1]) - statistic(x[g2])`` with the groups in sorted label
      order, compared two-sided on ``|T|``;
    * more than two groups: the range ``max_g statistic(x[g]) - min_g statistic(x[g])``,
      compared one-sided (``alternative = "greater"``).

    Parameters
    ----------
    x : array-like
        Values. Non-finite entries are dropped together with their labels.
    groups : array-like
        Group labels, same length as ``x``. Any hashable label type.
    statistic : callable
        ``statistic(values) -> float``, applied within each group. Anything goes: a mean, a
        normalised excess mass computed from a closure, a dispersion index.
    n_perm : int, default 999
        Number of label permutations.
    seed : int, optional
        Seed for ``numpy.random.default_rng``.

    Returns
    -------
    TestResult
        ``statistic`` is the observed contrast; ``details`` carries the per-group values,
        the group labels and sizes, and the permutation distribution summary.

    Raises
    ------
    ValueError
        If lengths differ, fewer than two distinct groups remain, ``n_perm < 1``, or the
        statistic returns a non-finite value on the observed data.
    """
    if not callable(statistic):
        raise ValueError("statistic must be callable: statistic(values) -> float")
    n_permutations = int(n_perm)
    if n_permutations < 1:
        raise ValueError(f"n_perm must be >= 1; got {n_perm!r}")

    arr = as_float_array(x, "x")
    labels = np.asarray(groups)
    if labels.ndim != 1:
        raise ValueError(f"groups must be 1-D; got shape {labels.shape}")
    if labels.size != arr.size:
        raise ValueError(f"groups must have the same length as x ({arr.size}); got {labels.size}")
    keep = np.isfinite(arr)
    n_dropped = int(np.sum(~keep))
    arr = arr[keep]
    labels = labels[keep]
    if arr.size == 0:
        raise ValueError("x contains no finite values")

    unique = np.unique(labels)
    if unique.size < 2:
        raise ValueError(f"permutation_test needs at least two distinct groups; got {unique.size}")

    def _contrast(lab: np.ndarray) -> float:
        values = np.array([float(statistic(arr[lab == g])) for g in unique], dtype=float)
        if unique.size == 2:
            return float(values[0] - values[1])
        return float(np.max(values) - np.min(values))

    observed = _contrast(labels)
    if not np.isfinite(observed):
        raise ValueError(
            "the statistic is not finite on the observed grouping; check that every group "
            "has enough observations for it"
        )

    rng = np.random.default_rng(seed)
    perm = np.empty(n_permutations, dtype=float)
    shuffled = labels.copy()
    for i in range(n_permutations):
        rng.shuffle(shuffled)
        perm[i] = _contrast(shuffled)

    two_sided = unique.size == 2
    if two_sided:
        n_ge = int(np.sum(np.abs(perm) >= abs(observed) - 1e-12))
        alternative = "two-sided"
    else:
        n_ge = int(np.sum(perm >= observed - 1e-12))
        alternative = "greater"
    pvalue = (1.0 + n_ge) / (1.0 + n_permutations)

    per_group = {str(g): float(statistic(arr[labels == g])) for g in unique}
    sizes = {str(g): int(np.sum(labels == g)) for g in unique}
    return TestResult(
        method="permutation_group_difference",
        statistic=float(observed),
        pvalue=float(pvalue),
        n=int(arr.size),
        details={
            "alternative": alternative,
            "groups": [str(g) for g in unique],
            "group_sizes": sizes,
            "per_group_statistic": per_group,
            "n_perm": n_permutations,
            "n_at_least_observed": n_ge,
            "permutation_mean": float(np.mean(perm)),
            "permutation_sd": float(np.std(perm, ddof=1)) if n_permutations > 1 else float("nan"),
            "seed": seed,
            "n_dropped": n_dropped,
        },
    )

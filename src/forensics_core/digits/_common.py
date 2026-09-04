"""Private helpers shared by the digit tests: input coercion, observation weights, the Kish
effective sample size and a chi-square goodness-of-fit wrapper.

Nothing here is part of the public contract (see INTERFACES.md); the public modules
re-implement no logic of their own for these chores so that weighting is handled uniformly.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats

#: Absolute tolerance used when a float must be integer-valued (terminal digits, denominators).
INTEGER_TOL = 1e-9


def as_float_array(x: ArrayLike, name: str = "x") -> np.ndarray:
    """Coerce ``x`` to a 1-D float64 array, raising ``ValueError`` on non-numeric input.

    Parameters
    ----------
    x : array-like
        Numbers, a numpy array or a pandas object (nullable pandas dtypes are converted with
        missing values mapped to ``nan``).
    name : str
        Name used in error messages.

    Returns
    -------
    numpy.ndarray
        1-D float64 array (a scalar becomes a length-1 array). Non-finite values are kept;
        callers decide whether to drop or reject them.
    """
    if hasattr(x, "to_numpy"):  # pandas Series / Index: handle nullable dtypes explicitly
        try:
            arr = x.to_numpy(dtype=float, na_value=np.nan)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    else:
        arr = np.asarray(x)
        if arr.dtype.kind == "b":
            raise ValueError(f"{name} must be numeric, not boolean")
        if arr.dtype.kind not in "iuf":
            try:
                arr = arr.astype(float)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric; got dtype {arr.dtype}") from exc
    arr = np.asarray(arr, dtype=float)
    if arr.ndim == 0:
        arr = arr.reshape(1)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
    return arr


def validate_weights(weights: ArrayLike | None, n: int) -> np.ndarray | None:
    """Validate observation weights against a sample of length ``n``.

    Weights must be 1-D, of length ``n``, finite, non-negative and not all zero. ``None`` is
    returned unchanged so callers can branch on the unweighted case.
    """
    if weights is None:
        return None
    w = as_float_array(weights, "weights")
    if w.size != n:
        raise ValueError(f"weights must have the same length as x ({n}); got {w.size}")
    if not np.all(np.isfinite(w)):
        raise ValueError("weights must be finite")
    if np.any(w < 0):
        raise ValueError("weights must be non-negative")
    if not np.any(w > 0):
        raise ValueError("weights must not all be zero")
    return w


def kish_effective_n(w: np.ndarray) -> float:
    """Kish (1965, *Survey Sampling*, Wiley, §8.2) effective sample size ``(Σw)² / Σw²``."""
    w = np.asarray(w, dtype=float)
    ss = float(np.sum(w * w))
    if ss <= 0:
        raise ValueError("cannot compute an effective sample size from all-zero weights")
    return float(np.sum(w)) ** 2 / ss


def chi2_goodness_of_fit(
    observed_prop: np.ndarray, expected_prop: np.ndarray, effective_n: float
) -> tuple[float, float, int]:
    """Pearson chi-square goodness of fit on proportions rescaled to ``effective_n``.

    With unit weights this is exactly ``scipy.stats.chisquare(observed, expected)``. With
    unequal weights the proportions are rescaled to the Kish effective sample size, which
    makes the p-value an approximation (it ignores the design-effect heterogeneity across
    cells that a Rao–Scott correction would capture).

    Returns
    -------
    (statistic, pvalue, df)
    """
    observed_prop = np.asarray(observed_prop, dtype=float)
    expected_prop = np.asarray(expected_prop, dtype=float)
    if observed_prop.shape != expected_prop.shape:
        raise ValueError("observed and expected proportions must have the same shape")
    if np.any(expected_prop <= 0):
        raise ValueError("expected proportions must all be positive")
    f_obs = observed_prop * effective_n
    f_exp = expected_prop * effective_n
    f_exp = f_exp * (f_obs.sum() / f_exp.sum())  # guard scipy's sum-equality check
    res = stats.chisquare(f_obs, f_exp)
    return float(res.statistic), float(res.pvalue), int(f_obs.size - 1)


def weighted_counts(idx: np.ndarray, w: np.ndarray | None, n_cells: int) -> np.ndarray:
    """Counts (``int64``) or weighted sums (``float64``) per cell index ``0..n_cells-1``."""
    if w is None:
        return np.bincount(idx, minlength=n_cells).astype(np.int64)
    return np.bincount(idx, weights=w, minlength=n_cells).astype(float)

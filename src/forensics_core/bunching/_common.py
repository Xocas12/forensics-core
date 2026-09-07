"""Private helpers for the bunching subpackage: input coercion, observation weights and the
Kish effective sample size.

These duplicate the small helpers other subpackages carry privately so that no subpackage
imports another's private module (the subpackages are developed concurrently). Nothing here
is part of the public contract in INTERFACES.md.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


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
        1-D float64 array (a scalar becomes a length-1 array). Non-finite values are kept so
        that callers can drop them and report ``n_dropped``.
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
    if ss <= 0.0:
        return 0.0
    return float(np.sum(w)) ** 2 / ss


def drop_nonfinite(
    x: np.ndarray, w: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray | None, int]:
    """Drop non-finite entries of ``x`` (and the matching weights); return the count dropped."""
    keep = np.isfinite(x)
    n_dropped = int(np.sum(~keep))
    if n_dropped == 0:
        return x, w, 0
    return x[keep], (None if w is None else w[keep]), n_dropped

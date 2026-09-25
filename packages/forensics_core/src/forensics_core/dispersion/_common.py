"""Private helpers shared by the dispersion modules: input coercion, non-finite handling and
the chi-square test for a variance.

Nothing here is part of the public contract (see INTERFACES.md).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def as_1d_float(x: ArrayLike, name: str = "x") -> np.ndarray:
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
        1-D float64 array. Non-finite values are kept; callers decide whether to drop them.
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


def drop_nonfinite(x: np.ndarray, name: str = "x") -> tuple[np.ndarray, int]:
    """Return ``(finite_values, n_dropped)``.

    Dropping breaks the spacing of a time series: two observations that were not adjacent
    become adjacent. Callers that treat the input as ordered in time (every function in
    :mod:`forensics_core.dispersion.underdispersion` does) must say so in their docstring.
    """
    finite = np.isfinite(x)
    n_dropped = int(x.size - finite.sum())
    return x[finite], n_dropped


def as_float_matrix(x: ArrayLike, name: str = "x") -> np.ndarray:
    """Coerce ``x`` to a 2-D float64 array (a 1-D input becomes a single row)."""
    if hasattr(x, "to_numpy"):
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
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be 1-D or 2-D; got shape {arr.shape}")
    return arr

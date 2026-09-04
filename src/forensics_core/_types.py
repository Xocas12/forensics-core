"""Shared result types. Every statistical routine in forensics_core returns one of these
(or a subclass) so results can be tabulated, serialised and compared across projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


def jsonable(v: Any) -> Any:
    """Recursively convert numpy scalars/arrays inside nested containers to plain Python."""
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [jsonable(x) for x in v]
    return v


@dataclass(frozen=True)
class TestResult:
    """Outcome of a single hypothesis test or estimator.

    Attributes
    ----------
    method : str
        Short machine-readable name, e.g. ``"benford_first_digit_chi2"``.
    statistic : float
        The test statistic or point estimate.
    pvalue : float | None
        Two-sided unless ``details["alternative"]`` says otherwise. ``None`` for
        estimators without a null distribution.
    n : int
        Number of observations actually used (after dropping non-finite / excluded values).
    details : dict
        Anything else worth keeping: expected/observed tables, thresholds, CIs, settings.
    """

    method: str
    statistic: float
    pvalue: float | None
    n: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        p = "n/a" if self.pvalue is None else f"{self.pvalue:.3g}"
        return f"{self.method}: stat={self.statistic:.4g} p={p} n={self.n}"

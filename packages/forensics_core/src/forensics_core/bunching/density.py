"""Polynomial counterfactual densities and excess mass ("bunching") at a threshold.

The estimator implemented here is the workhorse of the bunching literature:

* Chetty, R., J. N. Friedman, T. Olsen and L. Pistaferri (2011), "Adjustment Costs, Firm
  Responses, and Micro vs. Macro Labor Supply Elasticities: Evidence from Danish Tax
  Records", *Quarterly Journal of Economics* 126(2): 749-804 — the binned-count polynomial
  regression with dummies for the excluded window, the normalised excess mass, the
  integration constraint and the residual bootstrap.
* Saez, E. (2010), "Do Taxpayers Bunch at Kink Points?", *American Economic Journal:
  Economic Policy* 2(3): 180-212 — the original excess-mass-at-a-kink design.
* Kleven, H. J. and M. Waseem (2013), "Using Notches to Uncover Optimization Frictions and
  Structural Elasticities: Theory and Evidence from Pakistan", *Quarterly Journal of
  Economics* 128(2): 669-723 — notches, asymmetric windows and dominated regions.
* Kleven, H. J. (2016), "Bunching", *Annual Review of Economics* 8: 435-464 — survey and
  standardised notation.

Equation numbers are deliberately not quoted: the algebra below was reconstructed from the
standard description of the method rather than from the printed equations, so any citation
of a specific equation number should be confirmed against the primary texts.

All functions here are pure: no I/O, no globals, no plotting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from forensics_core._types import jsonable
from forensics_core.bunching._common import (
    as_float_array,
    drop_nonfinite,
    kish_effective_n,
    validate_weights,
)

__all__ = ["BunchingResult", "BunchingSide", "bin_around", "bunching_estimator"]

BunchingSide = Literal["below", "above"]

#: Relative tolerance used when snapping values onto the bin grid. A value that sits within
#: ``_GRID_TOL`` (relative) below a bin edge is treated as sitting *on* that edge, which
#: keeps binning stable under floating-point division (e.g. ``0.3 / 0.1 == 2.9999999999999996``).
_GRID_TOL = 1e-9

#: Guard against pathological ``bin_width`` values silently allocating gigabytes.
_MAX_BINS = 10_000_000


@dataclass(frozen=True)
class BunchingResult:
    """Result of a bunching estimation on binned counts.

    Attributes
    ----------
    centres : numpy.ndarray
        Bin centres, ascending. ``threshold`` is always a bin *edge*, so no centre ever
        coincides with it.
    counts : numpy.ndarray
        Observed (weighted) counts per bin.
    counterfactual : numpy.ndarray
        Fitted polynomial part of the regression, evaluated at every bin centre. Inside the
        excluded window this is the counterfactual density; outside it is the fitted value.
    excluded_mask : numpy.ndarray
        Boolean mask of the bins that carry their own dummy (the "excluded window").
    excess_mass : float
        ``B`` — summed (observed - counterfactual) over the excluded bins on the bunching
        side of the threshold. Positive when mass piles up there.
    missing_mass : float
        ``M`` — summed (counterfactual - observed) over the excluded bins on the other side.
        Positive when there is a hole. Note the sign convention: ``B`` and ``M`` are both
        reported as positive magnitudes so that mass conservation reads ``B == M``.
    normalized_excess : float
        ``b = B / (mean counterfactual count per bin over the excluded window)``.
    coefficients : numpy.ndarray
        Polynomial coefficients ``beta_0 ... beta_p`` in the scaled regressor
        ``z = (centre - threshold) / bin_width`` (lowest order first). The dummy
        coefficients are not returned; the fitted value in an excluded bin equals its
        observed count by construction.
    threshold : float
        The threshold the window was built around.
    settings : dict
        Everything else worth keeping: bin width, window sizes, sample bookkeeping
        (``n``, ``n_dropped``, ``effective_n``), integration-constraint diagnostics.
        Exposed as :attr:`details` too, which is the name INTERFACES.md uses.
    """

    centres: np.ndarray
    counts: np.ndarray
    counterfactual: np.ndarray
    excluded_mask: np.ndarray
    excess_mass: float
    missing_mass: float
    normalized_excess: float
    coefficients: np.ndarray
    threshold: float
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def details(self) -> dict[str, Any]:
        """Alias for :attr:`settings` (INTERFACES.md refers to ``details``)."""
        return self.settings

    @property
    def imbalance(self) -> float:
        """``|B - M|`` — zero when the excluded window conserves mass."""
        return abs(float(self.excess_mass) - float(self.missing_mass))

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"bunching at {self.threshold:g}: B={self.excess_mass:.4g} "
            f"M={self.missing_mass:.4g} b={self.normalized_excess:.4g}"
        )


def _snap(value: float, threshold: float, bin_width: float, mode: Literal["floor", "ceil"]) -> int:
    """Return the integer grid index of ``value`` on the threshold-aligned bin grid."""
    q = (value - threshold) / bin_width
    nudge = _GRID_TOL * max(1.0, abs(q))
    idx = np.floor(q + nudge) if mode == "floor" else np.ceil(q - nudge)
    if not np.isfinite(idx):
        raise ValueError(f"cannot place {value!r} on the bin grid around {threshold!r}")
    return int(idx)


def _check_threshold_and_width(threshold: float, bin_width: float) -> tuple[float, float]:
    thr = float(threshold)
    if not np.isfinite(thr):
        raise ValueError(f"threshold must be finite; got {threshold!r}")
    width = float(bin_width)
    if not np.isfinite(width) or width <= 0.0:
        raise ValueError(f"bin_width must be a positive finite number; got {bin_width!r}")
    return thr, width


def _grid_bounds(
    arr: np.ndarray,
    thr: float,
    width: float,
    lo: float | None,
    hi: float | None,
) -> tuple[int, int]:
    """Integer grid indices ``(lo_idx, hi_idx)`` of the first and one-past-last bin edge.

    Bin ``m`` spans ``[thr + m*width, thr + (m+1)*width)``. When ``lo``/``hi`` are ``None``
    the data range is used, expanded outwards to whole bins (and the upper end is expanded
    by a further bin when the maximum lands exactly on an edge, so that it stays inside the
    range). A user-supplied ``lo`` is snapped *down* and ``hi`` *up* onto the grid so that
    ``threshold`` remains an edge and the requested range is fully covered.
    """
    if lo is None:
        lo_idx = _snap(float(arr.min()), thr, width, "floor")
    else:
        lo_f = float(lo)
        if not np.isfinite(lo_f):
            raise ValueError(f"lo must be finite or None; got {lo!r}")
        lo_idx = _snap(lo_f, thr, width, "floor")
    if hi is None:
        hi_idx = _snap(float(arr.max()), thr, width, "floor") + 1
    else:
        hi_f = float(hi)
        if not np.isfinite(hi_f):
            raise ValueError(f"hi must be finite or None; got {hi!r}")
        hi_idx = _snap(hi_f, thr, width, "ceil")
    if hi_idx <= lo_idx:
        raise ValueError(
            f"empty binning range: lo={lo!r} must be strictly below hi={hi!r} "
            f"(grid indices {lo_idx} and {hi_idx} for bin_width={width!r})"
        )
    if hi_idx - lo_idx > _MAX_BINS:
        raise ValueError(
            f"binning range would need {hi_idx - lo_idx} bins (limit {_MAX_BINS}); "
            "widen bin_width or narrow lo/hi"
        )
    return lo_idx, hi_idx


def _histogram(
    arr: np.ndarray,
    wt: np.ndarray | None,
    thr: float,
    width: float,
    lo_idx: int,
    hi_idx: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Bin ``arr`` onto the threshold-aligned grid; return (centres, counts, n_out_of_range)."""
    n_bins = hi_idx - lo_idx
    centres = thr + width * (np.arange(lo_idx, hi_idx, dtype=float) + 0.5)
    q = (arr - thr) / width
    idx = np.floor(q + _GRID_TOL * np.maximum(1.0, np.abs(q))).astype(np.int64) - lo_idx
    inside = (idx >= 0) & (idx < n_bins)
    n_out = int(np.sum(~inside))
    counts = np.bincount(
        idx[inside],
        weights=None if wt is None else wt[inside],
        minlength=n_bins,
    ).astype(float)
    return centres, counts, n_out


def bin_around(
    x: ArrayLike,
    threshold: float,
    bin_width: float,
    lo: float | None = None,
    hi: float | None = None,
    weights: ArrayLike | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Bin ``x`` on a grid whose edges are aligned so that ``threshold`` is an edge.

    This alignment is what makes the bunching estimator well posed: no observation can
    straddle the threshold inside a bin, and every bin lies unambiguously below or above it
    (Chetty et al. 2011; Kleven 2016).

    Parameters
    ----------
    x : array-like
        1-D sample of the running variable. Non-finite values are dropped.
    threshold : float
        The value that must fall on a bin edge.
    bin_width : float
        Strictly positive bin width.
    lo, hi : float, optional
        Range to bin over, half-open ``[lo, hi)``. ``None`` (default) uses the data range
        expanded outwards to whole bins. Supplied values are snapped onto the grid (``lo``
        down, ``hi`` up) so that ``threshold`` stays an edge. Observations outside the range
        are silently excluded from the histogram (they are still counted in ``n`` by
        :func:`bunching_estimator`, which reports them in ``settings["n_out_of_range"]``).
    weights : array-like, optional
        Observation weights (e.g. precinct size). Counts become sums of weights.

    Returns
    -------
    centres : numpy.ndarray
        Bin centres, ascending.
    counts : numpy.ndarray
        (Weighted) counts, same length as ``centres``.

    Raises
    ------
    ValueError
        If ``bin_width`` is not positive and finite, ``threshold``/``lo``/``hi`` are not
        finite, the range is empty, the weights are invalid, or ``x`` has no finite value.

    Notes
    -----
    Bins are half-open on the right: an observation exactly equal to ``threshold`` falls in
    the bin ``[threshold, threshold + bin_width)``, i.e. it counts as *above* the threshold.
    A relative tolerance of ``1e-9`` is applied before flooring so that values that are one
    ulp below an edge are assigned to the upper bin.

    Examples
    --------
    >>> centres, counts = bin_around([0.3, 1.2, 1.7], threshold=1.0, bin_width=0.5)
    >>> centres
    array([0.25, 0.75, 1.25, 1.75])
    >>> counts
    array([1., 0., 1., 1.])
    """
    thr, width = _check_threshold_and_width(threshold, bin_width)
    arr = as_float_array(x, "x")
    wt = validate_weights(weights, arr.size)
    arr, wt, _ = drop_nonfinite(arr, wt)
    if arr.size == 0:
        raise ValueError("x contains no finite values; nothing to bin")
    lo_idx, hi_idx = _grid_bounds(arr, thr, width, lo, hi)
    centres, counts, _ = _histogram(arr, wt, thr, width, lo_idx, hi_idx)
    return centres, counts


def _window_masks(
    thr: float,
    width: float,
    lo_idx: int,
    hi_idx: int,
    exclude_below: float,
    exclude_above: float,
) -> tuple[np.ndarray, int, int]:
    """Boolean mask of the excluded window plus the number of bins excluded on each side.

    The requested half-widths are rounded *down* to whole bins, so the excluded window never
    reaches further from the threshold than asked for.
    """
    if not np.isfinite(exclude_below) or exclude_below < 0:
        raise ValueError(f"exclude_below must be finite and >= 0; got {exclude_below!r}")
    if not np.isfinite(exclude_above) or exclude_above < 0:
        raise ValueError(f"exclude_above must be finite and >= 0; got {exclude_above!r}")
    n_below = int(np.floor(exclude_below / width + _GRID_TOL))
    n_above = int(np.floor(exclude_above / width + _GRID_TOL))
    if n_below + n_above == 0:
        raise ValueError(
            "the excluded window is empty: exclude_below and exclude_above are both smaller "
            f"than one bin (bin_width={width!r})"
        )
    if -n_below < lo_idx or n_above > hi_idx:
        raise ValueError(
            f"the excluded window [{thr - n_below * width:g}, {thr + n_above * width:g}) "
            f"extends beyond the binned range [{thr + lo_idx * width:g}, "
            f"{thr + hi_idx * width:g}); widen lo/hi or shrink the window"
        )
    grid = np.arange(lo_idx, hi_idx)
    excluded = (grid >= -n_below) & (grid < n_above)
    return excluded, n_below, n_above


def _fit_counts(
    z: np.ndarray, counts: np.ndarray, excluded: np.ndarray, poly_degree: int
) -> tuple[np.ndarray, np.ndarray]:
    """OLS of ``counts`` on a polynomial in ``z`` plus one dummy per excluded bin.

    Returns the polynomial coefficients in the ``z`` basis (lowest order first) and the
    fitted polynomial part evaluated at every bin.

    The regression is run in the rescaled variable ``u = z / max|z|`` so that the Vandermonde
    matrix stays well conditioned at ``poly_degree = 7``; the coefficients are converted back
    to the ``z`` basis afterwards, while the counterfactual is evaluated in the ``u`` basis.
    """
    scale = float(np.max(np.abs(z)))
    if scale <= 0.0:
        scale = 1.0
    u = z / scale
    vander = np.vander(u, poly_degree + 1, increasing=True)
    n_excluded = int(np.count_nonzero(excluded))
    if n_excluded:
        dummies = np.zeros((z.size, n_excluded), dtype=float)
        dummies[np.flatnonzero(excluded), np.arange(n_excluded)] = 1.0
        design = np.hstack([vander, dummies])
    else:  # pragma: no cover - guarded by _window_masks
        design = vander
    beta, *_ = np.linalg.lstsq(design, counts, rcond=None)
    coef_u = beta[: poly_degree + 1]
    counterfactual = vander @ coef_u
    coef_z = coef_u / scale ** np.arange(poly_degree + 1, dtype=float)
    return coef_z, counterfactual


def _masses(
    counts: np.ndarray,
    counterfactual: np.ndarray,
    below: np.ndarray,
    above: np.ndarray,
    bunching_side: str,
) -> tuple[float, float]:
    """Excess mass ``B`` and missing mass ``M``, both as positive-when-expected magnitudes."""
    gap = counts - counterfactual
    if bunching_side == "below":
        return float(np.sum(gap[below])), float(-np.sum(gap[above]))
    return float(np.sum(gap[above])), float(-np.sum(gap[below]))


def _estimate_from_counts(
    z: np.ndarray,
    counts: np.ndarray,
    excluded: np.ndarray,
    below: np.ndarray,
    above: np.ndarray,
    source: np.ndarray,
    poly_degree: int,
    bunching_side: str,
    integration_constraint: bool,
    max_iter: int,
    tol: float,
) -> dict[str, Any]:
    """Core estimator on binned counts; shared by the public estimator and the bootstrap."""
    coef, counterfactual = _fit_counts(z, counts, excluded, poly_degree)
    excess, missing = _masses(counts, counterfactual, below, above, bunching_side)
    shift = 1.0
    n_iter = 0
    converged = True
    stop_reason = "not requested"

    if integration_constraint:
        if not np.any(source):
            raise ValueError(
                "integration_constraint=True needs bins outside the excluded window on the "
                "side the bunchers come from; widen lo/hi"
            )
        converged = False
        stop_reason = "max_iter reached"
        previous = excess
        for it in range(1, int(max_iter) + 1):
            n_iter = it
            adjusted = counts.copy()
            adjusted[source] = adjusted[source] * shift
            coef, counterfactual = _fit_counts(z, adjusted, excluded, poly_degree)
            excess, missing = _masses(counts, counterfactual, below, above, bunching_side)
            denom = float(np.sum(counterfactual[source]))
            if denom <= 0.0:
                converged = False
                stop_reason = "counterfactual mass in the source region is non-positive"
                break
            new_shift = 1.0 + excess / denom
            if not np.isfinite(new_shift) or new_shift <= 0.0:
                converged = False
                stop_reason = "implied shift factor is non-positive"
                break
            if it > 1 and abs(excess - previous) <= tol * max(1.0, abs(excess)):
                converged = True
                stop_reason = "|B_t - B_{t-1}| <= tol * max(1, |B_t|)"
                shift = new_shift
                break
            previous = excess
            shift = new_shift

    mean_cf = float(np.mean(counterfactual[excluded]))
    if not np.isfinite(mean_cf) or mean_cf <= 0.0:
        raise ValueError(
            "the fitted counterfactual is non-positive on average inside the excluded "
            f"window (mean = {mean_cf!r}); the polynomial fit is degenerate — check "
            "poly_degree, the binning range and the window widths"
        )
    return {
        "coefficients": coef,
        "counterfactual": counterfactual,
        "excess_mass": excess,
        "missing_mass": missing,
        "normalized_excess": excess / mean_cf,
        "mean_counterfactual_excluded": mean_cf,
        "shift_factor": float(shift),
        "n_iter": int(n_iter),
        "converged": bool(converged),
        "stop_reason": stop_reason,
    }


def bunching_estimator(
    x: ArrayLike,
    threshold: float,
    *,
    bin_width: float,
    exclude_below: float,
    exclude_above: float,
    poly_degree: int = 7,
    lo: float | None = None,
    hi: float | None = None,
    integration_constraint: bool = False,
    max_iter: int = 50,
    weights: ArrayLike | None = None,
    bunching_side: BunchingSide = "below",
    tol: float = 1e-6,
) -> BunchingResult:
    r"""Estimate excess mass at ``threshold`` against a polynomial counterfactual.

    The sample is binned on a grid aligned so that ``threshold`` is an edge
    (:func:`bin_around`), and the bin counts are regressed on a polynomial in the bin centre
    plus one dummy per bin of the *excluded window* — the bins close enough to the threshold
    that they may be contaminated by bunching:

    .. math::

        c_j = \sum_{k=0}^{p} \beta_k z_j^k
              + \sum_{i \in \text{excluded}} \gamma_i \mathbf{1}[j = i] + \varepsilon_j,
        \qquad z_j = (\text{centre}_j - \text{threshold}) / \text{bin\_width}

    The counterfactual is the polynomial part alone, :math:`\hat c_j^0 = \sum_k \hat\beta_k
    z_j^k`. Because the excluded bins are saturated by their own dummies, the polynomial is
    identified purely by the bins outside the window — this is exactly the Chetty, Friedman,
    Olsen and Pistaferri (2011) specification, also used by Saez (2010) and surveyed in
    Kleven (2016).

    Excess and missing mass are then

    .. math::

        B = \sum_{j \in \text{excluded, bunching side}} (c_j - \hat c_j^0), \qquad
        M = \sum_{j \in \text{excluded, other side}} (\hat c_j^0 - c_j),

    i.e. both are reported as positive magnitudes so that mass conservation reads
    :math:`B = M`, and the normalised excess mass is

    .. math:: b = B \,/\, \overline{\hat c^0_{\text{excluded}}}

    the excess expressed in "bins' worth of counterfactual observations" (Chetty et al.
    2011). The denominator here is the mean counterfactual count per bin over the *whole*
    excluded window, as fixed by INTERFACES.md; some implementations average only over the
    bunching side, which changes ``b`` (but not ``B``) — check before comparing numbers
    across papers.

    Parameters
    ----------
    x : array-like
        1-D sample of the running variable (plan fulfilment, vote share, EPS surprise, ...).
        Non-finite values are dropped and counted in ``settings["n_dropped"]``.
    threshold : float
        Location of the notch/kink. Becomes a bin edge.
    bin_width : float
        Bin width, strictly positive.
    exclude_below, exclude_above : float
        Half-widths of the excluded window, in units of ``x``. Rounded down to whole bins;
        at least one bin in total is required.
    poly_degree : int, default 7
        Degree of the counterfactual polynomial. Chetty et al. (2011) use 7 for their
        baseline; the estimate should be reported for a range of degrees.
    lo, hi : float, optional
        Binning range, see :func:`bin_around`. A tight range around the threshold is usual:
        the polynomial only has to describe the local shape of the density.
    integration_constraint : bool, default False
        Apply the Chetty et al. (2011) integration constraint (see Notes).
    max_iter : int, default 50
        Iteration cap for the integration constraint.
    weights : array-like, optional
        Observation weights; counts become sums of weights and ``B``, ``M`` are in weight
        units. ``settings["effective_n"]`` reports the Kish effective sample size.
    bunching_side : {"below", "above"}, default "below"
        Which side of the threshold the *excess* is expected on. ``"below"`` is the classic
        tax kink/notch (the reward lies below the threshold, agents bunch just under it).
        ``"above"`` is the bonus notch (a bonus is paid iff the reported value reaches the
        threshold, so agents pile up just at or above it). This keyword is an addition to
        the INTERFACES.md signature; its default reproduces the contracted behaviour.
    tol : float, default 1e-6
        Relative convergence tolerance for the integration constraint.

    Returns
    -------
    BunchingResult

    Raises
    ------
    ValueError
        On any invalid input: non-positive ``bin_width``, non-finite ``threshold``, an empty
        excluded window, a window reaching outside the binned range, ``poly_degree`` too
        large for the number of free bins, invalid weights, or a degenerate counterfactual.

    Notes
    -----
    **Integration constraint.** The counterfactual density must integrate to the same total
    mass as the observed one: the bunchers came from somewhere. Chetty et al. (2011) impose
    this by shifting the observed counts on the side the bunchers were drawn from (above the
    excluded window when ``bunching_side="below"``, below it otherwise) up by the factor

    .. math:: 1 + B \big/ \sum_{j \in \text{source}} \hat c_j^0

    re-fitting, and repeating until the estimate settles. The iteration here stops when
    ``|B_t - B_{t-1}| <= tol * max(1, |B_t|)`` and is capped at ``max_iter``; the number of
    iterations, the final shift factor, whether it converged and why it stopped are recorded
    in ``settings``. Raising the counterfactual on the source side pushes ``B`` down and
    ``M`` up, so the fixed point is where the two masses meet — check ``result.imbalance``.

    **Interpretation.** ``b`` is an estimate of excess mass, not of an elasticity. Mapping it
    to a behavioural elasticity needs the budget-set geometry (Saez 2010 for kinks; Kleven
    and Waseem 2013 for notches) and is deliberately out of scope here.
    """
    thr, width = _check_threshold_and_width(threshold, bin_width)
    degree = int(poly_degree)
    if degree < 0:
        raise ValueError(f"poly_degree must be >= 0; got {poly_degree!r}")
    if int(max_iter) < 1:
        raise ValueError(f"max_iter must be >= 1; got {max_iter!r}")
    if not np.isfinite(tol) or tol <= 0:
        raise ValueError(f"tol must be a positive finite number; got {tol!r}")
    if bunching_side not in ("below", "above"):
        raise ValueError(f"bunching_side must be 'below' or 'above'; got {bunching_side!r}")

    arr = as_float_array(x, "x")
    n_total = int(arr.size)
    wt = validate_weights(weights, n_total)
    arr, wt, n_dropped = drop_nonfinite(arr, wt)
    if arr.size == 0:
        raise ValueError("x contains no finite values")

    lo_idx, hi_idx = _grid_bounds(arr, thr, width, lo, hi)
    centres, counts, n_out = _histogram(arr, wt, thr, width, lo_idx, hi_idx)
    if not np.any(counts > 0):
        raise ValueError(
            "no observation falls inside the binning range "
            f"[{thr + lo_idx * width:g}, {thr + hi_idx * width:g})"
        )
    excluded, n_below, n_above = _window_masks(
        thr, width, lo_idx, hi_idx, exclude_below, exclude_above
    )
    n_free = int(np.count_nonzero(~excluded))
    if n_free < degree + 1:
        raise ValueError(
            f"poly_degree={degree} needs at least {degree + 1} bins outside the excluded "
            f"window; only {n_free} are available. Widen lo/hi, widen bin_width, or lower "
            "poly_degree."
        )

    grid = np.arange(lo_idx, hi_idx)
    below = excluded & (grid < 0)
    above = excluded & (grid >= 0)
    source = (grid >= n_above) if bunching_side == "below" else (grid < -n_below)
    z = (centres - thr) / width

    fit = _estimate_from_counts(
        z,
        counts,
        excluded,
        below,
        above,
        source,
        degree,
        bunching_side,
        bool(integration_constraint),
        int(max_iter),
        float(tol),
    )

    settings: dict[str, Any] = {
        "bin_width": width,
        "lo": thr + lo_idx * width,
        "hi": thr + hi_idx * width,
        "n_bins": int(centres.size),
        "poly_degree": degree,
        "exclude_below": float(exclude_below),
        "exclude_above": float(exclude_above),
        "n_excluded_below": n_below,
        "n_excluded_above": n_above,
        "bunching_side": bunching_side,
        "integration_constraint": bool(integration_constraint),
        "max_iter": int(max_iter),
        "tol": float(tol),
        "n_iter": fit["n_iter"],
        "converged": fit["converged"],
        "stop_reason": fit["stop_reason"],
        "shift_factor": fit["shift_factor"],
        "mean_counterfactual_excluded": fit["mean_counterfactual_excluded"],
        "imbalance": abs(fit["excess_mass"] - fit["missing_mass"]),
        "n": int(arr.size),
        "n_dropped": int(n_dropped),
        "n_out_of_range": int(n_out),
        "n_in_window": float(np.sum(counts[excluded])),
        "weighted": wt is not None,
        "effective_n": float(arr.size) if wt is None else kish_effective_n(wt),
    }
    return BunchingResult(
        centres=centres,
        counts=counts,
        counterfactual=fit["counterfactual"],
        excluded_mask=excluded,
        excess_mass=fit["excess_mass"],
        missing_mass=fit["missing_mass"],
        normalized_excess=fit["normalized_excess"],
        coefficients=fit["coefficients"],
        threshold=thr,
        settings=settings,
    )


def _refit_result(result: BunchingResult, counts: np.ndarray) -> dict[str, Any]:
    """Re-run the core estimator on a new count vector with ``result``'s settings.

    Used by :mod:`forensics_core.bunching.inference` for the residual bootstrap, which
    perturbs bin counts rather than units.
    """
    st = result.settings
    width = float(st["bin_width"])
    thr = float(result.threshold)
    z = (result.centres - thr) / width
    excluded = np.asarray(result.excluded_mask, dtype=bool)
    below = excluded & (result.centres < thr)
    above = excluded & (result.centres > thr)
    n_below = int(st["n_excluded_below"])
    n_above = int(st["n_excluded_above"])
    if st["bunching_side"] == "below":
        source = result.centres > thr + n_above * width
    else:
        source = result.centres < thr - n_below * width
    return _estimate_from_counts(
        z,
        np.asarray(counts, dtype=float),
        excluded,
        below,
        above,
        source,
        int(st["poly_degree"]),
        str(st["bunching_side"]),
        bool(st["integration_constraint"]),
        int(st["max_iter"]),
        float(st["tol"]),
    )

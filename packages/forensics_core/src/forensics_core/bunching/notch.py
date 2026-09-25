"""Notches, kinks, and the search for them.

A **kink** is a discontinuity in the *slope* of the payoff function (the marginal reward
changes at the threshold); a **notch** is a discontinuity in its *level* (a lump sum is won
or lost by crossing the threshold). Kinks produce modest bunching; notches produce sharp
bunching plus a *dominated region* on the other side — a range in which no optimising agent
should ever be observed, because a small move to the threshold raises the payoff and costs
almost nothing. The size of the hole in the dominated region is what identifies optimisation
frictions in Kleven and Waseem (2013).

References
----------
* Saez, E. (2010), "Do Taxpayers Bunch at Kink Points?", *American Economic Journal:
  Economic Policy* 2(3): 180-212.
* Chetty, R., J. N. Friedman, T. Olsen and L. Pistaferri (2011), "Adjustment Costs, Firm
  Responses, and Micro vs. Macro Labor Supply Elasticities", *Quarterly Journal of
  Economics* 126(2): 749-804.
* Kleven, H. J. and M. Waseem (2013), "Using Notches to Uncover Optimization Frictions and
  Structural Elasticities: Theory and Evidence from Pakistan", *Quarterly Journal of
  Economics* 128(2): 669-723.
* Kleven, H. J. (2016), "Bunching", *Annual Review of Economics* 8: 435-464.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from forensics_core.bunching.density import BunchingResult, bunching_estimator

__all__ = [
    "SCAN_COLUMNS",
    "Kink",
    "Notch",
    "estimate_kink",
    "estimate_notch",
    "scan_candidate_notches",
]

NotchSide = Literal["above", "below"]

#: Column order of the :func:`scan_candidate_notches` table, fixed by INTERFACES.md.
SCAN_COLUMNS = [
    "threshold",
    "excess_mass",
    "missing_mass",
    "normalized_excess",
    "n_in_window",
    "side",
]


def _check_threshold(value: float, name: str = "threshold") -> float:
    try:
        thr = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a real number; got {value!r}") from exc
    if not np.isfinite(thr):
        raise ValueError(f"{name} must be finite; got {value!r}")
    return thr


def _check_side(side: str) -> str:
    if side not in ("above", "below"):
        raise ValueError(f"side must be 'above' or 'below'; got {side!r}")
    return side


@dataclass(frozen=True)
class Notch:
    """A discontinuous jump in the payoff at ``threshold``.

    Parameters
    ----------
    threshold : float
        Where the payoff jumps.
    side : {"above", "below"}, default "above"
        Where the *reward* lies, i.e. the side agents want to be on. ``"above"`` is the
        bonus notch of a plan-fulfilment system (a bonus is paid iff reported output reaches
        100% of plan), so mass piles up at and just above the threshold and the hole sits
        just below it. ``"below"`` is the classic tax notch (Kleven and Waseem 2013): a
        higher average tax rate applies above the threshold, so mass piles up just below and
        the hole sits just above.
    label : str, default ""
        Free-text description, carried into ``settings["notch_label"]``.

    Raises
    ------
    ValueError
        If ``threshold`` is not finite or ``side`` is not one of the two allowed values.
    """

    threshold: float
    side: NotchSide = "above"
    label: str = ""

    def __post_init__(self) -> None:
        _check_threshold(self.threshold)
        _check_side(self.side)

    @property
    def dominated_side(self) -> str:
        """The side on which no optimising agent should be observed."""
        return "below" if self.side == "above" else "above"


@dataclass(frozen=True)
class Kink:
    """A discontinuous change in the *slope* of the payoff at ``threshold``.

    Parameters
    ----------
    threshold : float
        Where the marginal reward changes.
    label : str, default ""
        Free-text description, carried into ``settings["kink_label"]``.
    """

    threshold: float
    label: str = ""

    def __post_init__(self) -> None:
        _check_threshold(self.threshold)


def estimate_notch(
    x: ArrayLike,
    notch: Notch,
    *,
    bin_width: float,
    exclude_below: float,
    exclude_above: float,
    poly_degree: int = 7,
    weights: ArrayLike | None = None,
    **kw: Any,
) -> BunchingResult:
    """Estimate bunching at a notch with an asymmetric excluded window.

    The window is asymmetric on purpose: the bunching region and the dominated region have
    no reason to be the same width. For a bonus notch (``notch.side == "above"``) the excess
    sits at and just above the threshold while the hole sits just below it; for a tax notch
    (``notch.side == "below"``) it is the other way round (Kleven and Waseem 2013).

    Parameters
    ----------
    x : array-like
        Running variable.
    notch : Notch
        The notch to estimate at.
    bin_width, exclude_below, exclude_above, poly_degree, weights
        Passed to :func:`~forensics_core.bunching.density.bunching_estimator`.
    **kw
        Further keyword arguments for
        :func:`~forensics_core.bunching.density.bunching_estimator` (``lo``, ``hi``,
        ``integration_constraint``, ``max_iter``, ``tol``).

    Returns
    -------
    BunchingResult
        With ``settings["dominated_region"]`` set to the half-open interval in which no
        optimising agent should be observed, plus ``settings["notch_label"]`` and
        ``settings["side"]``.

    Notes
    -----
    INTERFACES.md fixes ``details["dominated_region"] = (threshold, threshold +
    exclude_above)``. That is correct only for a notch whose reward lies *below* the
    threshold (the tax notch): the dominated region is always on the side agents do **not**
    want to be on, adjacent to the threshold. Since the contracted default is
    ``side="above"`` (reward above, e.g. "bonus paid iff plan >= 100%"), taking the formula
    literally would place the dominated region on the rewarded side, where bunching — not a
    hole — is expected. This implementation therefore returns
    ``(threshold - exclude_below, threshold)`` when ``side == "above"`` and the contracted
    ``(threshold, threshold + exclude_above)`` when ``side == "below"``. The deviation is
    reported rather than patched into INTERFACES.md.
    """
    if not isinstance(notch, Notch):
        raise ValueError(f"notch must be a Notch instance; got {type(notch).__name__}")
    side = _check_side(notch.side)
    thr = _check_threshold(notch.threshold)
    kw.setdefault("bunching_side", side)
    result = bunching_estimator(
        x,
        thr,
        bin_width=bin_width,
        exclude_below=exclude_below,
        exclude_above=exclude_above,
        poly_degree=poly_degree,
        weights=weights,
        **kw,
    )
    if side == "above":
        dominated = (thr - float(exclude_below), thr)
    else:
        dominated = (thr, thr + float(exclude_above))
    settings = {
        **result.settings,
        "specification": "notch",
        "side": side,
        "dominated_region": dominated,
        "dominated_side": notch.dominated_side,
        "notch_label": notch.label,
    }
    return replace(result, settings=settings)


def estimate_kink(
    x: ArrayLike,
    kink: Kink,
    *,
    bin_width: float,
    exclude_halfwidth: float,
    poly_degree: int = 7,
    weights: ArrayLike | None = None,
    **kw: Any,
) -> BunchingResult:
    """Estimate bunching at a kink with a symmetric excluded window.

    A kink changes the marginal reward, not its level, so there is no dominated region and
    no reason for the window to be asymmetric: the same half-width is used on both sides
    (Saez 2010; Chetty et al. 2011).

    Parameters
    ----------
    x : array-like
        Running variable.
    kink : Kink
        The kink to estimate at.
    exclude_halfwidth : float
        Half-width of the symmetric excluded window, in units of ``x``.
    bin_width, poly_degree, weights, **kw
        As in :func:`estimate_notch`. ``bunching_side`` defaults to ``"below"`` (the
        convex-kink case: the marginal reward falls when the threshold is crossed, so agents
        stop just under it); pass ``bunching_side="above"`` for a concave kink.

    Returns
    -------
    BunchingResult
        With ``settings["specification"] = "kink"`` and ``settings["kink_label"]``.
    """
    if not isinstance(kink, Kink):
        raise ValueError(f"kink must be a Kink instance; got {type(kink).__name__}")
    thr = _check_threshold(kink.threshold)
    half = float(exclude_halfwidth)
    if not np.isfinite(half) or half <= 0:
        raise ValueError(f"exclude_halfwidth must be a positive finite number; got {half!r}")
    result = bunching_estimator(
        x,
        thr,
        bin_width=bin_width,
        exclude_below=half,
        exclude_above=half,
        poly_degree=poly_degree,
        weights=weights,
        **kw,
    )
    settings = {
        **result.settings,
        "specification": "kink",
        "exclude_halfwidth": half,
        "kink_label": kink.label,
    }
    return replace(result, settings=settings)


def scan_candidate_notches(
    x: ArrayLike,
    candidates: Sequence[float],
    *,
    bin_width: float,
    exclude_below: float,
    exclude_above: float,
    poly_degree: int = 7,
    weights: ArrayLike | None = None,
    side: NotchSide = "above",
    lo: float | None = None,
    hi: float | None = None,
    **kw: Any,
) -> pd.DataFrame:
    """**Find the notch.** Rank candidate thresholds by the excess mass sitting at them.

    This is the first-class operation of the programme: the working hypothesis is that
    distortion concentrates where the incentive function jumps, so the analytic move is to
    write down every threshold at which someone is paid, scan them all, and let the data say
    which one the reported numbers cluster at. The four canonical notches this library was
    built for are

    1. **100% plan fulfilment** — a bonus is paid iff reported output reaches the plan, so
       reported fulfilment piles up at and just above 100.
    2. **Round vote-share / turnout integers** — 50%, 70%, 95%, 100%: targets handed down to
       local officials, and the object of the integer-percentage literature (Kobak,
       Shpilkin and Pshenichnikov 2016, *Annals of Applied Statistics*).
    3. **Analyst-consensus EPS at zero surprise** — firms manage earnings to meet or just
       beat the consensus, which puts a spike at surprise = 0 and a hole just below it
       (Burgstahler and Dichev 1997, *Journal of Accounting and Economics*; Degeorge, Patel
       and Zeckhauser 1999, *Journal of Business*).
    4. **Provincial growth targets** — a headline target (e.g. "growth of 7%") that
       subordinate units are graded against, so reported growth bunches at the target.

    Parameters
    ----------
    x : array-like
        Running variable.
    candidates : sequence of float
        Thresholds to test. Must be finite and non-empty; duplicates are rejected.
    bin_width, exclude_below, exclude_above, poly_degree, weights, lo, hi, **kw
        Passed to :func:`~forensics_core.bunching.density.bunching_estimator`. Each
        candidate gets its own threshold-aligned grid, so the grids differ by less than one
        bin between candidates; pass explicit ``lo``/``hi`` if you want them comparable to
        the bin.
    side : {"above", "below"}, default "above"
        Where the reward lies, applied to every candidate (see :class:`Notch`).

    Returns
    -------
    pandas.DataFrame
        One row per candidate with columns ``[threshold, excess_mass, missing_mass,
        normalized_excess, n_in_window, side]``, sorted by ``normalized_excess``
        descending. ``n_in_window`` is the (weighted) number of observations inside the
        excluded window. The index is reset to 0..k-1 so that row 0 is the best candidate.

    Raises
    ------
    ValueError
        If ``candidates`` is empty, contains a non-finite or duplicated value, or if any
        single candidate cannot be estimated (the message names the offending candidate).

    Notes
    -----
    The ranking is descriptive, not a test: with many candidates the top one is selected on
    the same data it is measured on. Confirm the winner with
    :func:`forensics_core.bunching.inference.placebo_test` (are neighbouring, incentive-free
    thresholds as extreme?) and
    :func:`forensics_core.bunching.inference.bootstrap_bunching` (is the excess mass
    distinguishable from zero?), and prefer candidates named in advance by the incentive
    scheme over candidates found by scanning.
    """
    _check_side(side)
    cand = np.asarray(list(candidates), dtype=float)
    if cand.ndim != 1 or cand.size == 0:
        raise ValueError("candidates must be a non-empty 1-D sequence of thresholds")
    if not np.all(np.isfinite(cand)):
        raise ValueError("candidates must all be finite")
    if np.unique(cand).size != cand.size:
        raise ValueError("candidates must not contain duplicates")

    rows: list[dict[str, Any]] = []
    for candidate in cand:
        threshold = float(candidate)
        try:
            result = bunching_estimator(
                x,
                threshold,
                bin_width=bin_width,
                exclude_below=exclude_below,
                exclude_above=exclude_above,
                poly_degree=poly_degree,
                weights=weights,
                lo=lo,
                hi=hi,
                bunching_side=side,
                **kw,
            )
        except ValueError as exc:
            raise ValueError(
                f"candidate threshold {threshold!r} could not be estimated: {exc}"
            ) from exc
        rows.append(
            {
                "threshold": threshold,
                "excess_mass": result.excess_mass,
                "missing_mass": result.missing_mass,
                "normalized_excess": result.normalized_excess,
                "n_in_window": float(result.settings["n_in_window"]),
                "side": side,
            }
        )
    table = pd.DataFrame(rows, columns=SCAN_COLUMNS)
    table = table.sort_values("normalized_excess", ascending=False, kind="stable")
    return table.reset_index(drop=True)

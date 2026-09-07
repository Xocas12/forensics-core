"""Excess of integer percentages, after Kobak, D., Shpilkin, S. and Pshenichnikov, M. I.
(2016), "Integer percentages as electoral falsification fingerprints", *Annals of Applied
Statistics* 10(1): 54-73.

The fingerprint: when a result is manufactured to hit a target ("give him 65%"), the
reported percentage lands exactly on an integer far more often than binomial sampling noise
allows. The test therefore needs the denominators as well as the percentages, because the
null is not "percentages are smooth" but "each unit's numerator is a binomial draw at the
observed share, so the percentage inherits a spread of roughly
``100 * sqrt(p (1 - p) / d)`` percentage points". Small units are excluded: with a
denominator of 20 every percentage is a multiple of 5, so integer percentages there are
arithmetic, not fraud (Kobak et al. 2016, section 2).

All functions here are pure: no I/O, no globals, no plotting. Randomness flows through the
``seed`` argument only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy import stats

from forensics_core._types import TestResult, jsonable
from forensics_core.digits._common import (
    INTEGER_TOL,
    as_float_array,
    kish_effective_n,
    validate_weights,
)

_KSP_CITATION = (
    "Kobak, D., Shpilkin, S. and Pshenichnikov, M. I. (2016), 'Integer percentages as "
    "electoral falsification fingerprints', Annals of Applied Statistics 10(1): 54-73."
)


def _as_generator(seed: int | np.random.Generator | np.random.SeedSequence | None):
    """Turn ``seed`` into a ``numpy.random.Generator`` (HARD RULE: no legacy global RNG)."""
    if isinstance(seed, np.random.Generator):
        return seed
    return np.random.default_rng(seed)


def percentage(numerator: ArrayLike, denominator: ArrayLike) -> np.ndarray:
    """Percentage ``100 * numerator / denominator``, with ``nan`` where it is undefined.

    Parameters
    ----------
    numerator, denominator : array-like
        1-D numeric arrays of the same length.

    Returns
    -------
    numpy.ndarray
        ``float64`` percentages; entries whose denominator is zero, negative or non-finite,
        or whose numerator is non-finite, are ``nan``.

    Raises
    ------
    ValueError
        If the two inputs have different lengths, or are not 1-D numeric.

    Examples
    --------
    >>> percentage([50, 1, 3], [200, 0, 4]).tolist()
    [25.0, nan, 75.0]
    """
    num = as_float_array(numerator, "numerator")
    den = as_float_array(denominator, "denominator")
    if num.size != den.size:
        raise ValueError(
            f"numerator and denominator must have the same length; got {num.size} and {den.size}"
        )
    ok = np.isfinite(num) & np.isfinite(den) & (den > 0)
    out = np.full(num.size, np.nan)
    out[ok] = 100.0 * num[ok] / den[ok]
    return out


def percentage_histogram(
    pct: ArrayLike,
    bin_width: float = 0.1,
    weights: ArrayLike | None = None,
    lo: float = 0.0,
    hi: float = 100.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Histogram of percentages on bins centred so that every integer is a bin centre.

    With ``bin_width = 0.1`` the edges fall at ``k * 0.1 - 0.05``, so the bin centred on
    50.0 collects ``[49.95, 50.05)`` (Kobak et al. 2016 plot exactly this histogram; a
    histogram whose edges sat on the integers would split the spike in half).

    Parameters
    ----------
    pct : array-like
        1-D percentages; non-finite entries are dropped.
    bin_width : float, default 0.1
        Bin width. ``1 / bin_width`` must be an integer, otherwise the integers cannot all
        be bin centres.
    weights : array-like, optional
        Observation weights aligned with ``pct``; counts become summed weights.
    lo, hi : float, default 0.0 and 100.0
        First and last bin centre. Both must be integer multiples of ``bin_width``.

    Returns
    -------
    (centres, counts) : tuple of numpy.ndarray
        ``centres`` runs from ``lo`` to ``hi`` in steps of ``bin_width``; ``counts`` has the
        same length. Values outside ``[lo - bin_width/2, hi + bin_width/2)`` are not counted.

    Raises
    ------
    ValueError
        If ``bin_width`` does not divide 1, if ``lo``/``hi`` are not on the grid, or if
        ``hi <= lo``.
    """
    values = as_float_array(pct, "pct")
    w = validate_weights(weights, values.size)
    if not np.isfinite(bin_width) or bin_width <= 0:
        raise ValueError(f"bin_width must be a positive finite number; got {bin_width}")
    per_unit = 1.0 / bin_width
    if abs(per_unit - round(per_unit)) > 1e-9:
        raise ValueError(
            f"bin_width must divide 1 so that every integer is a bin centre; got {bin_width}"
        )
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        raise ValueError(f"need finite lo < hi; got lo={lo}, hi={hi}")
    for name, edge in (("lo", lo), ("hi", hi)):
        steps = edge / bin_width
        if abs(steps - round(steps)) > 1e-9:
            raise ValueError(f"{name}={edge} is not an integer multiple of bin_width={bin_width}")
    n_bins = round((hi - lo) / bin_width) + 1
    centres = lo + bin_width * np.arange(n_bins, dtype=float)
    edges = np.empty(n_bins + 1, dtype=float)
    edges[:-1] = centres - bin_width / 2.0
    edges[-1] = centres[-1] + bin_width / 2.0
    finite = np.isfinite(values)
    counts, _ = np.histogram(values[finite], bins=edges, weights=None if w is None else w[finite])
    return centres, counts


@dataclass(frozen=True)
class IntegerExcessResult:
    """Outcome of :func:`integer_excess`.

    Attributes
    ----------
    test : TestResult
        ``statistic`` is the z score of the observed integer count against the Monte Carlo
        null, ``pvalue`` the one-sided (``"greater"``) normal-approximation p-value.
    observed : float
        Number (or summed weight) of units within ``tolerance`` of an integer percentage.
    expected_mean, expected_sd : float
        Mean and standard deviation of the same count under the binomial-noise null.
    excess : float
        ``observed - expected_mean``.
    per_integer : numpy.ndarray
        Length 101: excess at each integer percentage 0..100.
    n_excluded_small : int
        Units dropped because their denominator was below ``min_denominator``.
    settings : dict
        The arguments the test ran with.
    """

    test: TestResult
    observed: float
    expected_mean: float
    expected_sd: float
    excess: float
    per_integer: np.ndarray
    n_excluded_small: int
    settings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


def _near_integer(pct: np.ndarray, tolerance: float) -> np.ndarray:
    """Mask of percentages within ``tolerance`` of an integer."""
    return np.abs(pct - np.round(pct)) <= tolerance


def _neighbour_estimate(
    pct: np.ndarray, w: np.ndarray | None, tolerance: float, neighbour_bins: int
) -> tuple[float, int]:
    """Model-free comparison: integer-bin count against equally wide neighbouring bins.

    Returns ``(mean count per neighbour bin, number of neighbour bins used)``. Offsets that
    would run past the half-integer are dropped, so ``neighbour_bins`` can be truncated.
    """
    residual = pct - np.round(pct)
    width = 2.0 * tolerance
    totals: list[float] = []
    for j in range(1, neighbour_bins + 1):
        offset = j * width
        if offset + tolerance > 0.5 + 1e-12:
            break
        for signed in (offset, -offset):
            mask = np.abs(residual - signed) <= tolerance
            totals.append(float(mask.sum()) if w is None else float(w[mask].sum()))
    if not totals:
        return float("nan"), 0
    return float(np.mean(totals)), len(totals)


def integer_excess(
    pct: ArrayLike,
    denominators: ArrayLike,
    *,
    tolerance: float = 0.05,
    min_denominator: int = 100,
    neighbour_bins: int = 5,
    n_mc: int = 200,
    seed: int | np.random.Generator | None = None,
    weights: ArrayLike | None = None,
) -> IntegerExcessResult:
    """Test for an excess of integer percentages against a binomial-noise null.

    Null model (Kobak et al. 2016, section 2): unit ``i`` reported ``n_i`` out of ``d_i``,
    i.e. a share ``p_i = pct_i / 100``. Re-drawing ``n_i* ~ Binomial(d_i, p_i)`` and
    recomputing ``100 * n_i* / d_i`` gives the distribution of integer-percentage hits that
    honest reporting with binomial noise produces at these denominators and these shares.
    The observed hit count is compared with that Monte Carlo null.

    Parameters
    ----------
    pct : array-like
        1-D percentages in ``[0, 100]`` (see :func:`percentage`). Non-finite entries are
        dropped. Values outside ``[0, 100]`` raise, because the binomial null is undefined
        for them.
    denominators : array-like
        1-D denominators aligned with ``pct``; must be integer-valued (to within 1e-9)
        because they are the ``n`` of a binomial.
    tolerance : float, default 0.05
        A percentage counts as integer when it is within ``tolerance`` of one. Must lie in
        ``(0, 0.5)``.
    min_denominator : int, default 100
        Units with a smaller denominator are excluded and counted in ``n_excluded_small``.
        This is the known trap: with ``d = 20`` every possible percentage is a multiple of
        5, so integer percentages there are arithmetic rather than evidence. The binomial
        null itself absorbs the trap (its draws land on the same coarse grid the data do),
        but the model-free ``neighbour_excess`` reported alongside does not, and neither do
        the histograms these units feed; keeping the exclusion keeps the two estimates
        comparable.
    neighbour_bins : int, default 5
        Number of equally wide bins on each side of the integer used for the model-free
        cross-check reported in ``details["neighbour_excess"]``. Offsets that would run past
        the half-integer are dropped and ``details["neighbour_bins_used"]`` records how many
        bins were actually used (with the defaults, 8 of the requested 10).
    n_mc : int, default 200
        Monte Carlo replications of the null.
    seed : int or numpy.random.Generator, optional
        Seeds ``numpy.random.default_rng``.
    weights : array-like, optional
        Observation weights. Both the observed count and the null counts become summed
        weights; ``details["effective_n"]`` reports the Kish effective sample size and the
        p-value is APPROXIMATE, since the normal approximation to a weighted count is
        cruder than to a plain count.

    Returns
    -------
    IntegerExcessResult

    Raises
    ------
    ValueError
        If the inputs are mis-shaped, if a percentage lies outside ``[0, 100]``, if a
        denominator is not integer-valued, if ``tolerance`` is outside ``(0, 0.5)``, if
        ``n_mc < 1``, or if no unit survives exclusion.

    Notes
    -----
    Units at exactly 0% or 100% always sit on an integer, in the data and in every null
    draw alike, so they cannot create a spurious excess; ``details["n_at_boundary"]``
    reports how many there are. The one-sided p-value uses the normal approximation to the
    null count; ``details["mc_pvalue"]`` gives the plain Monte Carlo alternative
    ``(1 + #{null >= observed}) / (n_mc + 1)``, which is the safer number when ``n_mc`` is
    small or the null count is far from normal.
    """
    values = as_float_array(pct, "pct")
    den = as_float_array(denominators, "denominators")
    if values.size != den.size:
        raise ValueError(
            f"pct and denominators must have the same length; got {values.size} and {den.size}"
        )
    w = validate_weights(weights, values.size)
    if not np.isfinite(tolerance) or not 0.0 < tolerance < 0.5:
        raise ValueError(f"tolerance must lie strictly between 0 and 0.5; got {tolerance}")
    if int(n_mc) < 1:
        raise ValueError(f"n_mc must be at least 1; got {n_mc}")
    n_mc = int(n_mc)
    if int(neighbour_bins) < 0:
        raise ValueError(f"neighbour_bins must be non-negative; got {neighbour_bins}")
    neighbour_bins = int(neighbour_bins)
    if not np.isfinite(min_denominator) or min_denominator < 1:
        raise ValueError(f"min_denominator must be at least 1; got {min_denominator}")

    finite = np.isfinite(values) & np.isfinite(den)
    n_dropped = int(values.size - finite.sum())
    small = finite & (den < min_denominator)
    n_excluded_small = int(small.sum())
    used = finite & (den >= min_denominator)
    if not np.any(used):
        raise ValueError(
            "no unit survives exclusion: every value was non-finite or had a denominator "
            f"below min_denominator={min_denominator}"
        )
    p_pct = values[used]
    d = den[used]
    if np.any(p_pct < 0.0) or np.any(p_pct > 100.0):
        raise ValueError(
            "percentages must lie in [0, 100] for the binomial null; filter or rescale "
            "out-of-range values before calling integer_excess"
        )
    if np.any(np.abs(d - np.round(d)) > INTEGER_TOL):
        raise ValueError("denominators must be integer-valued (they are binomial sample sizes)")
    d_int = np.round(d).astype(np.int64)
    share = p_pct / 100.0
    w_used = None if w is None else w[used]
    if w_used is not None and not np.any(w_used > 0):
        raise ValueError("every included unit has zero weight")

    n = int(p_pct.size)
    effective_n = float(n) if w_used is None else kish_effective_n(w_used)
    near = _near_integer(p_pct, tolerance)
    observed = float(near.sum()) if w_used is None else float(w_used[near].sum())
    observed_per_integer = np.bincount(
        np.round(p_pct[near]).astype(np.int64),
        weights=None if w_used is None else w_used[near],
        minlength=101,
    ).astype(float)

    rng = _as_generator(seed)
    null_counts = np.empty(n_mc, dtype=float)
    null_per_integer = np.zeros(101, dtype=float)
    for i in range(n_mc):
        drawn = rng.binomial(d_int, share)
        pct_null = 100.0 * drawn / d_int
        hit = _near_integer(pct_null, tolerance)
        null_counts[i] = float(hit.sum()) if w_used is None else float(w_used[hit].sum())
        null_per_integer += np.bincount(
            np.round(pct_null[hit]).astype(np.int64),
            weights=None if w_used is None else w_used[hit],
            minlength=101,
        )
    null_per_integer /= n_mc

    expected_mean = float(null_counts.mean())
    expected_sd = float(null_counts.std(ddof=1)) if n_mc > 1 else 0.0
    excess = observed - expected_mean
    if expected_sd > 0:
        z = excess / expected_sd
        pvalue = float(stats.norm.sf(z))
    else:
        z = float("inf") if excess > 0 else 0.0
        pvalue = 0.0 if excess > 0 else 1.0
    mc_pvalue = float((1.0 + np.sum(null_counts >= observed)) / (n_mc + 1.0))
    neighbour_mean, neighbour_used = _neighbour_estimate(p_pct, w_used, tolerance, neighbour_bins)

    settings = {
        "tolerance": tolerance,
        "min_denominator": int(min_denominator),
        "neighbour_bins": neighbour_bins,
        "n_mc": n_mc,
        "seed": seed if isinstance(seed, int) or seed is None else "Generator",
        "weighted": w is not None,
    }
    test = TestResult(
        method="integer_percentage_excess",
        statistic=float(z),
        pvalue=pvalue,
        n=n,
        details={
            "alternative": "greater",
            "observed": observed,
            "expected_mean": expected_mean,
            "expected_sd": expected_sd,
            "excess": excess,
            "excess_share_of_units": excess / n if n else float("nan"),
            "mc_pvalue": mc_pvalue,
            "neighbour_mean": neighbour_mean,
            "neighbour_excess": observed - neighbour_mean,
            "neighbour_bins_used": neighbour_used,
            "n_excluded_small": n_excluded_small,
            "n_dropped": n_dropped,
            "n_at_boundary": int(np.sum((p_pct <= 0.0) | (p_pct >= 100.0))),
            "effective_n": effective_n,
            "weighted_pvalue_is_approximate": w is not None,
            "observed_per_integer": observed_per_integer,
            "expected_per_integer": null_per_integer,
            "settings": settings,
            "citation": _KSP_CITATION,
        },
    )
    return IntegerExcessResult(
        test=test,
        observed=observed,
        expected_mean=expected_mean,
        expected_sd=expected_sd,
        excess=excess,
        per_integer=observed_per_integer - null_per_integer,
        n_excluded_small=n_excluded_small,
        settings=settings,
    )


def integer_excess_by_group(
    pct: ArrayLike,
    denominators: ArrayLike,
    groups: ArrayLike,
    **kw: Any,
) -> pd.DataFrame:
    """Run :func:`integer_excess` within each group (region, year, ...).

    Parameters
    ----------
    pct, denominators : array-like
        As in :func:`integer_excess`.
    groups : array-like
        Group label per observation; any hashable labels. Rows whose label is null are
        dropped.
    **kw
        Passed to :func:`integer_excess`. A ``seed`` given here seeds a parent generator
        whose spawned children drive each group, so the whole table is reproducible and no
        two groups share a stream.

    Returns
    -------
    pandas.DataFrame
        One row per group, in order of first appearance, with columns ``group``, ``n``,
        ``observed``, ``expected_mean``, ``expected_sd``, ``excess``, ``excess_per_unit``,
        ``z``, ``pvalue``, ``mc_pvalue`` and ``n_excluded_small``. Groups in which no unit
        survives exclusion are reported with ``n = 0`` and null statistics rather than
        raising, so one empty region does not sink the table.

    Raises
    ------
    ValueError
        If the three inputs have different lengths.
    """
    values = as_float_array(pct, "pct")
    den = as_float_array(denominators, "denominators")
    labels = pd.Series(np.asarray(groups))
    if not (values.size == den.size == labels.size):
        raise ValueError(
            "pct, denominators and groups must have the same length; got "
            f"{values.size}, {den.size} and {labels.size}"
        )
    weights = kw.pop("weights", None)
    w = validate_weights(weights, values.size)
    seed = kw.pop("seed", None)
    keep = labels.notna().to_numpy()
    unique_labels = pd.unique(labels[keep])
    parent = _as_generator(seed)
    children = parent.spawn(len(unique_labels)) if len(unique_labels) else []

    rows: list[dict[str, Any]] = []
    for label, child in zip(unique_labels, children, strict=True):
        mask = keep & (labels == label).to_numpy()
        try:
            res = integer_excess(
                values[mask],
                den[mask],
                seed=child,
                weights=None if w is None else w[mask],
                **kw,
            )
        except ValueError:
            rows.append(
                {
                    "group": label,
                    "n": 0,
                    "observed": np.nan,
                    "expected_mean": np.nan,
                    "expected_sd": np.nan,
                    "excess": np.nan,
                    "excess_per_unit": np.nan,
                    "z": np.nan,
                    "pvalue": np.nan,
                    "mc_pvalue": np.nan,
                    "n_excluded_small": int(np.sum(mask)),
                }
            )
            continue
        rows.append(
            {
                "group": label,
                "n": res.test.n,
                "observed": res.observed,
                "expected_mean": res.expected_mean,
                "expected_sd": res.expected_sd,
                "excess": res.excess,
                "excess_per_unit": res.excess / res.test.n if res.test.n else np.nan,
                "z": res.test.statistic,
                "pvalue": res.test.pvalue,
                "mc_pvalue": res.test.details["mc_pvalue"],
                "n_excluded_small": res.n_excluded_small,
            }
        )
    return pd.DataFrame(rows)

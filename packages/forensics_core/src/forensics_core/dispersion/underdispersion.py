"""Underdispersion: series that carry less noise than the underlying process permits.

A fabricated series is usually *too clean*. Two complementary symptoms are tested here.

1. **Too little variance.** If an outcome is driven by a shock whose size is known from
   outside the data (rainfall for crop yields, machine downtime for output), the reported
   variance cannot fall below the variance that the shock alone injects. The chi-square test
   for a variance (Snedecor & Cochran 1989, *Statistical Methods*, 8th ed., Iowa State
   University Press, section 6.13) gives the lower-tail p-value:
   ``(n - ddof) s^2 / floor ~ chi2(n - ddof)`` when ``Var(x) = floor`` and the observations
   are independent and normal.
2. **Too little roughness.** A fabricated path moves too consistently from one period to the
   next. The von Neumann ratio -- mean squared successive difference over the sample variance
   (von Neumann 1941, *Ann. Math. Statist.* 12(4):367-395) -- is ``2`` in expectation for an
   exchangeable (iid) series and falls towards ``0`` as successive values become more alike.
   The p-value here comes from a permutation of the exchangeable units rather than from von
   Neumann's tabulated critical values, so no tabulated constant enters the code (the
   permutation argument is Wald & Wolfowitz 1943, *Ann. Math. Statist.* 14(4):378-388).

All functions are pure and treat their input as **ordered in time**. Non-finite values are
dropped and counted in ``details["n_dropped"]``; because dropping closes a gap, an input with
missing periods should be interpolated or split by the caller before it gets here.

Citation note
-------------
No numeric coefficient or threshold in this module is taken from a secondary source: every
constant is either derived here (the permutation mean of the von Neumann ratio is exactly 2
by the pairing argument in :func:`smoothness_ratio`) or computed by :mod:`scipy.stats`. The
journal citations carry the methods. The textbook *locators* -- Snedecor & Cochran (1989)
section 6.13, Fisher (1950) section 17, Cox & Lewis (1966) section 6.3 -- are from memory and
should be confirmed against the primary texts before they are quoted anywhere.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy import stats

from forensics_core._types import TestResult
from forensics_core.dispersion._common import as_1d_float, drop_nonfinite

__all__ = [
    "dispersion_index",
    "implied_variance_floor",
    "residual_underdispersion",
    "rolling_variance_floor",
    "smoothness_ratio",
    "too_smooth_test",
    "variance_floor_test",
]

Detrend = Literal["none", "linear", "diff"]


def dispersion_index(x: ArrayLike, *, ddof: int = 1) -> float:
    """Variance-to-mean ratio (the index of dispersion).

    ``D = s^2 / xbar``. For a Poisson process ``D = 1``; ``D < 1`` is underdispersion (the
    series is smoother than pure counting noise) and ``D > 1`` overdispersion. The reference
    distribution ``(n - 1) D ~ chi2(n - 1)`` under the Poisson null is *not* applied here --
    call :func:`variance_floor_test` with ``floor_variance = mean(x)`` for that.

    Source: Fisher, R. A. (1950). *Statistical Methods for Research Workers*, 11th ed.,
    section 17 ("the index of dispersion"); see also Cox, D. R. & Lewis, P. A. W. (1966),
    *The Statistical Analysis of Series of Events*, Methuen, section 6.3.

    Parameters
    ----------
    x : array-like
        1-D sample. Non-finite values are dropped.
    ddof : int, default 1
        Delta degrees of freedom of the variance (1 = sample variance).

    Returns
    -------
    float
        ``var(x, ddof) / mean(x)``.

    Raises
    ------
    ValueError
        If at most ``ddof`` finite values remain, or the mean is exactly zero (the ratio is
        undefined; nothing is silently coerced to an infinity).

    Notes
    -----
    The index is only interpretable as "Poisson-like" for non-negative counts; for a series
    that can be negative the mean is not a scale and the ratio means very little. The value is
    still returned -- interpretation is the caller's job -- but a zero mean is an error.
    """
    arr, _ = drop_nonfinite(as_1d_float(x, "x"), "x")
    if arr.size <= ddof:
        raise ValueError(
            f"dispersion_index needs more than ddof={ddof} finite values; got {arr.size}"
        )
    mean = float(np.mean(arr))
    if mean == 0.0:
        raise ValueError("dispersion_index is undefined for a sample with mean exactly zero")
    return float(np.var(arr, ddof=ddof) / mean)


def variance_floor_test(x: ArrayLike, floor_variance: float, *, ddof: int = 1) -> TestResult:
    """Test whether a sample's variance sits below a physically implied floor.

    H0: ``Var(x) >= floor_variance``. In the boundary case ``Var(x) = floor_variance`` with
    independent normal observations, ``chi2 = (n - ddof) s^2 / floor`` follows a chi-square
    distribution on ``n - ddof`` degrees of freedom, and the evidence for underdispersion is
    in the *lower* tail: ``p = P(chi2(n - ddof) <= observed)``.

    Source: the classical chi-square test for a variance, e.g. Snedecor, G. W. & Cochran,
    W. G. (1989). *Statistical Methods*, 8th ed., Iowa State University Press, section 6.13.
    No coefficient is taken from a secondary source; the tail is evaluated with
    :func:`scipy.stats.chi2.cdf`.

    Parameters
    ----------
    x : array-like
        1-D sample, ordered in time if it is a series. Non-finite values are dropped.
    floor_variance : float
        Strictly positive lower bound on the variance, in the squared units of ``x``. See
        :func:`implied_variance_floor` for one way to obtain it.
    ddof : int, default 1
        Degrees of freedom removed by estimating the mean (1) or by a prior fit
        (``1 + number of fitted parameters``; see :func:`residual_underdispersion`). Must be
        ``>= 1``: the numerator is the sum of squares about the **sample** mean, which carries
        ``n - 1`` degrees of freedom at most, so ``ddof = 0`` would refer a ``chi2(n - 1)``
        quantity to a ``chi2(n)`` reference and over-reject (a 4000-replication calibration at
        ``n = 20`` gives a rejection rate of 0.071 at a nominal 0.05). A genuinely known mean
        would need the sum of squares about *that* mean, which this function does not compute.

    Returns
    -------
    TestResult
        ``method="variance_floor_chi2"``, ``statistic`` = the chi-square statistic,
        ``pvalue`` = lower-tail probability, ``details`` = ``s2``, ``floor`` (the contract
        name) and its alias ``floor_variance``, ``ratio`` (``s2 / floor``), ``df``, ``ddof``,
        ``alternative="less"``, ``n_dropped``.

    Raises
    ------
    ValueError
        If ``floor_variance`` is not finite and positive, if ``ddof < 1``, or if fewer than
        ``ddof + 1`` finite observations remain.

    Notes
    -----
    The test is sensitive to non-normality and to serial correlation: positively correlated
    observations make ``s^2`` look small relative to an independence null, so a rejection
    should be read together with :func:`too_smooth_test`, which tests the shape of the noise
    rather than its level.
    """
    floor_variance = float(floor_variance)
    if not np.isfinite(floor_variance) or floor_variance <= 0:
        raise ValueError(f"floor_variance must be finite and > 0; got {floor_variance!r}")
    if ddof < 1:
        raise ValueError(
            f"ddof must be >= 1; got {ddof}. The numerator is the sum of squares about the "
            "sample mean, so it carries at most n - 1 degrees of freedom; ddof = 0 would "
            "compare it with chi2(n) and reject too often. Use 1 (mean estimated) or 1 + k "
            "(k further parameters fitted on this sample)."
        )
    arr, n_dropped = drop_nonfinite(as_1d_float(x, "x"), "x")
    n = int(arr.size)
    df = n - ddof
    if df < 1:
        raise ValueError(
            f"variance_floor_test needs at least ddof + 1 = {ddof + 1} finite observations; got {n}"
        )
    s2 = float(np.var(arr, ddof=ddof))
    statistic = float(df * s2 / floor_variance)
    return TestResult(
        method="variance_floor_chi2",
        statistic=statistic,
        pvalue=float(stats.chi2.cdf(statistic, df)),
        n=n,
        details={
            "s2": s2,
            # "floor" is the name fixed by INTERFACES.md; "floor_variance" is kept as an
            # explicit alias because it matches the argument name.
            "floor": floor_variance,
            "floor_variance": floor_variance,
            "ratio": s2 / floor_variance,
            "df": int(df),
            "ddof": int(ddof),
            "alternative": "less",
            "n_dropped": n_dropped,
        },
    )


def implied_variance_floor(proxy: ArrayLike, elasticity: float, *, ddof: int = 1) -> float:
    """Variance floor implied by a driver the outcome must respond to.

    If the outcome is ``y = beta * p + u`` with ``p`` an observed physical driver (rainfall,
    temperature, an input quota) and ``beta`` its response coefficient, then

    ``Var(y) = beta^2 Var(p) + 2 beta Cov(p, u) + Var(u) >= beta^2 Var(p)``

    **provided** ``2 beta Cov(p, u) + Var(u) >= 0``, which is guaranteed when the remaining
    shocks ``u`` are uncorrelated with the proxy. That assumption is the whole content of the
    bound: this is a lower bound *only* under it. A reported series whose variance falls below
    ``beta^2 Var(p)`` either (a) has a smaller response coefficient than the one assumed,
    (b) has shocks that offset the driver -- irrigation, storage, a stabilisation policy, all
    economically real reasons for the bound to fail -- or (c) has been smoothed. Rule out (a)
    and (b) before reading a rejection as (c).

    Source: the elementary variance decomposition; used as a plausibility bound in the
    agronomic literature on reported crop output (rainfall-yield response). No coefficient is
    taken from any secondary source -- ``elasticity`` is supplied and must be defended by the
    caller.

    Parameters
    ----------
    proxy : array-like
        1-D driver series, in the units used to define ``elasticity``. Non-finite values are
        dropped.
    elasticity : float
        Response of the outcome to the proxy, ``d(outcome) / d(proxy)``. Units must match:
        for a true elasticity (``d log y / d log p``) pass ``log(proxy)`` and read the result
        as a floor on ``Var(log y)``.
    ddof : int, default 1
        Delta degrees of freedom of ``Var(proxy)``; 1 (sample variance) matches the default
        of :func:`variance_floor_test`.

    Returns
    -------
    float
        ``elasticity**2 * var(proxy, ddof=ddof)``.

    Raises
    ------
    ValueError
        If ``elasticity`` is not finite, or at most ``ddof`` finite proxy values remain.
    """
    elasticity = float(elasticity)
    if not np.isfinite(elasticity):
        raise ValueError(f"elasticity must be finite; got {elasticity!r}")
    arr, _ = drop_nonfinite(as_1d_float(proxy, "proxy"), "proxy")
    if arr.size <= ddof:
        raise ValueError(
            f"implied_variance_floor needs more than ddof={ddof} finite proxy values; "
            f"got {arr.size}"
        )
    return float(elasticity**2 * np.var(arr, ddof=ddof))


def residual_underdispersion(
    series: ArrayLike, fitted: ArrayLike, floor_variance: float, *, ddof: int = 1
) -> TestResult:
    """Variance-floor test applied to the residuals ``series - fitted``.

    Use it when the level of the series is explained by a model (a trend, a set of covariates,
    a plan target) and the question is whether what is left over carries enough noise.

    Source: as :func:`variance_floor_test` (chi-square test for a variance; Snedecor &
    Cochran 1989, section 6.13).

    Parameters
    ----------
    series, fitted : array-like
        Equal-length 1-D arrays. A position where either is non-finite is dropped from both.
    floor_variance : float
        Strictly positive lower bound on the residual variance.
    ddof : int, default 1
        Degrees of freedom used up by the fit. Pass ``1 + k`` when ``fitted`` came from a
        ``k``-parameter regression estimated on this same data (``ddof=2`` for a fitted linear
        trend), otherwise the test is anti-conservative. The default of 1 assumes ``fitted``
        is external to the sample.

    Returns
    -------
    TestResult
        As :func:`variance_floor_test`, with ``method="residual_underdispersion"`` and
        ``details["mean_residual"]`` added.

    Raises
    ------
    ValueError
        If the two inputs have different lengths, or the underlying test's preconditions fail.
    """
    y = as_1d_float(series, "series")
    f = as_1d_float(fitted, "fitted")
    if y.size != f.size:
        raise ValueError(f"series and fitted must have the same length; got {y.size} and {f.size}")
    keep = np.isfinite(y) & np.isfinite(f)
    n_dropped = int(y.size - keep.sum())
    resid = y[keep] - f[keep]
    res = variance_floor_test(resid, floor_variance, ddof=ddof)
    details = dict(res.details)
    details["n_dropped"] = n_dropped
    details["mean_residual"] = float(np.mean(resid))
    return replace(res, method="residual_underdispersion", details=details)


def smoothness_ratio(series: ArrayLike) -> float:
    """Von Neumann ratio: mean squared successive difference over the sample variance.

    ``eta = [sum_{i=2..n} (x_i - x_{i-1})^2 / (n - 1)] / [sum_i (x_i - xbar)^2 / (n - 1)]``

    The expectation is ``2`` for an exchangeable (iid) series -- exactly ``2`` under a random
    permutation of the values, because the mean squared difference over all ordered pairs of a
    fixed set is ``2 s^2``. Values near ``0`` mean successive observations barely move
    relative to the spread of the series (too smooth: positive serial correlation); values
    near ``4`` mean it alternates. To first order ``eta = 2 (1 - rho_1)`` with ``rho_1`` the
    lag-1 autocorrelation, which is why the Durbin-Watson statistic has the same form.

    Source: von Neumann, J. (1941). "Distribution of the ratio of the mean square successive
    difference to the variance." *Annals of Mathematical Statistics* 12(4):367-395. The ratio
    is that paper's ``delta^2 / s^2`` with both terms divided by ``n - 1``.

    Parameters
    ----------
    series : array-like
        1-D series **in time order**. Non-finite values are dropped, which closes gaps.

    Returns
    -------
    float
        The ratio. It is scale-invariant -- multiplying the series by a constant leaves it
        unchanged -- so it measures the *shape* of the noise, never its size (that is
        :func:`variance_floor_test`'s job).

    Raises
    ------
    ValueError
        If fewer than 3 finite values remain, or the series is constant *to within
        floating-point precision* -- the ratio would then be 0/0, or worse, a finite number
        computed entirely from rounding error. See :func:`_smoothness_ratio_clean` for the
        exact tolerance.
    """
    arr, _ = drop_nonfinite(as_1d_float(series, "series"), "series")
    return _smoothness_ratio_clean(arr)


#: Relative tolerance for "constant to within floating-point precision", as a multiple of the
#: unit roundoff. A value spaced ``scale`` from zero is represented to about ``eps * scale``,
#: so any spread below ``_ZERO_SD_EPS_FACTOR * eps * scale`` is rounding error, not data. The
#: factor 16 is our own numerical guard (nothing in von Neumann 1941 fixes it): measured
#: residual standard deviations of an exactly linear series detrended by
#: :func:`numpy.linalg.lstsq` reach about ``1.7 * eps * scale``, so 16 leaves roughly an order
#: of magnitude of headroom while staying ~1e-14 relative -- far below any real variation.
_ZERO_SD_EPS_FACTOR = 16.0


def _smoothness_ratio_clean(arr: np.ndarray, *, scale: float | None = None) -> float:
    """Von Neumann ratio of an array already known to be finite; see :func:`smoothness_ratio`.

    Parameters
    ----------
    arr : numpy.ndarray
        Finite 1-D values, in time order.
    scale : float, optional
        Magnitude of the data the values were derived from, used for the relative
        zero-variance guard. Defaults to ``max(abs(arr))``. Callers that pass *derived* values
        (detrended residuals, first differences) must pass the scale of the **original**
        series: the residuals of an exactly linear series are pure rounding error of size
        ``eps * scale_of_the_series``, which is enormous relative to the residuals themselves
        and invisible to a guard scaled by them.
    """
    n = int(arr.size)
    if n < 3:
        raise ValueError(f"smoothness_ratio needs at least 3 finite observations; got {n}")
    if scale is None:
        scale = float(np.max(np.abs(arr))) if n else 0.0
    s2 = float(np.var(arr, ddof=1))
    tol = (_ZERO_SD_EPS_FACTOR * float(np.finfo(float).eps) * max(1.0, float(scale))) ** 2
    if s2 <= tol:
        raise ValueError(
            "smoothness_ratio is undefined for a constant series (zero variance): the "
            f"variance {s2:.3g} is at or below {tol:.3g}, the square of "
            f"{_ZERO_SD_EPS_FACTOR:g} * eps * {max(1.0, float(scale)):.3g}, so the ratio "
            "would be computed from floating-point rounding error rather than from data. An "
            "exactly linear input under detrend='linear' lands here."
        )
    mssd = float(np.sum(np.diff(arr) ** 2) / (n - 1))
    return mssd / s2


#: Human-readable name of what each ``detrend`` option analyses; goes into
#: ``details["analysed"]`` so ``statistic`` is never misread as ``smoothness_ratio(series)``.
_ANALYSED_LABEL: dict[str, str] = {
    "none": "levels",
    "diff": "first differences",
    "linear": "linear-trend residuals",
}


def _detrend_values(arr: np.ndarray, detrend: Detrend) -> np.ndarray:
    """Return the values that are exchangeable under H0; see :func:`too_smooth_test`."""
    if detrend == "none":
        return arr
    if detrend == "diff":
        return np.diff(arr)
    if detrend == "linear":
        t = np.arange(arr.size, dtype=float)
        # centred time index: same fit, better conditioned than [1, 0..n-1]
        design = np.column_stack([np.ones_like(t), t - t.mean()])
        coef, *_ = np.linalg.lstsq(design, arr, rcond=None)
        return arr - design @ coef
    raise ValueError(f"detrend must be one of 'none', 'linear', 'diff'; got {detrend!r}")


def too_smooth_test(
    series: ArrayLike,
    *,
    detrend: Detrend = "diff",
    n_perm: int = 999,
    seed: int | None = None,
) -> TestResult:
    """Permutation test for a series that moves too consistently to be real.

    H0: the analysed values are exchangeable. With the default ``detrend="diff"`` those values
    are the **successive changes** of the series, so the null reads "the period-to-period
    changes could have arrived in any order". The statistic is the von Neumann ratio
    (:func:`smoothness_ratio`) of the analysed values and the null distribution is obtained by
    recomputing it on ``n_perm`` random permutations of those same values. The p-value is the
    lower tail (``alternative="less"``): a ratio far below the permutation distribution means
    neighbouring values are alike, i.e. the series is too smooth.

    ``p = (1 + #{permuted <= observed}) / (n_perm + 1)`` -- the add-one form that keeps a
    permutation test valid (Phipson & Smyth 2010, *Stat. Appl. Genet. Mol. Biol.* 9(1),
    Article 39).

    Sources: von Neumann (1941), *Ann. Math. Statist.* 12(4):367-395, for the ratio; Wald &
    Wolfowitz (1943), *Ann. Math. Statist.* 14(4):378-388, for testing serial randomness by
    permutation instead of a tabulated critical value. No constant is taken from memory: the
    null distribution is computed, and its mean is exactly 2 by the pairing argument recorded
    in :func:`smoothness_ratio`.

    Parameters
    ----------
    series : array-like
        1-D series **in time order**. Non-finite values are dropped, which closes gaps, so
        split the series yourself if periods are missing.
    detrend : {"none", "linear", "diff"}, default "diff"
        Which values H0 declares exchangeable. **The default ``"diff"`` is the exact test only
        for a random-walk-like series**: permuting first differences is a valid exchangeability
        null when the increments are iid. For a stationary or trend-stationary series use
        ``"linear"`` or ``"none"`` -- there ``"diff"`` has essentially no power, because
        differencing "trend + iid levels" produces an MA(1) with lag-1 autocorrelation ``-1/2``
        whose ratio sits *above* the permutation null, pinning the lower-tail p-value near 1.
        (Calibration on 400 honest iid N(0,1) series of length 60, ``n_perm=199``: mean p was
        0.998 under ``"diff"`` against 0.529 under ``"linear"`` and 0.492 under ``"none"``.)
        A smoothed mean-reverting path -- AR(1) deviations, the usual fabrication shape --
        therefore cannot be flagged under the default; an AR(1) with ``rho = 0.95`` has a
        differenced lag-1 autocorrelation of only ``-(1 - rho)/2 = -0.025``.

        * ``"diff"``: the first differences. Detects a path whose *changes* drift smoothly --
          an accelerating or decelerating fabricated series. A genuine "trend + iid noise"
          series differences to an MA(1) with lag-1 autocorrelation ``-1/2``, so its ratio
          sits near ``3`` and it is comfortably not rejected.
        * ``"linear"``: residuals of an OLS fit on the time index ``0..n-1``. Detects serially
          correlated deviations around a straight-line trend. OLS residuals are not exactly
          exchangeable (they are orthogonal to the regressors by construction), so the
          permutation p-value is an approximation here; it is exact for ``"none"`` and
          ``"diff"``.
        * ``"none"``: the levels themselves. *Any* trending series is "too smooth" under this
          option -- it flags trends, not fabrication. Use it only where the series is supposed
          to be stationary (a share, a rate, a residual computed elsewhere).
    n_perm : int, default 999
        Number of random permutations; the smallest attainable p-value is ``1/(n_perm + 1)``.
        Must be ``>= 2`` -- a single draw gives no usable null distribution (and no spread).
    seed : int | None
        Passed to :func:`numpy.random.default_rng`.

    Returns
    -------
    TestResult
        ``method=f"too_smooth_{detrend}"``, ``statistic`` = observed von Neumann ratio **of the
        analysed values** (with the default ``detrend="diff"`` that is
        ``smoothness_ratio(np.diff(series))``, not ``smoothness_ratio(series)`` --
        ``details["analysed"]`` says which), ``pvalue`` = permutation lower tail, ``n`` =
        finite observations in the input, and ``details`` = ``detrend``, ``analysed``
        (``"levels"`` / ``"first differences"`` / ``"linear-trend residuals"``),
        ``n_analysed``, ``n_perm``, ``seed``, ``null_mean``, ``null_sd``, ``null_q05``,
        ``implied_lag1_autocorr`` (``1 - statistic/2``), ``alternative="less"``, ``n_dropped``.

    Raises
    ------
    ValueError
        On an unknown ``detrend``, ``n_perm < 2``, fewer than 3 analysable values (4 raw
        observations when differencing), or an analysed series that is constant to within
        floating-point precision (an exactly linear input under ``detrend="linear"``).

    Notes
    -----
    A permutation leaves the multiset of analysed values untouched, so the denominator of the
    ratio is constant across permutations and the test is exactly a one-sided permutation test
    on the lag-1 autocorrelation of the analysed values. It says nothing about the *size* of
    the noise -- the ratio is scale-invariant -- so pair it with :func:`variance_floor_test`.
    """
    if n_perm < 2:
        raise ValueError(f"n_perm must be >= 2 for a usable permutation null; got {n_perm}")
    arr, n_dropped = drop_nonfinite(as_1d_float(series, "series"), "series")
    values = _detrend_values(arr, detrend)  # raises on an unknown option before anything else
    m = int(values.size)
    if m < 3:
        raise ValueError(
            f"too_smooth_test with detrend={detrend!r} needs at least 3 analysable values; got {m}"
        )
    # the guard scale is the magnitude of the *input*: detrended residuals of an exactly
    # linear series are rounding error of size eps * max|series|, not of their own size.
    scale = float(np.max(np.abs(arr))) if arr.size else 0.0
    observed = _smoothness_ratio_clean(values, scale=scale)

    rng = np.random.default_rng(seed)
    s2 = float(np.var(values, ddof=1))  # permutation-invariant
    draws = rng.permuted(np.broadcast_to(values, (n_perm, m)), axis=1)
    null = np.sum(np.diff(draws, axis=1) ** 2, axis=1) / ((m - 1) * s2)
    pvalue = float((1 + np.count_nonzero(null <= observed)) / (n_perm + 1))

    return TestResult(
        method=f"too_smooth_{detrend}",
        statistic=observed,
        pvalue=pvalue,
        n=int(arr.size),
        details={
            "detrend": detrend,
            "analysed": _ANALYSED_LABEL[detrend],
            "n_analysed": m,
            "n_perm": int(n_perm),
            "seed": seed,
            "null_mean": float(np.mean(null)),
            "null_sd": float(np.std(null, ddof=1)),
            "null_q05": float(np.quantile(null, 0.05)),
            "implied_lag1_autocorr": 1.0 - observed / 2.0,
            "alternative": "less",
            "n_dropped": n_dropped,
        },
    )


def rolling_variance_floor(
    series: ArrayLike,
    floor_variance: float,
    window: int,
    *,
    ddof: int = 1,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Run :func:`variance_floor_test` on every contiguous window of a series.

    Fabrication is usually episodic: one bad year, one office, one plan period. A series whose
    variance is only mildly low overall can still hide a stretch that is impossibly flat.

    Source: as :func:`variance_floor_test` (chi-square test for a variance; Snedecor &
    Cochran 1989, section 6.13). The windows overlap, so the p-values are strongly dependent;
    ``flag`` is a screening device and ``alpha`` is a nominal per-window level, not a
    family-wise error rate.

    Parameters
    ----------
    series : array-like
        1-D series **in time order**. Non-finite values are dropped first, which closes gaps;
        the ``start``/``end`` positions refer to the *cleaned* series.
    floor_variance : float
        Strictly positive lower bound on the variance, as in :func:`variance_floor_test`.
    window : int
        Window length in observations; must satisfy ``ddof < window <= n``.
    ddof : int, default 1
        Passed to :func:`variance_floor_test`.
    alpha : float, default 0.05
        Nominal per-window level used for the ``flag`` column; must lie in ``(0, 1)``.

    Returns
    -------
    pandas.DataFrame
        One row per window, columns ``start``, ``end`` (inclusive positional indices into the
        cleaned series), ``n``, ``s2``, ``statistic``, ``pvalue``, ``flag``
        (``pvalue < alpha``) and ``n_dropped``. ``n_dropped`` is a property of the *whole*
        input, not of the window: it is the number of non-finite observations removed before
        windowing, repeated on every row so that a caller reading one row can see that
        ``start``/``end`` index the cleaned series rather than the input. The same count is
        also on ``frame.attrs["n_dropped"]``.

    Raises
    ------
    ValueError
        If ``alpha`` or ``window`` is out of range, or the underlying test's checks fail.
    """
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    window = int(window)
    arr, n_dropped = drop_nonfinite(as_1d_float(series, "series"), "series")
    n = int(arr.size)
    if window <= ddof:
        raise ValueError(f"window must be greater than ddof={ddof}; got {window}")
    if window > n:
        raise ValueError(f"window ({window}) exceeds the number of finite observations ({n})")
    rows = []
    for start in range(n - window + 1):
        res = variance_floor_test(arr[start : start + window], floor_variance, ddof=ddof)
        rows.append(
            {
                "start": start,
                "end": start + window - 1,
                "n": res.n,
                "s2": res.details["s2"],
                "statistic": res.statistic,
                "pvalue": res.pvalue,
                "flag": bool(res.pvalue < alpha),
                "n_dropped": n_dropped,
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=["start", "end", "n", "s2", "statistic", "pvalue", "flag", "n_dropped"],
    )
    frame.attrs["n_dropped"] = n_dropped
    return frame

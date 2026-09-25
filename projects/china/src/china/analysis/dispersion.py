"""Underdispersion of provincial growth. **Stubs only: every function raises.**

The programme's second signal, weighted equally with bunching: a fabricated series contains
*too little* noise. A reported growth series that is smoother than the physical drivers of
that growth permit is impossible regardless of its level, and unlike a level test this one
needs no counterfactual for what the level should have been.

The variance floor is what makes it a test rather than an impression. If reported product
responds to a physical driver with elasticity ``e``, then the variance of reported growth
cannot be below ``e**2`` times the variance of the driver's growth, unless something else is
cancelling it out. :func:`forensics_core.dispersion.underdispersion.implied_variance_floor`
computes that bound and
:func:`forensics_core.dispersion.underdispersion.variance_floor_test` tests against it, with
the alternative "less": too smooth.

The trap, and it is a serious one here: provinces genuinely smooth their growth by managing
real activity, especially credit and infrastructure investment. Underdispersion in reported
growth is consistent both with fabrication and with a province that really did hit its target
every year by building things. What separates them is whether the *proxies* are equally
smooth: fabricating the report smooths the report alone, while managing the economy smooths
both.

References
----------
Narasimhan & Jordache (2000, *Data Reconciliation and Gross Error Detection*, Gulf, ch. 3-5)
for the reconciliation framing used alongside these tests, quoted as
:mod:`forensics_core.reconcile` carries it. That module files a provenance caveat on the
chapter numbers, so nothing is added to the citation here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = [
    "growth_series",
    "proxy_implied_floor",
    "smoothness_by_province",
    "underdispersion_by_province",
]


def growth_series(
    panel: pd.DataFrame,
    *,
    vintage: str,
    series: str = "grp_index_preceding_year",
) -> pd.DataFrame:
    """The per-province growth series the dispersion tests operate on.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage to use.
    series : str, default "grp_index_preceding_year"
        Preferred source of growth. The published index at constant prices, minus 100, is the
        real growth rate the province itself reported; differencing ``grp_nominal`` gives
        nominal growth and is a different quantity.

    Returns
    -------
    pandas.DataFrame
        Wide, indexed by year with one column per province, growth in percentage points.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: extraction. Note also that the index column exists only in editions that
    print one; the 2024-style single-year cross-section carries an index column, and the
    2015-style multi-year panel carries five, so coverage differs by edition family.
    """
    raise NotImplementedError("needs the extracted index columns from yearbook table 3-9")


def proxy_implied_floor(
    growth: pd.DataFrame,
    proxy_growth: pd.DataFrame,
    *,
    elasticity: float,
) -> pd.Series:
    """Lower bound on the variance of reported growth implied by a physical driver.

    Wraps :func:`forensics_core.dispersion.underdispersion.implied_variance_floor`:
    ``elasticity ** 2 * Var(proxy_growth)``, per province.

    Parameters
    ----------
    growth : pandas.DataFrame
        Reported growth, from :func:`growth_series`. Used for its index and column alignment
        only.
    proxy_growth : pandas.DataFrame
        Growth of the physical proxy, same shape.
    elasticity : float
        Elasticity of reported product with respect to the proxy, from
        :func:`china.analysis.proxies.proxy_elasticities`.

    Returns
    -------
    pandas.Series
        The floor, per province.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains, and it is a caveat that has to travel with any result: this is a lower bound
    **only if** the other shocks to reported product are uncorrelated with the proxy. If a
    province smooths both its economy and its report, the bound is satisfied and the test says
    nothing. That is a limitation of the test, not a clean bill of health, and must be
    reported as such.
    """
    raise NotImplementedError(
        "needs a proxy elasticity; and the bound holds only under the stated independence "
        "assumption, which must be reported with any result"
    )


def underdispersion_by_province(
    growth: pd.DataFrame,
    floors: pd.Series,
    *,
    window: int | None = None,
) -> pd.DataFrame:
    """Test each province's growth variance against its implied floor.

    Wraps :func:`forensics_core.dispersion.underdispersion.variance_floor_test`, whose
    statistic is ``(n - 1) s**2 / floor`` against a chi-square with ``n - 1`` degrees of
    freedom, alternative "less".

    Parameters
    ----------
    growth : pandas.DataFrame
        Reported growth, from :func:`growth_series`.
    floors : pandas.Series
        Variance floors, from :func:`proxy_implied_floor`.
    window : int, optional
        When given, run the test on rolling windows via
        :func:`forensics_core.dispersion.underdispersion.rolling_variance_floor`, so that a
        province that was smooth for four years and normal afterwards is visible.

    Returns
    -------
    pandas.DataFrame
        One row per province, or per province and window, with the statistic, the p-value,
        the sample variance and the floor.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the multiple-comparison policy. Thirty-one provinces tested at once will
    produce one or two nominally significant results by chance, so the reported quantity has
    to be a corrected one, decided before the test is run.
    """
    raise NotImplementedError(
        "needs growth_series and proxy_implied_floor, and a multiple-comparison correction "
        "chosen in advance for 31 simultaneous tests"
    )


def smoothness_by_province(
    growth: pd.DataFrame,
    *,
    detrend: str = "diff",
    n_perm: int = 999,
    seed: int | None = None,
) -> Any:
    """Test whether growth is too smooth, without needing a proxy at all.

    Wraps :func:`forensics_core.dispersion.underdispersion.too_smooth_test`, whose statistic
    is the von Neumann ratio, the mean squared successive difference over the variance, about
    2 for independent noise and lower for a series with too little year-to-year movement. The
    null is that successive changes are exchangeable and the p-value comes from permuting
    them.

    The value of this test is that it needs no elasticity and no proxy, so it can be run on
    any province and any vintage. Its cost is that a genuinely trending economy is smooth by
    construction, which is what ``detrend`` is for.

    Parameters
    ----------
    growth : pandas.DataFrame
        Reported growth, from :func:`growth_series`.
    detrend : {"none", "linear", "diff"}, default "diff"
        Detrending applied before the statistic.
    n_perm : int, default 999
        Permutations.
    seed : int, optional
        Passed to ``numpy.random.default_rng``.

    Returns
    -------
    pandas.DataFrame
        One row per province with the ratio, the p-value and the number of years used.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the panel. Note that with roughly a decade of annual observations per
    province the permutation distribution is coarse, so p-values should be reported with the
    number of distinct attainable values.
    """
    raise NotImplementedError(
        "needs growth_series; with about ten annual observations per province the "
        "permutation distribution is coarse and that has to be reported"
    )

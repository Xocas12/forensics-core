"""Carlisle's test: baseline tables that balance too well to be random.

Randomising patients (or precincts, or plots) into groups makes every baseline variable
differ between groups by chance alone, so the p-value for each between-group comparison is
Uniform(0, 1). Fabricated or "adjusted" baseline tables balance *better* than chance -- means
sit implausibly close together given the reported standard deviations -- and the p-values pile
up near 1. Carlisle's contribution is to test that pile-up rather than any single comparison.

Sources
-------
Carlisle, J. B. (2017). "Data fabrication and other reasons for non-random sampling in 5087
randomised, controlled trials in anaesthetic and general medical journals." *Anaesthesia*
72(8):944-952.
Carlisle, J. B. & Loadsman, J. A. (2017). "Evidence for non-random sampling in randomised,
controlled trials by Yuhji Saitoh." *Anaesthesia* 72(1):17-27.

Method as implemented here
--------------------------
1. Per variable, a between-group p-value is reconstructed from the reported summary
   statistics only (means, SDs, group sizes) with a one-way ANOVA; with two groups this is
   exactly the pooled two-sample t-test (``F = t^2``, same p-value).
2. Those per-variable p-values are combined in the *upper* direction -- evidence that they are
   too close to 1 -- with Stouffer's or Fisher's method, and are also compared with U(0, 1) by
   a one-sided Kolmogorov-Smirnov test.

Sign convention (applies to every combined statistic in this module)
--------------------------------------------------------------------
``details["alternative"] = "greater"`` and **large statistic = too balanced**. Stouffer's
``z = sum(Phi^-1(1 - p_i)) / sqrt(k)`` is *negative* when the p-values pile near 1, so the
statistic reported is ``-z``; the p-value is ``P(N(0,1) >= -z)``. Fisher's method is applied
to the complements ``1 - p_i`` for the same reason, so that its statistic also grows with
"too balanced" instead of with "significantly different".

Citation note
-------------
No numeric coefficient or threshold is taken from a secondary source: the only constant in the
module is the p-value clip (:data:`DEFAULT_CLIP`), which is our own numerical guard and is
reported in every result. The supporting *locators* -- Fisher (1932) section 21.1, Snedecor &
Cochran (1989) chapter 12, and the page ranges quoted for Whitlock (2005) and Birnbaum &
Tingey (1951) -- are from memory and should be confirmed against the primary texts.

Non-finite handling (a deliberate deviation)
--------------------------------------------
:func:`carlisle_test` follows the library convention: a variable whose reported summary
statistics are not all finite is dropped and counted in ``combined.details["n_dropped"]``.
:func:`combine_pvalues` does **not** drop -- a non-finite p-value raises, because it is a
failed upstream test rather than missing data, and silently combining ``k - 1`` values would
change the reference distribution behind the caller's back. It still reports
``details["n_dropped"] = 0`` so the key can be read uniformly.

Caveats worth carrying into any use
-----------------------------------
Non-random baseline p-values are evidence of *non-random sampling*, not proof of fraud:
Carlisle (2017) lists mis-transcription, unit errors, post-randomisation exclusions,
stratified or minimised allocation and correlated baseline variables among the innocent
explanations. Correlated variables in particular break the independence that both combining
methods assume, and they inflate the apparent significance of a combined test.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats

from forensics_core._types import TestResult, jsonable
from forensics_core.dispersion._common import as_1d_float, as_float_matrix

__all__ = ["CarlisleResult", "balance_pvalues", "carlisle_test", "combine_pvalues"]

CombineMethod = Literal["stouffer", "fisher"]

#: Default clip applied to p-values before Phi^-1 / log, so that an exact 0 or 1 does not
#: produce an infinite statistic. Recorded in ``details["clip"]`` and ``details["n_clipped"]``.
DEFAULT_CLIP = 1e-12


@dataclass(frozen=True)
class CarlisleResult:
    """Outcome of :func:`carlisle_test`.

    Attributes
    ----------
    per_variable : numpy.ndarray
        One between-group p-value per baseline variable (rows kept, in input order).
    combined : TestResult
        Stouffer or Fisher combination, ``alternative="greater"`` = too balanced (see the
        module docstring for the sign convention).
    ks_uniformity : TestResult
        One-sided Kolmogorov-Smirnov test of the p-values against U(0, 1), in the near-1
        direction.
    """

    per_variable: np.ndarray
    combined: TestResult
    ks_uniformity: TestResult

    def to_dict(self) -> dict[str, Any]:
        return jsonable(
            {
                "per_variable": self.per_variable,
                "combined": self.combined.to_dict(),
                "ks_uniformity": self.ks_uniformity.to_dict(),
            }
        )


def balance_pvalues(means: ArrayLike, sds: ArrayLike, ns: ArrayLike) -> float:
    """One-way ANOVA p-value for one baseline variable, from group summary statistics.

    With ``k`` groups of sizes ``n_i``, reported means ``m_i`` and reported sample standard
    deviations ``s_i`` (``ddof = 1``),

    * grand mean ``mbar = sum(n_i m_i) / N``, ``N = sum(n_i)``
    * between-group sum of squares ``SSB = sum n_i (m_i - mbar)^2`` on ``k - 1`` df
    * within-group sum of squares ``SSW = sum (n_i - 1) s_i^2`` on ``N - k`` df
    * ``F = (SSB / (k - 1)) / (SSW / (N - k))``, ``p = P(F(k-1, N-k) >= F_obs)``.

    This is algebraically the ANOVA that would be computed from the raw observations, so it
    matches :func:`scipy.stats.f_oneway` on any data with those summary statistics. For
    ``k = 2`` it is exactly the pooled (equal-variance) two-sample t-test, ``F = t^2``.

    Source: Carlisle, J. B. (2017). *Anaesthesia* 72(8):944-952 (the reconstruction of
    baseline p-values from published summary tables); the ANOVA identity itself is standard,
    e.g. Snedecor & Cochran (1989), *Statistical Methods*, 8th ed., chapter 12.

    Parameters
    ----------
    means, sds, ns : array-like
        1-D, same length ``k >= 2``: reported group means, reported group SDs (``ddof = 1``,
        non-negative) and group sizes (integers ``>= 2``).

    Returns
    -------
    float
        The two-sided ANOVA p-value. Note the direction: *small* p means the groups differ,
        *large* p means they are alike. Carlisle's test looks at the distribution of these
        values across variables, not at any one of them.

    Raises
    ------
    ValueError
        On mismatched lengths, fewer than two groups, non-finite values, negative SDs,
        non-integer group sizes or any ``n_i < 2``.

    Notes
    -----
    Degenerate reported data is handled explicitly rather than by returning ``nan``: if every
    SD is exactly zero then ``SSW = 0`` and the p-value is ``0.0`` when the means differ (the
    groups are certainly different) and ``1.0`` when they do not (perfect balance -- itself
    the strongest possible "too good to be true" signal).
    """
    m = as_1d_float(means, "means")
    s = as_1d_float(sds, "sds")
    n = as_1d_float(ns, "ns")
    if not (m.size == s.size == n.size):
        raise ValueError(
            f"means, sds and ns must have the same length; got {m.size}, {s.size}, {n.size}"
        )
    k = int(m.size)
    if k < 2:
        raise ValueError(f"balance_pvalues needs at least 2 groups; got {k}")
    if not (np.all(np.isfinite(m)) and np.all(np.isfinite(s)) and np.all(np.isfinite(n))):
        raise ValueError("means, sds and ns must all be finite")
    if np.any(s < 0):
        raise ValueError("sds must be non-negative")
    if np.any(n != np.round(n)):
        raise ValueError("ns must be whole numbers")
    if np.any(n < 2):
        raise ValueError("every group needs at least 2 observations to carry a reported SD")

    total = float(np.sum(n))
    grand_mean = float(np.sum(n * m) / total)
    ssb = float(np.sum(n * (m - grand_mean) ** 2))
    ssw = float(np.sum((n - 1) * s**2))
    df_between = k - 1
    df_within = round(total) - k  # every n_i is a whole number, checked above
    if df_within < 1:  # unreachable while every n_i >= 2, kept as a guard
        raise ValueError(f"need more observations than groups; got N={total}, k={k}")
    if ssw <= 0:
        return 0.0 if ssb > 0 else 1.0
    f_stat = (ssb / df_between) / (ssw / df_within)
    return float(stats.f.sf(f_stat, df_between, df_within))


def combine_pvalues(
    p: ArrayLike, method: CombineMethod = "stouffer", *, clip: float = DEFAULT_CLIP
) -> TestResult:
    """Combine p-values in the "too balanced" direction (large statistic = piled near 1).

    Stouffer (Stouffer, Suchman, DeVinney, Star & Williams 1949, *The American Soldier*,
    vol. 1, Princeton University Press; see Whitlock 2005, *J. Evol. Biol.* 18:1368-1373):
    ``z = sum(Phi^-1(1 - p_i)) / sqrt(k) ~ N(0, 1)`` under U(0, 1) p-values. Piling near 1
    drives ``z`` negative, so the reported ``statistic`` is ``-z`` and
    ``pvalue = P(N(0,1) >= -z)``.

    Fisher (Fisher 1932, *Statistical Methods for Research Workers*, 4th ed., section 21.1) is
    applied **to the complements**: ``X = -2 sum log(1 - p_i) ~ chi2(2k)``, so that a large
    ``X`` again means "too balanced". The conventional lower-tail statistic
    ``-2 sum log(p_i)`` is still reported in ``details["fisher_lower_tail_statistic"]`` for
    anyone who wants the usual direction.

    Both methods assume the p-values are independent. Baseline variables in a trial usually
    are not (age, height and weight move together), which makes the combined p-value
    anti-conservative; Carlisle (2017) discusses this at length.

    Parameters
    ----------
    p : array-like
        1-D p-values in ``[0, 1]``, at least one.
    method : {"stouffer", "fisher"}, default "stouffer"
    clip : float, default 1e-12
        p-values are clipped into ``[clip, 1 - clip]`` before ``Phi^-1``/``log`` so that an
        exactly-0 or exactly-1 input cannot produce an infinite statistic. The number of
        clipped values is reported in ``details["n_clipped"]`` -- if it is large, the
        combined statistic is an artefact of the clip and must be read as "at least this
        extreme" rather than as a number.

    Returns
    -------
    TestResult
        ``method=f"combine_pvalues_{method}"``, ``n`` = number of p-values, and ``details``
        containing ``alternative="greater"``, ``direction``, ``k``, ``clip``, ``n_clipped``,
        ``n_dropped`` (always ``0``; see the note below) and (Stouffer) ``z``, ``mean_z`` or
        (Fisher) ``df``, ``fisher_lower_tail_statistic``/``fisher_lower_tail_pvalue``.

    Raises
    ------
    ValueError
        If ``p`` is empty, contains a non-finite value or a value outside ``[0, 1]``, or
        ``clip`` is not in ``(0, 0.5)``, or ``method`` is unknown.

    Notes
    -----
    **Deviation from the library-wide non-finite convention, stated deliberately.** Elsewhere
    a non-finite input is dropped and counted in ``details["n_dropped"]``. Here a non-finite
    p-value is an error, because it is never data: it means an upstream test failed to
    produce a p-value, and silently combining the remaining ``k - 1`` values would change the
    reference distribution (``chi2(2k)``, ``sqrt(k)``) without the caller knowing which
    variable vanished. ``details["n_dropped"]`` is still emitted, always ``0``, so a caller
    that reads the key uniformly across the library finds it. :func:`carlisle_test` does the
    dropping one level up -- it removes variables with non-finite summary statistics and
    overwrites ``n_dropped`` with the real count.
    """
    if not 0 < clip < 0.5:
        raise ValueError(f"clip must be in (0, 0.5); got {clip}")
    arr = as_1d_float(p, "p")
    if arr.size == 0:
        raise ValueError("combine_pvalues needs at least one p-value")
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "p-values must be finite; a non-finite p-value means an upstream test failed and "
            "dropping it would silently change the reference distribution of the combination"
        )
    if np.any(arr < 0) or np.any(arr > 1):
        raise ValueError("p-values must lie in [0, 1]")
    k = int(arr.size)
    n_clipped = int(np.count_nonzero((arr < clip) | (arr > 1 - clip)))
    q = np.clip(arr, clip, 1 - clip)
    details: dict[str, Any] = {
        "alternative": "greater",
        "direction": "large statistic = p-values piled near 1 = too balanced",
        "k": k,
        "clip": float(clip),
        "n_clipped": n_clipped,
        # nothing is ever dropped here (a non-finite p-value raises); the key is present so
        # callers can read details["n_dropped"] uniformly across the library.
        "n_dropped": 0,
        "combine_method": method,
    }

    if method == "stouffer":
        z_i = stats.norm.ppf(1.0 - q)  # very negative when p is near 1
        z = float(np.sum(z_i) / np.sqrt(k))
        statistic = -z
        details["z"] = z
        details["mean_z"] = float(np.mean(z_i))
        return TestResult(
            method="combine_pvalues_stouffer",
            statistic=statistic,
            pvalue=float(stats.norm.sf(statistic)),
            n=k,
            details=details,
        )
    if method == "fisher":
        statistic = float(-2.0 * np.sum(np.log1p(-q)))
        df = 2 * k
        details["df"] = df
        details["fisher_lower_tail_statistic"] = float(-2.0 * np.sum(np.log(q)))
        details["fisher_lower_tail_pvalue"] = float(
            stats.chi2.sf(details["fisher_lower_tail_statistic"], df)
        )
        return TestResult(
            method="combine_pvalues_fisher",
            statistic=statistic,
            pvalue=float(stats.chi2.sf(statistic, df)),
            n=k,
            details=details,
        )
    raise ValueError(f"method must be 'stouffer' or 'fisher'; got {method!r}")


def _ks_too_balanced(p: np.ndarray) -> TestResult:
    """One-sided KS test of ``p`` against U(0, 1) in the near-1 direction.

    The statistic is ``D^- = sup_x [x - F_n(x)]``: p-values piled near 1 leave the empirical
    CDF *below* the uniform CDF. In :func:`scipy.stats.kstest` terms this is
    ``alternative="less"``, whose exact one-sided p-value is used here.

    Source: Carlisle (2017), *Anaesthesia* 72(8):944-952, compares the distribution of
    baseline p-values with the uniform; the one-sided KS machinery is standard (Birnbaum &
    Tingey 1951, *Ann. Math. Statist.* 22(4):592-596).
    """
    res = stats.kstest(p, "uniform", alternative="less")
    return TestResult(
        method="carlisle_ks_uniformity",
        statistic=float(res.statistic),
        pvalue=float(res.pvalue),
        n=int(p.size),
        details={
            "alternative": "greater",
            "direction": "large D- = empirical CDF below uniform = p-values piled near 1",
            "ks_statistic": "D-",
            "scipy_alternative": "less",
        },
    )


def carlisle_test(
    means: np.ndarray,
    sds: np.ndarray,
    ns: np.ndarray,
    *,
    method: CombineMethod = "stouffer",
    clip: float = DEFAULT_CLIP,
) -> CarlisleResult:
    """Carlisle's baseline-balance test over a table of variables.

    Each row of the summary table is one baseline variable, each column one randomisation
    group. A between-group p-value is reconstructed per row with :func:`balance_pvalues`, and
    the resulting p-values are examined for the pile-up near 1 that too-good-to-be-true
    balance produces (:func:`combine_pvalues` and a one-sided KS test against U(0, 1)).

    Source: Carlisle, J. B. (2017). *Anaesthesia* 72(8):944-952; Carlisle, J. B. & Loadsman,
    J. A. (2017). *Anaesthesia* 72(1):17-27. See the module docstring for the sign convention
    and for the innocent explanations that must be ruled out before "fabrication" is said.

    Parameters
    ----------
    means, sds : array-like, shape (n_variables, n_groups)
        Reported group means and SDs (``ddof = 1``). A 1-D input is read as a single variable.
    ns : array-like, shape (n_variables, n_groups) or (n_groups,)
        Group sizes. A 1-D input of length ``n_groups`` is used for every variable (the usual
        case: the same randomised groups measured on every baseline variable).
    method : {"stouffer", "fisher"}, default "stouffer"
        Combining method; both are oriented so that a large statistic means "too balanced".
    clip : float, default 1e-12
        Passed to :func:`combine_pvalues`.

    Returns
    -------
    CarlisleResult
        ``per_variable`` p-values, the ``combined`` test and the ``ks_uniformity`` test.
        ``combined.details["n_dropped"]`` counts variables dropped for non-finite summary
        statistics.

    Raises
    ------
    ValueError
        If the three arrays disagree in shape, if fewer than two groups or no usable variable
        remains, or if any kept row fails :func:`balance_pvalues`'s checks (SD < 0, ``n < 2``,
        non-integer ``n``).

    Notes
    -----
    Rows with any non-finite entry are dropped (the library-wide convention) rather than
    silently contributing a ``nan`` p-value; the count lands in
    ``combined.details["n_dropped"]``. With ``k`` variables the smallest useful sample is
    ``k = 1``, but the KS test is meaningless below roughly 5-10 variables and Carlisle
    himself works with the full baseline table of a trial.
    """
    mat_m = as_float_matrix(means, "means")
    mat_s = as_float_matrix(sds, "sds")
    n_vars, n_groups = mat_m.shape
    if mat_s.shape != mat_m.shape:
        raise ValueError(
            f"sds must have the same shape as means; got {mat_s.shape} vs {mat_m.shape}"
        )
    mat_n = as_float_matrix(ns, "ns")
    if mat_n.shape == (1, n_groups) and n_vars > 1:
        mat_n = np.broadcast_to(mat_n, mat_m.shape)
    if mat_n.shape != mat_m.shape:
        raise ValueError(f"ns must have shape {mat_m.shape} or ({n_groups},); got {np.shape(ns)}")
    if n_groups < 2:
        raise ValueError(f"carlisle_test needs at least 2 groups (columns); got {n_groups}")

    keep = (
        np.all(np.isfinite(mat_m), axis=1)
        & np.all(np.isfinite(mat_s), axis=1)
        & np.all(np.isfinite(mat_n), axis=1)
    )
    n_dropped = int(n_vars - np.count_nonzero(keep))
    if not np.any(keep):
        raise ValueError("every variable has a non-finite summary statistic; nothing to test")

    per_variable = np.array(
        [balance_pvalues(mat_m[i], mat_s[i], mat_n[i]) for i in np.flatnonzero(keep)],
        dtype=float,
    )

    combined = combine_pvalues(per_variable, method, clip=clip)
    details = dict(combined.details)
    details["n_dropped"] = n_dropped
    details["n_variables"] = int(per_variable.size)
    details["n_groups"] = int(n_groups)
    details["mean_pvalue"] = float(np.mean(per_variable))
    details["share_pvalue_above_0p9"] = float(np.mean(per_variable > 0.9))
    combined = replace(combined, details=details)
    return CarlisleResult(
        per_variable=per_variable,
        combined=combined,
        ks_uniformity=_ks_too_balanced(per_variable),
    )

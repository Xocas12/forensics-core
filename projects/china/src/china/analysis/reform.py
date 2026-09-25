"""The unified-accounting reform as a natural experiment. **Stubs only: every function raises.**

If part of the provincial-sum minus national gap is misreporting rather than method, the gap
should contract discontinuously when the centre took over the calculation. That is the single
most interesting test in this project, and getting its date right is the whole of its
validity.

The dates, verified from the bureau's own question-and-answer page of 27 December 2019
(registry id ``nbs_qa_unified_accounting_2019_12_27``), corroborated by Xinhua on 13 November
2019 and China Daily on 7 January 2020:

* **June 2017** the reform plan is approved by the 36th meeting of the Central Leading Group
  for Comprehensively Deepening Reform;
* **early 2020** unified accounting is implemented, computing the **2019** annual regional
  product;
* before that, a graded system in place since 1985 in which provincial bureaus computed their
  own figures.

**So the break is at the 2019 data year.** Not 2017, which is when a decision was taken about
a future accounting round, and not 2020, which is when the 2019 figures were published. Using
2017 tests whether provinces changed their reporting in anticipation of a reform, which is a
different and much weaker hypothesis, and using it by accident is the most likely way to get
a wrong answer that looks right.

Two further complications from ``docs/known_traps.md``. The reform was announced, piloted and
then applied, and provinces revised their back-series at different times, so the design has to
be tested at plus and minus one year. And the fourth economic census lands in the same window,
which is a rebasing rather than a reporting change; a discontinuity at 2019 that is really the
census is a confound, not a finding.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = [
    "REFORM_APPROVAL_YEAR",
    "REFORM_FIRST_DATA_YEAR",
    "REFORM_IMPLEMENTED",
    "break_year_sensitivity",
    "placebo_break_years",
    "reform_discontinuity",
    "vintage_revision_at_reform",
]

#: The 36th meeting of the Central Leading Group approves the plan. **Not the break year.**
REFORM_APPROVAL_YEAR = 2017

#: The first data year computed under unified accounting. **This is the break year.**
REFORM_FIRST_DATA_YEAR = 2019

#: When the reform was executed: the 2019 figures were computed and published in early 2020.
REFORM_IMPLEMENTED = "2020-01"


def reform_discontinuity(
    gap: pd.Series,
    *,
    break_year: int = REFORM_FIRST_DATA_YEAR,
    bandwidth: int = 5,
    polynomial_degree: int = 1,
) -> Any:
    """Test for a discontinuity in the gap at the reform's first data year.

    A regression-discontinuity-in-time design: fit a local polynomial in the data year on
    each side of ``break_year`` within ``bandwidth`` years, and test the jump at the
    threshold.

    Parameters
    ----------
    gap : pandas.Series
        The gap by data year, from :func:`china.analysis.gap.provincial_national_gap` or
        :func:`china.analysis.gap.gap_in_growth_rates`, within one vintage.
    break_year : int, default :data:`REFORM_FIRST_DATA_YEAR`
        The threshold. The default is the verified first data year; passing 2017 tests a
        different hypothesis and the caller should say so.
    bandwidth : int, default 5
        Years each side.
    polynomial_degree : int, default 1
        Order of the local fit. Kept low on purpose: with roughly a decade of annual
        observations a high-order polynomial fits the break rather than the trend.

    Returns
    -------
    forensics_core.TestResult
        ``statistic`` is the estimated jump, ``details`` carry the fitted coefficients, the
        bandwidth, the effective sample each side and the break year used.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains, and it is a design problem before it is a coding one: this test has about
    ten annual observations, so its power is very low and its standard errors need care.
    Decide before running it whether the unit of observation is the year (about ten points) or
    the province-year (about 310, but serially and cross-sectionally dependent), and say which
    in the write-up.
    """
    raise NotImplementedError(
        "needs the gap series; and the unit of observation and inference for a ten-point "
        "annual design must be settled first"
    )


def break_year_sensitivity(
    gap: pd.Series,
    *,
    candidate_years: tuple[int, ...] = (2017, 2018, 2019, 2020),
    bandwidth: int = 5,
) -> pd.DataFrame:
    """Re-run the discontinuity at each candidate break year.

    The specification check ``docs/known_traps.md`` asks for. The reform was announced,
    piloted and applied over several years, and provinces revised back-series at different
    times, so a jump that only exists at exactly one year is a different kind of evidence
    from one that is strongest at 2019 and present either side.

    Parameters
    ----------
    gap : pandas.Series
        The gap by data year.
    candidate_years : tuple of int, default (2017, 2018, 2019, 2020)
        Break years to try: the approval year, the year before the first data year, the first
        data year, and the publication year.
    bandwidth : int, default 5
        Years each side.

    Returns
    -------
    pandas.DataFrame
        One row per candidate year with the estimated jump, its p-value and the sample sizes.

    Raises
    ------
    NotImplementedError
        Always.
    """
    raise NotImplementedError("needs reform_discontinuity")


def placebo_break_years(
    gap: pd.Series,
    *,
    placebo_years: tuple[int, ...] = (),
    bandwidth: int = 5,
) -> Any:
    """Compare the jump at the reform against jumps at years where nothing happened.

    Uses :func:`forensics_core.bunching.inference.placebo_test`: the p-value is the share of
    placebo years whose estimated jump is at least as large as the real one.

    Parameters
    ----------
    gap : pandas.Series
        The gap by data year.
    placebo_years : tuple of int, optional
        Years to use as placebos. Empty by default and required in practice, because the
        choice is substantive: a placebo year must be one with no census rebasing (2004,
        2008, 2013, 2018) and no boundary change, or it is not a placebo.
    bandwidth : int, default 5
        Years each side.

    Returns
    -------
    forensics_core.TestResult
        With the placebo distribution in ``details``.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: with roughly a decade of usable years, there may not be enough clean placebo
    years for this test to have any power. Establishing that is itself a result and should be
    reported rather than worked around.
    """
    raise NotImplementedError(
        "needs reform_discontinuity, and a defensible list of placebo years that excludes "
        "census rebasings and boundary changes"
    )


def vintage_revision_at_reform(
    panel: pd.DataFrame,
    *,
    before_vintage: str,
    after_vintage: str,
    series: str = "grp_nominal",
) -> pd.DataFrame:
    """How much each province's history was rewritten across the reform.

    The complement to the discontinuity test, and the one that uses the vintage column for
    what it is for. Rather than asking whether the gap jumps at 2019, this asks how much a
    province's *already published* figures for years before 2019 changed between an edition
    published before the reform and one published after it. A province that was inflating
    should have to give it back somewhere.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel holding both vintages.
    before_vintage, after_vintage : str
        Vintage labels, e.g. ``"csy2015"`` and ``"csy2024"``.
    series : str, default "grp_nominal"
        Series to compare.

    Returns
    -------
    pandas.DataFrame
        One row per province and overlapping data year, with both values, the revision and
        the revision as a share of the earlier value.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: extraction of at least two editions. The registry already shows what this
    will look like for the one province checked by hand: the 2015 edition reports Liaoning at
    28,626.58 for 2014, and the 2024 edition reports 30,209.4 for 2023, nine years later.
    Reproducing that contrast from extracted tables, rather than from the registry's prose, is
    the acceptance test for the extraction step.
    """
    raise NotImplementedError("needs at least two extracted yearbook vintages in the panel")

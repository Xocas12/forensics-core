"""The provincial-sum minus national gap. **Stubs only: every function raises.**

The project's headline quantity. Summed provincial gross regional product has historically
exceeded the national gross domestic product the bureau published, and the bureau's own
deputy head gave that gap as the reason for the accounting reform, saying the two were "too
far apart".

The gap is not evidence of misreporting on its own, and treating it as such is the first way
to get this project wrong. Three mechanical components have to be estimated and removed
first, per ``docs/known_traps.md``:

1. **Cross-province double counting.** Activity claimed by both the producing province and
   the head-office province.
2. **Different deflators.** Provinces and the centre deflate differently, so the nominal gap
   and the real-growth gap are different quantities and must never be mixed.
3. **Boundary changes and census rebasing.** Chongqing separating from Sichuan in 1997,
   Hainan from Guangdong in 1988, and the 2004, 2008, 2013 and 2018 economic censuses each
   put a level shift in the series that looks exactly like manipulation.

The reconciliation framing is Narasimhan and Jordache (2000), chapters 3 to 5, as implemented
in :mod:`forensics_core.reconcile`: treat the provincial measurements and the national total
as a flow network with a conservation constraint, reconcile by weighted least squares, and
read the standardised adjustments as per-province gross-error statistics. What that framing
buys over a raw subtraction is an answer to "which province", not just "how much".

**Vintage discipline.** Every function here takes a ``vintage`` and uses one. A provincial sum
from the 2015 edition against a national total from the 2024 edition measures the revision.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = [
    "gap_in_growth_rates",
    "mechanical_gap_components",
    "provincial_national_gap",
    "provincial_sum",
    "reconcile_to_national",
    "sector_gap_decomposition",
]


def provincial_sum(
    panel: pd.DataFrame,
    *,
    vintage: str,
    series: str = "grp_nominal",
) -> pd.Series:
    """Sum a series over the 31 provinces, by year, within one vintage.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel in :data:`china.clean.schema.PANEL_COLUMNS`.
    vintage : str
        The single vintage to sum. Required, not optional: summing across vintages adds a
        province's pre-revision and post-revision figures together.
    series : str, default "grp_nominal"
        Series name from :data:`china.clean.schema.SERIES`.

    Returns
    -------
    pandas.Series
        Indexed by year. The national row and any residual rows are excluded, and a year in
        which fewer than 31 provinces are present is reported through the series' ``attrs``
        rather than silently summed short.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the panel is empty until
    :func:`china.clean.yearbook.extract_table_image` exists, and the incomplete-year policy
    has to be decided (report and exclude, or report and sum) before this returns anything.
    """
    raise NotImplementedError(
        "needs a populated panel; blocked on yearbook table extraction, and on the "
        "incomplete-year policy for provinces missing from an edition"
    )


def provincial_national_gap(
    panel: pd.DataFrame,
    *,
    vintage: str,
    provincial_series: str = "grp_nominal",
    national_series: str = "gdp_national_nominal",
) -> pd.DataFrame:
    """The gap, by year, in nominal levels within one vintage.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage for both sides of the subtraction.
    provincial_series : str, default "grp_nominal"
        Series summed over provinces.
    national_series : str, default "gdp_national_nominal"
        Series taken from the national row.

    Returns
    -------
    pandas.DataFrame
        One row per year with ``provincial_sum``, ``national``, ``gap``, ``gap_share`` (the
        gap over the national total) and ``n_provinces``.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: :func:`provincial_sum`, plus a national series in the same vintage, which
    means extracting yearbook table 3-1 and not falling back on the World Bank series
    (see :mod:`china.clean.worldbank`).
    """
    raise NotImplementedError(
        "needs provincial_sum and a same-vintage national total from yearbook table 3-1"
    )


def gap_in_growth_rates(
    panel: pd.DataFrame,
    *,
    vintage: str,
    provincial_index: str = "grp_index_preceding_year",
) -> pd.DataFrame:
    """The gap in real growth rather than in nominal levels.

    A separate quantity from :func:`provincial_national_gap`, not a transformation of it: the
    provincial index is at constant prices with provincial deflators, the national growth
    rate at national deflators, and the difference between the two gaps is itself
    informative.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage to use.
    provincial_index : str, default "grp_index_preceding_year"
        Series holding the constant-price index, preceding year equal to 100.

    Returns
    -------
    pandas.DataFrame
        One row per year with the weighted provincial growth rate, the national growth rate
        and their difference, plus the weights used.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the weighting decision. Aggregating provincial real growth to a national
    figure needs previous-year weights, and whether those come from the same vintage or from
    the province's own base year changes the answer.
    """
    raise NotImplementedError(
        "needs the extracted index columns and a documented previous-year weighting scheme"
    )


def mechanical_gap_components(
    panel: pd.DataFrame,
    *,
    vintage: str,
    boundary_changes: Any = None,
    rebasing_years: Any = None,
) -> pd.DataFrame:
    """Estimate how much of the gap is method rather than misreporting.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage to use.
    boundary_changes : sequence of china.clean.provinces.BoundaryChange, optional
        Defaults to :data:`china.clean.provinces.BOUNDARY_CHANGES`.
    rebasing_years : sequence of int, optional
        Defaults to :data:`china.clean.provinces.REBASING_YEARS`.

    Returns
    -------
    pandas.DataFrame
        One row per year with a column per mechanical component and a ``residual`` column.
        Every component that cannot be estimated from available data is present and null
        rather than absent, so that the residual is never mistaken for a clean one.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains, and it is the hardest open question in the project: there is no free source
    for the cross-province double-counting component, and no deflator series by province in
    the registry. Until both exist, the residual is an upper bound on misreporting and has to
    be reported as one.
    """
    raise NotImplementedError(
        "no free source for cross-province double counting or provincial deflators is in "
        "data/SOURCES.yaml; the decomposition cannot be estimated, only bounded"
    )


def reconcile_to_national(
    panel: pd.DataFrame,
    *,
    vintage: str,
    year: int,
    sigma: Any = None,
) -> Any:
    """Reconcile the provincial measurements against the national total, and rank suspects.

    Implements the data-reconciliation framing of Narasimhan and Jordache (2000), chapters 3
    to 5, through :func:`forensics_core.reconcile.balance.reconcile` and the gross-error
    tests in :mod:`forensics_core.reconcile.gross_error`. The network has one constraint,
    that the 31 provincial flows sum to the national total, and the standardised adjustment
    for each province is the per-unit suspicion score.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel.
    vintage : str
        Vintage to reconcile within.
    year : int
        Data year.
    sigma : array-like, optional
        Measurement standard deviations per province. Defaults to a size-proportional
        specification, which must be documented wherever it is used: it is an assumption
        about which provinces are measured precisely, and it drives which province the
        gross-error test names.

    Returns
    -------
    forensics_core.reconcile.balance.ReconciliationResult
        Adjustments, standardised adjustments and constraint residuals.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the ``sigma`` specification has to be justified before this is run, because
    with one constraint and 31 measurements the result is entirely determined by the relative
    weights. A uniform sigma names the largest province every time.
    """
    raise NotImplementedError(
        "needs a populated panel and, first, a defensible measurement-error specification: "
        "with a single constraint the gross-error ranking is driven by sigma"
    )


def sector_gap_decomposition(
    panel: pd.DataFrame,
    *,
    vintage: str,
    year: int,
) -> pd.DataFrame:
    """Split the gap across the sectors the yearbook's table 3-9 breaks out.

    The point of this test is that the sectors differ in how hard they are to verify. The
    2024 table gives value added for agriculture, industry, construction, wholesale and
    retail, transport and storage, hotels and catering, financial intermediation, real estate
    and a residual "others". If the gap concentrates in financial intermediation, real estate
    and "others", that is a different story from a gap spread evenly.

    Parameters
    ----------
    panel : pandas.DataFrame
        Tidy panel, with sectoral series extracted.
    vintage : str
        Vintage to use.
    year : int
        Data year.

    Returns
    -------
    pandas.DataFrame
        One row per sector with the provincial sum, the national figure, the gap and the
        gap's share of the total gap.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    What remains: the sectoral series are not yet in
    :data:`china.clean.schema.SERIES`, because their exact column headings should be read off
    an extracted table rather than transcribed from a description of one.
    """
    raise NotImplementedError(
        "sectoral series are not defined in china.clean.schema.SERIES yet; add them from an "
        "extracted table 3-9, not from a description of it"
    )

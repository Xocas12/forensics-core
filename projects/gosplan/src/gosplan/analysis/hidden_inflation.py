"""Value series against the physical series beneath them. STUBS ONLY -- nothing is computed.

The question. If the value of industrial output grows faster than the physical quantities
that output consists of, and the gap is not explained by a genuine change in the mix of
goods, the difference was booked as real growth when it was price. This is the core of the
critique that Selyunin and Khanin published in 1987 and that Khanin developed afterwards, and
``docs/known_traps.md`` trap 4 is emphatic that the divergence is **a finding, not noise**:
nothing in this module may "correct" a value series onto a physical one.

The comparison is not straightforward, and three things have to be handled before the gap
means anything.

**Index numbers.** Soviet growth rates swing enormously with base-year weights: early-year
(1926/27) prices weight the goods that subsequently expanded most and produce spectacular
growth, late-year weights produce modest growth. This is the Gerschenkron effect
(``known_traps.md`` trap 3), and any result has to be shown robust across weighting schemes.
A physical-quantity index is itself a weighted aggregate and inherits the same problem.

**The currency reform.** A value series crossing 1961 is rescaled by ten. The transcription
schema forces the basis to be declared per cell; this module must refuse to combine cells
whose ``currency_basis`` differs rather than converting silently.

**Definitional revisions.** Gross output, net output, normative net output and the 1988 move
toward net material product are different quantities. ``known_traps.md`` trap 5: never splice
across an unrecorded change.

The comparison series available now are the Western reconstructions in the registry -- the
World Bank archive of Easterly and Fischer (1995), which juxtaposes official net material
product, Khanin's alternative and the CIA's GNP estimate, and Harrison's Bergson-school
compilation. Trap 8 applies: those are alternative reconstructions to be reconciled, not
labels.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import pandas as pd
from forensics_core._types import TestResult

__all__ = [
    "compare_reconstructions",
    "implied_deflator",
    "physical_value_divergence",
    "weighting_robustness",
]


def physical_value_divergence(
    value_index: pd.Series,
    physical_index: pd.Series,
    *,
    base_period: str | int | None = None,
    currency_basis: str | None = None,
) -> pd.DataFrame:
    """The gap between a value aggregate and the physical quantities underneath it.

    Parameters
    ----------
    value_index : pandas.Series
        Value of output, indexed by period. Must be internally consistent in currency basis;
        the caller states which one in ``currency_basis`` and the implementation must refuse
        a series that mixes bases.
    physical_index : pandas.Series
        A quantity index built from physical output series over the same periods, on the same
        base.
    base_period : str or int, optional
        Period both series are normalised to. When None, the first period common to both.
    currency_basis : str, optional
        ``"old_roubles"`` or ``"new_roubles"``, from the transcription schema. Required for a
        series that crosses 1961.

    Returns
    -------
    pandas.DataFrame
        Per period: both indices, their ratio, the log gap, and the annualised divergence.

    Raises
    ------
    NotImplementedError
        Always.

    References
    ----------
    Selyunin, V. and G. Khanin, 1987. "Lukavaia tsifra", *Novyi mir* no. 2. TO CONFIRM: the
    registry's entry for this article is marked unverified -- the text fetched for it turned
    out to be commentary quoting the article, not the article -- so the bibliographic details
    here come from search results and must be checked against a copy before citation.

    Notes
    -----
    Remaining: a transcribed value series and a physical quantity index, plus a decision on
    how the physical index is weighted (see :func:`weighting_robustness`).
    """
    raise NotImplementedError(
        "needs a transcribed value series and a physical quantity index on a common base"
    )


def implied_deflator(
    value_index: pd.Series,
    physical_index: pd.Series,
    official_deflator: pd.Series | None = None,
) -> pd.DataFrame:
    """The price change implied by the value and quantity series, against the official one.

    The implied deflator is the value index divided by the quantity index. Where it exceeds
    the officially reported price change, the excess is the quantity that the hidden-inflation
    argument is about. Reporting both, and their difference, is the honest presentation: the
    implied deflator is not "the true deflator", it is what the two published series jointly
    imply.

    Parameters
    ----------
    value_index, physical_index : pandas.Series
        As in :func:`physical_value_divergence`.
    official_deflator : pandas.Series, optional
        The published price index for the same aggregate, where one exists.

    Returns
    -------
    pandas.DataFrame
        Implied deflator, official deflator and their ratio, per period.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: locate an official price index for the same aggregate and the same periods;
    the registry does not currently record one.
    """
    raise NotImplementedError(
        "implied deflator; needs both indices and, for the comparison, an official price index"
    )


def weighting_robustness(
    quantities: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    schemes: Sequence[Literal["laspeyres", "paasche", "fisher"]] = (
        "laspeyres",
        "paasche",
        "fisher",
    ),
    base_periods: Sequence[str | int] = (),
) -> pd.DataFrame:
    """Recompute the quantity index under several weighting schemes and base years.

    The Gerschenkron effect means a single index number is not a result. This function exists
    so that the robustness check is a required step rather than an appendix: a divergence that
    survives every scheme is evidence, and one that does not is an artefact of the weights.

    Parameters
    ----------
    quantities : pandas.DataFrame
        Physical output by product (columns) and period (index).
    prices : pandas.DataFrame
        Prices on the same axes, in a single stated currency basis.
    schemes : sequence of str
        Index formulae to compute.
    base_periods : sequence
        Base years to compute each scheme against, e.g. an early and a late year, which is
        where the Gerschenkron spread shows up.

    Returns
    -------
    pandas.DataFrame
        One column per (scheme, base) combination, indexed by period.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: a transcribed price matrix. Soviet published prices at product level are a
    transcription target that has not been located; without one, only physical quantity
    comparisons are possible and the index-number robustness check cannot be run at all.
    """
    raise NotImplementedError(
        "index-number robustness; needs a product-level price matrix, which is not yet located"
    )


def compare_reconstructions(
    official: pd.Series,
    reconstructions: pd.DataFrame,
    *,
    align_definitions: bool = True,
) -> tuple[pd.DataFrame, TestResult]:
    """Set the official series against the Western reconstructions of the same quantity.

    The registry holds three reconstructions in machine-readable form covering 1928-1987 --
    official net material product, Khanin's alternative, and the CIA's GNP estimate -- in the
    Easterly and Fischer (1995) archive. They disagree with each other, and the spread is the
    point: it bounds how much the choice of adjustment matters.

    Parameters
    ----------
    official : pandas.Series
        The officially reported series.
    reconstructions : pandas.DataFrame
        One column per alternative estimate, on the same period index.
    align_definitions : bool, default True
        Whether to attempt to put the series on a common definition before comparing. When
        True the implementation must report what it did; an undocumented alignment is worse
        than none.

    Returns
    -------
    (pandas.DataFrame, TestResult)
        Per-period comparison, and a test of whether the official series lies systematically
        outside the range of the reconstructions.

    Raises
    ------
    NotImplementedError
        Always.

    References
    ----------
    Easterly, W. and S. Fischer, 1995. The Soviet economic decline. *World Bank Economic
    Review* 9(3), 341-371. Data archive registered as ``wb_soviet_economic_decline``; the
    archive's README attributes the 1928-1987 series to Gomulka and Schaffer (1991).

    Notes
    -----
    Remaining: parse the archive's MicroTSP ``.DB`` and Lotus ``.WK1`` files, and settle what
    "systematically outside" means before testing it. ``docs/known_traps.md`` trap 8: these
    are not labels, and a divergence does not tell you which side is wrong.
    """
    raise NotImplementedError(
        "reconstruction comparison; needs the World Bank archive parsed and a stated definition "
        "of systematic divergence"
    )

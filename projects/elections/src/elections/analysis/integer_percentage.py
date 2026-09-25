"""Anchor 1: excess mass at integer percentages (the sawtooth). STUBS ONLY.

Method
------
Kobak, D., S. Shpilkin and M. S. Pshenichnikov, 2016. "Integer percentages as electoral
falsification fingerprints", *Annals of Applied Statistics* 10(1), 54-73. Turnout and vote
share reported as percentages pile up on whole numbers far more often than binomial noise
allows, and the excess concentrates in particular regions.

The estimator is :func:`forensics_core.digits.integer_pct.integer_excess`, whose null redraws
each station's numerator as ``Binomial(registered, observed share)``; that is the paper's own
null, so the functions here choose inputs and strata and do not reimplement statistics.

What must be reproduced (``docs/validation_anchors.md``, Tier 1 item 1)
----------------------------------------------------------------------
1. A significant positive excess nationally in 2011 and in 2018.
2. The excess concentrated in the regions the paper names.
3. The excess vanishing on the Poland 2010 and Spain 2011 control tables in the same
   supplement. This last one is what shows the test is not detecting arithmetic, and it is
   the number the ``gosplan`` project will inherit, since it cannot compute a false-positive
   rate for itself.

The trap this must not fall into (``docs/known_traps.md``, trap 1)
------------------------------------------------------------------
Small stations land on integer percentages honestly, and about 18 per cent of the 2011 sample
has 250 or fewer registered voters. A pooled national statistic is therefore not a result
until it is shown to survive size conditioning: hence
:func:`integer_percentage_excess_by_size_band`, and hence the requirement that any headline
number be reported next to the count of stations the denominator floor removed.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from forensics_core.digits import IntegerExcessResult

__all__ = [
    "PERCENTAGE_QUANTITIES",
    "integer_percentage_excess",
    "integer_percentage_excess_by_region",
    "integer_percentage_excess_by_size_band",
]

#: The two percentages the paper analyses, as columns of the derived tidy frame.
PERCENTAGE_QUANTITIES = ("turnout_boxes", "winner_share")

Quantity = Literal["turnout_boxes", "winner_share"]


def integer_percentage_excess(
    tidy: pd.DataFrame,
    *,
    election: str,
    quantity: Quantity = "turnout_boxes",
    tolerance: float = 0.05,
    min_denominator: int = 100,
    n_mc: int = 200,
    seed: int | None = None,
) -> IntegerExcessResult:
    """Excess mass at integer percentages for one election, nationally.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame from :func:`elections.clean.build_tidy`. Percentages are computed here
        from the canonical columns rather than taken from the frame, so that the denominator
        used is unambiguous and recorded in the result's ``settings``.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    quantity : {"turnout_boxes", "winner_share"}, default "turnout_boxes"
        Which percentage to test. ``turnout_boxes`` is ballots in boxes over registered
        voters, with the registered voters as the binomial denominator; ``winner_share`` is
        the winner's votes over valid plus invalid ballots, with that total as the
        denominator.
    tolerance : float, default 0.05
        Half-width, in percentage points, of the window that counts as "on an integer".
    min_denominator : int, default 100
        Stations with a smaller denominator are excluded and counted.
    n_mc : int, default 200
        Monte Carlo replications of the binomial null.
    seed : int, optional
        Seeds the generator.

    Returns
    -------
    forensics_core.digits.IntegerExcessResult
        As returned by :func:`forensics_core.digits.integer_pct.integer_excess`, with the
        election, the quantity and the denominator column added to ``settings``.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining: select the election's rows, build the percentage and its binomial "
        "denominator for the chosen quantity, and pass them to "
        "forensics_core.digits.integer_pct.integer_excess."
    )


def integer_percentage_excess_by_region(
    tidy: pd.DataFrame,
    *,
    election: str,
    quantity: Quantity = "turnout_boxes",
    tolerance: float = 0.05,
    min_denominator: int = 100,
    n_mc: int = 200,
    seed: int | None = None,
) -> pd.DataFrame:
    """The same excess computed within each federal subject, for the regional ranking.

    Anchor 1 item 2 is a claim about *which* regions carry the excess, so the comparison must
    be a ranking rather than a count of regions that reject: with roughly 85 regions, several
    will reject by chance (``docs/known_traps.md``, trap 6).

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    quantity : {"turnout_boxes", "winner_share"}, default "turnout_boxes"
        As in :func:`integer_percentage_excess`.
    tolerance, min_denominator, n_mc, seed
        As in :func:`integer_percentage_excess`.

    Returns
    -------
    pandas.DataFrame
        One row per region, as returned by
        :func:`forensics_core.digits.integer_pct.integer_excess_by_group`, sorted by excess
        per unit descending.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining: group the election's rows by region and delegate to "
        "forensics_core.digits.integer_pct.integer_excess_by_group, then sort for the ranking."
    )


def integer_percentage_excess_by_size_band(
    tidy: pd.DataFrame,
    *,
    election: str,
    quantity: Quantity = "turnout_boxes",
    tolerance: float = 0.05,
    min_denominator: int = 100,
    n_mc: int = 200,
    seed: int | None = None,
) -> pd.DataFrame:
    """The excess within each precinct-size band: the trap-1 control.

    The headline national number is not interpretable on its own. This table is what shows
    whether the excess is present among large stations, where integer percentages are not
    arithmetically favoured, or only among small ones, where they are.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    quantity : {"turnout_boxes", "winner_share"}, default "turnout_boxes"
        As in :func:`integer_percentage_excess`.
    tolerance, min_denominator, n_mc, seed
        As in :func:`integer_percentage_excess`.

    Returns
    -------
    pandas.DataFrame
        One row per band of :data:`elections.features.size.SIZE_BAND_LABELS`, with the fields
        of :class:`forensics_core.digits.IntegerExcessResult` plus the band's station count
        and the number of stations the denominator floor removed within it.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining: iterate elections.features.size.iter_size_strata and run "
        "integer_percentage_excess within each band, carrying the per-band n and exclusions."
    )

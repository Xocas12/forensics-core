"""Anchor 2: the comet tail in the turnout / vote-share plane. STUBS ONLY.

Method
------
Sergey Shpilkin's estimator, described in Kobak, D., S. Shpilkin and M. S. Pshenichnikov,
2016. "Integer percentages as electoral falsification fingerprints", *Annals of Applied
Statistics* 10(1), 54-73, and in the same authors' *Significance* article of that year. In the
two-dimensional histogram of station turnout against the winner's vote share, honest stations
form one cloud while a tail stretches towards the (100 per cent, 100 per cent) corner; the
estimator reads the votes in that tail, above the level implied by the distribution at
ordinary turnout, as a count of anomalous votes.

What must be reproduced (``docs/validation_anchors.md``, Tier 1 item 2)
----------------------------------------------------------------------
The anchor is marked **TO CONFIRM** and it is the reason these are stubs and not code. Neither
the exact estimator definition nor the published anomalous-vote counts for 2011 and 2018 were
read from a primary source during scaffolding. The papers have to be read first; implementing
a plausible-looking tail estimator before that would produce a number with nothing to check it
against, which is the failure mode this whole project is organised to avoid. The signature
below therefore fixes what the function consumes and returns, not how it computes.

Known fragility (``docs/known_traps.md``, trap 3)
-------------------------------------------------
The estimate is sensitive to which regions are in the sample: a handful of them can carry it.
Hence :func:`comet_tail_leave_one_region_out`, and hence the requirement that any national
count be reported with and without the largest contributors and at territorial-commission as
well as station level.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from forensics_core import TestResult

__all__ = [
    "AGGREGATION_LEVELS",
    "TURNOUT_BASES",
    "comet_tail_estimate",
    "comet_tail_leave_one_region_out",
]

#: The two documented turnout definitions (``docs/data_dictionary.md``).
TURNOUT_BASES = ("boxes", "issued")

#: Levels the estimate must be reported at, per trap 3.
AGGREGATION_LEVELS = ("uik", "tik")

TurnoutBasis = Literal["boxes", "issued"]
AggregationLevel = Literal["uik", "tik"]


def comet_tail_estimate(
    tidy: pd.DataFrame,
    *,
    election: str,
    turnout_basis: TurnoutBasis = "boxes",
    level: AggregationLevel = "uik",
    bin_width: float = 0.5,
    min_denominator: int = 100,
    seed: int | None = None,
) -> TestResult:
    """Anomalous-vote count from the turnout / vote-share tail, for one election.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame from :func:`elections.clean.build_tidy`.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    turnout_basis : {"boxes", "issued"}, default "boxes"
        Which documented turnout definition to use;
        :func:`elections.clean.derive.turnout_ballots_in_boxes` is the default because it is
        the one the literature analyses.
    level : {"uik", "tik"}, default "uik"
        Aggregate to territorial commissions before estimating, or stay at station level.
    bin_width : float, default 0.5
        Width, in percentage points, of the turnout bins the tail is read over.
    min_denominator : int, default 100
        Stations below this many registered voters are excluded, as in the integer-percentage
        test and following the exclusion rule of Klimek et al. (2012).
    seed : int, optional
        Seeds any resampling used for the interval.

    Returns
    -------
    forensics_core.TestResult
        ``statistic`` is the estimated anomalous vote count; ``details`` must carry the
        counterfactual vote share used, the turnout range treated as the tail, the excluded
        station count, and the estimator definition actually implemented, with its citation.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Blocked on reading the primary source: the estimator definition and the published "
        "2011 and 2018 anomalous-vote counts are still TO CONFIRM in docs/validation_anchors.md."
    )


def comet_tail_leave_one_region_out(
    tidy: pd.DataFrame,
    *,
    election: str,
    turnout_basis: TurnoutBasis = "boxes",
    level: AggregationLevel = "uik",
    bin_width: float = 0.5,
    min_denominator: int = 100,
    seed: int | None = None,
) -> pd.DataFrame:
    """The national estimate recomputed with each region removed in turn.

    Trap 3 made operational: if dropping one federal subject moves the national count by a
    large fraction, the count is a statement about that subject and not about the country.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    turnout_basis, level, bin_width, min_denominator, seed
        As in :func:`comet_tail_estimate`.

    Returns
    -------
    pandas.DataFrame
        One row per region omitted, with the recomputed statistic, its change from the
        all-regions estimate, and that change as a share of it, sorted by absolute change
        descending.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining, once comet_tail_estimate exists: loop the regions, drop each, recompute, "
        "and tabulate the change against the all-regions estimate."
    )

"""Anchor 3: a second mode in the turnout distribution near complete turnout. STUBS ONLY.

Method
------
Klimek, P., Y. Yegorov, R. Hanel and S. Thurner, 2012. "Statistical detection of systematic
election irregularities", *PNAS* 109(41), 16469-16473. The distribution of station turnout
shows a second mode close to 100 per cent that honest elections do not produce, and the
authors fit a parametric model of incremental and extreme ballot stuffing to the joint
turnout / vote-share distribution.

Two details from the paper are already confirmed and are reflected in the signatures below:
units with an electorate smaller than 100 are excluded, to keep very small communities from
producing extreme turnout and vote rates as artefacts; and the authors report that their
results do not depend much on the level of aggregation. Both were read from the PubMed Central
full text (registry entry ``pmc_klimek_2012``).

What must be reproduced (``docs/validation_anchors.md``, Tier 1 item 3)
----------------------------------------------------------------------
A second mode near complete turnout in 2011 and 2018, located where the paper locates it.
Whether the paper's supplementary material holds its underlying data or only figures was
settled after that document was written: it holds neither data nor code, only an index page
and one PDF, so the replication runs on the precinct files acquired here and no Klimek data is
needed. The supplementary PDF itself is behind a bot block and remains a human task
(``data/ACCESS_NOTES.md``).

The caveat that belongs inside the result (``docs/known_traps.md``, trap 2)
--------------------------------------------------------------------------
Bimodality alone is not a signature. Genuine heterogeneity - urban against rural, republics
with different mobilisation patterns - produces a second mode in an honest election too. The
claim is about the joint distribution of turnout and vote share and about where the second
mode sits, which is why :func:`turnout_mode_locations` returns the location and not only a
test of unimodality, and why a bimodality result that is not accompanied by the joint
distribution is not evidence of anything.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from forensics_core import TestResult

__all__ = [
    "KLIMEK_MIN_ELECTORATE",
    "turnout_bimodality_test",
    "turnout_mode_locations",
]

#: The exclusion rule stated in the paper's Data and Methods section: units with an electorate
#: smaller than 100 are excluded.
KLIMEK_MIN_ELECTORATE = 100

TurnoutBasis = Literal["boxes", "issued"]


def turnout_bimodality_test(
    tidy: pd.DataFrame,
    *,
    election: str,
    turnout_basis: TurnoutBasis = "boxes",
    min_electorate: int = KLIMEK_MIN_ELECTORATE,
    bin_width: float = 0.5,
    n_boot: int = 999,
    seed: int | None = None,
) -> TestResult:
    """Test the station turnout distribution for a second mode, for one election.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame from :func:`elections.clean.build_tidy`.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    turnout_basis : {"boxes", "issued"}, default "boxes"
        Which documented turnout definition to use.
    min_electorate : int, default 100
        Stations with fewer registered voters are excluded, following the paper.
    bin_width : float, default 0.5
        Width, in percentage points, of the turnout histogram bins.
    n_boot : int, default 999
        Resamples used for the null distribution of the statistic.
    seed : int, optional
        Seeds the generator.

    Returns
    -------
    forensics_core.TestResult
        ``details`` must record the excluded-station count, the bin width, the statistic's
        definition, and the trap-2 caveat, so that the result cannot be quoted without the
        condition under which it means anything.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining: choose and cite a unimodality statistic, apply the electorate floor, and "
        "compute the null by resampling; the mode location is reported by turnout_mode_locations."
    )


def turnout_mode_locations(
    tidy: pd.DataFrame,
    *,
    election: str,
    turnout_basis: TurnoutBasis = "boxes",
    min_electorate: int = KLIMEK_MIN_ELECTORATE,
    bin_width: float = 0.5,
    weight_by: Literal["stations", "registered"] = "registered",
    seed: int | None = None,
) -> pd.DataFrame:
    """Where the modes are, in turnout and in the joint turnout / vote-share plane.

    The anchor is about the *location* of the second mode, so the location is the output,
    not a by-product of a test. Reported both unweighted, one row per station, and weighted by
    registered voters, because a mode carried by a few large stations and a mode carried by
    many small ones are different claims.

    Parameters
    ----------
    tidy : pandas.DataFrame
        The tidy frame.
    election : str
        One of :data:`elections.clean.schema.ELECTIONS`.
    turnout_basis : {"boxes", "issued"}, default "boxes"
        Which documented turnout definition to use.
    min_electorate : int, default 100
        As in :func:`turnout_bimodality_test`.
    bin_width : float, default 0.5
        Histogram bin width in percentage points.
    weight_by : {"stations", "registered"}, default "registered"
        Weight each station equally, or by its electorate.
    seed : int, optional
        Seeds any smoothing bandwidth selection that resamples.

    Returns
    -------
    pandas.DataFrame
        One row per detected mode, with its turnout, the winner's vote share at it, the mass
        it carries and the weighting used.

    Raises
    ------
    NotImplementedError
        Always, for now.
    """
    raise NotImplementedError(
        "Remaining: estimate the turnout density and the joint turnout / vote-share density, "
        "and locate their modes under both weightings."
    )

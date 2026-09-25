"""Replication targets, one module per validation anchor. **Every function here is a stub.**

``docs/validation_anchors.md`` names three published signatures and the order to attempt them:

1. :mod:`elections.analysis.integer_percentage` - excess mass at integer percentages
   (Kobak, Shpilkin & Pshenichnikov 2016). The cleanest anchor and the first target, and the
   only one whose false-positive control data is already in the registry.
2. :mod:`elections.analysis.comet_tail` - the turnout / vote-share tail and its
   anomalous-vote count (Shpilkin). Blocked on reading the primary source: the estimator
   definition and the published counts are still marked TO CONFIRM.
3. :mod:`elections.analysis.turnout_bimodality` - a second mode near complete turnout
   (Klimek, Yegorov, Hanel & Thurner 2012).

No analysis has been run in this tree and no findings exist in it. Each function fixes its
signature, cites its method and its anchor, and raises ``NotImplementedError`` naming what
remains. The signatures are the contract: they consume the tidy frame from
:func:`elections.clean.build_tidy` and return ``forensics_core`` result types, so that a
detector calibrated here can be scored by :mod:`forensics_core.eval.harness` and transferred
to the projects that have no ground truth.
"""

from elections.analysis.comet_tail import (
    comet_tail_estimate,
    comet_tail_leave_one_region_out,
)
from elections.analysis.integer_percentage import (
    integer_percentage_excess,
    integer_percentage_excess_by_region,
    integer_percentage_excess_by_size_band,
)
from elections.analysis.turnout_bimodality import (
    turnout_bimodality_test,
    turnout_mode_locations,
)

__all__ = [
    "comet_tail_estimate",
    "comet_tail_leave_one_region_out",
    "integer_percentage_excess",
    "integer_percentage_excess_by_region",
    "integer_percentage_excess_by_size_band",
    "turnout_bimodality_test",
    "turnout_mode_locations",
]

"""Bunching at incentive discontinuities: polynomial counterfactual densities, notch vs kink
specifications, candidate-notch scanning, and bootstrap / placebo inference.

The unifying hypothesis of the programme is that distortion concentrates at discontinuities
in the incentive function. "Find the notch, estimate excess mass around it" is the
first-class operation here: see :func:`forensics_core.bunching.notch.scan_candidate_notches`.

Method sources
--------------
Chetty, Friedman, Olsen and Pistaferri (2011, *QJE* 126(2): 749-804) for the binned-count
polynomial counterfactual, the normalised excess mass, the integration constraint and the
residual bootstrap; Saez (2010, *AEJ: Economic Policy* 2(3): 180-212) for bunching at kinks;
Kleven and Waseem (2013, *QJE* 128(2): 669-723) for notches and dominated regions; Kleven
(2016, *Annual Review of Economics* 8: 435-464) for the survey and notation.
"""

from forensics_core.bunching.density import (
    BunchingResult,
    BunchingSide,
    bin_around,
    bunching_estimator,
)
from forensics_core.bunching.inference import (
    BootstrapResult,
    bootstrap_bunching,
    permutation_test,
    placebo_test,
)
from forensics_core.bunching.notch import (
    SCAN_COLUMNS,
    Kink,
    Notch,
    estimate_kink,
    estimate_notch,
    scan_candidate_notches,
)

__all__ = [
    "SCAN_COLUMNS",
    "BootstrapResult",
    "BunchingResult",
    "BunchingSide",
    "Kink",
    "Notch",
    "bin_around",
    "bootstrap_bunching",
    "bunching_estimator",
    "estimate_kink",
    "estimate_notch",
    "permutation_test",
    "placebo_test",
    "scan_candidate_notches",
]

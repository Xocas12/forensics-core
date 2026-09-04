"""forensics_core — shared methods for statistical forensics of strategically reported data.

Subpackages
-----------
digits       Benford / terminal-digit / integer-percentage tests.
bunching     Excess mass at incentive discontinuities (notches and kinks).
dispersion   Underdispersion (too little noise) and too-good-to-be-true balance.
reconcile    Flow-conservation reconciliation and gross-error detection.
labels       Positive-unlabeled learning.
eval         Rank metrics and the cross-project evaluation harness.
provenance   Fetch logging, checksums, SOURCES.yaml registry, contact/rate-limit policy.

See INTERFACES.md at the package root for the contract every module honours, and
docs/method_transfer.md at the repository root for how a method calibrated on one project
is carried to another.
"""

from forensics_core._types import TestResult

__all__ = ["TestResult", "__version__"]
__version__ = "0.1.0"

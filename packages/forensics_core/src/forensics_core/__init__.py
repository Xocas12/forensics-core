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

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from forensics_core._types import TestResult

__all__ = ["TestResult", "__version__"]

# Read from installed metadata rather than a literal. The literal had drifted to 0.1.0 while
# pyproject.toml said 0.3.0 and core-v0.2.0 and core-v0.3.0 had both been tagged, so anything
# stamping a provenance record with __version__ would have recorded a release that did not
# contain the code it ran. A stored power atlas does exactly that.
try:
    __version__ = _version("forensics-core")
except PackageNotFoundError:  # pragma: no cover - running from a source tree, not installed
    __version__ = "0.0.0+unknown"

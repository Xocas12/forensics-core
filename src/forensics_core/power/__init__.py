"""Detection power as a function of sample size, effect size and aggregation.

The reusable artefact of the programme. A detector is only as useful as the sample size it
works at, and the target project has three orders of magnitude fewer units than the
calibration projects.
"""

from forensics_core.power.atlas import (
    ATLAS_COLUMNS,
    DEFAULT_SAMPLE_SIZES,
    AtlasError,
    PowerSpec,
    detectable,
    load_atlas,
    minimum_detectable_effect,
    power_curve,
    save_atlas,
)

__all__ = [
    "ATLAS_COLUMNS",
    "DEFAULT_SAMPLE_SIZES",
    "AtlasError",
    "PowerSpec",
    "detectable",
    "load_atlas",
    "minimum_detectable_effect",
    "power_curve",
    "save_atlas",
]

"""Too little noise is a fabrication signal. Reported series with less variance than the
physical process permits are impossible regardless of level (underdispersion), and groups
that balance too well are suspicious (Carlisle). Treat these as first-class, not as an
afterthought to the digit tests."""

from forensics_core.dispersion.carlisle import (
    CarlisleResult,
    balance_pvalues,
    carlisle_test,
    combine_pvalues,
)
from forensics_core.dispersion.underdispersion import (
    dispersion_index,
    implied_variance_floor,
    residual_underdispersion,
    rolling_variance_floor,
    smoothness_ratio,
    too_smooth_test,
    variance_floor_test,
)

__all__ = [
    "CarlisleResult",
    "balance_pvalues",
    "carlisle_test",
    "combine_pvalues",
    "dispersion_index",
    "implied_variance_floor",
    "residual_underdispersion",
    "rolling_variance_floor",
    "smoothness_ratio",
    "too_smooth_test",
    "variance_floor_test",
]

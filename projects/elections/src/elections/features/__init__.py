"""Per-station features. Currently one family: precinct size and its consequences.

Size is not an optional covariate here. ``docs/known_traps.md`` trap 1 says an
integer-percentage test that ignores station size measures arithmetic rather than fraud, and
neither results file carries a station type, so for 2011 size conditioning is the only control
that exists. Everything in :mod:`elections.features.size` serves that.
"""

from elections.features.size import (
    DEFAULT_MIN_DENOMINATOR,
    SIZE_BAND_EDGES,
    SIZE_BAND_LABELS,
    FloorSummary,
    add_size_band,
    denominator_floor_summary,
    exact_integer_share,
    iter_size_strata,
    percentage_resolution,
    size_band,
    size_band_counts,
)

__all__ = [
    "DEFAULT_MIN_DENOMINATOR",
    "SIZE_BAND_EDGES",
    "SIZE_BAND_LABELS",
    "FloorSummary",
    "add_size_band",
    "denominator_floor_summary",
    "exact_integer_share",
    "iter_size_strata",
    "percentage_resolution",
    "size_band",
    "size_band_counts",
]

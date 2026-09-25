"""Precinct size: the covariate the integer-percentage test cannot be run without.

Trap 1 in ``docs/known_traps.md``. A station with 100 registered voters can only report
turnouts that are whole percentages, so it lands on an integer with certainty and no
dishonesty at all. In the 2011 file 4,228 stations have 100 or fewer registered voters and
17,299 have 250 or fewer: about 18 per cent of the sample. An integer-percentage test run over
the pooled sample without conditioning on size measures the arithmetic of small denominators.

There is no station-type column in either results file, and the station number is a bare
integer, so military, hospital, prison and remote stations - the usual small cases - cannot be
identified from the data at hand. Size is therefore not merely the convenient control; for
2011 it is the only one available. (For 2018 the commission register acquired by
``elections.acquire.commissions`` can supply names and addresses, at the cost of a fuzzy join;
for 2011 nothing can.)

Nothing here is inference. Two of these functions are pure arithmetic on a precinct size and
do not look at any votes at all, and the rest are bookkeeping: which band a station falls in,
how many fall below a floor, and how to iterate over the bands.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

__all__ = [
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

#: Upper edges of the size bands, in registered voters; each band is ``(previous, edge]``.
#:
#: The first two edges are the documented ones: 100 is the denominator at which every
#: attainable percentage is an integer, and is also the exclusion threshold used by Klimek et
#: al. (2012) and the default ``min_denominator`` of
#: :func:`forensics_core.digits.integer_pct.integer_excess`; 250 is the second figure quoted
#: in ``docs/data_dictionary.md`` and ``docs/known_traps.md``. The remaining edges are round
#: numbers spanning the observed range (median 996, maximum 22,671 in 2011) and carry no
#: authority - change them freely, but report which edges a result was computed on.
SIZE_BAND_EDGES: tuple[float, ...] = (0.0, 100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0, np.inf)

#: Labels for the bands defined by :data:`SIZE_BAND_EDGES`.
SIZE_BAND_LABELS: tuple[str, ...] = (
    "1-100",
    "101-250",
    "251-500",
    "501-1000",
    "1001-2000",
    "2001-5000",
    "5001+",
)

#: The default denominator floor: the value used by ``forensics_core`` and the electorate
#: exclusion rule stated in Klimek, Yegorov, Hanel & Thurner (2012), PNAS 109(41), Data and
#: Methods ("units with an electorate smaller than 100 are excluded").
DEFAULT_MIN_DENOMINATOR = 100


def size_band(
    registered: ArrayLike,
    *,
    edges: tuple[float, ...] = SIZE_BAND_EDGES,
    labels: tuple[str, ...] = SIZE_BAND_LABELS,
) -> pd.Categorical:
    """Bucket precinct sizes into ordered bands.

    Parameters
    ----------
    registered : array-like
        Registered voters per station. Nulls and non-positive sizes get no band.
    edges : tuple of float, optional
        Band upper edges; see :data:`SIZE_BAND_EDGES`. Must be increasing and one longer than
        ``labels``.
    labels : tuple of str, optional
        Band labels, in the same order.

    Returns
    -------
    pandas.Categorical
        Ordered categorical, one entry per input, ``NaN`` where the size is null or not
        positive.

    Raises
    ------
    ValueError
        If ``edges`` and ``labels`` do not correspond.
    """
    if len(edges) != len(labels) + 1:
        raise ValueError(f"{len(edges)} edges need {len(edges) - 1} labels, got {len(labels)}")
    values = pd.Series(registered).astype("Float64").to_numpy(dtype="float64", na_value=np.nan)
    return pd.cut(values, bins=list(edges), labels=list(labels), right=True, ordered=True)


def add_size_band(
    frame: pd.DataFrame,
    *,
    column: str = "registered",
    out_column: str = "size_band",
    edges: tuple[float, ...] = SIZE_BAND_EDGES,
    labels: tuple[str, ...] = SIZE_BAND_LABELS,
) -> pd.DataFrame:
    """Return a copy of ``frame`` with an ordered ``size_band`` column added.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame.
    column : str, default "registered"
        Size column to band.
    out_column : str, default "size_band"
        Name of the column to add.
    edges, labels : optional
        As in :func:`size_band`.

    Returns
    -------
    pandas.DataFrame
        Copy of ``frame`` with the band column appended.
    """
    if column not in frame.columns:
        raise KeyError(f"frame has no column {column!r}")
    out = frame.copy()
    out[out_column] = pd.Series(
        size_band(frame[column], edges=edges, labels=labels), index=frame.index
    )
    return out


def size_band_counts(
    frame: pd.DataFrame,
    *,
    column: str = "registered",
    by: str | None = "election",
    edges: tuple[float, ...] = SIZE_BAND_EDGES,
    labels: tuple[str, ...] = SIZE_BAND_LABELS,
) -> pd.DataFrame:
    """How many stations fall in each size band, and what share of the sample they are.

    Descriptive bookkeeping for the data audit, not a result: it is the table that tells a
    reader how much of the sample the denominator floor will remove.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame.
    column : str, default "registered"
        Size column.
    by : str or None, default "election"
        Extra grouping column; pass ``None`` to pool.
    edges, labels : optional
        As in :func:`size_band`.

    Returns
    -------
    pandas.DataFrame
        Columns ``size_band``, ``n``, ``share`` (and ``by`` when given), one row per band.
    """
    banded = add_size_band(frame, column=column, edges=edges, labels=labels)
    group_keys = ["size_band"] if by is None else [by, "size_band"]
    counts = banded.groupby(group_keys, observed=False, dropna=False).size().reset_index(name="n")
    denominator = (
        counts.groupby(by, observed=False)["n"].transform("sum") if by else counts["n"].sum()
    )
    counts["share"] = counts["n"] / denominator
    return counts


@dataclass(frozen=True)
class FloorSummary:
    """What a denominator floor removes from a sample.

    Attributes
    ----------
    min_denominator : int
        The floor applied; stations with fewer registered voters are excluded.
    n_total : int
        Stations considered.
    n_below : int
        Stations strictly below the floor.
    n_missing : int
        Stations whose size is null and which therefore cannot be placed either way.
    """

    min_denominator: int
    n_total: int
    n_below: int
    n_missing: int

    @property
    def n_kept(self) -> int:
        """Stations at or above the floor."""
        return self.n_total - self.n_below - self.n_missing

    @property
    def share_below(self) -> float:
        """Fraction of the sample the floor removes; ``nan`` for an empty sample."""
        return self.n_below / self.n_total if self.n_total else float("nan")


def denominator_floor_summary(
    registered: ArrayLike, *, min_denominator: int = DEFAULT_MIN_DENOMINATOR
) -> FloorSummary:
    """Count what a denominator floor would exclude, before anything is excluded.

    :func:`forensics_core.digits.integer_pct.integer_excess` applies the floor itself and
    reports ``n_excluded_small``. This function exists so the same number can be stated in the
    data audit and in the analysis plan, before a test is run, because how much of the sample
    a control removes is part of the result and not a footnote to it.

    Parameters
    ----------
    registered : array-like
        Registered voters per station.
    min_denominator : int, default 100
        Stations strictly below this are counted as excluded.

    Returns
    -------
    FloorSummary
    """
    values = pd.Series(registered).astype("Float64").to_numpy(dtype="float64", na_value=np.nan)
    missing = np.isnan(values)
    below = ~missing & (values < min_denominator)
    return FloorSummary(
        min_denominator=int(min_denominator),
        n_total=int(values.size),
        n_below=int(below.sum()),
        n_missing=int(missing.sum()),
    )


def iter_size_strata(
    frame: pd.DataFrame,
    *,
    column: str = "registered",
    edges: tuple[float, ...] = SIZE_BAND_EDGES,
    labels: tuple[str, ...] = SIZE_BAND_LABELS,
    min_denominator: int | None = None,
    skip_empty: bool = True,
) -> Iterator[tuple[str, pd.DataFrame]]:
    """Iterate over the size bands, yielding ``(label, rows)``.

    This is the size-conditioning helper the integer-percentage trap requires: run the test
    within a band rather than over the pooled sample, so that the comparison is between
    stations whose attainable percentages have the same granularity. Compare bands rather than
    reading the pooled statistic.

    Parameters
    ----------
    frame : pandas.DataFrame
        Tidy frame.
    column : str, default "registered"
        Size column.
    edges, labels : optional
        As in :func:`size_band`.
    min_denominator : int or None, optional
        When given, bands whose entire range lies below this floor are not yielded at all,
        and the band that straddles it is yielded whole. Nothing is silently filtered inside
        a band: a caller that wants the floor applied row-wise should pass it to
        :func:`forensics_core.digits.integer_pct.integer_excess`, which counts what it drops.
    skip_empty : bool, default True
        Do not yield bands with no rows.

    Yields
    ------
    tuple
        ``(band label, rows in that band)``. Stations with a null or non-positive size fall in
        no band and are never yielded, so the bands do not necessarily partition ``frame``.
    """
    banded = add_size_band(frame, column=column, edges=edges, labels=labels)
    for index, label in enumerate(labels):
        if min_denominator is not None and edges[index + 1] <= min_denominator:
            continue
        rows = banded.loc[banded["size_band"] == label]
        if skip_empty and rows.empty:
            continue
        yield label, rows.drop(columns=["size_band"])


def percentage_resolution(registered: ArrayLike) -> pd.Series:
    """Spacing, in percentage points, between percentages a station can attain.

    ``100 / n``: with 100 registered voters consecutive attainable turnouts are 1.0 points
    apart, with 2,500 they are 0.04 apart. This is the quantity that makes the trap concrete,
    and it depends on nothing but the station's size.

    Parameters
    ----------
    registered : array-like
        Registered voters per station.

    Returns
    -------
    pandas.Series
        Float series; ``NaN`` where the size is null or not positive.
    """
    values = pd.Series(registered).astype("Float64").to_numpy(dtype="float64", na_value=np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(values > 0, 100.0 / np.where(values > 0, values, 1.0), np.nan)
    return pd.Series(out, name="percentage_resolution")


def exact_integer_share(registered: ArrayLike) -> pd.Series:
    """Share of a station's attainable percentages that are exactly whole numbers.

    A station with ``n`` registered voters can report ``100 * k / n`` for ``k = 0..n``. That
    value is a whole number exactly when ``k`` is a multiple of ``n / gcd(n, 100)``, so
    ``gcd(n, 100) + 1`` of the ``n + 1`` attainable percentages are integers. Pure arithmetic:
    it uses no votes and no data, only the size.

    Worked values: ``n = 100`` gives 101/101 = 1.0, every attainable turnout is an integer;
    ``n = 250`` gives 51/251 = 0.203; ``n = 2500`` gives 101/2501 = 0.0404, which is the "fewer
    than 1 in 20" quoted for 2,500 voters in ``docs/known_traps.md``.

    Note a documentation discrepancy rather than resolving it: ``docs/known_traps.md`` also
    says that at 250 voters "4 in 10 possible turnout values land within 0.05 of an integer".
    At 250 voters the attainable percentages are 0.4 apart, so the only ones within 0.05 of an
    integer are the exact hits, and this function gives 0.203, not 0.4. The quoted figure
    looks like the 0.4-point spacing rather than a share. Confirm against the source before
    either number is used in prose.

    Parameters
    ----------
    registered : array-like
        Registered voters per station. Must be integer-valued where present.

    Returns
    -------
    pandas.Series
        Float series in ``(0, 1]``; ``NaN`` where the size is null or not positive.
    """
    values = pd.Series(registered).astype("Float64").to_numpy(dtype="float64", na_value=np.nan)
    valid = np.isfinite(values) & (values > 0)
    if np.any(valid & (values != np.round(values))):
        raise ValueError("registered voters must be integer-valued")
    out = np.full(values.shape, np.nan, dtype="float64")
    sizes = np.round(values[valid]).astype("int64")
    out[valid] = (np.gcd(sizes, 100) + 1) / (sizes + 1)
    return pd.Series(out, name="exact_integer_share")

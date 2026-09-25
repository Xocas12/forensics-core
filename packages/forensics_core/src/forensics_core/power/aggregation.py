"""How much detection power survives aggregation.

Soviet statistics are aggregate. Elections are not. Every method in this library was built and
validated on precinct-level data, and gosplan will have sector-year totals, so applying a
precinct-calibrated detector to aggregates is an act of faith unless someone measures what
aggregation costs.

That measurement is possible because elections has the hierarchy: precinct, territorial
commission, region. Distortion is injected at the **unit** level, where it actually happens,
and the data is then aggregated up a rung before the test runs. The power lost between rungs
is the price of the aggregation, measured rather than assumed.

The two aggregation semantics are not the same question
--------------------------------------------------------
``"sum_then_ratio"``
    Sum the numerators, sum the denominators, then divide. This is what a statistical office
    does, and it is the only one that yields a well-defined aggregate percentage.

``"mean_of_ratios"``
    Average the percentages the units already carry. This is what a careless analyst does when
    handed a column of percentages and no counts.

Both are supported because reporting both turned up something the WO-101 card got backwards.
The card's note says averaging "destroys the integer-percentage signal by construction",
implying that summing counts is the safe choice. Measured on unequal denominators, with every
unit snapped onto an exact integer percentage (share of units still within 0.05 of an integer;
the background rate is 0.10):

==========  ===============  ==============
group size  sum_then_ratio   mean_of_ratios
==========  ===============  ==============
1           1.000            1.000
2           0.256            0.489
3           0.141            0.334
4           0.089            0.235
8           0.100            0.150
==========  ===============  ==============

**Averaging retains more**, not less. The mean of ``k`` integers is a multiple of ``1/k`` and
lands on an integer often; summing counts across unequal denominators produces a weighted
average with arbitrary weights, which has no reason to be an integer at all. With *equal*
denominators the two coincide exactly, so this is a fact about unequal precinct sizes rather
than about averaging as such.

The finding that constrains a card is neither of those. **Both collapse to the background rate
by a group size of four to eight**, so the integer-percentage test does not survive
aggregation under either semantics, and a gosplan card must not run it on aggregates at all.
That is a stronger and more useful statement than a preference between the two.

What this measures and what it does not
---------------------------------------
This is the power of a test on a *collection*, as in :mod:`forensics_core.power.atlas`: at what
aggregation level can the method see the effect at all. It is not the ranking power of a
per-unit detector, which aggregation also destroys for the simpler reason that the units stop
existing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import ArrayLike

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = [
    "LADDER_COLUMNS",
    "SEMANTICS",
    "AggregationError",
    "aggregate",
    "aggregation_ladder",
    "coarsest_level_with_power",
]

#: The two ways a percentage can be aggregated. They answer different questions.
SEMANTICS: tuple[str, ...] = ("sum_then_ratio", "mean_of_ratios")

#: Columns :func:`aggregation_ladder` returns, in order.
LADDER_COLUMNS = [
    "level",
    "semantics",
    "effect_size",
    "n_units",
    "mean_group_size",
    "power",
    "power_se",
    "false_positive_rate",
    "n_replicates",
    "alpha",
]


class AggregationError(ValueError):
    """A ladder was built or queried in a way that would misstate the power it measures."""


def aggregate(
    numerators: ArrayLike,
    denominators: ArrayLike,
    group: ArrayLike | None = None,
    *,
    semantics: str = "sum_then_ratio",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate counts up one rung and return ``(numerators, denominators, percentages)``.

    Parameters
    ----------
    group : array-like or None
        One group key per unit. ``None`` is the identity aggregation: every unit is its own
        group, and the output is the input. That case is exact, not approximate — it is what
        makes the ladder's first rung comparable to the ungrouped curve.
    semantics : {"sum_then_ratio", "mean_of_ratios"}
        See the module docstring. Under ``"mean_of_ratios"`` the returned numerators and
        denominators are the summed counts (so the group's size is still available) but the
        percentage is the mean of the units' own percentages, which is the point of the
        contrast.

    Returns
    -------
    (numerators, denominators, percentages)
        One entry per group, groups in order of first appearance so that a caller can align
        the result with a group label array built the same way.
    """
    num = np.asarray(numerators, dtype=float).ravel()
    den = np.asarray(denominators, dtype=float).ravel()
    if num.size != den.size:
        raise AggregationError(
            f"numerators and denominators must be the same length; got {num.size} and {den.size}"
        )
    if num.size == 0:
        raise AggregationError("nothing to aggregate")
    if not np.isfinite(num).all() or not np.isfinite(den).all():
        raise AggregationError("numerators and denominators must be finite")
    if (den <= 0).any():
        raise AggregationError("denominators must be positive; a percentage is undefined otherwise")
    if semantics not in SEMANTICS:
        raise AggregationError(f"semantics must be one of {SEMANTICS}; got {semantics!r}")

    if group is None:
        pct = 100.0 * num / den
        return num.copy(), den.copy(), pct

    keys = np.asarray(group).ravel()
    if keys.size != num.size:
        raise AggregationError(
            f"group has {keys.size} entries for {num.size} units; one key per unit is required"
        )

    # first-appearance order, so a caller's parallel label array lines up
    _, first_index, inverse = np.unique(keys, return_index=True, return_inverse=True)
    order = np.argsort(first_index)
    remap = np.empty_like(order)
    remap[order] = np.arange(order.size)
    codes = remap[inverse]
    n_groups = order.size

    num_out = np.bincount(codes, weights=num, minlength=n_groups)
    den_out = np.bincount(codes, weights=den, minlength=n_groups)

    if semantics == "sum_then_ratio":
        pct_out = 100.0 * num_out / den_out
    else:
        unit_pct = 100.0 * num / den
        counts = np.bincount(codes, minlength=n_groups)
        pct_out = np.bincount(codes, weights=unit_pct, minlength=n_groups) / counts

    return num_out, den_out, pct_out


def aggregation_ladder(
    numerators: ArrayLike,
    denominators: ArrayLike,
    levels: Sequence[tuple[str, ArrayLike | None]],
    test: Callable[[np.ndarray, np.ndarray, np.ndarray], float],
    injector: Callable[[np.ndarray, np.ndarray, float, np.random.Generator], np.ndarray],
    *,
    effect_sizes: Sequence[float],
    n_replicates: int = 200,
    semantics: Sequence[str] = SEMANTICS,
    alpha: float = 0.05,
    seed: int | None = 0,
) -> pd.DataFrame:
    """Measure detection power at each rung of an aggregation hierarchy.

    The distortion is injected at the **unit** level, before aggregation, because that is where
    it happens. Aggregating first and injecting into the aggregate would measure a different
    and much easier problem.

    Parameters
    ----------
    levels : sequence of (name, group_keys)
        Ordered, coarsest last. Use ``None`` for the group keys of the identity level, which
        must come first and which reproduces the ungrouped curve exactly.
    test : callable
        ``test(numerators, denominators, percentages) -> p-value``, run on the aggregated data.
    injector : callable
        ``injector(numerators, denominators, effect, rng) -> numerators``, run on the unit-level
        data. Must be a no-op at effect size zero, which this function checks — otherwise the
        zero row would not be the false-positive rate.
    effect_sizes : sequence of float
        Zero is added if absent.

    Returns
    -------
    pandas.DataFrame
        One row per ``(level, semantics, effect_size)`` with :data:`LADDER_COLUMNS`.

    Raises
    ------
    AggregationError
        If the levels are empty, the first level is not the identity, or the injector is not a
        no-op at effect size zero.
    """
    import pandas as pd

    num0 = np.asarray(numerators, dtype=float).ravel()
    den0 = np.asarray(denominators, dtype=float).ravel()
    if num0.size != den0.size:
        raise AggregationError("numerators and denominators must be the same length")
    if not levels:
        raise AggregationError("no levels given")
    if levels[0][1] is not None:
        raise AggregationError(
            "the first level must be the identity (group keys None). Without it the ladder has "
            "no ungrouped baseline and every power number on it is uninterpretable."
        )
    bad = [s for s in semantics if s not in SEMANTICS]
    if bad:
        raise AggregationError(f"unknown semantics {bad}; known are {SEMANTICS}")
    if not 0.0 < alpha < 1.0:
        raise AggregationError(f"alpha must be in (0, 1); got {alpha}")

    probe = injector(num0, den0, 0.0, np.random.default_rng(0))
    if not np.allclose(np.asarray(probe, dtype=float), num0, equal_nan=True):
        raise AggregationError(
            "the injector is not a no-op at effect size zero, so the zero row would not "
            "measure the false-positive rate"
        )

    effects = sorted({float(e) for e in effect_sizes} | {0.0})
    rng = np.random.default_rng(seed)

    rows: list[dict[str, Any]] = []
    fpr: dict[tuple[str, str], float] = {}
    for level_name, keys in levels:
        for sem in semantics:
            for effect in effects:
                reject = 0
                n_units_seen = 0
                for _ in range(n_replicates):
                    num = (
                        num0
                        if effect == 0.0
                        else np.asarray(injector(num0, den0, effect, rng), dtype=float)
                    )
                    a_num, a_den, a_pct = aggregate(num, den0, keys, semantics=sem)
                    n_units_seen = a_num.size
                    try:
                        p = float(test(a_num, a_den, a_pct))
                    except (ValueError, ZeroDivisionError, FloatingPointError):
                        continue
                    if np.isfinite(p) and p <= alpha:
                        reject += 1
                power = reject / n_replicates
                if effect == 0.0:
                    fpr[(level_name, sem)] = power
                rows.append(
                    {
                        "level": level_name,
                        "semantics": sem,
                        "effect_size": effect,
                        "n_units": int(n_units_seen),
                        "mean_group_size": float(num0.size / n_units_seen) if n_units_seen else 0.0,
                        "power": power,
                        "power_se": float(np.sqrt(power * (1.0 - power) / n_replicates)),
                        "false_positive_rate": np.nan,
                        "n_replicates": n_replicates,
                        "alpha": alpha,
                    }
                )

    frame = pd.DataFrame(rows, columns=LADDER_COLUMNS)
    frame["false_positive_rate"] = [
        fpr.get((r.level, r.semantics), np.nan) for r in frame.itertuples()
    ]
    return frame


def coarsest_level_with_power(
    ladder: pd.DataFrame,
    effect_size: float,
    *,
    target_power: float = 0.8,
    semantics: str = "sum_then_ratio",
) -> str | None:
    """The coarsest rung that still reaches ``target_power`` against ``effect_size``.

    This is the number a gosplan card cites: *this method survives aggregation to the region
    level and no further*. Returns ``None`` when even the identity level fails, which is a
    statement about the method rather than about aggregation.

    Levels are taken in the order they appear in the frame, which is the order they were
    measured in — coarsest last.
    """
    subset = ladder[
        (ladder["semantics"] == semantics) & (ladder["effect_size"] == float(effect_size))
    ]
    if subset.empty:
        raise AggregationError(
            f"the ladder has no rows for effect_size={effect_size} under {semantics!r}. It "
            "will not interpolate between measured effect sizes."
        )
    passing = subset[subset["power"] >= target_power]
    if passing.empty:
        return None
    # the frame preserves measurement order, so the last passing row is the coarsest
    return str(passing["level"].iloc[-1])

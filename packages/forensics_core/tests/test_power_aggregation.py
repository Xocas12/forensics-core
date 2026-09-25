"""Power falls as groups grow, the identity rung reproduces the ungrouped curve exactly, and
the integer-percentage signal does not survive aggregation under either semantics.

The third of those is the one worth having, and it came out the opposite way to the card's
expectation. A power loss is a trade-off a card can reason about; a signal that is at the
background rate by a group size of four is a different kind of fact, and it says a gosplan
card must not run this test on aggregates whichever way it aggregates them.
"""

from __future__ import annotations

import numpy as np
import pytest

from forensics_core.power.aggregation import (
    LADDER_COLUMNS,
    SEMANTICS,
    AggregationError,
    aggregate,
    aggregation_ladder,
    coarsest_level_with_power,
)


def panel(n: int = 2400, seed: int = 0):
    """Honest precinct counts: numerator binomial in the denominator."""
    rng = np.random.default_rng(seed)
    den = rng.integers(600, 1400, size=n).astype(float)
    num = rng.binomial(den.astype(int), 0.55).astype(float)
    return num, den


def nested_keys(n: int, size: int) -> np.ndarray:
    """Contiguous groups of `size` units, which is how a real hierarchy nests."""
    return np.arange(n) // size


def round_injector(num, den, effect, rng):
    """Snap a share of units onto an exactly integer percentage. A no-op at zero."""
    num = np.asarray(num, dtype=float)
    if effect == 0.0:
        return num.copy()
    out = num.copy()
    k = round(float(effect) * num.size)
    if k:
        chosen = rng.choice(num.size, size=k, replace=False)
        pct = 100.0 * out[chosen] / den[chosen]
        out[chosen] = np.round(pct) * den[chosen] / 100.0
    return out


def integer_share_test(num, den, pct):
    """A blunt integer-percentage test: how much mass sits within 0.05 of an integer,
    against a binomial null redrawn at each aggregated unit's own denominator."""
    from scipy import stats

    near = np.abs(pct - np.round(pct)) <= 0.05
    observed = float(near.sum())
    n_mc = 60
    rng = np.random.default_rng(0)
    p = np.clip(num / den, 0.0, 1.0)
    draws = np.empty(n_mc)
    for i in range(n_mc):
        sim_num = rng.binomial(den.astype(np.int64), p).astype(float)
        sim_pct = 100.0 * sim_num / den
        draws[i] = float((np.abs(sim_pct - np.round(sim_pct)) <= 0.05).sum())
    mu, sd = draws.mean(), draws.std(ddof=1)
    if sd == 0:
        return 1.0
    return float(stats.norm.sf((observed - mu) / sd))


# ---------------------------------------------------------------- the identity rung is exact


def test_the_identity_aggregation_returns_the_input_unchanged():
    num, den = panel(200)
    a_num, a_den, a_pct = aggregate(num, den, None)
    assert np.array_equal(a_num, num)
    assert np.array_equal(a_den, den)
    assert np.array_equal(a_pct, 100.0 * num / den)


def test_grouping_every_unit_into_its_own_group_is_also_the_identity():
    """A ladder whose first real rung has group size 1 must agree with `group=None`."""
    num, den = panel(200)
    keys = np.arange(num.size)
    a_num, a_den, a_pct = aggregate(num, den, keys)
    assert np.array_equal(a_num, num)
    assert np.array_equal(a_den, den)
    assert np.allclose(a_pct, 100.0 * num / den)


def test_the_two_semantics_agree_at_group_size_one_and_not_above():
    num, den = panel(200)
    singles = np.arange(num.size)
    _, _, sum_first = aggregate(num, den, singles, semantics="sum_then_ratio")
    _, _, mean_first = aggregate(num, den, singles, semantics="mean_of_ratios")
    assert np.allclose(sum_first, mean_first), "with one unit per group the two must coincide"

    pairs = nested_keys(num.size, 8)
    _, _, sum_eight = aggregate(num, den, pairs, semantics="sum_then_ratio")
    _, _, mean_eight = aggregate(num, den, pairs, semantics="mean_of_ratios")
    assert not np.allclose(sum_eight, mean_eight), (
        "with unequal denominators the two semantics must differ; if they do not, the "
        "fixture has equal denominators and demonstrates nothing"
    )


def test_groups_come_back_in_first_appearance_order():
    num = np.array([10.0, 20.0, 30.0, 40.0])
    den = np.array([100.0, 100.0, 100.0, 100.0])
    keys = np.array(["b", "a", "b", "a"])
    a_num, _, _ = aggregate(num, den, keys)
    # "b" appears first, so it is row 0: 10 + 30
    assert a_num[0] == 40.0
    assert a_num[1] == 60.0


# ---------------------------------------------------------------- power falls as groups grow


def test_power_falls_monotonically_as_the_group_size_grows():
    """The card's must-pass. Aggregation costs power, and the cost is measured not assumed."""
    num, den = panel(2400)
    levels = [
        ("precinct", None),
        ("commission_4", nested_keys(num.size, 4)),
        ("region_20", nested_keys(num.size, 20)),
    ]
    ladder = aggregation_ladder(
        num,
        den,
        levels,
        integer_share_test,
        round_injector,
        effect_sizes=(0.3,),
        n_replicates=40,
        semantics=("sum_then_ratio",),
        seed=3,
    )
    at_effect = ladder[ladder["effect_size"] == 0.3].sort_values("mean_group_size")
    powers = list(at_effect["power"])
    assert powers == sorted(powers, reverse=True), (
        f"power must not rise with aggregation: {list(zip(at_effect['level'], powers, strict=True))}"
    )
    assert powers[0] > powers[-1], "aggregation must cost something on this fixture"


def test_the_ladder_has_the_documented_columns_and_one_row_per_cell():
    num, den = panel(400)
    levels = [("precinct", None), ("group_4", nested_keys(num.size, 4))]
    ladder = aggregation_ladder(
        num,
        den,
        levels,
        integer_share_test,
        round_injector,
        effect_sizes=(0.5,),
        n_replicates=10,
        seed=1,
    )
    assert list(ladder.columns) == LADDER_COLUMNS
    # 2 levels x 2 semantics x 2 effect sizes (0.0 is added)
    assert len(ladder) == 8
    assert set(ladder["semantics"]) == set(SEMANTICS)


def test_the_zero_effect_row_is_the_false_positive_rate_of_its_own_level():
    num, den = panel(400)
    levels = [("precinct", None), ("group_4", nested_keys(num.size, 4))]
    ladder = aggregation_ladder(
        num,
        den,
        levels,
        integer_share_test,
        round_injector,
        effect_sizes=(0.5,),
        n_replicates=20,
        semantics=("sum_then_ratio",),
        seed=2,
    )
    for level in ("precinct", "group_4"):
        rows = ladder[ladder["level"] == level]
        zero = float(rows[rows["effect_size"] == 0.0]["power"].iloc[0])
        assert np.allclose(rows["false_positive_rate"], zero)


def test_mean_group_size_is_recorded_so_a_reader_can_see_the_cost():
    num, den = panel(400)
    levels = [("precinct", None), ("group_10", nested_keys(num.size, 10))]
    ladder = aggregation_ladder(
        num,
        den,
        levels,
        integer_share_test,
        round_injector,
        effect_sizes=(0.5,),
        n_replicates=5,
        semantics=("sum_then_ratio",),
        seed=1,
    )
    sizes = dict(zip(ladder["level"], ladder["mean_group_size"], strict=True))
    assert sizes["precinct"] == pytest.approx(1.0)
    assert sizes["group_10"] == pytest.approx(10.0)


# ---------------------------------------------------------------- averaging erases the signal


def test_averaging_leaves_the_signal_near_the_background_rate_by_group_size_eight():
    """A manufactured precinct reports exactly 65.0%; the mean of eight such percentages is
    rarely an integer. The measured residue is 0.150 against a 0.10 background — weakened
    nearly to nothing, though see the next test for the fact that summing does worse."""
    num, den = panel(1600)
    rng = np.random.default_rng(7)
    # snap every unit onto an integer percentage: the strongest possible signal
    snapped = round_injector(num, den, 1.0, rng)

    singles = np.arange(num.size)
    _, _, unit_pct = aggregate(snapped, den, singles, semantics="sum_then_ratio")
    on_integer_before = np.mean(np.abs(unit_pct - np.round(unit_pct)) <= 0.05)
    assert on_integer_before > 0.99, "the fixture must start with the signal at full strength"

    groups = nested_keys(num.size, 8)
    _, _, averaged = aggregate(snapped, den, groups, semantics="mean_of_ratios")
    on_integer_after = np.mean(np.abs(averaged - np.round(averaged)) <= 0.05)
    assert on_integer_after < 0.15, (
        f"averaging left {on_integer_after:.3f} of groups on an integer; the signal was "
        "supposed to be erased by construction"
    )


def test_neither_semantics_keeps_the_integer_signal_past_group_size_four():
    """Measured, and it contradicts the card.

    WO-101's implementation note says averaging percentages "destroys the integer-percentage
    signal by construction", implying that summing counts is the safe choice. Measured on
    unequal denominators with every unit snapped onto an exact integer percentage, the
    ordering is the other way round:

        group size   sum_then_ratio   mean_of_ratios
                 1            1.000            1.000
                 2            0.256            0.489
                 3            0.141            0.334
                 4            0.089            0.235
                 8            0.100            0.150

    Averaging retains MORE integer mass, because the mean of k integers is a multiple of 1/k
    and lands on an integer often; summing counts with unequal denominators produces a
    weighted average with arbitrary weights, which has no reason to be an integer at all.

    The finding that matters is not which is better. It is that **both collapse to the 0.10
    background rate by group size 4 or 8**, so the integer-percentage test does not survive
    aggregation under either semantics. A gosplan card must not run it on aggregates.
    """
    num, den = panel(4800)
    pct = 100.0 * num / den
    snapped = np.round(pct) * den / 100.0

    def near(p):
        return float(np.mean(np.abs(p - np.round(p)) <= 0.05))

    _, _, at_one = aggregate(snapped, den, np.arange(num.size), semantics="sum_then_ratio")
    assert near(at_one) > 0.99, "the fixture must start with the signal at full strength"

    _, _, sum_2 = aggregate(snapped, den, nested_keys(num.size, 2), semantics="sum_then_ratio")
    _, _, mean_2 = aggregate(snapped, den, nested_keys(num.size, 2), semantics="mean_of_ratios")
    assert near(mean_2) > near(sum_2), (
        f"averaging kept {near(mean_2):.3f} and summing {near(sum_2):.3f}; the recorded "
        "direction is that averaging keeps more, contrary to the card's note"
    )

    # and the finding that actually constrains a card: both are gone by group size 8
    for semantics in SEMANTICS:
        _, _, at_eight = aggregate(snapped, den, nested_keys(num.size, 8), semantics=semantics)
        assert near(at_eight) < 0.25, (
            f"{semantics} retained {near(at_eight):.3f} of the signal at group size 8; the "
            "background rate for a 0.05 tolerance is 0.10"
        )


def test_the_two_semantics_coincide_when_denominators_are_equal():
    """Which is why the contrast above is a fact about unequal precinct sizes, not about
    averaging as such. With equal denominators summing counts IS averaging ratios."""
    n = 800
    den = np.full(n, 1000.0)
    num = np.random.default_rng(4).binomial(den.astype(int), 0.55).astype(float)
    keys = nested_keys(n, 4)
    _, _, summed = aggregate(num, den, keys, semantics="sum_then_ratio")
    _, _, averaged = aggregate(num, den, keys, semantics="mean_of_ratios")
    assert np.allclose(summed, averaged)


# ---------------------------------------------------------------- the citable answer


def test_the_coarsest_passing_level_is_reported_and_none_when_nothing_passes():
    num, den = panel(2400)
    levels = [
        ("precinct", None),
        ("commission_4", nested_keys(num.size, 4)),
        ("region_20", nested_keys(num.size, 20)),
    ]
    ladder = aggregation_ladder(
        num,
        den,
        levels,
        integer_share_test,
        round_injector,
        effect_sizes=(0.3,),
        n_replicates=40,
        semantics=("sum_then_ratio",),
        seed=3,
    )
    answer = coarsest_level_with_power(ladder, 0.3, target_power=0.8)
    assert answer in {None, "precinct", "commission_4", "region_20"}
    # an unreachable target must give None rather than the least-bad level
    assert coarsest_level_with_power(ladder, 0.3, target_power=1.01) is None


def test_an_unmeasured_effect_size_is_refused_rather_than_interpolated():
    num, den = panel(400)
    ladder = aggregation_ladder(
        num,
        den,
        [("precinct", None)],
        integer_share_test,
        round_injector,
        effect_sizes=(0.5,),
        n_replicates=5,
        semantics=("sum_then_ratio",),
        seed=1,
    )
    with pytest.raises(AggregationError, match="will not interpolate"):
        coarsest_level_with_power(ladder, 0.25)


# ---------------------------------------------------------------- refusals


def test_a_ladder_without_an_identity_first_level_is_refused():
    num, den = panel(100)
    with pytest.raises(AggregationError, match="first level must be the identity"):
        aggregation_ladder(
            num,
            den,
            [("group_4", nested_keys(num.size, 4))],
            integer_share_test,
            round_injector,
            effect_sizes=(0.5,),
            n_replicates=2,
        )


def test_an_injector_that_is_not_a_noop_at_zero_is_refused():
    num, den = panel(100)

    def sneaky(n, d, effect, rng):
        return np.asarray(n, dtype=float) + effect + 1.0

    with pytest.raises(AggregationError, match="no-op at effect size zero"):
        aggregation_ladder(
            num,
            den,
            [("precinct", None)],
            integer_share_test,
            sneaky,
            effect_sizes=(0.5,),
            n_replicates=2,
        )


def test_a_group_key_per_unit_is_required():
    num, den = panel(100)
    with pytest.raises(AggregationError, match="one key per unit"):
        aggregate(num, den, np.arange(5))


def test_a_non_positive_denominator_is_refused():
    with pytest.raises(AggregationError, match="denominators must be positive"):
        aggregate([1.0, 2.0], [10.0, 0.0])


def test_unknown_semantics_are_refused():
    num, den = panel(10)
    with pytest.raises(AggregationError, match="semantics must be one of"):
        aggregate(num, den, None, semantics="whatever")

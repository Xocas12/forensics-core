"""Power falls as groups grow, the identity rung reproduces the ungrouped curve exactly, and
whether the integer-percentage signal survives aggregation depends on the semantics and the
group size.

The third is measured with ``integer_excess`` on the aggregates, a significance test against a
binomial null, not by comparing the share of near-integer aggregates with the background rate
by eye. Read that way, with every unit snapped: ``sum_then_ratio`` is still detected at group
sizes 2 and 3, sometimes at 4, and is at the nominal rate from 6; ``mean_of_ratios`` is still
detected through group size 8, because the mean of k integer percentages sits on a 1/k
lattice, and reaches the nominal rate somewhere between 8 and 12. The 30-panel rejection
counts behind "sometimes" are in docs/power_atlas.md.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import numpy as np
import pytest

from forensics_core.digits.integer_pct import integer_excess
from forensics_core.power import aggregation as aggregation_module
from forensics_core.power.aggregation import (
    LADDER_COLUMNS,
    SEMANTICS,
    AggregationError,
    aggregate,
    aggregation_ladder,
    coarsest_level_with_power,
)

ATLAS_DOC = Path(__file__).resolve().parents[1] / "docs" / "power_atlas.md"


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


# ---------------------------------------------------------------- what survives aggregation


def test_averaging_puts_the_aggregates_on_a_one_over_k_lattice():
    """Why averaging keeps the signal. A manufactured precinct reports exactly 65.0%; the mean
    of eight such percentages is a multiple of 1/8. It is not erased by construction: it sits
    on a lattice that contains every integer, and lands on one about 1/8 of the time."""
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
    assert np.allclose(8.0 * averaged, np.round(8.0 * averaged)), (
        "the mean of eight integer percentages must be a multiple of 1/8"
    )
    _, _, summed = aggregate(snapped, den, groups, semantics="sum_then_ratio")
    assert not np.allclose(8.0 * summed, np.round(8.0 * summed)), (
        "summing counts over unequal denominators has no lattice; if it has one, the fixture "
        "has equal denominators and demonstrates nothing"
    )


FULL_SNAP_N = 4800
FULL_SNAP_GROUP_SIZES = (1, 2, 3, 4, 6, 8, 12, 16)


@functools.cache
def full_snap_results() -> dict[tuple[str, int], tuple[float, float, float, float]]:
    """``integer_excess`` on the aggregates of one honest panel and of the same panel with
    every unit snapped onto an integer percentage, per semantics and group size.

    Returns ``{(semantics, k): (z_snapped, p_snapped, z_honest, p_honest)}``. The settings are
    the ones docs/power_atlas.md records: ``panel(4800, seed=0)``, contiguous groups of ``k``,
    and ``integer_excess(pct, den, seed=0)`` with its defaults (tolerance 0.05, n_mc 200).
    """
    num, den = panel(FULL_SNAP_N)
    snapped = np.round(100.0 * num / den) * den / 100.0
    out = {}
    for k in FULL_SNAP_GROUP_SIZES:
        keys = nested_keys(num.size, k)
        for semantics in SEMANTICS:
            row: list[float] = []
            for counts in (snapped, num):
                _, a_den, a_pct = aggregate(counts, den, keys, semantics=semantics)
                result = integer_excess(a_pct, a_den, seed=0).test
                row += [float(result.statistic), float(result.pvalue)]
            out[(semantics, k)] = tuple(row)
    return out


def test_whether_the_integer_signal_survives_depends_on_semantics_and_group_size():
    """Measured with ``integer_excess`` on the aggregates, at alpha 0.05.

    This replaces an older test that compared the share of aggregates within 0.05 of an integer
    with the 0.10 background, asserted only that it was below 0.25 at group size 8, and
    concluded that the signal does not survive aggregation under either semantics. The share
    under ``mean_of_ratios`` there is 0.150 over 600 aggregates, which the significance test
    rejects with z = 3.92: not the background.

    With every unit snapped, on one panel (the table is in docs/power_atlas.md):

    - ``sum_then_ratio`` is detected at group sizes 2 and 3 and not from 4 on.
    - ``mean_of_ratios`` is detected at every group size up to 8, and not at 12 or 16.
    - Honest data is not rejected at any group size under either semantics.
    - At group size 2 averaging keeps more than summing (the larger z), contrary to the
      plan's note that averaging destroys the signal by construction.
    """
    results = full_snap_results()
    alpha = 0.05

    def rejects(semantics, k):
        return results[(semantics, k)][1] <= alpha

    for semantics in SEMANTICS:
        for k in FULL_SNAP_GROUP_SIZES:
            p_honest = results[(semantics, k)][3]
            assert p_honest > alpha, (
                f"honest data under {semantics} at group size {k} gave p = {p_honest:.3g}; "
                "the comparison below means nothing if the null rejects on its own"
            )

    for k in (1, 2, 3):
        for semantics in SEMANTICS:
            assert rejects(semantics, k), f"{semantics} at group size {k} should be detected"
    for k in (4, 6, 8, 12, 16):
        assert not rejects("sum_then_ratio", k), (
            f"sum_then_ratio at group size {k} was detected (p = "
            f"{results[('sum_then_ratio', k)][1]:.3g}); the recorded result is that it is not"
        )
    for k in (4, 6, 8):
        assert rejects("mean_of_ratios", k), (
            f"mean_of_ratios at group size {k} gave p = {results[('mean_of_ratios', k)][1]:.3g};"
            " the recorded result is that averaged percentages are still detected there"
        )
    for k in (12, 16):
        assert not rejects("mean_of_ratios", k)

    z_mean_2 = results[("mean_of_ratios", 2)][0]
    z_sum_2 = results[("sum_then_ratio", 2)][0]
    assert z_mean_2 > z_sum_2, (
        f"averaging gave z = {z_mean_2:.2f} and summing z = {z_sum_2:.2f} at group size 2; "
        "the recorded direction is that averaging keeps more, contrary to the card's note"
    )


def test_the_documented_aggregation_table_is_the_measured_one():
    """docs/power_atlas.md and the module docstring both carry the ``integer_excess`` z and
    verdict per semantics and group size. If this fails, re-measure and update both texts;
    do not loosen the comparison."""
    results = full_snap_results()
    texts = {
        "docs/power_atlas.md": ATLAS_DOC.read_text(encoding="utf-8"),
        "the aggregation module docstring": aggregation_module.__doc__ or "",
    }
    for where, text in texts.items():
        for k in FULL_SNAP_GROUP_SIZES:
            z_sum, p_sum = results[("sum_then_ratio", k)][:2]
            z_mean, p_mean = results[("mean_of_ratios", k)][:2]
            cells = [
                str(k),
                f"{z_sum:.2f}",
                "yes" if p_sum <= 0.05 else "no",
                f"{z_mean:.2f}",
                "yes" if p_mean <= 0.05 else "no",
            ]
            row = r"^[|\s]*" + r"[|\s]+".join(re.escape(c) for c in cells) + r"[|\s]*$"
            assert re.search(row, text, re.MULTILINE), (
                f"{where} has no row for group size {k} reading {cells}"
            )
        assert "does not survive aggregation under either semantics" not in text, (
            f"{where} still states the near-integer-share conclusion the measurement refutes"
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

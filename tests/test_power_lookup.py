"""A stored atlas loads, answers a minimum-detectable-effect query, and refuses one it does not
cover.

The refusals carry the card. A lookup that interpolated between measured sample sizes, or that
picked one of two atlases that differ in their settings, would put a number into a gosplan claim
that nobody measured and nobody can cite. Every test below that expects an exception is testing
the same property from a different side: the lookup answers only what a stored, versioned
measurement supports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from forensics_core import __version__
from forensics_core.power.aggregation import aggregation_ladder
from forensics_core.power.atlas import (
    ATLAS_COLUMNS,
    AtlasError,
    power_curve,
    save_atlas,
)
from forensics_core.power.lookup import (
    UNIT_RUNG,
    PowerLookup,
    power_lookup,
    publish_atlas,
)

SIZES = (50, 100, 200, 400)
EFFECTS = (0.0, 0.3, 0.9)


def population(n: int = 8000, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, 1.0, size=n)


def shift_test(sample: np.ndarray) -> float:
    """A one-sample t-test against zero: textbook power, so a bad answer here is a defect in
    the lookup rather than in the curve."""
    return float(stats.ttest_1samp(sample, popmean=0.0).pvalue)


def shift_injector(sample: np.ndarray, effect: float, rng: np.random.Generator) -> np.ndarray:
    return sample + effect


def unit_atlas(**kw) -> pd.DataFrame:
    return power_curve(
        population(),
        shift_test,
        shift_injector,
        method=kw.pop("method", "mean_shift"),
        effect_sizes=EFFECTS,
        sample_sizes=SIZES,
        n_replicates=kw.pop("n_replicates", 120),
        seed=kw.pop("seed", 0),
        **kw,
    )


def published(tmp_path):
    """A unit atlas on disk, which is what most of these tests have to load."""
    return publish_atlas(unit_atlas(), tmp_path / "mean_shift.parquet")


# ---------------------------------------------------------------- a stored atlas loads


def test_a_published_atlas_loads_and_answers_a_minimum_detectable_effect_query(tmp_path):
    """The card's must-pass, first half: load a stored atlas, ask for the smallest effect it
    can see at a sample size it measured, and get a measured number back."""
    publish_atlas(unit_atlas(), tmp_path / "mean_shift.parquet")
    lookup = power_lookup(tmp_path / "mean_shift.parquet")

    mde = lookup.minimum_detectable_effect("mean_shift", 400)
    assert mde in set(unit_atlas()["effect_size"])
    assert mde > 0
    # a bigger sample needs no bigger effect
    assert mde <= lookup.minimum_detectable_effect("mean_shift", 50)


def test_the_loaded_atlas_records_the_release_the_settings_and_the_seed(tmp_path):
    """A number whose source release cannot be named is not citable, which is what this card
    exists to stop."""
    publish_atlas(unit_atlas(seed=7), tmp_path / "a.parquet", settings={"estimator": "t"})
    loaded = power_lookup(tmp_path / "a.parquet").select("mean_shift")

    assert loaded.library_version == __version__
    assert loaded.seed == 7
    assert loaded.aggregation == UNIT_RUNG
    assert loaded.settings["estimator"] == "t"
    assert loaded.sample_sizes == SIZES
    assert f"forensics-core {__version__}" in loaded.cite()
    assert "seed=7" in loaded.cite()


def test_the_same_atlas_loaded_twice_is_one_entry(tmp_path):
    publish_atlas(unit_atlas(), tmp_path / "one.parquet")
    publish_atlas(unit_atlas(), tmp_path / "two.parquet")
    lookup = power_lookup([tmp_path / "one.parquet", tmp_path / "two.parquet"])
    assert len(lookup) == 1


def test_a_directory_of_atlases_loads_them_all(tmp_path):
    publish_atlas(unit_atlas(method="mean_shift"), tmp_path / "a.parquet")
    publish_atlas(unit_atlas(method="other", seed=3), tmp_path / "b.parquet")
    lookup = power_lookup(tmp_path)
    assert len(lookup) == 2
    assert lookup.methods() == ("mean_shift", "other")
    assert "mean_shift" in lookup.describe()
    assert __version__ in lookup.describe()


# ---------------------------------------------------------------- refusing to extrapolate


def test_a_query_below_the_measured_range_is_refused(tmp_path):
    """gosplan asking about n = 12 when the atlas starts at n = 50 must get an exception, not a
    plausible number: silent extrapolation here puts an unearned figure into a claim about the
    USSR."""
    lookup = power_lookup(published(tmp_path).path)
    with pytest.raises(AtlasError, match="does not cover n=12"):
        lookup.minimum_detectable_effect("mean_shift", 12)


def test_a_query_between_two_measured_points_is_refused(tmp_path):
    """n = 250 sits inside the measured span and was still never measured."""
    lookup = power_lookup(published(tmp_path).path)
    with pytest.raises(AtlasError, match="does not cover n=250"):
        lookup.minimum_detectable_effect("mean_shift", 250)


def test_a_query_above_the_measured_range_is_refused(tmp_path):
    lookup = power_lookup(published(tmp_path).path)
    with pytest.raises(AtlasError, match="does not cover n=100000"):
        lookup.minimum_detectable_effect("mean_shift", 100000)


def test_an_effect_that_never_reaches_the_target_is_refused(tmp_path):
    """The honest answer is that the method has no useful power here, not a number."""
    flat = power_curve(
        population(),
        shift_test,
        shift_injector,
        method="mean_shift",
        effect_sizes=(0.0, 0.001),
        sample_sizes=(100,),
        n_replicates=60,
    )
    publish_atlas(flat, tmp_path / "flat.parquet")
    lookup = power_lookup(tmp_path / "flat.parquet")
    with pytest.raises(AtlasError, match="no useful power at this sample size"):
        lookup.minimum_detectable_effect("mean_shift", 100)


def test_detectable_is_true_inside_the_range_and_false_outside_it(tmp_path):
    lookup = power_lookup(published(tmp_path).path)
    assert lookup.detectable("mean_shift", 400, 0.9) is True
    assert lookup.detectable("mean_shift", 400, 0.001) is False
    # outside the measured range it is False rather than a raise, matching atlas.detectable:
    # an atlas that has not shown the effect detectable has not shown it
    assert lookup.detectable("mean_shift", 12, 0.9) is False


def test_the_false_positive_check_carries_through_the_loader(tmp_path):
    """A method that rejects clean data half the time has high 'power' and no meaning, and the
    stored atlas must not launder it."""
    broken = power_curve(
        population(),
        lambda sample: 0.001,
        shift_injector,
        method="broken",
        effect_sizes=(0.0, 0.5),
        sample_sizes=(100,),
        n_replicates=20,
    )
    publish_atlas(broken, tmp_path / "broken.parquet")
    lookup = power_lookup(tmp_path / "broken.parquet")
    with pytest.raises(AtlasError, match="false-positive rate"):
        lookup.minimum_detectable_effect("broken", 100)


# ---------------------------------------------------------------- keeping two atlases apart


def test_two_atlases_that_differ_in_settings_are_kept_apart(tmp_path):
    publish_atlas(unit_atlas(seed=1), tmp_path / "a.parquet", settings={"variant": "a"})
    publish_atlas(unit_atlas(seed=2), tmp_path / "b.parquet", settings={"variant": "b"})
    lookup = power_lookup(tmp_path)
    assert len(lookup) == 2
    with pytest.raises(AtlasError, match="different atlases"):
        lookup.select("mean_shift")
    # each is still answerable on its own, which is what "kept apart" has to mean
    assert power_lookup(tmp_path / "a.parquet").minimum_detectable_effect("mean_shift", 400) > 0
    assert power_lookup(tmp_path / "b.parquet").minimum_detectable_effect("mean_shift", 400) > 0


def test_a_different_seed_alone_makes_a_different_atlas(tmp_path):
    publish_atlas(unit_atlas(seed=1), tmp_path / "a.parquet")
    publish_atlas(unit_atlas(seed=2), tmp_path / "b.parquet")
    assert len(power_lookup(tmp_path)) == 2


def test_a_method_or_rung_the_lookup_does_not_hold_is_refused(tmp_path):
    lookup = power_lookup(published(tmp_path).path)
    with pytest.raises(AtlasError, match="no atlas for method 'other'"):
        lookup.minimum_detectable_effect("other", 400)
    with pytest.raises(AtlasError, match="no atlas for method 'mean_shift' at rung 'region'"):
        lookup.minimum_detectable_effect("mean_shift", 400, aggregation="region")
    with pytest.raises(AtlasError, match="no atlas for method 'other'"):
        lookup.detectable("other", 400, 0.9)


# ---------------------------------------------------------------- the aggregation rung


def panel(n: int = 2400, seed: int = 0):
    """Honest precinct counts: numerator binomial in the denominator."""
    rng = np.random.default_rng(seed)
    den = rng.integers(600, 1400, size=n).astype(float)
    num = rng.binomial(den.astype(int), 0.55).astype(float)
    return num, den


def nested_keys(n: int, size: int) -> np.ndarray:
    return np.arange(n) // size


def share_test(num, den, pct) -> float:
    """A z-test that the aggregate share is 0.55. It reads only the totals, so its power is the
    same at every rung; that is deliberate here, because the rung tests are about the loader
    and not about aggregation."""
    p0 = 0.55
    total = float(den.sum())
    se = float(np.sqrt(p0 * (1.0 - p0) / total))
    return float(stats.norm.sf((float(num.sum()) / total - p0) / se))


def inflate(num, den, effect, rng):
    """Raise every unit's share by ``effect`` per cent. A no-op at zero."""
    num = np.asarray(num, dtype=float)
    if effect == 0.0:
        return num.copy()
    return num + (float(effect) * 0.01) * np.asarray(den, dtype=float)


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


def integer_share_test(num, den, pct) -> float:
    """How much mass sits within 0.05 of an integer, against a binomial null redrawn at each
    aggregated unit's own denominator. It reads ``pct``, so the two aggregation semantics give
    it different answers."""
    near = np.abs(pct - np.round(pct)) <= 0.05
    observed = float(near.sum())
    n_mc = 40
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


def unit_and_group_ladder(**kw) -> pd.DataFrame:
    num, den = panel(2400)
    return aggregation_ladder(
        num,
        den,
        [("unit", None), ("groups_8", nested_keys(num.size, 8))],
        share_test,
        inflate,
        effect_sizes=(0.0, 0.3),
        n_replicates=60,
        semantics=("sum_then_ratio",),
        seed=3,
        **kw,
    )


def test_a_ladder_rung_is_published_with_n_as_the_number_of_aggregate_units(tmp_path):
    """A gosplan card has sector-year totals, not precincts, so the rung is part of what it
    cites and n has to mean the number of aggregates."""
    publish_atlas(
        unit_and_group_ladder(), tmp_path / "rung.parquet", method="grouped", aggregation="groups_8"
    )
    lookup = power_lookup(tmp_path / "rung.parquet")
    atlas = lookup.select("grouped", aggregation="groups_8")

    assert atlas.aggregation == "groups_8"
    assert atlas.sample_sizes == (300,)
    assert atlas.settings["mean_group_size"] == pytest.approx(8.0)
    assert atlas.settings["semantics"] == "sum_then_ratio"
    assert lookup.minimum_detectable_effect("grouped", 300, aggregation="groups_8") == 0.3


def test_a_ladders_identity_rung_is_published_under_the_canonical_name(tmp_path):
    """Whatever the ladder calls its first level, an unaggregated curve is the unit rung, so
    the default aggregation= names it without the caller knowing the ladder's own label."""
    publish_atlas(unit_and_group_ladder(), tmp_path / "identity.parquet", method="grouped")
    lookup = power_lookup(tmp_path / "identity.parquet")
    atlas = lookup.select("grouped")
    assert atlas.aggregation == UNIT_RUNG
    assert atlas.sample_sizes == (2400,)
    assert atlas.settings["mean_group_size"] == pytest.approx(1.0)


def test_publishing_a_rung_the_ladder_never_measured_is_refused(tmp_path):
    with pytest.raises(AtlasError, match="no rung 'groups_64'"):
        publish_atlas(
            unit_and_group_ladder(),
            tmp_path / "rung.parquet",
            method="grouped",
            aggregation="groups_64",
        )
    assert not (tmp_path / "rung.parquet").exists()


def test_a_rung_carrying_two_disagreeing_semantics_is_refused_without_a_choice(tmp_path):
    """They are two different atlases, and one stored file cannot hold both."""
    num, den = panel(1600)
    ladder = aggregation_ladder(
        num,
        den,
        [("precinct", None), ("groups_8", nested_keys(num.size, 8))],
        integer_share_test,
        round_injector,
        effect_sizes=(0.3,),
        n_replicates=20,
        seed=5,
    )
    with pytest.raises(AtlasError, match="both semantics"):
        publish_atlas(
            ladder, tmp_path / "conflict.parquet", method="integer", aggregation="groups_8"
        )
    assert not (tmp_path / "conflict.parquet").exists()

    # at the identity rung the two coincide, so there is nothing to disambiguate
    identity = publish_atlas(ladder, tmp_path / "identity.parquet", method="integer")
    assert identity.aggregation == UNIT_RUNG
    # and naming the semantics publishes the rung
    chosen = publish_atlas(
        ladder,
        tmp_path / "chosen.parquet",
        method="integer",
        aggregation="groups_8",
        semantics="mean_of_ratios",
    )
    assert chosen.settings["semantics"] == "mean_of_ratios"


def test_a_unit_frame_cannot_be_published_at_a_named_rung(tmp_path):
    with pytest.raises(AtlasError, match="no 'level' column"):
        publish_atlas(unit_atlas(), tmp_path / "x.parquet", aggregation="region")


def test_a_ladder_frame_without_a_method_is_refused(tmp_path):
    with pytest.raises(AtlasError, match="pass method"):
        publish_atlas(unit_and_group_ladder(), tmp_path / "x.parquet")


def test_publishing_a_frame_under_a_method_it_was_not_measured_for_is_refused(tmp_path):
    with pytest.raises(AtlasError, match="misattribute"):
        publish_atlas(unit_atlas(), tmp_path / "x.parquet", method="something_else")
    assert not (tmp_path / "x.parquet").exists()


# ---------------------------------------------------------------- what is not an atlas


def test_an_atlas_saved_without_the_publish_record_is_refused(tmp_path):
    """save_atlas alone stamps no library version, and an uncitable atlas is not a published
    one."""
    save_atlas(unit_atlas(), tmp_path / "raw.parquet")
    with pytest.raises(AtlasError, match="records no library version"):
        power_lookup(tmp_path / "raw.parquet")


def test_a_frame_with_no_measurement_record_is_refused(tmp_path):
    pd.DataFrame(columns=ATLAS_COLUMNS).to_parquet(tmp_path / "empty.parquet", index=False)
    with pytest.raises(AtlasError, match="no measurement record"):
        power_lookup(tmp_path / "empty.parquet")


def test_a_ladder_frame_is_not_silently_read_as_a_unit_atlas(tmp_path):
    """Its sample size column is n_units, so reading it as a unit curve would answer a query
    about the wrong quantity."""
    unit_and_group_ladder().to_parquet(tmp_path / "ladder.parquet", index=False)
    with pytest.raises(AtlasError, match="missing the column"):
        power_lookup(tmp_path / "ladder.parquet")


def test_a_directory_holding_no_atlas_and_a_missing_path_are_refused(tmp_path):
    with pytest.raises(AtlasError, match="holds no"):
        power_lookup(tmp_path)
    with pytest.raises(AtlasError, match="does not exist"):
        power_lookup(tmp_path / "absent.parquet")
    with pytest.raises(AtlasError, match="no atlas path"):
        power_lookup([])


def test_an_empty_lookup_says_so_rather_than_answering(tmp_path):
    empty = PowerLookup()
    assert len(empty) == 0
    assert empty.describe() == "NO STORED ATLAS."
    with pytest.raises(AtlasError, match="holds nothing"):
        empty.minimum_detectable_effect("mean_shift", 400)

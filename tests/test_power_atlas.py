"""The atlas must rise with n and with effect size, and must refuse to extrapolate.

The refusals matter as much as the curves. An atlas that quietly interpolated between measured
points, or answered for a sample size it never measured, would put an invented number into a
claim about the historical record, which is the specific failure this programme exists to
avoid.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from forensics_core.dispersion.underdispersion import too_smooth_test
from forensics_core.inject import inject_smoothing
from forensics_core.power import (
    ATLAS_COLUMNS,
    AtlasError,
    detectable,
    load_atlas,
    minimum_detectable_effect,
    power_curve,
    save_atlas,
)
from forensics_core.power.atlas import FPR_TOLERANCE
from forensics_core.power.lookup import power_lookup, publish_atlas
from forensics_core.redteam import persistent_series

SIZES = (100, 400, 1600)
EFFECTS = (0.0, 0.3, 0.9)


def population(n: int = 20000, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, 1.0, size=n)


def shift_test(sample: np.ndarray) -> float:
    """A one-sample t-test against zero. Simple, correct, and its power is textbook, so a
    departure from the expected shape is a defect in the harness rather than in the test."""
    return float(stats.ttest_1samp(sample, popmean=0.0).pvalue)


def shift_injector(sample: np.ndarray, effect: float, rng: np.random.Generator) -> np.ndarray:
    """Shift the whole sample. A no-op at zero, as the harness requires."""
    return sample + effect


def small_atlas(**kw):
    return power_curve(
        population(),
        shift_test,
        shift_injector,
        method="mean_shift",
        effect_sizes=EFFECTS,
        sample_sizes=SIZES,
        n_replicates=kw.pop("n_replicates", 120),
        seed=kw.pop("seed", 0),
        **kw,
    )


# ---------------------------------------------------------------- shape


def test_the_atlas_has_the_documented_columns_and_one_row_per_cell():
    atlas = small_atlas()
    assert list(atlas.columns) == ATLAS_COLUMNS
    assert len(atlas) == len(SIZES) * len(EFFECTS)
    assert set(atlas["n"]) == set(SIZES)
    assert atlas.attrs["spec"].method == "mean_shift"


def test_power_rises_with_effect_size_at_fixed_n():
    atlas = small_atlas()
    for n in SIZES:
        row = atlas[atlas["n"] == n].sort_values("effect_size")
        powers = list(row["power"])
        assert powers == sorted(powers), f"power not monotone in effect at n={n}: {powers}"


def test_power_rises_with_n_at_fixed_effect_size():
    atlas = small_atlas()
    biggest = max(EFFECTS)
    row = atlas[atlas["effect_size"] == biggest].sort_values("n")
    powers = list(row["power"])
    assert powers[0] <= powers[-1], f"power not rising with n: {powers}"
    assert powers[-1] > 0.9, "a large effect at the largest n should be found nearly always"


def test_the_zero_effect_row_is_the_false_positive_rate_and_sits_near_alpha():
    """The row that makes every other row readable."""
    atlas = small_atlas(n_replicates=400)
    zero = atlas[atlas["effect_size"] == 0.0]
    assert (zero["power"] < 0.12).all(), (
        f"false-positive rate far above the 0.05 nominal: {list(zero['power'])}"
    )
    for n in SIZES:
        row = atlas[atlas["n"] == n]
        fpr = float(zero[zero["n"] == n]["power"].iloc[0])
        assert np.allclose(row["false_positive_rate"], fpr)


def test_the_standard_error_is_the_binomial_one():
    atlas = small_atlas()
    p = atlas["power"].to_numpy()
    k = atlas["n_replicates"].to_numpy()
    assert np.allclose(atlas["power_se"], np.sqrt(p * (1 - p) / k))


def test_the_atlas_is_reproducible_from_its_seed():
    a = small_atlas(seed=7)
    b = small_atlas(seed=7)
    assert list(a["power"]) == list(b["power"])


# ---------------------------------------------------------------- refusals


def test_a_population_smaller_than_the_largest_sample_is_refused():
    with pytest.raises(AtlasError, match="without replacement"):
        power_curve(
            population(n=200),
            shift_test,
            shift_injector,
            method="m",
            effect_sizes=(0.0, 0.5),
            sample_sizes=(500,),
            n_replicates=5,
        )


def test_an_injector_that_is_not_a_noop_at_zero_is_refused():
    """Otherwise the false-positive row would not measure the false-positive rate."""

    def sneaky(sample, effect, rng):
        return sample + effect + 0.5

    with pytest.raises(AtlasError, match="no-op at effect size zero"):
        power_curve(
            population(),
            shift_test,
            sneaky,
            method="m",
            effect_sizes=(0.0, 0.5),
            sample_sizes=(100,),
            n_replicates=5,
        )


def test_zero_is_added_to_the_effect_grid_even_if_omitted():
    atlas = power_curve(
        population(),
        shift_test,
        shift_injector,
        method="m",
        effect_sizes=(0.5,),
        sample_sizes=(200,),
        n_replicates=30,
    )
    assert 0.0 in set(atlas["effect_size"])


# ---------------------------------------------------------------- lookup


def test_minimum_detectable_effect_returns_a_measured_point():
    atlas = small_atlas(n_replicates=300)
    mde = minimum_detectable_effect(atlas, 1600, target_power=0.8)
    assert mde in set(atlas["effect_size"])
    assert mde > 0


def test_a_larger_sample_needs_no_larger_effect():
    atlas = small_atlas(n_replicates=300)
    small = minimum_detectable_effect(atlas, 100, target_power=0.8)
    large = minimum_detectable_effect(atlas, 1600, target_power=0.8)
    assert large <= small


def test_lookup_refuses_a_sample_size_it_never_measured():
    """The refusal that matters: gosplan asking about n=200 when the atlas starts at n=100
    must get an exception, not a plausible number."""
    atlas = small_atlas()
    with pytest.raises(AtlasError, match="does not cover n=250"):
        minimum_detectable_effect(atlas, 250)


def test_lookup_refuses_when_no_measured_effect_reaches_the_target():
    atlas = power_curve(
        population(),
        shift_test,
        shift_injector,
        method="m",
        effect_sizes=(0.0, 0.001),
        sample_sizes=(100,),
        n_replicates=60,
    )
    with pytest.raises(AtlasError, match="no useful power at this sample size"):
        minimum_detectable_effect(atlas, 100, target_power=0.8)


def test_lookup_refuses_an_atlas_whose_false_positive_rate_is_out_of_control():
    """A method that rejects half the time on clean data has high 'power' and no meaning."""
    atlas = power_curve(
        population(),
        lambda s: 0.001,  # rejects always, whatever the data
        shift_injector,
        method="broken",
        effect_sizes=(0.0, 0.5),
        sample_sizes=(100,),
        n_replicates=20,
    )
    with pytest.raises(AtlasError, match="false-positive rate"):
        minimum_detectable_effect(atlas, 100)
    # and the override exists, but has to be asked for
    assert minimum_detectable_effect(atlas, 100, check_calibration=False) == 0.5


def test_detectable_is_false_rather_than_raising_when_the_atlas_cannot_answer():
    atlas = small_atlas()
    assert detectable(atlas, 250, 0.9) is False


# ---------------------------------------------------------------- order-dependent tests


def honest_persistent_population() -> np.ndarray:
    """An honest AR(0.7) series of 20,000 in time order (trap core-1, docs/known_traps.md).

    The same population docs/redteam.md measures: persistent_series(20000, 0.7, seed=2028).
    """
    return persistent_series(20000, 0.7, seed=2028)[0]


def too_smooth_levels(sample: np.ndarray) -> float:
    """too_smooth_test on the levels: the setting whose docstring once advised it for a
    stationary series, and which depends on the order of the sample."""
    return too_smooth_test(sample, detrend="none", n_perm=99, seed=0).pvalue


def smoothing_injector(sample: np.ndarray, effect: float, rng: np.random.Generator) -> np.ndarray:
    """Remove ``effect`` of the deviation variance around a local trend; a no-op at zero."""
    return inject_smoothing(sample, retain=1.0 - effect)[0]


def persistent_atlas(sampling: str):
    return power_curve(
        honest_persistent_population(),
        too_smooth_levels,
        smoothing_injector,
        method="too_smooth_none",
        effect_sizes=(0.5,),
        sample_sizes=(100, 300),
        n_replicates=40,
        seed=0,
        sampling=sampling,
    )


def test_an_honest_persistent_population_gives_a_zero_effect_row_the_lookup_refuses(tmp_path):
    """With contiguous windows the false-positive row sees the persistence, and a published
    atlas built from it is refused rather than lending its power column to a claim.

    docs/redteam.md records a false-positive row of 1.00 at n = 50, 100 and 300 on this
    population (100 replicates), and 66 of 66 contiguous windows of 300 rejected. This test
    runs 40 replicates at n = 100 and 300.
    """
    atlas = persistent_atlas("contiguous")
    zero = atlas[atlas["effect_size"] == 0.0]
    assert (zero["power"] >= 0.9).all(), (
        f"too_smooth_test(detrend='none') on contiguous windows of an honest AR(0.7) series "
        f"rejected at {list(zero['power'])}; docs/redteam.md records 1.00 at every n"
    )

    publish_atlas(atlas, tmp_path / "too_smooth_none.parquet")
    lookup = power_lookup(tmp_path / "too_smooth_none.parquet")
    assert lookup.select("too_smooth_none").settings["sampling"] == "contiguous"
    for n in (100, 300):
        with pytest.raises(AtlasError, match="false-positive rate"):
            lookup.minimum_detectable_effect("too_smooth_none", n)
        assert lookup.detectable("too_smooth_none", n, 0.5) is False


def test_the_default_sampler_shuffles_the_same_population_into_a_nominal_looking_row():
    """Why the contiguous sampler exists. Drawing units at random returns them in random
    order, so the zero-effect row is the test on exchangeable data and passes the
    calibration check that the contiguous row fails. docs/redteam.md records 0.04 / 0.04 /
    0.02 at n = 50 / 100 / 300 under sampling="units", and a minimum detectable effect of 0.5.
    """
    atlas = persistent_atlas("units")
    zero = atlas[atlas["effect_size"] == 0.0]
    assert (zero["power"] <= FPR_TOLERANCE * 0.05).all(), list(zero["power"])
    assert atlas.attrs["spec"].settings["sampling"] == "units"
    # the blind spot, stated as what it does: a number comes back
    assert minimum_detectable_effect(atlas, 300) == 0.5


def test_a_contiguous_sample_is_a_window_of_consecutive_values():
    seen: list[np.ndarray] = []

    def record(sample: np.ndarray) -> float:
        seen.append(sample.copy())
        return 0.5

    population = np.arange(5000, dtype=float)
    power_curve(
        population,
        record,
        shift_injector,
        method="m",
        effect_sizes=(0.0,),
        sample_sizes=(50, 400),
        n_replicates=25,
        sampling="contiguous",
    )
    assert len(seen) == 50
    for sample in seen:
        assert np.all(np.diff(sample) == 1.0), "a contiguous sample must keep the order"
        assert 0.0 <= sample[0] and sample[-1] <= population[-1]
    starts = {float(sample[0]) for sample in seen}
    assert len(starts) > 1, "every replicate drew the same window"


def test_an_injector_writing_in_place_cannot_leak_into_later_windows():
    """A window is a slice of the population; handing the slice itself to an injector that
    writes into its argument would corrupt every later replicate drawn over it."""
    seen: list[np.ndarray] = []

    def in_place(sample, effect, rng):
        sample *= 1.0 - effect  # zeroes the window at effect 1.0
        return sample

    def record(sample: np.ndarray) -> float:
        seen.append(sample.copy())
        return 0.5

    power_curve(
        np.arange(1.0, 401.0),
        record,
        in_place,
        method="m",
        effect_sizes=(1.0,),
        sample_sizes=(100, 120),
        n_replicates=20,
        seed=3,
        sampling="contiguous",
    )
    # calls run n=100 (effect 0, then 1.0), then n=120 (effect 0, then 1.0)
    later_zero_row = seen[40:60]
    assert all(np.all(np.diff(s) == 1.0) for s in later_zero_row), (
        "an in-place injection at n=100 altered the population that n=120 sampled from"
    )


def test_a_contiguous_population_with_a_gap_is_refused():
    """Dropping a missing value would join two periods that were not adjacent."""
    population = honest_persistent_population()[:2000].copy()
    population[700] = np.nan
    with pytest.raises(AtlasError, match="finite throughout"):
        power_curve(
            population,
            too_smooth_levels,
            smoothing_injector,
            method="m",
            effect_sizes=(0.5,),
            sample_sizes=(100,),
            n_replicates=5,
            sampling="contiguous",
        )


def test_an_unknown_sampler_is_refused():
    with pytest.raises(AtlasError, match="sampling must be one of"):
        power_curve(
            population(),
            shift_test,
            shift_injector,
            method="m",
            effect_sizes=(0.5,),
            sample_sizes=(100,),
            n_replicates=5,
            sampling="blocks",
        )


def test_settings_that_contradict_the_sampler_are_refused():
    """The record must describe the measurement that produced the numbers."""
    with pytest.raises(AtlasError, match="different measurement"):
        power_curve(
            population(),
            shift_test,
            shift_injector,
            method="m",
            effect_sizes=(0.5,),
            sample_sizes=(100,),
            n_replicates=5,
            settings={"sampling": "contiguous"},
        )


def test_publishing_cannot_relabel_the_sampler(tmp_path):
    """The published record is what the lookup and a citation read, so it must name the
    sampler that produced the numbers. A shuffled-units curve published as "contiguous" would
    be the blind spot again, under a label that says it was fixed."""
    atlas = power_curve(
        population(),
        shift_test,
        shift_injector,
        method="m",
        effect_sizes=(0.5,),
        sample_sizes=(100,),
        n_replicates=5,
    )
    path = tmp_path / "m.parquet"
    with pytest.raises(AtlasError, match="different measurement"):
        publish_atlas(atlas, path, settings={"sampling": "contiguous"})
    assert not path.exists(), "a refused publication must leave no file behind"

    # settings that agree with the measurement, or add to it, still publish
    publish_atlas(atlas, path, settings={"sampling": "units", "note": "agrees"})
    published = power_lookup(path).select("m").settings
    assert published["sampling"] == "units"
    assert published["note"] == "agrees"


# ---------------------------------------------------------------- storage


def test_an_atlas_round_trips_through_parquet_with_its_spec(tmp_path):
    atlas = small_atlas()
    path = save_atlas(atlas, tmp_path / "a.parquet")
    back = load_atlas(path)
    assert list(back.columns) == ATLAS_COLUMNS
    assert list(back["power"]) == list(atlas["power"])
    assert back.attrs["spec"].method == "mean_shift"
    assert back.attrs["spec"].alpha == 0.05

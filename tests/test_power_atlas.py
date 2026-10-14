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

from forensics_core.power import (
    ATLAS_COLUMNS,
    AtlasError,
    detectable,
    load_atlas,
    minimum_detectable_effect,
    power_curve,
    save_atlas,
)

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


# ---------------------------------------------------------------- storage


def test_an_atlas_round_trips_through_parquet_with_its_spec(tmp_path):
    atlas = small_atlas()
    path = save_atlas(atlas, tmp_path / "a.parquet")
    back = load_atlas(path)
    assert list(back.columns) == ATLAS_COLUMNS
    assert list(back["power"]) == list(atlas["power"])
    assert back.attrs["spec"].method == "mean_shift"
    assert back.attrs["spec"].alpha == 0.05


# ---------------------------------------------------------------- refusals


def refusing_test(refuse: float, reject: float, seed: int = 0):
    """A test that raises on ``refuse`` of its calls and rejects ``reject`` of its answers,
    whatever the sample. Its false-positive rate is ``reject`` by construction."""
    rng = np.random.default_rng(seed)

    def test(sample):
        if rng.random() < refuse:
            raise ValueError("refused")
        return 0.001 if rng.random() < reject else 0.5

    return test


def test_a_refusal_is_counted_beside_the_rate_rather_than_as_a_non_rejection():
    """Refusing 70% of the time and rejecting 25% of its answers is five times nominal. Read
    over all replicates that came out as about 0.075, under the 2x-alpha guard, and the
    calibration check passed a test it exists to stop."""
    atlas = power_curve(
        population(),
        refusing_test(0.7, 0.25),
        shift_injector,
        method="refuses",
        effect_sizes=(0.0, 0.5),
        sample_sizes=(100,),
        n_replicates=400,
    )
    zero = atlas[atlas["effect_size"] == 0.0].iloc[0]
    # about 120 answered replicates, so the standard error of 0.25 is about 0.04
    assert abs(zero["false_positive_rate"] - 0.25) < 0.1, (
        f"false-positive rate {zero['false_positive_rate']:.4f}; refusals were counted as "
        "non-rejections if this reads about 0.075"
    )
    assert 240 <= zero["n_failed"] <= 320
    assert zero["refusal_share"] == zero["n_failed"] / 400
    assert zero["power"] == zero["false_positive_rate"]
    with pytest.raises(AtlasError, match="false-positive rate is"):
        minimum_detectable_effect(atlas, 100)


def test_a_cell_where_the_test_never_answered_has_no_power_and_is_refused():
    def always_refuses(sample):
        raise ValueError("no unit survives exclusion")

    atlas = power_curve(
        population(),
        always_refuses,
        shift_injector,
        method="never_answers",
        effect_sizes=(0.0, 0.5),
        sample_sizes=(100,),
        n_replicates=20,
    )
    assert (atlas["n_failed"] == 20).all()
    assert atlas["power"].isna().all(), "zero would claim the test never rejects"
    assert atlas["false_positive_rate"].isna().all()
    with pytest.raises(AtlasError, match="refused on 100%"):
        minimum_detectable_effect(atlas, 100, check_calibration=False)


def test_a_refusal_share_limit_refuses_the_query_when_the_null_row_exceeds_it():
    atlas = power_curve(
        population(),
        refusing_test(0.7, 0.0),
        shift_injector,
        method="refuses",
        effect_sizes=(0.0, 0.5),
        sample_sizes=(100,),
        n_replicates=100,
    )
    with pytest.raises(AtlasError, match="refused on"):
        minimum_detectable_effect(atlas, 100, max_refusal_share=0.5)
    with pytest.raises(AtlasError, match="max_refusal_share"):
        minimum_detectable_effect(atlas, 100, max_refusal_share=1.5)


def test_an_atlas_saved_without_refusal_columns_loads_them_as_not_recorded(tmp_path):
    atlas = small_atlas().drop(columns=["n_failed", "refusal_share"])
    back = load_atlas(save_atlas(atlas, tmp_path / "old.parquet"))
    assert list(back.columns) == ATLAS_COLUMNS
    assert back["n_failed"].isna().all(), "an unrecorded refusal count is not zero"

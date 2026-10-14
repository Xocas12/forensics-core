"""The atlas must rise with n and with effect size, and must refuse to extrapolate.

The refusals matter as much as the curves. An atlas that quietly interpolated between measured
points, or answered for a sample size it never measured, would put an invented number into a
claim about the historical record, which is the specific failure this programme exists to
avoid.
"""

from __future__ import annotations

import warnings

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


# ---------------------------------------------------------------- a null that does not match


def synthetic_levels(n: int = 20000, seed: int = 1) -> np.ndarray:
    """iid N(100, 5) levels. power_curve draws from them in random order, so every sample the
    test sees is exchangeable, which is what the too-smooth atlas was measured on."""
    return np.random.default_rng(seed).normal(100.0, 5.0, size=n)


def blind_at_zero_test(sample: np.ndarray) -> float:
    """Finds a shift but never rejects an unshifted sample: zero false positives by
    construction, the shape a mismatched null leaves in an atlas."""
    return 0.001 if sample.mean() > 0.4 else 1.0


def test_a_zero_effect_row_far_below_nominal_is_flagged_when_the_atlas_is_built():
    """Zero rejections in 100 null replicates against a nominal 0.05 happens to a calibrated
    test with probability 0.006. Whether the null does not match the samples or the test is far
    more conservative than its level, the power column is not the method's power at alpha, and
    whoever reads the table has to be told."""
    with pytest.warns(UserWarning, match="far below nominal") as caught:
        atlas = power_curve(
            population(),
            blind_at_zero_test,
            shift_injector,
            method="blind_at_zero",
            effect_sizes=(0.0, 0.9),
            sample_sizes=(100, 400),
            n_replicates=100,
        )
    assert (atlas[atlas["effect_size"] == 0.0]["power"] == 0.0).all()
    flagged = [str(w.message) for w in caught if "far below nominal" in str(w.message)]
    assert len(flagged) == 1, flagged
    message = flagged[0]
    assert "n=100" in message and "n=400" in message, message
    assert "0 of 100" in message, message


def test_the_far_below_flag_is_an_atlas_calibration_warning():
    from forensics_core.power import AtlasCalibrationWarning

    assert issubclass(AtlasCalibrationWarning, UserWarning)
    with pytest.warns(AtlasCalibrationWarning, match="far below nominal"):
        power_curve(
            population(),
            blind_at_zero_test,
            shift_injector,
            method="blind_at_zero",
            effect_sizes=(0.0, 0.9),
            sample_sizes=(100,),
            n_replicates=100,
        )


def test_lookup_refuses_a_zero_effect_row_far_below_nominal():
    """The power column of an atlas whose null rejects nothing is not the method's power: the
    lookup refuses it the way it refuses one that rejects too much, with the same override."""
    with pytest.warns(UserWarning):
        atlas = power_curve(
            population(),
            blind_at_zero_test,
            shift_injector,
            method="blind_at_zero",
            effect_sizes=(0.0, 0.9),
            sample_sizes=(100,),
            n_replicates=100,
        )
    with pytest.raises(AtlasError, match="far below nominal"):
        minimum_detectable_effect(atlas, 100)
    assert detectable(atlas, 100, 0.9) is False
    assert minimum_detectable_effect(atlas, 100, check_calibration=False) == 0.9


def test_the_far_below_refusal_carries_through_a_published_atlas(tmp_path):
    from forensics_core.power.lookup import power_lookup, publish_atlas

    with pytest.warns(UserWarning):
        atlas = power_curve(
            population(),
            blind_at_zero_test,
            shift_injector,
            method="blind_at_zero",
            effect_sizes=(0.0, 0.9),
            sample_sizes=(100,),
            n_replicates=100,
        )
    publish_atlas(atlas, tmp_path / "blind.parquet")
    with pytest.raises(AtlasError, match="far below nominal"):
        power_lookup(tmp_path / "blind.parquet").minimum_detectable_effect("blind_at_zero", 100)


def test_a_calibrated_atlas_is_not_flagged():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        atlas = small_atlas(n_replicates=400)
    for n in SIZES:
        minimum_detectable_effect(atlas, n, target_power=0.8)


def test_too_few_replicates_cannot_flag_a_low_rate():
    """Zero of 60 happens to a calibrated test with probability 0.046, so 60 replicates cannot
    tell a mismatched null from luck, and the flag stays silent rather than guessing."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        atlas = power_curve(
            population(),
            blind_at_zero_test,
            shift_injector,
            method="blind_at_zero",
            effect_sizes=(0.0, 0.9),
            sample_sizes=(100,),
            n_replicates=60,
        )
    assert minimum_detectable_effect(atlas, 100) == 0.9


def test_too_smooth_diff_on_exchangeable_samples_is_flagged_as_a_misconfigured_null():
    """The case the old docs/power_atlas.md result came from: too_smooth_test's default
    detrend="diff" run on power_curve's random-order samples. Its zero-effect row rejects
    nothing, which the atlas now flags instead of reading it as a conservative test; the same
    samples under detrend="none", the exact null for them, are not flagged."""
    from forensics_core.power import too_smooth_atlas

    kw = dict(effect_sizes=(0.0, 0.5), sample_sizes=(50, 300), n_perm=99, n_replicates=120, seed=1)
    with pytest.warns(UserWarning, match="far below nominal"):
        diff = too_smooth_atlas(synthetic_levels(), detrend="diff", **kw)
    assert (diff[diff["effect_size"] == 0.0]["power"] == 0.0).all()
    with pytest.raises(AtlasError, match="far below nominal"):
        minimum_detectable_effect(diff, 300)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        none = too_smooth_atlas(synthetic_levels(), detrend="none", **kw)
    assert minimum_detectable_effect(none, 300) == 0.5


# ---------------------------------------------------------------- too-smooth records its detrend


@pytest.mark.parametrize("detrend", ["none", "linear", "diff"])
def test_every_row_of_a_too_smooth_atlas_records_its_detrend(detrend):
    from forensics_core.power import too_smooth_atlas

    atlas = too_smooth_atlas(
        synthetic_levels(),
        detrend=detrend,
        effect_sizes=(0.8,),
        sample_sizes=(50, 100),
        n_perm=49,
        n_replicates=10,
        settings={"population": "iid N(100, 5)"},
    )
    assert (atlas["method"] == f"too_smooth_{detrend}").all()
    settings = atlas.attrs["spec"].settings
    assert settings["detrend"] == detrend
    assert settings["n_perm"] == 49
    assert settings["population"] == "iid N(100, 5)"


def test_a_published_too_smooth_atlas_cites_its_detrend(tmp_path):
    from forensics_core.power import too_smooth_atlas
    from forensics_core.power.lookup import power_lookup, publish_atlas

    atlas = too_smooth_atlas(
        synthetic_levels(),
        detrend="none",
        effect_sizes=(0.8,),
        sample_sizes=(50,),
        n_perm=49,
        n_replicates=10,
    )
    publish_atlas(atlas, tmp_path / "too_smooth_none.parquet")
    stored = power_lookup(tmp_path / "too_smooth_none.parquet").select("too_smooth_none")
    assert (stored.frame["method"] == "too_smooth_none").all()
    assert stored.settings["detrend"] == "none" and stored.settings["n_perm"] == 49
    assert '"detrend": "none"' in stored.cite()


def test_a_too_smooth_atlas_is_reproducible_from_its_seed():
    from forensics_core.power import too_smooth_atlas

    def build():
        return too_smooth_atlas(
            synthetic_levels(),
            detrend="none",
            effect_sizes=(0.5,),
            sample_sizes=(50,),
            n_perm=49,
            n_replicates=30,
            seed=4,
        )

    assert list(build()["power"]) == list(build()["power"])


def test_too_smooth_atlas_has_no_default_detrend():
    from forensics_core.power import too_smooth_atlas

    with pytest.raises(TypeError, match="detrend"):
        too_smooth_atlas(synthetic_levels(), effect_sizes=(0.5,), sample_sizes=(50,))
    with pytest.raises(AtlasError, match="detrend must be one of"):
        too_smooth_atlas(
            synthetic_levels(), detrend="quadratic", effect_sizes=(0.5,), sample_sizes=(50,)
        )
    with pytest.raises(AtlasError, match=r"outside \[0, 1\]"):
        too_smooth_atlas(
            synthetic_levels(), detrend="none", effect_sizes=(1.5,), sample_sizes=(50,)
        )
    with pytest.raises(AtlasError, match="contradict"):
        too_smooth_atlas(
            synthetic_levels(),
            detrend="none",
            effect_sizes=(0.5,),
            sample_sizes=(50,),
            settings={"detrend": "diff"},
        )


@pytest.mark.parametrize(
    ("method", "settings"),
    [
        ("too_smooth", {}),
        ("too_smooth", {"detrend": "diff", "n_perm": 199}),
        ("too_smooth_diff", {"n_perm": 199}),
        ("too_smooth_none", {"detrend": "diff", "n_perm": 199}),
        ("too_smooth_none", {"detrend": "none"}),
    ],
)
def test_a_too_smooth_atlas_that_does_not_record_its_detrend_is_refused(method, settings):
    """A too-smooth number without its detrend cannot be read, so power_curve refuses to
    measure one rather than producing rows that do not say which null they were run under."""
    with pytest.raises(AtlasError, match="must record the detrend"):
        power_curve(
            synthetic_levels(),
            lambda s: 0.5,
            lambda s, e, rng: s,
            method=method,
            effect_sizes=(0.5,),
            sample_sizes=(50,),
            n_replicates=5,
            settings=settings,
        )


def test_publishing_a_too_smooth_frame_without_its_detrend_is_refused(tmp_path):
    """The same rule at the citable boundary, for a frame that did not come from power_curve."""
    import pandas as pd

    from forensics_core.power.lookup import publish_atlas

    frame = pd.DataFrame([["too_smooth", 50, 0.0, 0.0, 0.0, 100, 0.05, 0.0]], columns=ATLAS_COLUMNS)
    with pytest.raises(AtlasError, match="must record the detrend"):
        publish_atlas(frame, tmp_path / "x.parquet")
    assert not (tmp_path / "x.parquet").exists()


def test_the_doc_names_the_detrend_behind_every_too_smooth_number():
    """docs/power_atlas.md once read power 0.00 and a false-positive rate of 0.00 as a weak,
    conservative test. Those came from detrend="diff" on random-order samples, a null that
    does not match them. Every too-smooth row the doc quotes must say which detrend produced
    it, and the withdrawn reading must not come back."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[1] / "docs" / "power_atlas.md").read_text(
        encoding="utf-8"
    )
    assert "conservative rather than broken" not in doc
    assert "underdispersion family is weak" not in doc

    lines = doc.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("| `detrend` |"))
    rows = []
    for line in lines[header + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(line)
    named = [row.split("|")[1].strip().split()[0] for row in rows]
    assert named == ["`diff`", "`none`", "`linear`"], named
    assert "flagged" in rows[0], "the diff row must say its false-positive row is flagged"

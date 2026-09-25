"""The common scale is monotone in every injector's own parameter, and refuses to overclaim.

The must-pass has two halves. Monotonicity puts the four mechanisms on one axis, which is
what the power atlas needs. The second half is the refusal: the scale is a gross quantity, and
for two of the four mechanisms gross movement is not net misreporting, so the substantive
sentence must not be writable for them.
"""

from __future__ import annotations

import numpy as np
import pytest

from forensics_core.effect import (
    QUANTITY_MECHANISMS,
    SHAPE_MECHANISMS,
    CommonEffect,
    EffectError,
    as_quantity_claim,
    effect_table,
    measure_effect,
)
from forensics_core.inject import (
    inject_bunching,
    inject_padding,
    inject_rounding,
    inject_smoothing,
)


def percentage_panel(n: int = 4000, seed: int = 0):
    rng = np.random.default_rng(seed)
    den = rng.integers(400, 3000, size=n).astype(float)
    val = rng.binomial(den.astype(int), 0.55).astype(float)
    return val, den


def running(n: int = 4000, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(100.0, 12.0, size=n)


def series(n: int = 60, sd: float = 8.0, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(100.0, sd, size=n)


# ---------------------------------------------------------------- monotone in every parameter


def test_rounding_displacement_is_monotone_and_linear_in_fraction():
    val, den = percentage_panel()
    ds = []
    for f in (0.0, 0.05, 0.1, 0.25, 0.5, 1.0):
        out, _ = inject_rounding(val, den, fraction=f, seed=1)
        ds.append(measure_effect(val, out).displacement)
    assert ds == sorted(ds), f"not monotone in fraction: {ds}"
    # the mean relative displacement per touched unit does not depend on how many are touched,
    # so displacement is linear in fraction; check the top of the range against the quarter
    assert ds[-1] / ds[3] == pytest.approx(4.0, rel=0.05)


def test_bunching_displacement_is_monotone_and_linear_in_mass():
    run = running()
    ds = []
    for m in (0.0, 0.1, 0.3, 0.6, 0.9):
        out, _ = inject_bunching(run, threshold=100.0, mass=m, window=4.0, side="above", seed=1)
        ds.append(measure_effect(run, out).displacement)
    assert ds == sorted(ds), f"not monotone in mass: {ds}"
    assert ds[-1] / ds[2] == pytest.approx(3.0, rel=0.10)


def test_padding_displacement_recovers_the_magnitude_exactly():
    """The cleanest of the four: the block is fixed, so mean relative displacement IS the
    magnitude and displacement is the block share times it."""
    ser = series()
    block = np.arange(20, 36)
    for mag in (0.05, 0.1, 0.3, 0.6):
        out, _ = inject_padding(ser, years=block, magnitude=mag, seed=1)
        eff = measure_effect(ser, out)
        assert eff.mean_relative_displacement == pytest.approx(mag, rel=1e-9)
        assert eff.share_touched == pytest.approx(len(block) / len(ser), rel=1e-9)
        assert eff.displacement == pytest.approx(len(block) / len(ser) * mag, rel=1e-9)


def test_smoothing_displacement_is_monotone_decreasing_in_retain():
    """The inverted parameter: retain=1 is the no-op, so more distortion is a lower retain."""
    ser = series()
    ds = []
    for k in (1.0, 0.8, 0.5, 0.2, 0.02):
        out, _ = inject_smoothing(ser, retain=k, seed=1)
        ds.append(measure_effect(ser, out).displacement)
    assert ds == sorted(ds), f"displacement must rise as retain falls: {ds}"
    assert ds[0] == 0.0, "retain=1 must be the no-op"


def test_all_four_mechanisms_land_on_one_axis():
    """The point of the card: four parameters in four units, one comparable number."""
    val, den = percentage_panel()
    run = running()
    ser = series()
    effects = {
        "rounding": measure_effect(val, inject_rounding(val, den, fraction=0.5, seed=1)[0]),
        "bunching": measure_effect(
            run, inject_bunching(run, threshold=100.0, mass=0.6, window=4.0, seed=1)[0]
        ),
        "padding": measure_effect(
            ser, inject_padding(ser, years=np.arange(20, 36), magnitude=0.1, seed=1)[0]
        ),
        "smoothing": measure_effect(ser, inject_smoothing(ser, retain=0.5, seed=1)[0]),
    }
    for name, eff in effects.items():
        assert eff.displacement > 0, f"{name} produced no measurable displacement"
        assert 0 < eff.share_touched <= 1


# ---------------------------------------------------------------- the split the scale forces


def test_padding_and_bunching_move_quantity():
    """Every touched unit moves the same way, so gross displacement is net misreporting."""
    run = running()
    ser = series()
    bunched = measure_effect(
        run, inject_bunching(run, threshold=100.0, mass=0.6, window=4.0, seed=1)[0]
    )
    padded = measure_effect(
        ser, inject_padding(ser, years=np.arange(20, 36), magnitude=0.3, seed=1)[0]
    )
    assert bunched.directionality == pytest.approx(1.0, abs=1e-9)
    assert padded.directionality == pytest.approx(1.0, abs=1e-9)
    assert bunched.moves_quantity and padded.moves_quantity


def test_rounding_and_smoothing_do_not_move_quantity():
    """The finding that splits the scale. Units round up and down about equally; smoothing
    shrinks deviations both ways around a level it preserves. Gross movement is real and
    measurable; net movement is essentially zero."""
    val, den = percentage_panel()
    ser = series()
    rounded = measure_effect(val, inject_rounding(val, den, fraction=1.0, seed=1)[0])
    smoothed = measure_effect(ser, inject_smoothing(ser, retain=0.02, seed=1)[0])

    assert abs(rounded.directionality) < 0.05, (
        f"rounding directionality {rounded.directionality:.4f}; docs/effect_size.md records 0.018"
    )
    assert abs(smoothed.directionality) < 0.05
    assert not rounded.moves_quantity
    assert not smoothed.moves_quantity
    # and the gross movement is genuinely much larger than the net
    assert rounded.gross_displacement > 20 * abs(rounded.net_displacement)


def test_the_substantive_sentence_is_refused_where_it_would_be_false():
    val, den = percentage_panel()
    rounded = measure_effect(val, inject_rounding(val, den, fraction=1.0, seed=1)[0])
    with pytest.raises(EffectError, match="the movement cancels"):
        as_quantity_claim(rounded)


def test_the_sentence_is_refused_by_mechanism_name_even_before_measurement():
    """A caller who knows the mechanism should not have to measure to be stopped."""
    ser = series()
    smoothed = measure_effect(ser, inject_smoothing(ser, retain=0.5, seed=1)[0])
    with pytest.raises(EffectError, match="shape of the numbers"):
        as_quantity_claim(smoothed, mechanism="smoothing")


def test_the_sentence_is_written_where_it_holds():
    ser = series()
    padded = measure_effect(
        ser, inject_padding(ser, years=np.arange(20, 36), magnitude=0.3, seed=1)[0]
    )
    sentence = as_quantity_claim(padded, mechanism="padding")
    assert "26.7% of units" in sentence
    assert "30.0% each" in sentence


def test_the_two_mechanism_lists_are_disjoint_and_cover_the_four_injectors():
    assert set(QUANTITY_MECHANISMS) | set(SHAPE_MECHANISMS) == {
        "rounding",
        "bunching",
        "padding",
        "smoothing",
    }
    assert not set(QUANTITY_MECHANISMS) & set(SHAPE_MECHANISMS)


# ---------------------------------------------------------------- native units are preserved


def test_the_table_prints_native_values_unchanged_beside_the_common_scale():
    """The card's forbidden list: never silently rescale a published estimator's output."""
    ser = series()
    padded = measure_effect(
        ser, inject_padding(ser, years=np.arange(20, 36), magnitude=0.3, seed=1)[0]
    )
    val, den = percentage_panel()
    rounded = measure_effect(val, inject_rounding(val, den, fraction=0.5, seed=1)[0])

    table = effect_table(
        [
            ("integer_excess", "excess units (count)", 137.0, rounded),
            ("bunching_estimator", "normalised excess mass", 0.42, padded),
        ]
    )
    assert "137" in table, "the estimator's own number must appear unchanged"
    assert "0.42" in table
    assert "excess units (count)" in table
    assert "never rescaled" in table
    assert "shape" in table and "quantity" in table


def test_an_empty_table_says_so():
    assert "NO EFFECTS MEASURED" in effect_table([])


# ---------------------------------------------------------------- refusals and edges


def test_an_unchanged_series_has_zero_effect_rather_than_a_division_by_zero():
    ser = series()
    eff = measure_effect(ser, ser)
    assert eff.displacement == 0.0
    assert eff.n_touched == 0
    assert eff.directionality == 0.0


def test_mismatched_lengths_are_refused():
    with pytest.raises(EffectError, match="same length"):
        measure_effect([1.0, 2.0], [1.0])


def test_non_finite_values_are_refused_rather_than_dropped():
    with pytest.raises(EffectError, match="refused rather than"):
        measure_effect([1.0, 2.0], [1.0, np.nan])


def test_an_all_zero_baseline_is_refused():
    with pytest.raises(EffectError, match="identically zero"):
        measure_effect([0.0, 0.0], [1.0, 2.0])


def test_a_touched_unit_with_a_zero_baseline_is_counted_not_infinite():
    """Its relative displacement is undefined, and an infinity would swallow the mean."""
    eff = measure_effect([0.0, 10.0, 10.0], [5.0, 12.0, 8.0])
    assert eff.n_undefined == 1
    assert np.isfinite(eff.mean_relative_displacement)
    assert eff.mean_relative_displacement == pytest.approx(0.2)


def test_the_effect_round_trips_to_a_dict():
    ser = series()
    eff = measure_effect(ser, inject_smoothing(ser, retain=0.5, seed=1)[0])
    d = eff.to_dict()
    assert d["moves_quantity"] is False
    assert isinstance(
        CommonEffect(**{k: v for k, v in d.items() if k != "moves_quantity"}), CommonEffect
    )

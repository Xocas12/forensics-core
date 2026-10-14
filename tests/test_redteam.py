"""Every trap generates honest data, and at least one trap makes a real detector fire.

The second half is the card's point and the reason this file runs the actual library tests
rather than stand-ins. A red-team pass in which nothing ever fires has not been shown capable
of firing, and would quietly become a certificate.

Where a detector does fire, the pair is asserted here AND must appear in `docs/redteam.md` --
`test_every_firing_pair_is_in_the_document` enforces that, because the card's forbidden list
names quietly dropping a trap that makes a detector look bad.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from forensics_core.digits.integer_pct import integer_excess
from forensics_core.digits.terminal import terminal_digit_test
from forensics_core.redteam import (
    TRAPS,
    RedTeamError,
    TrapSample,
    casualties,
    format_redteam_table,
    heterogeneous_mixture,
    level_shift,
    ocr_firing_threshold,
    ocr_gate,
    ocr_noise,
    red_team,
    reweighting,
    small_units,
    survivors,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "redteam.md"


# ---------------------------------------------------------------- nothing is injected


def test_small_units_numerators_are_exactly_binomial_draws():
    """The honesty claim, checked as arithmetic rather than taken from the docstring."""
    pct, sample = small_units(4000, [80, 120, 200], p=0.55, seed=0)
    den = sample.truth["denominators"]
    num = sample.truth["numerators"]
    assert np.allclose(pct, 100.0 * num / den)
    assert ((num >= 0) & (num <= den)).all()
    # a binomial draw at p=0.55 has mean 0.55*den and sd sqrt(den*p*q); over 4000 units the
    # pooled rate is within a few SEs of p, and a rounding step would not preserve that
    pooled = num.sum() / den.sum()
    se = np.sqrt(0.55 * 0.45 / den.sum())
    assert abs(pooled - 0.55) < 5 * se, f"pooled rate {pooled:.5f} is not the stated p"


def test_small_units_has_no_reference_to_integers_in_its_source():
    """A generator that snapped values onto integers would produce the same spike and would
    not be honest data. The mechanism has to be checkable, so it is checked."""
    from forensics_core import redteam

    source = Path(redteam.__file__).read_text(encoding="utf-8")
    body = source.split("def small_units(")[1].split("\ndef ")[0]
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith(("#", '"', "'"))
    )
    for forbidden in ("round(", "np.round", "floor", "ceil", "tolerance"):
        assert forbidden not in code, f"small_units contains {forbidden!r}; that is a rounding step"


def test_the_mixture_keeps_every_unit_inside_its_own_group():
    values, sample = heterogeneous_mixture(
        [
            {"name": "urban", "n": 2000, "mean": 45.0, "sd": 6.0},
            {"name": "rural", "n": 2000, "mean": 80.0, "sd": 5.0},
        ],
        seed=1,
    )
    labels = sample.truth["group_of_unit"]
    assert len(values) == len(labels) == 4000
    urban = values[labels == "urban"]
    rural = values[labels == "rural"]
    assert abs(urban.mean() - 45.0) < 1.0
    assert abs(rural.mean() - 80.0) < 1.0
    assert rural.mean() > urban.mean(), "the two modes must be separated"


def test_undoing_a_level_shift_restores_the_input_exactly():
    """The strongest available statement that nothing else was done to the numbers."""
    rng = np.random.default_rng(2)
    series = rng.normal(100.0, 5.0, size=60)

    shifted, sample = level_shift(series, at=30, size=25.0)

    # the pre-break segment is bitwise untouched -- nothing was reordered or resampled
    assert np.array_equal(shifted[:30], series[:30])
    # and the post-break segment differs by the shift alone. Not bitwise: x + 25.0 - 25.0 is
    # not exactly x in binary floating point, and asserting that it were would be asserting
    # something false about arithmetic rather than something true about the generator.
    assert np.allclose(shifted[30:] - 25.0, series[30:], rtol=0, atol=1e-12)
    assert np.array_equal(sample.truth["series"], series)

    scaled, _ = level_shift(series, at=30, size=10.0, kind="multiplicative")
    assert np.array_equal(scaled[:30], series[:30])
    assert np.allclose(scaled[30:] / 10.0, series[30:], rtol=1e-12, atol=0)


def test_reweighting_leaves_the_physical_quantities_identical():
    """The Gerschenkron effect: the same real output, two very different growth stories."""
    periods = 30
    t = np.arange(periods)[:, None]
    # one good expands fast, one is flat; early prices weight the fast one highly
    quantities = np.column_stack(
        [
            10 * 1.12 ** t.ravel(),
            10 * 1.10 ** t.ravel(),
            np.full(periods, 40.0),
            np.full(periods, 30.0),
        ]
    )
    prices = np.column_stack(
        [
            np.linspace(8.0, 1.0, periods),  # the expanding good gets cheap
            np.linspace(6.0, 1.0, periods),
            np.linspace(1.0, 3.0, periods),
            np.linspace(1.0, 3.0, periods),
        ]
    )

    early, s_early = reweighting(quantities, prices, base_period=0)
    late, s_late = reweighting(quantities, prices, base_period=periods - 1)

    assert np.array_equal(s_early.truth["quantities"], s_late.truth["quantities"])
    assert early[0] == pytest.approx(100.0) and late[-1] == pytest.approx(100.0)
    growth_early = early[-1] / early[0]
    growth_late = late[-1] / late[0]
    assert growth_early > growth_late, (
        f"early-year weights must produce the faster growth: {growth_early:.2f} vs "
        f"{growth_late:.2f}. If they do not, the fixture is not exhibiting the trap."
    )


def test_ocr_noise_changes_only_the_permitted_digit_positions():
    rng = np.random.default_rng(3)
    values = rng.integers(1000, 9999, size=3000).astype(float)
    out, sample = ocr_noise(values, error_rate=0.3, positions=(0,), seed=4)

    changed = out != values
    assert changed.any(), "an error rate of 0.3 must corrupt something"
    # only the last digit moved, so the tens-and-above part is untouched everywhere
    assert np.array_equal(out // 10, values // 10)
    assert np.array_equal(sample.truth["values"], values)
    assert set(sample.truth["changed_index"]) == set(np.flatnonzero(changed))


def test_ocr_noise_has_no_preferred_digit():
    """A misread is noise; a person choosing a number is not. If the generator favoured a
    digit it would be manufacturing data, and the trap would prove nothing about OCR."""
    rng = np.random.default_rng(5)
    values = rng.integers(10000, 99999, size=40000).astype(float)
    out, _ = ocr_noise(values, error_rate=1.0, positions=(0,), seed=6)
    digits = (np.abs(out) % 10).astype(int)
    counts = np.bincount(digits, minlength=10)
    share = counts / counts.sum()
    assert share.max() < 0.125, f"digit distribution is not near-uniform: {share.round(4)}"


def test_ocr_noise_refuses_non_integer_values():
    with pytest.raises(RedTeamError, match="integer-valued"):
        ocr_noise([1.5, 2.5], error_rate=0.1)


def test_a_zero_error_rate_is_a_no_op():
    values = np.arange(100, 200, dtype=float)
    out, sample = ocr_noise(values, error_rate=0.0, seed=7)
    assert np.array_equal(out, values)
    assert sample.truth["n_digit_misreads"] == 0


# ---------------------------------------------------------------- traps are documented


def test_every_generator_names_a_real_trap_from_a_known_traps_document():
    samples = [
        small_units(50, [200], seed=0)[1],
        heterogeneous_mixture([{"n": 10, "mean": 1.0, "sd": 1.0}], seed=0)[1],
        level_shift(np.arange(10, dtype=float), at=5, size=1.0)[1],
        reweighting(np.ones((5, 2)), np.ones((5, 2)), base_period=0)[1],
        ocr_noise(np.arange(100, 110, dtype=float), 0.1, seed=0)[1],
    ]
    for s in samples:
        assert s.trap_id in TRAPS
        assert s.spec.project in {"elections", "china", "gosplan", "aaer"}
        assert s.spec.document_section
        assert s.honest_because


def test_an_invented_trap_id_is_refused():
    """Inventing a confound overstates a detector's fragility as surely as dropping one
    understates it."""
    with pytest.raises(RedTeamError, match="unknown trap id"):
        TrapSample(values=np.zeros(3), trap_id="plausible-1", mechanism="m", honest_because="h")


# ---------------------------------------------------------------- the pass itself


def integer_test_unconditional(sample: TrapSample):
    """The integer-percentage test with its small-precinct mitigation switched off.

    `min_denominator=1` is the naive analysis trap elections-1 warns about. Keeping it here as
    a named detector is what lets the pass demonstrate that the trap is real.
    """
    return integer_excess(
        sample.values,
        sample.truth["denominators"],
        min_denominator=1,
        n_mc=200,
        seed=0,
    ).test


def integer_test_conditioned(sample: TrapSample):
    """The same test as shipped, which excludes precincts below `min_denominator`."""
    return integer_excess(
        sample.values,
        sample.truth["denominators"],
        min_denominator=100,
        n_mc=200,
        seed=0,
    ).test


def terminal_test(sample: TrapSample):
    return terminal_digit_test(sample.values)


def glyph_confused(values, rate, seed):
    """A scanner that resolves 3, 5, 6 and 9 all to 8. The realistic OCR failure."""
    return ocr_noise(values, rate, (0,), confusion={3: 8, 5: 8, 6: 8, 9: 8}, seed=seed)[1]


def test_at_least_one_trap_makes_at_least_one_detector_fire():
    """The card's must-pass. A pass in which nothing ever fires is a certificate, not a test.

    The firing recorded here is trap gosplan-9 with a glyph confusion, and it is not a lucky
    draw. Measured over 60 seeds at n = 4000, the terminal-digit test fires on 20/60 of tables
    at a confusion rate of 0.02, 54/60 at 0.05 and 60/60 from 0.10 upward. This test uses 0.10
    so that the assertion is deterministic rather than a 90% coin. See docs/redteam.md.
    """
    rng = np.random.default_rng(11)
    clean = rng.integers(10000, 99999, size=4000).astype(float)

    fired = 0
    for i in range(10):
        sample = glyph_confused(clean, 0.10, seed=i)
        (r,) = red_team({"terminal_digit": terminal_test}, [sample])
        fired += int(r.fired)
    assert fired == 10, (
        f"a 10% glyph confusion made the terminal-digit test fire on only {fired} of 10 "
        "seeds. docs/redteam.md records 60 of 60 at this rate."
    )


def test_the_clean_table_does_not_fire_which_is_what_makes_that_a_finding():
    fired = 0
    for i in range(20):
        clean = np.random.default_rng(3000 + i).integers(10000, 99999, size=4000).astype(float)
        sample = TrapSample(
            values=clean,
            trap_id="gosplan-9",
            mechanism="no transcription error",
            honest_because="the values are the table",
            truth={"values": clean},
        )
        (r,) = red_team({"terminal_digit": terminal_test}, [sample])
        fired += int(r.fired)
    assert fired <= 3, f"the terminal-digit test fired on {fired} of 20 clean tables"


def test_a_uniform_misread_does_not_fire_and_that_distinction_matters():
    """The two OCR modes are not equally dangerous, and a test that survives one has not been
    shown to survive the other. A uniform misread leaves the digit distribution uniform."""
    rng = np.random.default_rng(13)
    clean = rng.integers(10000, 99999, size=4000).astype(float)
    fired = 0
    for i in range(10):
        _, sample = ocr_noise(clean, 0.3, (0,), seed=i)
        (r,) = red_team({"terminal_digit": terminal_test}, [sample])
        fired += int(r.fired)
    # measured over 60 seeds: 4/60 at rate 0.25 and 5/60 at rate 1.0, both inside Monte Carlo
    # error of the nominal 0.05. A uniform misread is invisible to a uniformity test at any
    # rate, which is exactly why surviving it says nothing about surviving a glyph confusion.
    assert fired <= 3, (
        f"a uniform misread at rate 0.3 made the digit test fire {fired} of 10 times; it "
        "should be invisible to a uniformity test"
    )


def test_the_small_precinct_trap_does_not_make_the_integer_test_fire():
    """A survival, recorded as one.

    The obvious expectation is that trap elections-1 breaks the integer-percentage test, and a
    single draw can be made to show it: at seed 10 the unconditional test returns p = 0.026.
    It does not replicate. Over 100 replicates the firing rate is 0.080 against a nominal
    0.05 with a Monte Carlo SE of 0.022 — 1.4 SEs out, which is not a finding. The KSP
    per-precinct binomial null already redraws each numerator at that precinct's own size, so
    the denominator-driven integer mass is in the null as well as in the data.

    This test uses a smaller budget than that measurement, so it can only catch a gross
    regression. The full numbers are in docs/redteam.md.
    """
    from forensics_core.control import classify

    reps = 30
    fired = 0
    for i in range(reps):
        _, sample = small_units(1500, [60, 80, 100], p=0.55, seed=4000 + i)
        result = integer_excess(
            sample.values,
            sample.truth["denominators"],
            min_denominator=1,
            n_mc=100,
            seed=i,
        )
        fired += int(result.test.pvalue <= 0.05)

    rate = fired / reps
    verdict = classify(rate, 0.05, reps)
    assert verdict != "anticonservative", (
        f"the unconditional integer-percentage test fired on {fired}/{reps} honest "
        f"small-precinct samples (rate {rate:.3f}). docs/redteam.md records this trap as "
        "survived; if that has changed, the document must change with it."
    )


def test_every_pair_appears_in_the_output_with_no_way_to_filter():
    _, sample = small_units(500, [200], seed=12)
    results = red_team(
        {"a": integer_test_conditioned, "b": integer_test_conditioned}, [sample, sample]
    )
    assert len(results) == 4, "red_team must report every (trap, detector) pair"


def test_a_detector_that_crashes_is_recorded_rather_than_dropped():
    _, sample = small_units(100, [200], seed=13)

    def broken(s):
        raise RuntimeError("no")

    (r,) = red_team({"broken": broken}, [sample])
    assert r.fired is False
    assert "RuntimeError" in r.detail["error"], "a crash must be visible in the record"


def test_survivors_lists_what_a_detector_withstood():
    _, small = small_units(2000, [200, 400], seed=14)
    results = red_team({"integer_excess_conditioned": integer_test_conditioned}, [small])
    assert survivors(results, "integer_excess_conditioned") == ["elections-1"]


def test_a_detector_that_excludes_every_unit_is_recorded_as_an_error_not_a_pass():
    """min_denominator=100 against denominators of 60 and 80 leaves nothing to test. That is
    not the detector surviving the trap; it is the detector declining to answer, and a report
    that scored it as a survival would be reading a refusal as a clean bill of health."""
    _, tiny = small_units(500, [60, 80], seed=15)
    (r,) = red_team({"integer_excess_conditioned": integer_test_conditioned}, [tiny])
    assert r.fired is False
    assert r.pvalue is None
    assert "no unit survives exclusion" in r.detail["error"]


def test_an_empty_pass_is_refused():
    with pytest.raises(RedTeamError, match="empty pass proves nothing"):
        red_team({"a": integer_test_conditioned}, [])


# ---------------------------------------------------------------- the OCR gate


#: The glyph confusion docs/redteam.md measures: a scanner that resolves 3, 5, 6 and 9 to 8.
GLYPHS = {3: 8, 5: 8, 6: 8, 9: 8}


def honest_five_digit_table(rng):
    """One fresh honest table: 4000 five-digit counts, last digits uniform."""
    return rng.integers(10000, 100000, size=4000).astype(float)


def misread_to_measured_rate(table, rate, seed):
    """Glyph-confuse last digits so that ``rate`` of them differ from the table, on average.

    Written apart from ocr_firing_threshold's own conversion so that the check below does not
    share its arithmetic: ocr_noise's rate is the chance that a digit is misread, and under
    GLYPHS a misread changes only the digits that are its keys.
    """
    confusable = np.isin(table.astype(np.int64) % 10, list(GLYPHS)).mean()
    injector = rate / confusable if rate else 0.0
    return ocr_noise(table, injector, (0,), confusion=GLYPHS, seed=seed)[0]


def test_the_ocr_threshold_under_glyph_confusion_keeps_the_digit_test_calibrated_below_it():
    """The gate's promise, checked on tables the threshold never saw.

    A uniform misread cannot make a uniformity test fire, so a threshold that simulated only
    that mode never arrived and the gate stayed shut for good. With the glyph confusion the
    threshold exists. It is the share of last digits that differ from the source, which is
    what a transcription comparison reports and what ocr_gate takes. And at every rate the
    gate admits, the terminal-digit test fires on fresh honest tables at no more than
    alpha + tolerance = 0.08, the band the threshold was computed against. docs/redteam.md
    records the threshold this computes, 0.003, and the firing rates behind it.
    """
    threshold = ocr_firing_threshold(
        terminal_test,
        honest_five_digit_table,
        error_rates=(0.003, 0.006),
        confusions=GLYPHS,
        n_replicates=1000,
        seed=0,
    )
    assert threshold is not None and threshold > 0.0, (
        f"terminal_digit_test under glyph confusion must get a usable threshold; got {threshold}"
    )
    assert threshold == 0.003, (
        f"docs/redteam.md records a threshold of 0.003 for this table shape; got {threshold}"
    )

    reps = 1000
    for rate in (0.0, threshold / 2, threshold):
        fired = changed = 0
        for i in range(reps):
            table = honest_five_digit_table(np.random.default_rng(50_000 + i))
            read = misread_to_measured_rate(table, rate, seed=60_000 + i)
            changed += int((read != table).sum())
            fired += int(terminal_digit_test(read).pvalue <= 0.05)
        measured = changed / (reps * 4000)
        assert measured == pytest.approx(rate, rel=0.05, abs=1e-12), (
            f"tables built at {rate} have {measured:.5f} of last digits changed; the rate "
            "being checked is not in the unit a comparison with the source would report"
        )
        assert fired / reps <= 0.08, (
            f"the gate admits a measured error rate of {rate}, and there the terminal-digit "
            f"test fired on {fired}/{reps} honest tables, above alpha + tolerance = 0.08"
        )

    # a table compared on 20,000 digits and found with half the threshold's error rate passes;
    # one found exactly at it does not, because the gate reads the rate's upper bound
    assert ocr_gate(threshold, threshold / 2, n_compared=20_000) is True
    assert ocr_gate(threshold, threshold, n_compared=20_000) is False


def test_the_threshold_is_in_the_unit_a_comparison_with_the_source_measures():
    """A detector that fires once more than 1.5% of digits differ from the source must get the
    threshold 0.01 on this grid. Read in ocr_noise's unit instead, where only four glyphs in
    ten can change, 0.02 would change 0.8% of digits and the answer would be 0.02."""

    def fires_past_one_and_a_half_percent_changed(sample):
        if sample.truth["confusion"] is None:
            return 1.0
        changed = len(sample.truth["changed_index"]) / len(sample)
        return 0.0 if changed > 0.015 else 1.0

    threshold = ocr_firing_threshold(
        fires_past_one_and_a_half_percent_changed,
        honest_five_digit_table,
        error_rates=(0.005, 0.01, 0.02, 0.04),
        confusions=GLYPHS,
        n_replicates=300,
    )
    assert threshold == 0.01


def test_every_corruption_mode_is_run_and_the_lowest_threshold_wins():
    """The uniform misread and every confusion given are each a way the scanner can fail, and
    a rate is safe only if it is safe under all of them. The detector here reacts to one mode
    only; the threshold must come from that mode whichever it is. (GLYPHS reacting is the
    test above.)"""

    def fires_under(mode):
        def detector(sample):
            changed = len(sample.truth["changed_index"]) / len(sample)
            return 0.0 if sample.truth["confusion"] == mode and changed > 0.015 else 1.0

        return detector

    for mode in (None, {1: 7}):
        threshold = ocr_firing_threshold(
            fires_under(mode),
            honest_five_digit_table,
            error_rates=(0.005, 0.01, 0.02, 0.04),
            confusions=[{1: 7}, GLYPHS],
            n_replicates=300,
        )
        assert threshold == 0.01, (
            f"the mode {mode} fires from 0.02 but the threshold is {threshold}"
        )


def test_a_rate_passes_only_if_its_firing_is_shown_within_tolerance_not_just_estimated():
    """A detector that fires on exactly 7 tables in 100 from a rate of 0.01 has a point
    estimate inside alpha + tolerance = 0.08, but 300 tables cannot show its true rate is: the
    95% upper bound on 21/300 is above 0.08. The threshold must stop below 0.01."""
    drawn = iter(range(10**6))

    def numbered_table(rng):
        table = rng.integers(10000, 100000, size=500).astype(float)
        table[0] = 10000 + next(drawn)  # the table's own number, for the detector below
        return table

    def fires_on_seven_in_a_hundred_from_one_percent(sample):
        # under a uniform misread ocr_noise's rate is the measured rate itself
        reacts = sample.truth["confusion"] is None and sample.truth["error_rate"] >= 0.01
        number = int(sample.truth["values"][0]) - 10000
        return 0.0 if reacts and number % 100 < 7 else 1.0

    threshold = ocr_firing_threshold(
        fires_on_seven_in_a_hundred_from_one_percent,
        numbered_table,
        error_rates=(0.005, 0.01),
        confusions=GLYPHS,
        n_replicates=300,
    )
    assert threshold == 0.005


def test_a_detector_that_never_answers_gets_no_threshold():
    """A refusal is not a pass. Counted as one, a detector that never returned a p-value would
    be calibrated at every rate and the gate would open for it."""

    def refuses(sample):
        raise ValueError("cannot test this")

    for detector in (refuses, lambda s: None, lambda s: float("nan")):
        threshold = ocr_firing_threshold(
            detector,
            honest_five_digit_table,
            error_rates=(0.01,),
            confusions=GLYPHS,
            n_replicates=300,
        )
        assert threshold is None
        assert ocr_gate(threshold, 0.0, n_compared=1_000_000) is False


def test_the_threshold_refuses_inputs_that_would_misstate_it():
    def never(sample):
        return 1.0

    kwargs = {"error_rates": (0.01,), "confusions": GLYPHS, "n_replicates": 300}
    fixed = honest_five_digit_table(np.random.default_rng(0))
    with pytest.raises(RedTeamError, match="fresh honest table"):
        ocr_firing_threshold(never, fixed, **kwargs)
    with pytest.raises(RedTeamError, match="confusions is empty"):
        ocr_firing_threshold(never, honest_five_digit_table, **{**kwargs, "confusions": []})
    with pytest.raises(RedTeamError, match="cannot resolve a tolerance"):
        ocr_firing_threshold(never, honest_five_digit_table, **{**kwargs, "n_replicates": 200})
    # four glyphs in ten cannot change half the last digits however often they are misread
    with pytest.raises(RedTeamError, match="cannot be produced"):
        ocr_firing_threshold(never, honest_five_digit_table, **{**kwargs, "error_rates": (0.5,)})


def test_the_gate_holds_the_upper_bound_of_the_measured_rate_to_the_threshold():
    assert ocr_gate(0.10, 0.02, n_compared=4000) is True
    assert ocr_gate(0.10, 0.10, n_compared=4000) is False
    assert ocr_gate(0.10, 0.30, n_compared=4000) is False
    # the same point estimate, one error in 200 digits against 500 in 100,000
    assert ocr_gate(0.01, 0.005, n_compared=200) is False
    assert ocr_gate(0.01, 0.005, n_compared=100_000) is True


def test_the_gate_stays_shut_when_no_rate_was_shown_safe():
    assert ocr_gate(None, 0.0, n_compared=1_000_000) is False
    # 0.0 admits only an error-free transcription, and no finite comparison proves one
    assert ocr_gate(0.0, 0.0, n_compared=1_000_000) is False


def test_the_gate_refuses_a_nonsense_error_rate():
    with pytest.raises(RedTeamError, match="measured_error_rate"):
        ocr_gate(0.1, 1.5, n_compared=100)
    with pytest.raises(RedTeamError, match="n_compared"):
        ocr_gate(0.1, 0.01, n_compared=0)


# ---------------------------------------------------------------- the document


def test_the_document_exists_and_names_every_trap():
    assert DOC.is_file(), f"{DOC} is missing; the card requires it"
    text = DOC.read_text(encoding="utf-8")
    for trap_id in TRAPS:
        assert trap_id in text, f"trap {trap_id} is not recorded in docs/redteam.md"


def test_every_firing_pair_is_in_the_document():
    """The card's forbidden list: a trap that fires is a result and goes in the document.

    This is the enforcement. Making a detector survive by deleting the trap that catches it
    now breaks a test.

    The pair used is the glyph confusion, because it is the firing that replicates. An earlier
    version of this test used the small-precinct trap at seed 10, where the unconditional
    integer test returns p = 0.026 — and would then have demanded that a non-replicating
    single draw be written into the document as a finding. Enforcing that a marginal artefact
    be recorded is the same error as suppressing a real one, in the other direction.
    """
    rng = np.random.default_rng(17)
    clean = rng.integers(10000, 99999, size=4000).astype(float)
    results = red_team({"terminal_digit_test": terminal_test}, [glyph_confused(clean, 0.10, 0)])

    fired = casualties(results)
    assert fired, "the fixture must produce a firing for this test to enforce anything"

    text = DOC.read_text(encoding="utf-8")
    for r in fired:
        # both names present is the check. Requiring a particular order or proximity would
        # constrain how the document is written rather than what it records.
        assert r.detector in text, f"{r.detector} fires and is not named in docs/redteam.md"
        assert r.trap_id in text, f"trap {r.trap_id} fires and is not named in docs/redteam.md"
        assert "FIRES" in text, "the document must mark a firing as one"


def test_the_table_lists_every_pair_and_calls_out_the_firings():
    """Uses a hand-built firing so the assertion does not depend on a marginal draw."""
    _, small = small_units(2000, [60, 80, 200], seed=16)
    results = red_team(
        {
            "integer_excess_unconditional": integer_test_unconditional,
            "always_fires": lambda s: 0.0,
        },
        [small],
    )
    table = format_redteam_table(results)
    assert "integer_excess_unconditional" in table
    assert "always_fires" in table
    assert "fired on honest data" in table


def test_an_empty_table_says_no_pass_was_run():
    assert "NO RED-TEAM PASS RUN" in format_redteam_table([])

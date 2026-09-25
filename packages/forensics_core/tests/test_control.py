"""A calibrated detector on a clean control rejects at alpha; a broken one is caught.

The second half is the part that earns its keep. A control check that only ever confirms
good behaviour has never been shown to be able to fail, and a check that cannot fail is
decoration — which is the same objection this module makes to synthetic nulls.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.control import (
    CONTROL_KINDS,
    Control,
    ControlError,
    ControlReport,
    anticonservative,
    classify,
    control_report,
    format_control_table,
    from_rejections,
    has_external_control,
    monte_carlo_se,
    worst_verdict,
)
from forensics_core.eval.harness import Dataset


def clean_control(name: str, n: int = 4000, kind: str = "external") -> Control:
    """Units carrying no signal. What they hold does not matter: the detectors below
    manufacture p-values without reading them, so the control's job here is only to fix n."""
    return Control(
        name=name,
        dataset=Dataset(
            unit_id=pd.Series([f"{name}{i}" for i in range(n)]),
            X=pd.DataFrame({"x": np.zeros(n)}),
            y=pd.Series([np.nan] * n),
        ),
        kind=kind,  # type: ignore[arg-type]
        source=f"synthetic fixture for {name}",
    )


def calibrated_detector(seed: int = 0):
    """A correct test: under the null its p-values are uniform on [0, 1]."""
    rng = np.random.default_rng(seed)
    return lambda ds: rng.uniform(0.0, 1.0, size=len(ds))


def always_rejects(ds):
    """The broken detector the card requires be caught."""
    return np.zeros(len(ds))


def never_rejects(ds):
    return np.ones(len(ds))


# ---------------------------------------------------------------- the calibrated case


def test_a_calibrated_detector_on_a_clean_control_rejects_at_about_alpha():
    reports = control_report(calibrated_detector(), [clean_control("poland")], alpha=0.05)
    (r,) = reports
    se = monte_carlo_se(0.05, r.n)
    assert abs(r.excess) < 3 * se, (
        f"rejection rate {r.rejection_rate:.4f} against nominal 0.05 is "
        f"{abs(r.excess) / se:.1f} Monte Carlo SEs out"
    )
    assert r.verdict == "calibrated"


def test_the_report_carries_the_arithmetic_a_reader_needs_to_check_it():
    (r,) = control_report(calibrated_detector(), [clean_control("spain")], alpha=0.05)
    assert r.n == 4000
    assert r.nominal_alpha == 0.05
    assert r.excess == pytest.approx(r.rejection_rate - 0.05)
    assert r.detail["n_rejected"] == pytest.approx(r.rejection_rate * r.n, abs=1)
    assert r.detail["monte_carlo_se"] == pytest.approx(monte_carlo_se(0.05, r.n))


def test_alpha_is_respected_rather_than_assumed():
    control = clean_control("poland")
    at_01 = control_report(calibrated_detector(seed=3), [control], alpha=0.01)[0]
    at_20 = control_report(calibrated_detector(seed=3), [control], alpha=0.20)[0]
    assert at_01.rejection_rate < at_20.rejection_rate
    assert at_01.verdict == at_20.verdict == "calibrated"


# ---------------------------------------------------------------- the broken cases


def test_a_detector_that_always_rejects_is_caught():
    (r,) = control_report(always_rejects, [clean_control("poland")], alpha=0.05)
    assert r.rejection_rate == 1.0
    assert r.verdict == "anticonservative"
    assert r.excess == pytest.approx(0.95)


def test_a_detector_that_never_rejects_is_reported_as_conservative_not_as_good():
    """A conservative detector's failure to find something is not evidence of absence, so the
    verdict has to distinguish it from a calibrated one."""
    (r,) = control_report(never_rejects, [clean_control("poland")], alpha=0.05)
    assert r.rejection_rate == 0.0
    assert r.verdict == "conservative"


def test_a_mildly_anticonservative_detector_is_caught_at_large_n_and_excused_at_small_n():
    """The Monte Carlo error is doing the work. 8% against a nominal 5% is a different claim
    at n=40 than at n=8000, and calling both anticonservative would be wrong."""

    def mild(ds):
        n = len(ds)
        p = np.full(n, 0.5)
        p[: round(0.08 * n)] = 0.001
        return p

    big = control_report(mild, [clean_control("big", n=8000)], alpha=0.05)[0]
    small = control_report(mild, [clean_control("small", n=40)], alpha=0.05)[0]
    assert big.verdict == "anticonservative"
    assert small.verdict == "calibrated", (
        "at n=40 a rejection rate of 0.08 is well inside Monte Carlo error of 0.05"
    )


def test_classify_uses_the_stated_tolerance():
    assert classify(0.08, 0.05, 8000) == "anticonservative"
    assert classify(0.08, 0.05, 8000, tolerance_se=100.0) == "calibrated"


# ---------------------------------------------------------------- no hiding in an average


def test_one_bad_control_sets_the_corpus_verdict():
    """The rule the card calls forbidden: a corpus average would read as calibrated here."""
    reports = control_report(
        calibrated_detector(), [clean_control("a"), clean_control("b"), clean_control("c")]
    )
    reports.append(
        from_rejections("d", np.ones(4000, dtype=bool), nominal_rate=0.05, source="broken")
    )
    mean_rate = float(np.mean([r.rejection_rate for r in reports]))
    assert mean_rate < 0.30, "the average is the thing that would have hidden it"
    assert worst_verdict(reports) == "anticonservative"
    assert [r.control_name for r in anticonservative(reports)] == ["d"]


def test_there_is_no_corpus_average_to_reach_for():
    import forensics_core.control as mod

    for forbidden in ("mean_rejection_rate", "corpus_average", "average_report"):
        assert not hasattr(mod, forbidden), (
            f"{forbidden} would let an anticonservative control hide behind calibrated ones"
        )


# ---------------------------------------------------------------- the kinds are not equal


def test_only_an_external_control_counts_as_real_evidence():
    synthetic = control_report(calibrated_detector(), [clean_control("null", kind="synthetic")])
    within = control_report(calibrated_detector(), [clean_control("sub", kind="within_dataset")])
    external = control_report(calibrated_detector(), [clean_control("poland")])

    assert not has_external_control(synthetic)
    assert not has_external_control(within)
    assert has_external_control(external)
    assert synthetic[0].is_real_evidence is False
    assert external[0].is_real_evidence is True


def test_a_corpus_of_synthetic_nulls_warns_however_many_it_has():
    reports = control_report(
        calibrated_detector(),
        [clean_control(f"null{i}", n=500, kind="synthetic") for i in range(10)],
    )
    assert all(r.verdict == "calibrated" for r in reports)
    table = format_control_table(reports)
    assert "no external control" in table, (
        "ten calibrated synthetic nulls must not read as a satisfied rule 9"
    )


def test_the_kinds_are_a_closed_set():
    assert CONTROL_KINDS == ("external", "within_dataset", "synthetic")
    with pytest.raises(ControlError, match="kind must be one of"):
        clean_control("x", kind="probably_fine")


# ---------------------------------------------------------------- refusals


def test_an_empty_corpus_is_refused_rather_than_passing_vacuously():
    with pytest.raises(ControlError, match="CONTRACT rule 9"):
        control_report(calibrated_detector(), [])


def test_an_external_control_without_a_source_is_refused():
    with pytest.raises(ControlError, match="no source"):
        Control(
            name="poland2010",
            dataset=clean_control("p", n=10).dataset,
            kind="external",
            source="   ",
        )


def test_duplicate_control_names_are_refused():
    with pytest.raises(ControlError, match="unique"):
        control_report(calibrated_detector(), [clean_control("a"), clean_control("a")])


def test_scores_outside_zero_one_say_to_use_from_rejections():
    """A score has no nominal alpha until a threshold gives it one, and silently treating a
    score as a p-value would produce a confident and meaningless rejection rate."""

    def scores(ds):
        return np.linspace(0.0, 12.0, len(ds))

    with pytest.raises(ControlError, match="from_rejections"):
        control_report(scores, [clean_control("poland", n=100)])


def test_a_non_finite_pvalue_is_refused_rather_than_counted_either_way():
    def flaky(ds):
        p = np.full(len(ds), 0.5)
        p[0] = np.nan
        return p

    with pytest.raises(ControlError, match="non-finite"):
        control_report(flaky, [clean_control("poland", n=100)])


def test_the_wrong_number_of_pvalues_is_refused():
    with pytest.raises(ControlError, match="one p-value per unit"):
        control_report(lambda ds: np.array([0.5, 0.5]), [clean_control("poland", n=100)])


def test_an_empty_control_is_refused():
    with pytest.raises(ControlError, match="empty"):
        Control(
            name="nothing",
            dataset=Dataset(
                unit_id=pd.Series([], dtype=str),
                X=pd.DataFrame({"x": pd.Series([], dtype=float)}),
                y=pd.Series([], dtype=float),
            ),
            kind="external",
            source="s",
        )


# ---------------------------------------------------------------- the threshold route


def test_from_rejections_carries_the_rate_the_rule_was_meant_to_produce():
    flags = np.zeros(1000, dtype=bool)
    flags[:70] = True
    r = from_rejections("target_control", flags, nominal_rate=0.05, source="calibration curve")
    assert r.n == 1000
    assert r.rejection_rate == pytest.approx(0.07)
    assert r.excess == pytest.approx(0.02)
    assert r.verdict == "anticonservative"
    assert r.detail["rule"] == "threshold"


def test_from_rejections_needs_a_nominal_rate_because_a_score_does_not_imply_one():
    with pytest.raises(ControlError, match="nominal_rate"):
        from_rejections("c", np.zeros(10, dtype=bool), nominal_rate=0.0)


# ---------------------------------------------------------------- the printable output


def test_the_table_names_every_control_and_never_averages():
    reports = control_report(calibrated_detector(), [clean_control("a"), clean_control("b")])
    table = format_control_table(reports)
    assert "a" in table and "b" in table
    assert "worst individual, never an average" in table


def test_an_empty_table_says_no_detection_may_be_reported():
    assert "rule 9" in format_control_table([])


def test_a_report_round_trips_to_a_dict():
    (r,) = control_report(calibrated_detector(), [clean_control("poland")])
    d = r.to_dict()
    assert d["control_name"] == "poland"
    assert set(d) == {
        "control_name",
        "n",
        "rejection_rate",
        "nominal_alpha",
        "excess",
        "verdict",
        "detail",
    }
    assert isinstance(ControlReport(**d), ControlReport)

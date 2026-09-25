"""Controls: what a detector does on data where it should find nothing.

CONTRACT rule 9 requires every reported detection to travel with this number. The reason is
arithmetic rather than principle. A detector that rejects 30% of clean units and 40% of
suspect ones has found nothing at all, but the 40% quoted alone reads as a discovery, and
nothing in the number itself says otherwise.

Three kinds of control, and they are not equivalent
---------------------------------------------------
``"external"``
    A genuinely separate collection that the literature treats as undistorted — an election
    in a country where no systematic anomaly is reported, a period before an incentive
    existed. **This is the only kind that is real evidence.** It can fail in ways the analyst
    did not anticipate, which is exactly what makes passing it informative.

``"within_dataset"``
    A subsample of the same data that the literature treats as clean. Weaker: it shares the
    collection process, the coding conventions, the rounding habits and the transcription
    errors of the units under suspicion, so it cannot detect a problem that afflicts all of
    them. It is a check on the detector, not on the data.

``"synthetic"``
    Draws from a fitted counterfactual. Weakest, and circular in a specific way: the null was
    fitted to the same data, so it inherits whatever the analyst's model already assumed.
    A synthetic null tells you the test's nominal size is implemented correctly. It tells you
    nothing about the world.

A corpus of ten synthetic nulls and no external control has not satisfied rule 9. Use
:func:`has_external_control` before reporting.

Why there is no corpus average here
-----------------------------------
Averaging rejection rates across controls is the natural summary and it is forbidden. One
anticonservative control is the finding; a mean over nine calibrated controls and one that
rejects half the time reads as calibrated. :func:`worst_verdict` returns the worst individual
verdict instead, and :func:`format_control_table` prints every control.

Relationship to ``eval.harness.transfer``
-----------------------------------------
``transfer(..., controls=[...])`` answers a nearby but different question: the *share of a
control flagged* at each threshold on the source calibration curve, computed with the same
fitted instance. That is the right object when the detector produces scores and the threshold
came from somewhere else. This module is for the case where the detector produces calibrated
p-values and there is a nominal alpha to be held to. Use :func:`from_rejections` to build a
:class:`ControlReport` from the boolean outcome of any other rejection rule.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .eval.harness import Dataset

#: The kinds of control, ordered from strongest evidence to weakest.
CONTROL_KINDS: tuple[str, ...] = ("external", "within_dataset", "synthetic")

#: Verdicts, ordered worst to best. A control that rejects too often is the one that matters:
#: it inflates every detection the detector reports elsewhere.
VERDICT_ORDER: tuple[str, ...] = ("anticonservative", "conservative", "calibrated")

#: Standard errors of slack before a departure from nominal is called. Two is about a 95%
#: interval; the default is deliberately not tighter, because calling a well-behaved detector
#: anticonservative on noise would train readers to ignore the verdict.
DEFAULT_TOLERANCE_SE: float = 2.0


class ControlError(ValueError):
    """A control corpus was built or used in a way that cannot support a rule-9 claim."""


@dataclass(frozen=True)
class Control:
    """One collection where the detector should find nothing.

    Parameters
    ----------
    name : str
        Short identifier used in reports, e.g. ``"poland2010"``.
    dataset : Dataset
        The units. Labels are not used and need not be present.
    kind : {"external", "within_dataset", "synthetic"}
        See the module docstring. Only ``"external"`` is real evidence.
    source : str
        For an external control, the ``data/SOURCES.yaml`` key it was fetched under —
        required, and checked, because an external control whose provenance nobody can
        retrieve is an assertion rather than a control. For the other kinds, a description of
        how the subsample or the null was constructed.
    """

    name: str
    dataset: Dataset
    kind: Literal["external", "within_dataset", "synthetic"]
    source: str

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ControlError("a control needs a name; it appears in the report")
        if self.kind not in CONTROL_KINDS:
            raise ControlError(f"kind must be one of {CONTROL_KINDS}; got {self.kind!r}")
        if not str(self.source).strip():
            raise ControlError(
                f"control {self.name!r} has no source. For an external control this is the "
                "data/SOURCES.yaml key it was fetched under; for the other kinds it is how "
                "the subsample or null was built. A control nobody can retrieve or "
                "reconstruct is an assertion."
            )
        if len(self.dataset) == 0:
            raise ControlError(f"control {self.name!r} is empty")

    def __len__(self) -> int:
        return len(self.dataset)


@dataclass(frozen=True)
class ControlReport:
    """What one detector did on one control.

    ``excess`` is the number to read: how much more often the detector rejected than it
    claimed it would. It is signed, so a conservative detector is visible too — that matters
    because a conservative detector's *failure* to find something is not evidence of absence.
    """

    control_name: str
    n: int
    rejection_rate: float
    nominal_alpha: float
    excess: float
    verdict: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """The control's kind, carried through in ``detail``."""
        return str(self.detail.get("kind", "unknown"))

    @property
    def is_real_evidence(self) -> bool:
        """True only for an external control. See the module docstring."""
        return self.kind == "external"

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_name": self.control_name,
            "n": self.n,
            "rejection_rate": self.rejection_rate,
            "nominal_alpha": self.nominal_alpha,
            "excess": self.excess,
            "verdict": self.verdict,
            "detail": dict(self.detail),
        }


def monte_carlo_se(alpha: float, n: int) -> float:
    """Standard error of a rejection rate of ``alpha`` over ``n`` independent units.

    This is what separates "rejected a bit more than 5%" from "is not a 5% test". At n = 40
    the SE at alpha = 0.05 is 0.034, so a rejection rate of 0.10 is unremarkable; at n = 4000
    it is 0.0034, and 0.10 is a different test.
    """
    if n <= 0:
        raise ControlError("n must be positive to compute a Monte Carlo standard error")
    return float(np.sqrt(alpha * (1.0 - alpha) / n))


def classify(
    rejection_rate: float,
    nominal_alpha: float,
    n: int,
    *,
    tolerance_se: float = DEFAULT_TOLERANCE_SE,
) -> str:
    """``"anticonservative"``, ``"conservative"`` or ``"calibrated"``.

    Anticonservative means the rejection rate exceeds nominal by more than ``tolerance_se``
    Monte Carlo standard errors. A detector that is anticonservative on a control does not get
    to report a detection elsewhere without this number printed beside it.
    """
    se = monte_carlo_se(nominal_alpha, n)
    slack = tolerance_se * se
    if rejection_rate > nominal_alpha + slack:
        return "anticonservative"
    if rejection_rate < nominal_alpha - slack:
        return "conservative"
    return "calibrated"


def _pvalues(raw: Any, control: Control) -> np.ndarray:
    """Coerce a detector's output to one finite p-value per unit, or refuse."""
    values = np.asarray(raw, dtype=float).ravel()
    n = len(control.dataset)
    if values.size != n:
        raise ControlError(
            f"the detector returned {values.size} values for control {control.name!r}, which "
            f"has {n} units. control_report needs one p-value per unit."
        )
    if not np.isfinite(values).all():
        bad = int((~np.isfinite(values)).sum())
        raise ControlError(
            f"the detector returned {bad} non-finite p-values on control {control.name!r}. "
            "A unit that could not be tested has not been found innocent, and counting it "
            "either way changes the rejection rate. Drop those units deliberately and say how "
            "many were dropped."
        )
    if (values < 0.0).any() or (values > 1.0).any():
        raise ControlError(
            f"control_report expects p-values in [0, 1]; control {control.name!r} produced "
            f"values in [{values.min():.4g}, {values.max():.4g}]. If the detector returns "
            "scores rather than p-values, there is no nominal alpha to hold it to: apply a "
            "threshold yourself and use from_rejections."
        )
    return values


def control_report(
    detector: Callable[[Dataset], Any],
    controls: Sequence[Control],
    *,
    alpha: float = 0.05,
    tolerance_se: float = DEFAULT_TOLERANCE_SE,
) -> list[ControlReport]:
    """Run a detector on each control and report what it did, one row per control.

    Parameters
    ----------
    detector : callable
        ``detector(dataset) -> p-values``, one finite p-value per unit. A score-based
        :class:`~forensics_core.eval.harness.Detector` does not fit here and is not silently
        accepted: a score has no nominal alpha until a threshold gives it one, so pick the
        threshold explicitly and use :func:`from_rejections`.
    controls : sequence of Control
        Never averaged. Each appears in the output on its own.
    alpha : float
        The rejection level the detector claims, and the rate the control is held to.

    Returns
    -------
    list of ControlReport
        In the order the controls were given.

    Raises
    ------
    ControlError
        If ``controls`` is empty, two controls share a name, or a detector returns the wrong
        number of values, a non-finite p-value, or something outside [0, 1].
    """
    if not controls:
        raise ControlError(
            "no controls given. An empty corpus is not a passing control check; it is the "
            "absence of one, and reporting a detection on that basis violates CONTRACT rule 9."
        )
    if not 0.0 < alpha < 1.0:
        raise ControlError(f"alpha must be in (0, 1); got {alpha}")

    names = [c.name for c in controls]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ControlError(
            f"control names must be unique; {sorted(duplicates)} appear more than once. Two "
            "rows with the same name in a report cannot be told apart by a reader."
        )

    reports: list[ControlReport] = []
    for control in controls:
        values = _pvalues(detector(control.dataset), control)
        n = int(values.size)
        rate = float(np.mean(values <= alpha))
        verdict = classify(rate, alpha, n, tolerance_se=tolerance_se)
        reports.append(
            ControlReport(
                control_name=control.name,
                n=n,
                rejection_rate=rate,
                nominal_alpha=float(alpha),
                excess=float(rate - alpha),
                verdict=verdict,
                detail={
                    "kind": control.kind,
                    "source": control.source,
                    "n_rejected": int((values <= alpha).sum()),
                    "monte_carlo_se": monte_carlo_se(alpha, n),
                    "tolerance_se": float(tolerance_se),
                    "is_real_evidence": control.kind == "external",
                },
            )
        )
    return reports


def from_rejections(
    control_name: str,
    rejected: Any,
    *,
    nominal_rate: float,
    kind: Literal["external", "within_dataset", "synthetic"] = "external",
    source: str = "",
    tolerance_se: float = DEFAULT_TOLERANCE_SE,
    detail: dict[str, Any] | None = None,
) -> ControlReport:
    """Build a report from an already-applied rejection rule.

    For the score-and-threshold case, where the rejection rule is "score at or above t" and
    ``nominal_rate`` is the share the threshold was *calibrated* to flag. Keeping this
    separate from :func:`control_report` is deliberate: the caller has to state what rate the
    rule was supposed to produce, because unlike an alpha it is not implied by anything.
    """
    flags = np.asarray(rejected).ravel().astype(bool)
    n = int(flags.size)
    if n == 0:
        raise ControlError(f"control {control_name!r} is empty")
    if not 0.0 < nominal_rate < 1.0:
        raise ControlError(f"nominal_rate must be in (0, 1); got {nominal_rate}")
    rate = float(flags.mean())
    return ControlReport(
        control_name=control_name,
        n=n,
        rejection_rate=rate,
        nominal_alpha=float(nominal_rate),
        excess=float(rate - nominal_rate),
        verdict=classify(rate, nominal_rate, n, tolerance_se=tolerance_se),
        detail={
            "kind": kind,
            "source": source,
            "n_rejected": int(flags.sum()),
            "monte_carlo_se": monte_carlo_se(nominal_rate, n),
            "tolerance_se": float(tolerance_se),
            "is_real_evidence": kind == "external",
            "rule": "threshold",
            **(detail or {}),
        },
    )


def worst_verdict(reports: Sequence[ControlReport]) -> str:
    """The worst individual verdict in the corpus.

    This exists in place of an average. One anticonservative control is the finding, and a
    mean over nine calibrated controls and one that rejects half the time reads as calibrated.
    """
    if not reports:
        raise ControlError("no reports to summarise")
    for verdict in VERDICT_ORDER:
        if any(r.verdict == verdict for r in reports):
            return verdict
    return "calibrated"


def anticonservative(reports: Sequence[ControlReport]) -> list[ControlReport]:
    """The controls the detector over-rejected on, worst excess first."""
    hits = [r for r in reports if r.verdict == "anticonservative"]
    return sorted(hits, key=lambda r: r.excess, reverse=True)


def has_external_control(reports: Sequence[ControlReport]) -> bool:
    """Whether the corpus contains at least one genuinely external control.

    A corpus of within-dataset subsamples and synthetic nulls has not satisfied rule 9,
    however many entries it has.
    """
    return any(r.is_real_evidence for r in reports)


def format_control_table(reports: Sequence[ControlReport]) -> str:
    """Every control, one line each, with the corpus verdict and the evidence caveat.

    Intended to be pasted next to a detection result, which is the whole point of rule 9.
    """
    if not reports:
        return "NO CONTROLS RUN — no detection may be reported (CONTRACT rule 9)."

    header = f"{'control':<24} {'kind':<15} {'n':>7} {'rate':>8} {'nominal':>8} {'verdict':>18}"
    lines = [header, "-" * len(header)]
    for r in reports:
        lines.append(
            f"{r.control_name:<24} {r.kind:<15} {r.n:>7} {r.rejection_rate:>8.4f} "
            f"{r.nominal_alpha:>8.4f} {r.verdict:>18}"
        )
    lines.append("")
    lines.append(f"corpus verdict (worst individual, never an average): {worst_verdict(reports)}")
    if not has_external_control(reports):
        lines.append(
            "WARNING: no external control in this corpus. Within-dataset subsamples and "
            "synthetic nulls check the test, not the data, and do not satisfy rule 9."
        )
    for r in anticonservative(reports):
        lines.append(
            f"WARNING: {r.control_name} rejected {r.rejection_rate:.4f} against a nominal "
            f"{r.nominal_alpha:.4f} (excess {r.excess:+.4f}). Any detection this detector "
            "reports must be printed beside this number."
        )
    return "\n".join(lines)

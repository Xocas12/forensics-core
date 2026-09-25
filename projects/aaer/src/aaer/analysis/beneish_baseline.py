"""Evaluate the Beneish M-score as a detector of AAER-labelled misstatement. STUBS ONLY.

Reference for the score itself: Beneish, M. D. (1999). "The Detection of Earnings
Manipulation." *Financial Analysts Journal* 55(5): 24-36. The arithmetic lives in
:mod:`aaer.features.beneish` and is complete and tested; nothing here recomputes it.

What this module is for
-----------------------
Sub-question 1 of ``docs/research_question.md``: does the eight-variable M-score, computed from
the free SEC Financial Statement Data Sets, reproduce the published sensitivity and specificity
on the overlapping years? The M-score is the floor every later model has to clear, and it is the
one detector in the project with no free parameters to tune, so it is also the honest way to
show how much of a "result" is method and how much is fitting.

Three things this evaluation must do that a naive one would not
---------------------------------------------------------------
* **Report rank metrics, never accuracy.** The AAER base rate is well under 1 per cent
  (``docs/known_traps.md`` trap 2), so accuracy is uninformative. Use
  :func:`forensics_core.eval.metrics.rank_metrics` and print the base rate beside every figure.
* **Say which cost ratio the threshold encodes.** Beneish's -1.78 cut-off holds at 20:1 or 30:1
  relative error costs; at 10:1 the paper gives -1.49. A table that flags at -1.78 without
  saying so is asserting a cost assumption it has not made explicit
  (``docs/validation_anchors.md``, Tier 0).
* **Split on the fiscal year of the violation, not the release year.** An AAER is issued years
  after the misstatement (trap 3), and firms recur, so splits must be temporal or grouped by
  firm -- never random rows (trap 4).

A published comparison figure exists and is *not* to be treated as this module's target: Walker
(2022) reports that the Dechow-style logit benchmark identified 8 cases in the erratum's own
table. That is a different model on a different sample. The Beneish baseline's number has to be
produced here, on stated data, before anything is compared to anything.
"""

from __future__ import annotations

import pandas as pd
from forensics_core.eval.harness import Dataset, Detector, EvalReport, EvalSpec

from aaer.features.beneish import BENEISH_FLAG_THRESHOLD


def build_dataset(panel: pd.DataFrame, labels: pd.DataFrame) -> Dataset:
    """Assemble the firm-year :class:`~forensics_core.eval.harness.Dataset` for the baseline.

    Parameters
    ----------
    panel : pandas.DataFrame
        Firm-year frame carrying the eight Beneish component indices, indexed by ``(cik, fy)``
        or holding those as columns. Produced by :func:`aaer.clean.xbrl_map.map_beneish_items`
        followed by :func:`aaer.clean.xbrl_map.add_lags` and
        :func:`aaer.features.beneish.beneish_components`.
    labels : pandas.DataFrame
        One row per labelled firm-year: the firm identifier, the **fiscal year of the
        violation** and the AAER number.

    Returns
    -------
    Dataset
        ``y`` is 1 for labelled violation firm-years and ``NaN`` -- not 0 -- for everything
        else, because unflagged firm-years are unlabeled rather than clean (trap 1).
        ``groups`` is the firm and ``time`` the fiscal year, so both grouped and temporal
        splits are available.

    Raises
    ------
    NotImplementedError
        Remaining: decide the firm key that joins labels to the panel (the AAER listing carries
        a respondent name, not a CIK) and fix the violation-year convention.
    """
    raise NotImplementedError(
        "Remaining: join AAER labels to firm-years -- the listing has no CIK, so the identifier "
        "has to come from the release PDFs or from a curated dataset (data/ACCESS_NOTES.md)."
    )


def beneish_detector(*, threshold: float = BENEISH_FLAG_THRESHOLD) -> Detector:
    """Wrap the M-score as a :class:`~forensics_core.eval.harness.Detector`.

    The detector is unsupervised: ``fit`` ignores labels entirely and ``score`` returns the
    M-score itself, which is already oriented so that higher means more suspicious.
    ``threshold`` is carried only so that a flag-rate can be reported alongside the rank
    metrics; it does not affect the ranking.

    Parameters
    ----------
    threshold : float, default :data:`aaer.features.beneish.BENEISH_FLAG_THRESHOLD`
        Cut-off used for the reported flag rate. State the cost ratio it encodes.

    Returns
    -------
    Detector

    Raises
    ------
    NotImplementedError
        Remaining: wire :func:`aaer.features.beneish.m_score` into
        :class:`forensics_core.eval.harness.FunctionDetector` and decide how ``NaN`` components
        rank (they must not sort as "most suspicious").
    """
    raise NotImplementedError(
        "Remaining: wrap m_score in FunctionDetector and fix the rank position of NaN scores."
    )


def evaluate_beneish(ds: Dataset, spec: EvalSpec | None = None) -> EvalReport:
    """Score the Beneish baseline on ``ds`` under a temporal or grouped split.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    spec : EvalSpec, optional
        Defaults to a temporal split with rank metrics at k = 1 per cent of test firm-years,
        matching the benchmark's own choice (``docs/known_traps.md`` trap 2).

    Returns
    -------
    EvalReport

    Raises
    ------
    NotImplementedError
        Remaining: choose the default ``train_end`` fiscal year and confirm that the label
        timing convention keeps post-cutoff releases out of training.
    """
    raise NotImplementedError(
        "Remaining: set the default temporal split and prove no post-cutoff release leaks in."
    )


def component_contributions(ds: Dataset, spec: EvalSpec | None = None) -> pd.DataFrame:
    """Rank metrics for each Beneish component used alone, and for the score as a whole.

    Sub-question 4 of ``docs/research_question.md``: which of the eight components carry the
    signal. This matters beyond this project, because the components with analogues in the
    Soviet data (growth, margin and accrual-like ratios) are the ones whose transfer to
    ``gosplan`` is defensible.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    spec : EvalSpec, optional
        Split specification; the same one used for the full score.

    Returns
    -------
    pandas.DataFrame
        One row per component plus one for the combined score, with the metrics in
        ``spec.metrics`` and the number of firm-years each component was computable on.

    Raises
    ------
    NotImplementedError
        Remaining: decide whether components are compared on the common support of all eight or
        each on its own support -- the two give different rankings and the choice must be
        stated.
    """
    raise NotImplementedError(
        "Remaining: fix the support convention for per-component comparison, then evaluate each."
    )


def flag_rate_by_threshold(ds: Dataset, thresholds: tuple[float, ...]) -> pd.DataFrame:
    """Share of firm-years flagged, and precision among them, at several M-score cut-offs.

    Beneish's own cut-offs are cost-ratio-dependent (-1.78 at 20:1 or 30:1, -1.49 at 10:1), so
    the honest presentation is a curve rather than a single flag.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    thresholds : tuple of float
        M-score cut-offs to report.

    Returns
    -------
    pandas.DataFrame
        Columns ``threshold, n_flagged, flag_rate, n_positive_flagged, precision``, with the
        base rate attached as a frame-level attribute.

    Raises
    ------
    NotImplementedError
        Remaining: define precision under PU labels -- with unlabeled negatives it is a lower
        bound, and must be reported as one.
    """
    raise NotImplementedError(
        "Remaining: define and label the PU lower-bound precision before reporting any curve."
    )

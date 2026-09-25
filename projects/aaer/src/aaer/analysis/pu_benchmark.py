"""Positive-unlabeled benchmark against the treat-unflagged-as-clean formulation. STUBS ONLY.

Methods
-------
Elkan, C. and K. Noto (2008). "Learning classifiers from only positive and unlabeled data."
*KDD*: the constant-``c`` correction, ``P(y=1|x) = g(x)/c``, implemented as
:class:`forensics_core.labels.pu.ElkanNotoPU`.

Mordelet, F. and J.-P. Vert (2014). "A bagging SVM to learn from positive and unlabeled
examples." *Pattern Recognition Letters* 37: 201-209: bagging all positives against bootstrap
subsamples of the unlabeled pool, implemented as
:class:`forensics_core.labels.pu.BaggingPU`.

Bao, Y., B. Ke, B. Li, Y. J. Yu and J. Zhang (2020). *JAR* 58(1): 199-235, with the 2022
erratum at *JAR* 60(4): 1635-1646: the published benchmark this module is measured against.

Why the PU framing is the point, not a refinement
-------------------------------------------------
The SEC prosecutes what is detectable, large and litigable. A firm-year with no AAER is a
firm-year nobody charged, which is not the same thing as a clean one (``docs/known_traps.md``,
trap 1). A classifier trained with those rows as negatives is being told that every
undetected misstatement is an example of honesty, and it learns to predict *enforcement*.
Sub-question 3 of ``docs/research_question.md`` asks whether the honest formulation is also the
more powerful one. Either answer is publishable; a null result here is a real finding about how
much the label noise costs.

The target to match, and its provenance caveat
----------------------------------------------
``docs/validation_anchors.md`` Tier 1 gives the **corrected** RUSBoost figures: AUC 0.7428 and
NDCG@1% 0.0394 with 9 hits for the 2003-2005 test window, AUC 0.7228 and NDCG@1% 0.0237 with 10
hits for 2003-2008. Those were read from Walker (2022) in *Econ Journal Watch*, which tabulates
the erratum; the erratum itself is paywalled and was not read, and Walker's own re-runs got 8
hits in both windows. Reproduction means matching AUC to within roughly +/- 0.02 on the same
windows with the same labels, and the coverage problem in ``data/ACCESS_NOTES.md`` means that
is only attempted on the Bao et al. CSV, not on the SEC path.

The original (pre-erratum) figures are **not** the target. Do not compare to them.
"""

from __future__ import annotations

import pandas as pd
from forensics_core.eval.harness import Dataset, EvalReport, EvalSpec, TransferResult

#: PU estimators compared, by their name in :data:`forensics_core.eval.harness.DETECTOR_REGISTRY`.
PU_ESTIMATORS: tuple[str, ...] = ("pu_elkan_noto", "pu_bagging")

#: Test windows used by the published benchmark, so that any comparison is like for like.
BAO_TEST_WINDOWS: tuple[tuple[int, int], ...] = ((2003, 2005), (2003, 2008))


def build_dataset(features: pd.DataFrame, labels: pd.DataFrame, *, source: str) -> Dataset:
    """Assemble the firm-year dataset for the PU benchmark.

    Parameters
    ----------
    features : pandas.DataFrame
        Firm-year features. Two provenances are in scope and they must never be silently mixed:
        the 28 raw items of the Bao et al. replication CSV (fiscal years 1990-2014), and the
        items mapped from the SEC Financial Statement Data Sets (2009 onward, and see
        :mod:`aaer.clean.xbrl_map` on how provisional that mapping is).
    labels : pandas.DataFrame
        Labelled violation firm-years, with the serial-fraud identifier that groups releases
        belonging to one case (``p_aaer`` in the Bao et al. files).
    source : str
        ``"bao"`` or ``"fsds"``. Recorded in ``Dataset.meta`` and printed in every report,
        because the two are not comparable.

    Returns
    -------
    Dataset
        ``y`` is 1 on labelled positives and ``NaN`` on the unlabeled remainder;
        :class:`forensics_core.eval.harness.PUDetector` reads ``NaN`` as unlabeled.

    Raises
    ------
    NotImplementedError
        Remaining: decide how serial-fraud cases spanning the train/test boundary are handled.
        Mishandling exactly that is what the 2022 erratum was about.
    """
    raise NotImplementedError(
        "Remaining: fix the serial-fraud recoding rule for cases spanning the split -- the "
        "erratum's error was that about 10 percent of them were not recoded to zero in training."
    )


def naive_supervised_report(ds: Dataset, spec: EvalSpec) -> EvalReport:
    """The comparison arm: unlabeled firm-years treated as negatives.

    This is the formulation the literature mostly uses. It is included to be beaten, or not, on
    the same split and the same metrics.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    spec : EvalSpec
        Split and metric specification, shared with the PU arm.

    Returns
    -------
    EvalReport

    Raises
    ------
    NotImplementedError
        Remaining: choose the base classifier so that the PU and naive arms differ only in the
        label treatment, not in the model family.
    """
    raise NotImplementedError(
        "Remaining: pick one base classifier shared by both arms so the comparison isolates "
        "the label treatment."
    )


def run_pu_benchmark(
    ds: Dataset,
    spec: EvalSpec | None = None,
    estimators: tuple[str, ...] = PU_ESTIMATORS,
) -> pd.DataFrame:
    """Score every PU estimator and the naive arm on one dataset.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    spec : EvalSpec, optional
        Defaults to the temporal split matching :data:`BAO_TEST_WINDOWS` with k = 1 per cent.
    estimators : tuple of str, default :data:`PU_ESTIMATORS`
        Detector registry names to run.

    Returns
    -------
    pandas.DataFrame
        One row per (estimator, test window) with AUC, average precision, NDCG@1% and
        precision@1%, the number of test positives, and the test-period base rate.

    Raises
    ------
    NotImplementedError
        Remaining: everything below the harness call -- the estimators exist and are tested in
        forensics_core; what is missing is the dataset and the split.
    """
    raise NotImplementedError(
        "Remaining: build the dataset and the temporal split, then call evaluate() per window."
    )


def estimated_class_prior(ds: Dataset, spec: EvalSpec | None = None) -> float:
    """Elkan-Noto estimate of ``P(y=1)``: how much misstatement is never charged.

    The gap between this and the observed AAER rate is an estimate of the enforcement
    selection, and it is arguably the most interesting quantity in the project -- it is the
    closest thing to a measurement of what the labels do not see, which is precisely the
    quantity that has no ground truth at all in the ``gosplan`` case.

    Parameters
    ----------
    ds : Dataset
        From :func:`build_dataset`.
    spec : EvalSpec, optional
        Split used to fit the non-traditional classifier.

    Returns
    -------
    float
        Estimated ``P(y=1)``.

    Raises
    ------
    NotImplementedError
        Remaining: the Elkan-Noto estimator assumes labelling is completely at random given
        ``y``, which enforcement plainly is not. State how far that assumption is violated
        before reporting a number, or report the estimate only as a bound.
    """
    raise NotImplementedError(
        "Remaining: state the selected-completely-at-random violation before reporting a prior."
    )


def transfer_to(source: Dataset, target: Dataset, spec: EvalSpec | None = None) -> TransferResult:
    """Fit on the labelled project and score an unlabelled one, carrying the calibration across.

    This is the programme's whole design in one call: a detector calibrated where ground truth
    exists is scored where it does not, and the source-calibrated score-to-precision curve is
    what makes a target score readable at all
    (:func:`forensics_core.eval.harness.transfer`).

    Parameters
    ----------
    source : Dataset
        A labelled dataset, normally this project's.
    target : Dataset
        An unlabelled dataset from another project.
    spec : EvalSpec, optional
        Split used for the source-side report.

    Returns
    -------
    TransferResult

    Raises
    ------
    NotImplementedError
        Remaining: define the feature correspondence between projects. Transfer is meaningless
        unless the columns mean the same thing on both sides, and for the Soviet data most of
        them do not.
    """
    raise NotImplementedError(
        "Remaining: define and defend the cross-project feature correspondence before transfer."
    )

"""Detectors calibrated where truth is knowable, applied here. STUBS ONLY -- nothing is run.

This module is the reason the programme has four projects instead of one. ``elections``,
``aaer`` and ``china`` have ground truth: published falsification signatures, enforcement
actions, and a reconciliation against an independent aggregate. ``gosplan`` has one anchor.
A detector fitted and validated on that single anchor would be fitted and validated on the
same event, so its score here would carry no information about how often it is wrong.

The design is therefore: fit on a source project, score here, and carry the source-calibrated
score-to-precision curve across so that a score in this project can be read as "on the source
project, a score this high had precision p". That is what
:func:`forensics_core.eval.harness.transfer` returns, and the calibration table is the part
that matters -- the raw score is meaningless without it.

The split is ``anchor_holdout``. :class:`forensics_core.eval.harness.EvalSpec` takes an
``anchor_mask`` marking the rows that *are* the anchor; those rows are held out of fitting and
scored blind. With one anchor this does not estimate a false-positive rate -- nothing can,
from inside this project -- but it does stop the anchor from being used to choose the
detector that finds it.

What a transferred detector has to do, from ``docs/validation_anchors.md``:

1. rank Uzbek cotton in 1978-1983 at or near the top of the full panel, applied blind;
2. **not** fire equally on sectors and periods with no independent evidence of padding -- and
   where it does fire, that has to be reported rather than filtered away, because a detector
   that fires everywhere has told you nothing;
3. survive the weighting-scheme robustness check and the currency-reform and boundary-change
   controls in ``docs/known_traps.md``.

And the standing limit on what any of it can conclude: with a single anchor the honest output
is a **bound under a stated assumption** -- "reported distortion is at least X in sector S over
years Y, assuming the padding mechanism resembles the anchor" -- not a point estimate of
aggregate distortion.

One further source of labels exists and should be used before falling back on the single
anchor: Harrison's plan-fraud case index (registry id ``harrison_plan_fraud``) records
prosecuted Soviet reporting fraud at case level -- establishment, branch, republic, what was
falsified -- for 1943 to 1962. It is a different period and a different selection process
from the anchor (it labels what was *prosecuted*, which is not what was *done*), so it is a
positive-unlabelled problem rather than a clean label set, which is what
:mod:`forensics_core.labels.pu` is for. Treating it as a second anchor without saying that
would overstate what the project has.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from forensics_core.eval.harness import Dataset, Detector, EvalReport, EvalSpec, TransferResult

__all__ = [
    "SOURCE_PROJECTS",
    "anchor_holdout_spec",
    "build_panel",
    "build_uzbek_cotton_anchor_mask",
    "transfer_from_calibrated",
    "transfer_report",
]

#: The three projects with ground truth, in the order the programme validates them. A
#: detector should be transferred from each separately and the results compared: agreement
#: between three differently-calibrated detectors is worth more than any single ranking.
SOURCE_PROJECTS: tuple[str, ...] = ("elections", "aaer", "china")


def build_panel(
    series: pd.DataFrame,
    *,
    unit_col: str = "unit_id",
    time_col: str = "period",
    group_col: str = "sector",
    features: Sequence[str] = (),
) -> Dataset:
    """Assemble the gosplan panel as a harness :class:`~forensics_core.eval.harness.Dataset`.

    Parameters
    ----------
    series : pandas.DataFrame
        Long-format panel of reported series with their derived features, built from
        transcribed tables that have passed validation and double transcription.
    unit_col, time_col, group_col : str
        Column names for the unit identifier, the period and the grouping key
        (sector, republic, or their interaction).
    features : sequence of str
        Feature columns to expose as ``Dataset.X``. Every feature must be computable for every
        row: a feature available only for the anchor's sector would make the anchor
        identifiable from the features alone.

    Returns
    -------
    forensics_core.eval.harness.Dataset
        With ``y`` mostly NaN: this project is almost entirely unlabelled, and encoding
        "presumed clean" as 0 across the panel would assert exactly what
        ``docs/known_traps.md`` trap 6 says cannot be assumed.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: transcribed series to build the panel from, and a decision on the unit of
    observation. Sector-year, republic-year and sector-republic-year give different panels
    and different amounts of power, and the choice has to be made before the anchor is looked
    at.
    """
    raise NotImplementedError(
        "needs validated transcribed series and a unit of observation fixed in advance"
    )


def build_uzbek_cotton_anchor_mask(
    ds: Dataset,
    *,
    years: tuple[int, int] = (1978, 1983),
    sector: str = "cotton",
    republic: str = "uzbek_ssr",
) -> pd.Series:
    """Mark the rows that are the anchor, for the ``anchor_holdout`` split.

    Parameters
    ----------
    ds : Dataset
        The panel from :func:`build_panel`.
    years : (int, int), default (1978, 1983)
        Inclusive window. This is the period for which the Soviet investigation's figure of
        4.548 million tons of non-existent cotton is quoted in Cucciolla (2017), paragraph 23.
        **An unresolved inconsistency sits behind this window**: the same article's paragraph
        11 gives 270,000 to 340,000 tons per year, which does not reconcile with 4.548 Mt over
        six years (about 758,000 t/yr). Which figure refers to what must be settled from the
        sources before either is used as a target; the window itself is the better-supported
        part of the claim.
    sector, republic : str
        Keys identifying the anchor rows in the panel's grouping columns.

    Returns
    -------
    pandas.Series
        Boolean mask aligned with ``ds.unit_id``, True for anchor rows.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: the panel, and a decision on the window's edges. Padding is described as
    intensifying in 1980-1982 and as beginning as early as 1976 depending on the source, so
    the window is itself uncertain and any sensitivity to it must be reported.
    """
    raise NotImplementedError(
        "needs the panel; and the anchor window's edges are themselves uncertain across sources"
    )


def anchor_holdout_spec(
    anchor_mask: pd.Series, *, ks: tuple[float, ...] = (0.01, 0.05, 0.10)
) -> EvalSpec:
    """The evaluation specification this project uses: hold the anchor out, score it blind.

    Parameters
    ----------
    anchor_mask : pandas.Series
        From :func:`build_uzbek_cotton_anchor_mask`.
    ks : tuple of float
        Cut-offs for the rank metrics, as fractions of the panel.

    Returns
    -------
    forensics_core.eval.harness.EvalSpec
        With ``split="anchor_holdout"``.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: trivial to construct, deliberately left as a stub so that no part of this
    package can be run before the panel exists. What still needs deciding is whether the
    metrics are computed over the whole panel or within sector, which changes what "ranked at
    the top" means.
    """
    raise NotImplementedError(
        "constructs an EvalSpec with split='anchor_holdout'; blocked on the panel and on "
        "whether ranking is global or within sector"
    )


def transfer_from_calibrated(
    detector: Detector,
    source: Dataset,
    target: Dataset,
    *,
    source_spec: EvalSpec | None = None,
) -> TransferResult:
    """Fit a detector on a project with ground truth and score the gosplan panel with it.

    Parameters
    ----------
    detector : Detector
        Any detector in :data:`forensics_core.eval.harness.DETECTOR_REGISTRY`, or a custom
        one satisfying the protocol.
    source : Dataset
        The calibration project's dataset: ``elections``, ``aaer`` or ``china``.
    target : Dataset
        The gosplan panel.
    source_spec : EvalSpec, optional
        Evaluation specification for the source project, so that the source-side performance
        is reported alongside the transferred scores rather than assumed.

    Returns
    -------
    forensics_core.eval.harness.TransferResult
        Scores and ranks for the target, the source-side report, and the calibration table
        mapping a score threshold to the precision and recall it achieved on the source.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: the panel, and a feature representation shared between source and target. That
    second requirement is the hard one -- a detector fitted on precinct-level vote shares
    cannot be applied to sector-year output series unless both are reduced to features that
    mean the same thing in each, and defining those features honestly is most of the work.
    """
    raise NotImplementedError(
        "wraps forensics_core.eval.harness.transfer; blocked on the panel and, more seriously, "
        "on a feature representation that means the same thing in both projects"
    )


def transfer_report(
    results: dict[str, TransferResult],
    *,
    anchor_mask: pd.Series,
    top_k: float = 0.05,
) -> tuple[pd.DataFrame, dict[str, EvalReport]]:
    """Assemble the transfer results into the three checks the anchor document demands.

    Parameters
    ----------
    results : dict
        Transfer results keyed by source project name.
    anchor_mask : pandas.Series
        Which rows are the anchor.
    top_k : float, default 0.05
        Fraction of the panel counted as "the top" when asking whether the anchor was ranked
        there.

    Returns
    -------
    (pandas.DataFrame, dict)
        A table with, per source project: the anchor's rank, whether it fell inside the top
        ``top_k``, and how many non-anchor rows scored above it -- the last being the number
        that says whether the detector is discriminating or simply firing everywhere. Plus the
        per-source evaluation reports.

    Raises
    ------
    NotImplementedError
        Always.

    Notes
    -----
    Remaining: everything upstream. Also decide how disagreement between the three source
    projects is reported. Three detectors that disagree is a result about the methods, and
    presenting only the one that ranks the anchor highest would be the exact failure this
    programme's design exists to prevent.
    """
    raise NotImplementedError(
        "blocked on the panel; and the presentation of disagreement between source projects "
        "must be fixed before any of them is run"
    )

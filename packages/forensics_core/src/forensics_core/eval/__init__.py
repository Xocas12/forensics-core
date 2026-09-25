"""Rank metrics (base rates are tiny; never use accuracy) and the uniform Detector /
Dataset / evaluate / transfer harness that lets a method scored on one project run on
another."""

from forensics_core.eval.harness import (
    DETECTOR_REGISTRY,
    Dataset,
    Detector,
    EvalReport,
    EvalSpec,
    FunctionDetector,
    PUDetector,
    SklearnDetector,
    TransferResult,
    evaluate,
    make_detector,
    register_detector,
    transfer,
)
from forensics_core.eval.metrics import (
    BootstrapResult,
    average_precision,
    bootstrap_metric,
    ndcg_at_k,
    precision_at_k,
    rank_metrics,
    recall_at_k,
    roc_auc,
)

__all__ = [
    "DETECTOR_REGISTRY",
    "BootstrapResult",
    "Dataset",
    "Detector",
    "EvalReport",
    "EvalSpec",
    "FunctionDetector",
    "PUDetector",
    "SklearnDetector",
    "TransferResult",
    "average_precision",
    "bootstrap_metric",
    "evaluate",
    "make_detector",
    "ndcg_at_k",
    "precision_at_k",
    "rank_metrics",
    "recall_at_k",
    "register_detector",
    "roc_auc",
    "transfer",
]

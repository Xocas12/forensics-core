"""Positive-unlabeled learning. Enforcement-based labels (SEC AAERs, admitted falsification)
identify some positives; everything else is *unlabeled*, not negative.

Public API
----------
ElkanNotoPU
    Elkan & Noto (2008) constant-``c`` correction: ``P(y=1|x) = g(x)/c``.
BaggingPU
    Mordelet & Vert (2014) bagging of positives against unlabeled subsamples, with
    out-of-bag scores for the unlabeled pool.
estimate_class_prior
    Elkan-Noto ratio estimator of ``P(y=1)`` from classifier scores.
"""

from forensics_core.labels.pu import BaggingPU, ElkanNotoPU, estimate_class_prior

__all__ = ["BaggingPU", "ElkanNotoPU", "estimate_class_prior"]

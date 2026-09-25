"""Analysis for the aaer project. **Every function in this package is a stub.**

No analysis has been run in this repository and no finding exists in this tree. Each module
here ships fixed signatures, docstrings that cite the method and state the target, and bodies
that raise :class:`NotImplementedError` naming what remains. That is deliberate: the scaffolding
session that produced them was forbidden from computing anything, so that no number in the
repository can have entered it without someone deciding to compute it.

``beneish_baseline``
    The Beneish (1999) M-score evaluated against AAER labels with rank metrics. The floor every
    later model has to clear.
``pu_benchmark``
    Positive-unlabeled learning (Elkan and Noto 2008; Mordelet and Vert 2014) against the
    treat-unflagged-as-clean formulation, measured against the corrected Bao et al. (2020)
    figures in ``docs/validation_anchors.md``.
``earnings_bunching``
    Excess mass at the earnings thresholds firms are rewarded for clearing. The feature family
    with a direct analogue in the Soviet plan-fulfilment data.

Before implementing any of them, read ``docs/known_traps.md``. The three traps that decide
whether a result means anything are: unflagged firm-years are unlabeled rather than clean, the
base rate is under 1 per cent so accuracy is meaningless, and an AAER attaches to the misstated
fiscal years rather than to the release year.
"""

__all__: list[str] = []

"""Analysis interfaces for the china project. **Every function here raises.**

Nothing in this package computes anything yet, and that is deliberate rather than unfinished:
there is no data to compute it on. Every provincial number this project needs is inside a
JPEG scan, and :func:`china.clean.yearbook.extract_table_image` is a stub. A function here
that returned a number today would be returning a number about nothing.

What each module fixes is the **signature**: what the test takes, what it returns, and which
published method it implements, so that the shape of the analysis is settled before the data
arrives and so that the shared evaluation harness can be wired to it.

The five tests, and why each one is here
----------------------------------------
:mod:`china.analysis.gap`
    The provincial-sum minus national gap. The project's headline quantity, and the one that
    has to be decomposed into its mechanical part (cross-province double counting, different
    deflators, boundary changes) before any residual can be called misreporting.
:mod:`china.analysis.reform`
    The unified-accounting reform as a natural experiment. The break is at the **2019 data
    year**, verified from the bureau's own question-and-answer page, and not at the June 2017
    approval.
:mod:`china.analysis.proxies`
    Provincial product against electricity, rail freight, credit and nightlights. The residual
    from these relationships is what separates a province that hit its target by managing
    real activity from one that hit it on paper.
:mod:`china.analysis.dispersion`
    Underdispersion: a reported series with less variance than its physical driver permits is
    impossible regardless of level. This is one of the two signals that carry to the Soviet
    case.
:mod:`china.analysis.bunching`
    Excess mass at the provincial growth target. The other transferable signal, and the one
    that needs a source this project does not yet have: the targets themselves.
"""

__all__: list[str] = []

"""The analysis package must stay stubs until someone decides to run something.

These tests exist to make the "no analysis has been run" claim in the README enforceable rather
than aspirational. If a stub is implemented, its test here fails and has to be replaced by a
real test of the real behaviour -- which is the point.
"""

from __future__ import annotations

import inspect

import pytest
from aaer.analysis import beneish_baseline, earnings_bunching, pu_benchmark

MODULES = (beneish_baseline, pu_benchmark, earnings_bunching)


def _public_functions(module):
    return [
        (f"{module.__name__}.{name}", obj)
        for name, obj in vars(module).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == module.__name__
    ]


def test_every_analysis_function_is_still_a_stub():
    functions = [pair for module in MODULES for pair in _public_functions(module)]
    assert len(functions) >= 12, "the three analysis modules should expose their full surface"
    for qualname, fn in functions:
        source = inspect.getsource(fn)
        assert "raise NotImplementedError" in source, f"{qualname} is no longer a stub"


def test_every_stub_says_what_remains():
    for module in MODULES:
        for qualname, fn in _public_functions(module):
            doc = inspect.getdoc(fn) or ""
            assert doc.strip(), f"{qualname} has no docstring"
            source = inspect.getsource(fn)
            start = source.index("raise NotImplementedError")
            message = source[start:]
            assert len(message) > len("raise NotImplementedError()") + 20, (
                f"{qualname} raises NotImplementedError without saying what remains"
            )


def test_calling_a_stub_raises_rather_than_returning_something_plausible():
    with pytest.raises(NotImplementedError, match="Remaining"):
        beneish_baseline.beneish_detector()
    with pytest.raises(NotImplementedError, match="Remaining"):
        pu_benchmark.run_pu_benchmark(None)
    with pytest.raises(NotImplementedError, match="Remaining"):
        earnings_bunching.scaled_earnings(None)


def test_the_unreachable_notch_says_so_instead_of_guessing_a_source():
    """No registry entry provides analyst forecasts, and the stub has to name that."""
    with pytest.raises(NotImplementedError, match="No analyst-forecast source"):
        earnings_bunching.consensus_notch()


def test_the_two_reachable_notches_are_declared_at_zero():
    assert earnings_bunching.ZERO_EARNINGS_NOTCH.threshold == 0.0
    assert earnings_bunching.ZERO_EARNINGS_NOTCH.side == "above"
    assert earnings_bunching.PRIOR_YEAR_NOTCH.threshold == 0.0
    assert earnings_bunching.PRIOR_YEAR_NOTCH.side == "above"


def test_the_pu_estimator_names_exist_in_the_shared_detector_registry():
    from forensics_core.eval.harness import DETECTOR_REGISTRY

    for name in pu_benchmark.PU_ESTIMATORS:
        assert name in DETECTOR_REGISTRY


def test_the_benchmark_windows_match_the_published_test_periods():
    assert pu_benchmark.BAO_TEST_WINDOWS == ((2003, 2005), (2003, 2008))

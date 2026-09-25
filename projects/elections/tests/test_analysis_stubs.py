"""The analysis layer is stubs, and this file is what keeps it honest.

Two things are asserted. First, that no function in ``elections.analysis`` returns anything:
every one of them raises ``NotImplementedError`` with a message that says what remains, so a
half-finished replication cannot be mistaken for a result. Second, that the signatures are the
ones the rest of the project is written against, since those signatures are the contract the
``forensics_core`` evaluation harness and the later projects rely on.
"""

from __future__ import annotations

import inspect

import pytest
from elections import analysis
from elections.analysis import comet_tail, integer_percentage, turnout_bimodality

STUB_MODULES = (integer_percentage, comet_tail, turnout_bimodality)

STUBS = [
    (module.__name__, name)
    for module in STUB_MODULES
    for name in module.__all__
    if callable(getattr(module, name))
]


def test_there_is_one_module_per_validation_anchor():
    assert len(STUB_MODULES) == 3
    assert {m.__name__.rsplit(".", 1)[-1] for m in STUB_MODULES} == {
        "integer_percentage",
        "comet_tail",
        "turnout_bimodality",
    }


@pytest.mark.parametrize(("module_name", "name"), STUBS)
def test_every_analysis_function_raises_not_implemented(module_name, name, tidy):
    """Called with a real tidy frame, so a stub cannot pass by failing on its arguments."""
    module = dict((m.__name__, m) for m in STUB_MODULES)[module_name]
    function = getattr(module, name)
    with pytest.raises(NotImplementedError) as excinfo:
        function(tidy, election="2011-duma")
    message = str(excinfo.value)
    assert message.strip(), f"{name} must say what remains"
    assert len(message) > 40, f"{name}: the message must name the remaining work"


@pytest.mark.parametrize(("module_name", "name"), STUBS)
def test_every_analysis_function_documents_its_method_and_anchor(module_name, name):
    module = dict((m.__name__, m) for m in STUB_MODULES)[module_name]
    doc = inspect.getdoc(getattr(module, name)) or ""
    assert "Parameters" in doc
    assert "Returns" in doc
    assert "NotImplementedError" in doc
    # the module docstring is where the citation lives, and every one must have one
    module_doc = inspect.getdoc(module) or ""
    assert "docs/validation_anchors.md" in module_doc
    assert "docs/known_traps.md" in module_doc


def test_every_stub_consumes_the_tidy_frame_and_names_its_election():
    for module in STUB_MODULES:
        for name in module.__all__:
            function = getattr(module, name)
            if not callable(function):
                continue
            params = inspect.signature(function).parameters
            assert next(iter(params)) == "tidy", f"{name} must take the tidy frame first"
            assert params["election"].kind is inspect.Parameter.KEYWORD_ONLY
            assert params["election"].default is inspect.Parameter.empty


def test_the_package_exports_every_stub():
    for module in STUB_MODULES:
        for name in module.__all__:
            if callable(getattr(module, name)):
                assert name in analysis.__all__
                assert getattr(analysis, name) is getattr(module, name)


def test_the_seeded_estimators_all_take_a_seed():
    """Randomness flows through an explicit seed everywhere, per the library contract."""
    seeded = [
        integer_percentage.integer_percentage_excess,
        comet_tail.comet_tail_estimate,
        turnout_bimodality.turnout_bimodality_test,
    ]
    for function in seeded:
        params = inspect.signature(function).parameters
        assert "seed" in params
        assert params["seed"].default is None


def test_the_size_conditioned_variant_defaults_to_the_documented_floor():
    """Trap 1: the denominator floor is 100, matching forensics_core and Klimek et al."""
    from elections.features import DEFAULT_MIN_DENOMINATOR

    params = inspect.signature(integer_percentage.integer_percentage_excess).parameters
    assert params["min_denominator"].default == DEFAULT_MIN_DENOMINATOR
    assert turnout_bimodality.KLIMEK_MIN_ELECTORATE == DEFAULT_MIN_DENOMINATOR

"""The analysis package is stubs, and these tests keep it that way.

Two things are being asserted. First, that nothing in ``china.analysis`` computes anything:
every public callable raises :class:`NotImplementedError` with a message that says what
remains, so a stub can never be mistaken for a result. Second, that the one thing the stubs do
assert as fact is right: the accounting reform's first data year is 2019, not the 2017
approval, because getting that wrong is the most likely way to produce a confident wrong
answer later.
"""

from __future__ import annotations

import inspect
from types import ModuleType

import pytest
from china.analysis import bunching, dispersion, gap, proxies, reform

MODULES: tuple[ModuleType, ...] = (gap, reform, proxies, dispersion, bunching)

#: Helpers that legitimately compute something: they build candidate lists, not results.
PURE_HELPERS = {"round_number_candidates"}


def _module_functions(module: ModuleType) -> dict[str, object]:
    """Every public function *defined in* ``module``, whether or not it is exported.

    Iterating ``__all__`` instead would let a future analysis function that someone forgot to
    export slip past the "must raise" guard, which is the one violation these tests exist to
    catch. Functions imported from elsewhere are excluded on ``__module__``.
    """
    return {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and inspect.isfunction(value)
        and value.__module__ == module.__name__
    }


def _public_callables(module: ModuleType):
    yield from _module_functions(module).items()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_every_function_defined_in_an_analysis_module_is_exported(module):
    """``__all__`` must name every function the module defines, so the guard above is total.

    An unexported analysis function would still be importable and callable, and the "must
    raise" test iterates the module's own members rather than ``__all__`` for that reason.
    This test keeps the two in step, so that a mismatch is a failure rather than a silent
    difference between what is documented and what exists.
    """
    defined = set(_module_functions(module))
    exported = set(module.__all__)
    assert defined - exported == set(), (
        f"{module.__name__} defines public functions missing from __all__: "
        f"{sorted(defined - exported)}"
    )
    assert exported - defined <= {
        name for name in exported if not inspect.isfunction(getattr(module, name))
    }, f"{module.__name__} exports a function it does not define"


def test_the_five_analysis_modules_are_all_present():
    assert len(MODULES) == 5
    assert {m.__name__.rsplit(".", 1)[-1] for m in MODULES} == {
        "gap",
        "reform",
        "proxies",
        "dispersion",
        "bunching",
    }


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_every_analysis_function_raises_with_an_explanation(module):
    checked = 0
    for name, fn in _public_callables(module):
        if name in PURE_HELPERS:
            continue
        signature = inspect.signature(fn)
        args = [None] * sum(
            1
            for p in signature.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
        )
        kwargs = {
            p.name: None
            for p in signature.parameters.values()
            if p.kind is p.KEYWORD_ONLY and p.default is p.empty
        }
        with pytest.raises(NotImplementedError) as excinfo:
            fn(*args, **kwargs)
        assert len(str(excinfo.value).strip()) > 20, f"{name} must say what remains"
        checked += 1
    assert checked > 0, f"{module.__name__} exposes no analysis functions"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_every_analysis_function_documents_itself(module):
    for name, fn in _public_callables(module):
        doc = inspect.getdoc(fn) or ""
        assert "Parameters" in doc, f"{name} has no numpy-style parameter section"
        assert "Returns" in doc, f"{name} has no numpy-style returns section"


def test_the_reform_break_is_the_2019_data_year_and_not_the_2017_approval():
    assert reform.REFORM_FIRST_DATA_YEAR == 2019
    assert reform.REFORM_APPROVAL_YEAR == 2017
    assert reform.REFORM_IMPLEMENTED == "2020-01"
    default = inspect.signature(reform.reform_discontinuity).parameters["break_year"].default
    assert default == reform.REFORM_FIRST_DATA_YEAR


def test_the_break_year_sensitivity_default_spans_the_approval_and_the_publication():
    candidates = (
        inspect.signature(reform.break_year_sensitivity).parameters["candidate_years"].default
    )
    assert candidates == (2017, 2018, 2019, 2020)


def test_bunching_requires_targets_because_the_registry_has_no_source_for_them():
    parameters = inspect.signature(bunching.growth_target_bunching).parameters
    assert parameters["targets"].default is inspect.Parameter.empty


def test_the_keqiang_index_refuses_to_supply_weights_it_cannot_cite():
    parameters = inspect.signature(proxies.keqiang_index).parameters
    assert parameters["weights"].default is None
    with pytest.raises(NotImplementedError, match="no sourced weights"):
        proxies.keqiang_index(None, vintage="csy2024")


def test_round_number_candidates_is_a_real_helper_and_validates_its_input():
    assert bunching.round_number_candidates(6.0, 7.0, 0.5) == [6.0, 6.5, 7.0]
    assert bunching.round_number_candidates(4.0, 12.0, 0.5)[0] == 4.0
    assert len(bunching.round_number_candidates(4.0, 12.0, 0.5)) == 17
    with pytest.raises(ValueError, match="step must be positive"):
        bunching.round_number_candidates(4.0, 12.0, 0.0)
    with pytest.raises(ValueError, match="hi must exceed lo"):
        bunching.round_number_candidates(12.0, 4.0, 0.5)


def test_the_proxy_list_names_the_four_the_project_can_build():
    assert proxies.PROXY_SERIES == (
        "electricity_consumption",
        "freight_rail",
        "loans_outstanding",
        "nightlights_dn_sum",
    )


def test_the_nightlights_stub_names_the_missing_boundary_source():
    with pytest.raises(NotImplementedError, match="boundary"):
        proxies.seam_break_test(None)

"""The analysis package must be stubs, and must stay stubs until there is data.

This suite exists to make an accidental half-implementation loud. Every public entry point in
``gosplan.analysis`` has to raise :class:`NotImplementedError` carrying a message that says
what is still missing, so that nobody can run a number out of this tree and mistake it for a
finding. When a function is genuinely implemented, the corresponding assertion here is what
has to be deleted deliberately.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

MODULES = (
    "gosplan.analysis.plan_fulfilment",
    "gosplan.analysis.hidden_inflation",
    "gosplan.analysis.io_reconciliation",
    "gosplan.analysis.harvest_dispersion",
    "gosplan.analysis.transfer",
)


def _public_callables(module):
    exported = getattr(module, "__all__", ())
    return [
        (name, getattr(module, name)) for name in exported if callable(getattr(module, name, None))
    ]


def _call_with_placeholders(fn):
    """Call ``fn`` supplying a placeholder for every parameter it requires."""
    sig = inspect.signature(fn)
    args = []
    kwargs = {}
    for param in sig.parameters.values():
        if param.default is not inspect.Parameter.empty:
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if param.kind is param.KEYWORD_ONLY:
            kwargs[param.name] = None
        else:
            args.append(None)
    return fn(*args, **kwargs)


@pytest.mark.parametrize("module_name", MODULES)
def test_module_exports_something(module_name):
    module = importlib.import_module(module_name)
    assert _public_callables(module), f"{module_name} exports no entry points"


@pytest.mark.parametrize("module_name", MODULES)
def test_every_analysis_entry_point_is_a_stub(module_name):
    module = importlib.import_module(module_name)
    for name, fn in _public_callables(module):
        with pytest.raises(NotImplementedError) as exc:
            _call_with_placeholders(fn)
        message = str(exc.value)
        assert len(message) > 20, f"{module_name}.{name} raises without saying what remains"


@pytest.mark.parametrize("module_name", MODULES)
def test_every_analysis_entry_point_documents_its_method(module_name):
    module = importlib.import_module(module_name)
    for name, fn in _public_callables(module):
        doc = inspect.getdoc(fn) or ""
        assert doc, f"{module_name}.{name} has no docstring"
        assert "Parameters" in doc, f"{module_name}.{name} does not document its parameters"
        assert "Returns" in doc, f"{module_name}.{name} does not document its return"
        assert "Notes" in doc or "References" in doc, (
            f"{module_name}.{name} cites neither a method source nor what remains"
        )


@pytest.mark.parametrize("module_name", MODULES)
def test_no_analysis_module_reads_or_writes_anything(module_name):
    """A stub that already opens files is a stub that is about to compute something."""
    module = importlib.import_module(module_name)
    source = inspect.getsource(module)
    for forbidden in ("open(", "read_csv", "to_csv", "read_parquet", "to_parquet"):
        assert forbidden not in source, f"{module_name} performs I/O: {forbidden}"


def test_the_transfer_module_names_the_three_calibration_projects():
    from gosplan.analysis.transfer import SOURCE_PROJECTS

    assert set(SOURCE_PROJECTS) == {"elections", "aaer", "china"}


def test_the_transfer_module_uses_the_anchor_holdout_split():
    from gosplan.analysis import transfer

    doc = inspect.getdoc(transfer.anchor_holdout_spec) or ""
    assert "anchor_holdout" in doc or "anchor_holdout" in inspect.getsource(
        transfer.anchor_holdout_spec
    )


def test_the_anchor_window_stub_records_the_unresolved_inconsistency():
    """validation_anchors.md flags two irreconcilable figures; the code must not pick one."""
    from gosplan.analysis.transfer import build_uzbek_cotton_anchor_mask

    doc = inspect.getdoc(build_uzbek_cotton_anchor_mask) or ""
    assert "4.548" in doc
    assert "270,000" in doc or "270" in doc

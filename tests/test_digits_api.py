"""The public surface of forensics_core.digits: re-exports and the INTERFACES.md contract.

These tests exist so that a rename inside a module cannot silently break the four projects
that build against the contract.
"""

from __future__ import annotations

import inspect

import pytest

import forensics_core.digits as digits

CONTRACT_SIGNATURES = {
    "benford_expected": ["position"],
    "digit_support": ["position"],
    "leading_digits": ["x", "position"],
    "digit_frequencies": ["x", "position", "weights"],
    "benford_test": ["x", "position", "weights", "statistics"],
    "terminal_digits": ["x", "k"],
    "terminal_digit_test": ["x", "k", "weights"],
    "terminal_digit_pair_test": ["x", "weights"],
    "percentage": ["numerator", "denominator"],
    "percentage_histogram": ["pct", "bin_width", "weights", "lo", "hi"],
    "integer_excess": [
        "pct",
        "denominators",
        "tolerance",
        "min_denominator",
        "neighbour_bins",
        "n_mc",
        "seed",
        "weights",
    ],
    "integer_excess_by_group": ["pct", "denominators", "groups"],
}


@pytest.mark.parametrize("name", sorted(CONTRACT_SIGNATURES))
def test_public_names_are_re_exported(name):
    assert name in digits.__all__
    assert callable(getattr(digits, name))


@pytest.mark.parametrize(("name", "expected"), sorted(CONTRACT_SIGNATURES.items()))
def test_contract_parameters_are_present_and_in_order(name, expected):
    """Extra keyword arguments with defaults are allowed; renames and removals are not."""
    parameters = inspect.signature(getattr(digits, name)).parameters
    present = [p for p in parameters if p in expected]
    assert present == expected, f"{name} lost or reordered contract parameters"
    for extra in set(parameters) - set(expected):
        param = parameters[extra]
        assert param.default is not inspect.Parameter.empty or param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ), f"{name} added a required parameter {extra}"


@pytest.mark.parametrize(
    "name", ["DigitTable", "BenfordResult", "IntegerExcessResult", "DigitPosition"]
)
def test_public_types_are_re_exported(name):
    assert name in digits.__all__
    assert getattr(digits, name) is not None


def test_result_containers_expose_to_dict():
    for name in ("DigitTable", "BenfordResult", "IntegerExcessResult"):
        assert callable(getattr(digits, name).to_dict)

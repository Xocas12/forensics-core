"""The audit notebook must be valid, output-free, and safe to open with no data acquired."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
import pytest

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "00_data_audit.ipynb"


@pytest.fixture(scope="module")
def notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def test_the_notebook_is_valid_nbformat_4(notebook):
    assert notebook["nbformat"] == 4
    nbformat.validate(notebook)


def test_it_is_also_plain_json_on_disk():
    raw = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert raw["nbformat"] == 4
    assert raw["cells"]


def test_no_cell_carries_an_output_or_an_execution_count(notebook):
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        assert cell["outputs"] == [], f"cell {index} has outputs"
        assert cell["execution_count"] is None, f"cell {index} has an execution count"


def test_every_code_cell_guards_against_an_empty_data_directory(notebook):
    """Opening this notebook before `make data` must print instructions, not traceback."""
    code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) >= 8
    setup, *rest = code_cells
    assert "RawFileMissing" in setup["source"]
    assert "RUN_FIRST" in setup["source"]
    assert "make data" in setup["source"]
    for index, cell in enumerate(rest, start=1):
        assert cell["source"].lstrip().startswith("if TIDY is None:"), (
            f"code cell {index} does not guard on TIDY"
        )
        assert "RUN_FIRST" in cell["source"]


def test_it_states_that_it_does_no_inference(notebook):
    first_markdown = next(c for c in notebook["cells"] if c["cell_type"] == "markdown")
    assert "no inference" in first_markdown["source"].lower()


def test_it_covers_every_subject_the_audit_is_for(notebook):
    text = "\n".join(cell["source"] for cell in notebook["cells"])
    for subject in (
        "size_band_counts",
        "denominator_floor_summary",
        "exact_integer_share",
        "isna",
        "dtypes",
        "unit",
        "region",
        "in_stationary_boxes",
        "run_all_checks",
        "raw_headers",
    ):
        assert subject in text, f"the audit does not cover {subject}"


def test_it_fits_no_model(notebook):
    """A crude guard against the notebook quietly acquiring an analysis."""
    text = "\n".join(cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "code")
    for forbidden in ("integer_excess", "pvalue", "p_value", ".fit(", "ols", "regress"):
        assert forbidden not in text, f"the audit notebook must not use {forbidden}"

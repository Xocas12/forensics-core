"""The loaders in :mod:`gosplan.clean`, against synthetic fixtures and against the registry.

Two properties matter more than the parsing. First, the column names a loader expects are
the ones ``data/SOURCES.yaml`` records, so the tests read them out of the registry text
rather than restating them. Second, every loaded frame has passed the seal: the fixtures
carry rows shaped like the held-out anchor (with invented values), and the tests assert only
that those rows are gone and how many were withheld, never anything about their values.

Nothing here reads ``data/raw`` or makes a network request.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml
from gosplan import seal
from gosplan.clean import BASIS_COLUMNS, LOADERS, N_WITHHELD_ATTR, UNLOADED, SchemaError
from gosplan.clean.agriculture import (
    USDA_PSD_COLUMNS,
    USDA_PSD_COTTON_COMMODITY_CODE,
    USDA_PSD_MEMBER,
    USDA_PSD_SOURCE_ID,
    load_usda_psd_cotton,
)
from gosplan.clean.western_estimates import (
    SESS_ID_COLUMNS,
    SESS_SOURCE_ID,
    load_hokudai_sess,
)
from gosplan.transcribe.schema import CurrencyBasis, TerritorialBasis

USDA_FIXTURE = "synthetic_usda_psd_cotton.csv"
SESS_FIXTURE = "synthetic_sess_series.csv"
PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry(sources_yaml):
    entries = yaml.safe_load(sources_yaml.read_text(encoding="utf-8"))
    return {e["id"]: e for e in entries}


@pytest.fixture(autouse=True)
def _sealed():
    # These tests are about the sealed state, which is the state until G3 is signed.
    assert seal.is_sealed()


# ---------------------------------------------------------------------------------------
# The registry is the authority on column names
# ---------------------------------------------------------------------------------------


def test_usda_columns_are_the_ones_the_registry_records(registry):
    notes = registry[USDA_PSD_SOURCE_ID]["notes"]
    match = re.search(r"Columns: ([A-Za-z_,]+)\.", notes)
    assert match, "the registry no longer records the USDA PSD header"
    assert tuple(match.group(1).split(",")) == USDA_PSD_COLUMNS


def test_usda_member_and_commodity_are_the_ones_the_registry_records(registry):
    plan = registry[USDA_PSD_SOURCE_ID]["download_plan"]
    assert f"Unzip {USDA_PSD_MEMBER}" in plan
    assert f"Commodity_Code=={USDA_PSD_COTTON_COMMODITY_CODE}" in plan


def test_sess_columns_are_the_ones_the_registry_records(registry):
    notes = registry[SESS_SOURCE_ID]["notes"]
    match = re.search(r"header '([^']+)'", notes)
    assert match, "the registry no longer records the SESS header"
    recorded = [c.strip() for c in match.group(1).split(",")]
    assert tuple(recorded[: len(SESS_ID_COLUMNS)]) == SESS_ID_COLUMNS
    assert all(re.fullmatch(r"\d{4}|\.\.\.", c) for c in recorded[len(SESS_ID_COLUMNS) :])


def test_sess_missing_code_is_the_registry_rule(registry):
    assert "Treat 0.0 as missing" in registry[SESS_SOURCE_ID]["download_plan"]


# ---------------------------------------------------------------------------------------
# No silent gaps
# ---------------------------------------------------------------------------------------


def test_every_loaded_or_unloaded_id_is_a_registry_entry(registry):
    assert set(LOADERS) <= set(registry)
    assert set(UNLOADED) <= set(registry)
    assert not set(LOADERS) & set(UNLOADED)


def test_every_gap_is_documented_in_the_data_dictionary():
    text = (PROJECT_DIR / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    for source_id in (*LOADERS, *UNLOADED):
        assert f"`{source_id}`" in text, source_id


def test_every_unloaded_reason_is_non_empty():
    assert all(reason.strip() for reason in UNLOADED.values())


# ---------------------------------------------------------------------------------------
# USDA PSD cotton
# ---------------------------------------------------------------------------------------


def test_usda_loads_from_the_zip_and_keeps_published_columns(fixtures_dir, tmp_path):
    archive = tmp_path / "psd_cotton_csv.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(fixtures_dir / USDA_FIXTURE, arcname=USDA_PSD_MEMBER)
    frame = load_usda_psd_cotton(archive)
    assert list(frame.columns) == [*USDA_PSD_COLUMNS, *BASIS_COLUMNS]
    assert frame.attrs["source_id"] == USDA_PSD_SOURCE_ID


def test_usda_basis_columns(fixtures_dir):
    frame = load_usda_psd_cotton(fixtures_dir / USDA_FIXTURE)
    assert (frame["source_id"] == USDA_PSD_SOURCE_ID).all()
    assert (frame["unit"] == frame["Unit_Description"]).all()
    assert (frame["territorial_basis"] == TerritorialBasis.UNSTATED.value).all()
    assert (frame["currency_basis"] == CurrencyBasis.NOT_MONETARY.value).all()


def test_usda_keeps_only_the_recorded_commodity(fixtures_dir):
    frame = load_usda_psd_cotton(fixtures_dir / USDA_FIXTURE)
    assert (frame["Commodity_Code"] == USDA_PSD_COTTON_COMMODITY_CODE).all()


def test_usda_types_and_blank_value(fixtures_dir):
    frame = load_usda_psd_cotton(fixtures_dir / USDA_FIXTURE)
    assert str(frame["Market_Year"].dtype) == "Int64"
    assert str(frame["Value"].dtype) == "Float64"
    ussr = frame.loc[frame["Country_Code"] == "UR"]
    assert ussr["Value"].tolist() == [111.0, 222.0]
    assert frame["Value"].isna().sum() == 1


def test_usda_withholds_the_anchor_under_either_year(fixtures_dir):
    frame = load_usda_psd_cotton(fixtures_dir / USDA_FIXTURE)
    # One synthetic row has a held-out market year; another only a held-out calendar year.
    assert frame.attrs[N_WITHHELD_ATTR] == 2
    uz = frame.loc[frame["Country_Code"] == "UZ"]
    assert uz["Market_Year"].tolist() == [1990, 1991]


def test_usda_refuses_an_unrecorded_header(fixtures_dir, tmp_path):
    bad = tmp_path / "psd_cotton.csv"
    text = (fixtures_dir / USDA_FIXTURE).read_text(encoding="utf-8")
    bad.write_text(text.replace("Unit_Description", "Unit", 1), encoding="utf-8")
    with pytest.raises(SchemaError, match="recorded"):
        load_usda_psd_cotton(bad)


def test_usda_refuses_a_zip_without_the_recorded_member(fixtures_dir, tmp_path):
    archive = tmp_path / "psd_cotton_csv.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(fixtures_dir / USDA_FIXTURE, arcname="other.csv")
    with pytest.raises(SchemaError, match=USDA_PSD_MEMBER):
        load_usda_psd_cotton(archive)


def test_usda_refuses_a_monetary_unit(fixtures_dir, tmp_path):
    bad = tmp_path / "psd_cotton.csv"
    text = (fixtures_dir / USDA_FIXTURE).read_text(encoding="utf-8")
    bad.write_text(text.replace("synthetic unit,222", "Mil. rubles,222"), encoding="utf-8")
    with pytest.raises(SchemaError, match="monetary"):
        load_usda_psd_cotton(bad)


# ---------------------------------------------------------------------------------------
# Hokkaido SESS
# ---------------------------------------------------------------------------------------


def test_sess_long_form_and_basis_columns(fixtures_dir):
    frame = load_hokudai_sess(fixtures_dir / SESS_FIXTURE)
    assert list(frame.columns) == [
        *SESS_ID_COLUMNS,
        "year",
        "value_raw",
        "value",
        *BASIS_COLUMNS,
    ]
    assert (frame["source_id"] == SESS_SOURCE_ID).all()
    assert (frame["unit"] == frame["UNIT"]).all()
    assert (frame["territorial_basis"] == TerritorialBasis.UNSTATED.value).all()


def test_sess_currency_basis_is_blank_because_the_registry_does_not_record_it(fixtures_dir):
    frame = load_hokudai_sess(fixtures_dir / SESS_FIXTURE)
    monetary = frame.loc[frame["UNIT"] == "Mil. rubles"]
    assert len(monetary) > 0
    assert frame["currency_basis"].isna().all()


def test_sess_zero_is_missing_and_raw_cell_is_kept(fixtures_dir):
    frame = load_hokudai_sess(fixtures_dir / SESS_FIXTURE)
    row = frame.loc[(frame["CODE NUMBER"] == "S000000000001") & (frame["year"] == 1940)]
    assert row["value_raw"].tolist() == ["0.0"]
    assert row["value"].isna().all()
    blank = frame.loc[(frame["CODE NUMBER"] == "S000000000003") & (frame["year"] == 1940)]
    assert blank["value"].isna().all()
    kept = frame.loc[(frame["CODE NUMBER"] == "S000000000001") & (frame["year"] == 1941)]
    assert kept["value"].tolist() == [1.5]


def test_sess_withholds_a_series_named_for_the_anchor(fixtures_dir):
    frame = load_hokudai_sess(fixtures_dir / SESS_FIXTURE)
    assert frame.attrs[N_WITHHELD_ATTR] == 1
    anchor_like = frame.loc[frame["CODE NUMBER"] == "S000000000002"]
    assert 1980 not in anchor_like["year"].tolist()
    # The same series outside the window stays loaded.
    assert sorted(anchor_like["year"].tolist()) == [1940, 1941, 1989]


def test_sess_loads_a_directory_of_series_files(fixtures_dir, tmp_path):
    for name in ("S111.csv", "S112.csv"):
        shutil.copy(fixtures_dir / SESS_FIXTURE, tmp_path / name)
    (tmp_path / "SESS-d.html").write_text("not a series file", encoding="utf-8")
    frame = load_hokudai_sess(tmp_path)
    single = load_hokudai_sess(fixtures_dir / SESS_FIXTURE)
    assert len(frame) == 2 * len(single)
    assert frame.attrs[N_WITHHELD_ATTR] == 2


def test_sess_refuses_an_unrecorded_header(fixtures_dir, tmp_path):
    bad = tmp_path / "S1.csv"
    text = (fixtures_dir / SESS_FIXTURE).read_text(encoding="utf-8")
    bad.write_text(text.replace("FULL NAME", "NAME", 1), encoding="utf-8")
    with pytest.raises(SchemaError, match="registry records"):
        load_hokudai_sess(bad)


def test_sess_refuses_a_non_number(fixtures_dir, tmp_path):
    bad = tmp_path / "S1.csv"
    text = (fixtures_dir / SESS_FIXTURE).read_text(encoding="utf-8")
    bad.write_text(text.replace("3.5", "3.5x"), encoding="utf-8")
    with pytest.raises(SchemaError, match="not a number"):
        load_hokudai_sess(bad)


def test_loaded_frames_are_dataframes(fixtures_dir):
    assert isinstance(load_usda_psd_cotton(fixtures_dir / USDA_FIXTURE), pd.DataFrame)
    assert isinstance(load_hokudai_sess(fixtures_dir / SESS_FIXTURE), pd.DataFrame)

"""The panel schema, and above all the vintage column.

The tests that matter here are the ones that reject things: a panel that holds two values for
one province-year-series **without** distinguishing them by vintage is exactly the failure the
whole project is built to avoid, so it has to be a hard error rather than a warning.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from china.clean.schema import (
    NATIONAL,
    PANEL_COLUMNS,
    PANEL_KEY,
    SERIES,
    coerce_panel,
    concat_vintages,
    empty_panel,
    read_panel,
    validate_panel,
    vintage_of_yearbook_edition,
    write_panel,
)
from forensics_core.provenance.manifest import load_sources

#: Defined here rather than imported from conftest: under pytest's importlib import
#: mode (set in the workspace pyproject) a test module cannot import its own conftest.
SOURCES_YAML = Path(__file__).resolve().parents[1] / "data" / "SOURCES.yaml"


def _row(**overrides) -> dict:
    row = {
        "province": "Liaoning",
        "year": 2034,
        "series": "grp_nominal",
        "value": 111.1,
        "unit": SERIES["grp_nominal"].unit,
        "vintage": "csy2034",
        "source_id": "csy_2024_grp",
    }
    row.update(overrides)
    return row


def _panel(*rows: dict) -> pd.DataFrame:
    return coerce_panel(pd.DataFrame(list(rows), columns=list(PANEL_COLUMNS)))


def test_vintage_is_part_of_the_key():
    assert PANEL_KEY == ("province", "year", "series", "vintage")


def test_empty_panel_has_the_declared_columns_and_dtypes():
    frame = empty_panel()
    assert list(frame.columns) == list(PANEL_COLUMNS)
    assert frame.empty
    assert str(frame["year"].dtype) == "int64"
    assert str(frame["value"].dtype) == "float64"


def test_a_valid_panel_reports_no_problems():
    assert validate_panel(_panel(_row())) == []


def test_two_vintages_of_one_observation_are_legal_and_are_the_whole_point():
    frame = _panel(
        _row(vintage="csy2015", value=111.1),
        _row(vintage="csy2024", value=99.9),
    )
    assert validate_panel(frame) == []
    assert len(frame) == 2


def test_two_values_for_one_key_are_rejected():
    frame = _panel(_row(value=111.1), _row(value=222.2))
    problems = validate_panel(frame)
    assert any("duplicate the key" in p for p in problems)


def test_an_unknown_province_is_rejected_rather_than_dropped():
    problems = validate_panel(_panel(_row(province="Provinceland")))
    assert any("unknown province" in p for p in problems)


def test_the_national_row_is_allowed_and_is_not_one_of_the_provinces():
    frame = _panel(_row(province=NATIONAL, series="gdp_national_nominal"))
    assert validate_panel(frame) == []
    assert NATIONAL not in set(frame.loc[frame["province"] != NATIONAL, "province"])


def test_an_unknown_series_is_rejected():
    problems = validate_panel(_panel(_row(series="synthetic_series")))
    assert any("unknown series" in p for p in problems)


def test_a_series_carrying_the_wrong_unit_is_rejected():
    problems = validate_panel(_panel(_row(unit="synthetic unit")))
    assert any("must carry unit" in p for p in problems)


def test_a_missing_observation_may_not_be_a_nan_row():
    problems = validate_panel(_panel(_row(value=float("nan"))))
    assert any("non-finite" in p for p in problems)


def test_an_empty_vintage_is_rejected():
    problems = validate_panel(_panel(_row(vintage="")))
    assert any("empty vintage" in p for p in problems)


def test_a_year_outside_the_plausible_window_is_rejected():
    problems = validate_panel(_panel(_row(year=1234)))
    assert any("year outside" in p for p in problems)


def test_a_source_id_outside_the_registry_is_rejected_when_the_registry_is_supplied():
    known = {s.id for s in load_sources(SOURCES_YAML)}
    assert validate_panel(_panel(_row()), known_source_ids=known) == []
    problems = validate_panel(_panel(_row(source_id="synthetic_source")), known_source_ids=known)
    assert any("not in SOURCES.yaml" in p for p in problems)


def test_coerce_maps_edition_specific_province_spellings_onto_one_name():
    frame = _panel(
        _row(province="Tibet", vintage="csy2015"),
        _row(province="Xizang", vintage="csy2024"),
    )
    assert set(frame["province"]) == {"Xizang"}
    assert validate_panel(frame) == []


def test_coerce_rejects_a_frame_missing_a_column():
    incomplete = pd.DataFrame([{"province": "Liaoning", "year": 2034}])
    with pytest.raises(KeyError, match="missing columns"):
        coerce_panel(incomplete)


def test_concat_vintages_stacks_rather_than_merging():
    a = _panel(_row(vintage="csy2015", value=111.1))
    b = _panel(_row(vintage="csy2024", value=99.9))
    stacked = concat_vintages([a, b])
    assert len(stacked) == 2
    assert sorted(stacked["value"]) == [99.9, 111.1]
    assert concat_vintages([]).empty


def test_vintage_label_names_the_edition_not_the_data_year():
    assert vintage_of_yearbook_edition(2015) == "csy2015"
    with pytest.raises(ValueError, match="outside"):
        vintage_of_yearbook_edition(1800)


def test_every_series_declares_a_unit_and_its_registry_ids_exist():
    known = {s.id for s in load_sources(SOURCES_YAML)}
    for name, spec in SERIES.items():
        assert spec.name == name
        assert spec.unit.strip()
        assert spec.description.strip()
        unknown = [sid for sid in spec.source_ids if sid not in known]
        assert unknown == [], f"series {name} cites unregistered sources {unknown}"


def test_the_one_unconfirmed_unit_is_flagged_as_such():
    unconfirmed = {name for name, spec in SERIES.items() if not spec.unit_confirmed}
    assert unconfirmed == {"freight_ton_km"}


def test_write_refuses_an_invalid_panel_and_round_trips_a_valid_one(tmp_path):
    bad = _panel(_row(series="synthetic_series"))
    with pytest.raises(ValueError, match="refusing to write"):
        write_panel(bad, tmp_path / "bad.parquet")
    assert not (tmp_path / "bad.parquet").exists()

    good = _panel(_row(vintage="csy2015"), _row(vintage="csy2024", value=99.9))
    path = write_panel(good, tmp_path / "nested" / "panel.parquet")
    back = read_panel(path)
    assert list(back.columns) == list(PANEL_COLUMNS)
    assert sorted(back["value"]) == [99.9, 111.1]

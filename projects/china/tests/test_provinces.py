"""The province list: names that drift, rows that are not provinces, units that are not either.

Each of these is a real way to corrupt a provincial sum, and each is asserted against a
concrete value rather than against "does not crash". The second half tests the recorded
published-name table in ``data/provinces.yaml`` that ``china.clean.pbc_reports`` applies:
every canonical province resolves from the spellings this repository attests, the traps sit
in the file as data, and a name the table does not know raises rather than shrinking the
panel.
"""

from __future__ import annotations

import pandas as pd
import pytest
import yaml
from china.clean.pbc_reports import (
    PROVINCES_YAML,
    load_province_mapping,
    map_province_names,
)
from china.clean.provinces import (
    ATTESTED_REGION_CODES,
    BOUNDARY_CHANGES,
    PROVINCES,
    REBASING_YEARS,
    SUBPROVINCIAL_UNITS,
    canonical_province,
    is_non_province_row,
    is_province,
    normalize_label,
    subprovincial_unit,
)


def test_there_are_thirty_one_provincial_level_units_and_no_duplicates():
    assert len(PROVINCES) == 31
    assert len(set(PROVINCES)) == 31


def test_the_tibet_to_xizang_rename_is_handled_in_both_spellings():
    assert canonical_province("Tibet") == "Xizang"
    assert canonical_province("Xizang") == "Xizang"
    assert canonical_province("Tibet Autonomous Region") == "Xizang"


def test_a_footnote_marker_does_not_create_a_new_province():
    assert canonical_province("Xizang a") == "Xizang"
    assert canonical_province("Inner Mongolia a)") == "Inner Mongolia"


def test_the_two_shan_provinces_do_not_collide():
    assert canonical_province("Shanxi") == "Shanxi"
    assert canonical_province("Shaanxi") == "Shaanxi"
    assert canonical_province("Shannxi") == "Shaanxi"
    assert canonical_province("Shanxi") != canonical_province("Shaanxi")


def test_aggregate_and_residual_rows_are_not_provinces():
    for label in ("National Total", "Not Classified by Region", "Total"):
        assert is_non_province_row(label)
        assert not is_province(label)
        assert canonical_province(label) is None


def test_binhai_new_area_is_recognised_as_sub_provincial_and_never_a_province():
    unit = subprovincial_unit("Binhai New Area")
    assert unit is not None
    assert unit.parent == "Tianjin"
    assert "33.4" in unit.why
    assert not is_province("Binhai New Area")
    assert canonical_province("Binhai New Area") is None


def test_shenzhen_is_the_thirty_second_central_bank_summary_and_not_a_province():
    unit = subprovincial_unit("Shenzhen")
    assert unit is not None and unit.parent == "Guangdong"
    assert not is_province("Shenzhen")


def test_every_sub_provincial_unit_has_a_real_parent():
    for unit in SUBPROVINCIAL_UNITS:
        assert unit.parent in PROVINCES
        assert unit.why.strip()


def test_an_unrecognised_label_returns_none_rather_than_a_guess():
    assert canonical_province("Provinceland") is None
    assert canonical_province("") is None


def test_normalize_label_collapses_whitespace_and_punctuation():
    assert normalize_label("  Inner  Mongolia a) ") == "inner mongolia a"
    assert normalize_label("NOT CLASSIFIED BY REGION") == "not classified by region"
    assert normalize_label("") == ""


def test_boundary_changes_and_rebasings_are_the_ones_the_traps_document_names():
    created = {change.created: change for change in BOUNDARY_CHANGES}
    assert created["Chongqing"].year == 1997
    assert created["Chongqing"].from_parent == "Sichuan"
    assert created["Hainan"].year == 1988
    assert set(REBASING_YEARS) == {2004, 2008, 2013, 2018}


def test_only_the_region_codes_read_from_the_registry_are_hard_coded():
    assert ATTESTED_REGION_CODES == {
        "Beijing": "110000",
        "Tianjin": "120000",
        "Inner Mongolia": "150000",
        "Liaoning": "210000",
    }
    assert all(name in PROVINCES for name in ATTESTED_REGION_CODES)


# ------------------------------------------------------- the recorded name table


# A verbatim copy of the recorded table, written to tmp_path so each validation test can
# mutate one thing into a state the loader must refuse.
def _copy_of_recorded_table(tmp_path):
    document = yaml.safe_load(PROVINCES_YAML.read_text(encoding="utf-8"))
    path = tmp_path / "provinces.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


def test_the_recorded_table_resolves_all_thirty_one_canonical_english_names():
    mapping = load_province_mapping()
    for province in PROVINCES:
        assert mapping[province] == province


def test_the_recorded_table_resolves_the_variants_the_repository_attests():
    mapping = load_province_mapping()
    assert mapping["Tibet"] == "Xizang"
    assert mapping["Tibet Autonomous Region"] == "Xizang"
    assert mapping["Xizang Autonomous Region"] == "Xizang"
    assert mapping["Nei Mongol"] == "Inner Mongolia"
    assert mapping["Shannxi"] == "Shaanxi"
    assert mapping["Shanxi"] == "Shanxi", "a variant of one Shan province must not move the other"


def test_the_recorded_table_resolves_the_one_chinese_name_the_registry_attests():
    mapping = load_province_mapping()
    # The escaped string below is the name the registry quotes verbatim (registry id
    # nbs_dg_api_values, request body {"text":"...","code":"210000000000"}); escapes
    # keep this file ASCII, the way pbc_reports.py writes its own Chinese literals
    assert mapping["\u8fbd\u5b81\u7701"] == "Liaoning"


def test_the_table_carries_no_chinese_name_beyond_the_attested_one():
    mapping = load_province_mapping()
    chinese = sorted(k for k in mapping if any("\u4e00" <= ch <= "\u9fff" for ch in k))
    assert chinese == ["\u8fbd\u5b81\u7701"], (
        "a Chinese name enters the table only with its source; typing the other thirty from "
        "memory would put unverified strings at the join with the panel"
    )


def test_map_province_names_uses_the_recorded_table_when_no_mapping_is_passed():
    published = pd.Series(["Liaoning", "\u8fbd\u5b81\u7701", "Tibet"])
    assert list(map_province_names(published)) == ["Liaoning", "Liaoning", "Xizang"]


def test_a_published_name_outside_the_recorded_table_raises_and_names_it():
    published = pd.Series(["Liaoning", "PROVINCE-Z"])
    with pytest.raises(ValueError, match="PROVINCE-Z"):
        map_province_names(published)
    # against an explicitly supplied mapping the same series stays visible as <NA>: the
    # strict refusal is a property of the recorded table, which is complete
    mapped = map_province_names(published, {"Liaoning": "Liaoning"})
    assert mapped.iloc[0] == "Liaoning"
    assert pd.isna(mapped.iloc[1]), "an unmapped name stays visible rather than becoming a guess"


def test_matching_is_exact_and_not_fuzzy():
    published = pd.Series(["liaoning", "LIAONING", "Liaoning "])
    with pytest.raises(ValueError, match="not in the recorded province table"):
        map_province_names(published)


def test_the_sub_provincial_units_map_to_labels_that_say_they_are_not_provinces():
    mapping = load_province_mapping()
    for unit in SUBPROVINCIAL_UNITS:
        label = mapping[unit.name]
        assert unit.parent in label
        assert "not a province" in label
        assert label not in PROVINCES
    assert mapping["Shenzhen"] == "Shenzhen (sub-provincial unit of Guangdong, not a province)"


def test_the_boundary_changes_are_in_the_file_as_data_with_their_years():
    document = yaml.safe_load(PROVINCES_YAML.read_text(encoding="utf-8"))
    entries = {row["canonical"]: row for row in document["provinces"]}
    assert entries["Chongqing"]["separated"] == {"from": "Sichuan", "year": 1997}
    assert entries["Hainan"]["separated"] == {"from": "Guangdong", "year": 1988}
    created = {change.created: change for change in BOUNDARY_CHANGES}
    for name, row in entries.items():
        if "separated" in row:
            assert row["separated"]["year"] == created[name].year
            assert row["separated"]["from"] == created[name].from_parent


def test_the_loader_refuses_a_table_that_loses_a_canonical_province(tmp_path):
    path = _copy_of_recorded_table(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["provinces"] = [row for row in document["provinces"] if row["canonical"] != "Liaoning"]
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="Liaoning"):
        load_province_mapping(path)


def test_the_loader_refuses_a_canonical_name_the_code_does_not_carry(tmp_path):
    path = _copy_of_recorded_table(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["provinces"].append({"canonical": "Provinceland"})
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="Provinceland"):
        load_province_mapping(path)


def test_the_loader_refuses_a_boundary_year_that_disagrees_with_the_code(tmp_path):
    path = _copy_of_recorded_table(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for row in document["provinces"]:
        if row["canonical"] == "Chongqing":
            row["separated"]["year"] = 1998
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="boundary"):
        load_province_mapping(path)


def test_the_loader_refuses_one_spelling_mapped_to_two_targets(tmp_path):
    path = _copy_of_recorded_table(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for row in document["provinces"]:
        if row["canonical"] == "Shanxi":
            row.setdefault("english", []).append("Shaanxi")
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="two targets"):
        load_province_mapping(path)


def test_the_loader_refuses_a_not_province_entry_the_code_does_not_record(tmp_path):
    path = _copy_of_recorded_table(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["not_provinces"] = [
        row for row in document["not_provinces"] if row["name"] != "Shenzhen"
    ]
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="Shenzhen"):
        load_province_mapping(path)


def test_the_loader_refuses_a_missing_table(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_province_mapping(tmp_path / "absent.yaml")

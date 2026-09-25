"""Reading the Financial Statement Data Sets quarterly zips.

The zip is assembled in ``tmp_path`` from the synthetic tab-delimited fixtures, so the column
names under test are the documented ones and the values are impossible ones.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest
from aaer.clean import fsds


def test_documented_headers_are_what_the_loader_expects():
    """The four headers were read off the 2009q2 zip and confirmed by a second fetch."""
    assert fsds.NUM_COLUMNS == (
        "adsh",
        "tag",
        "version",
        "ddate",
        "qtrs",
        "uom",
        "segments",
        "coreg",
        "value",
        "footnote",
    )
    assert fsds.PRE_COLUMNS[:3] == ("adsh", "report", "line")
    assert fsds.TAG_COLUMNS[:3] == ("tag", "version", "custom")
    assert fsds.SUB_COLUMNS[0] == "adsh"
    assert len(fsds.SUB_COLUMNS) == 36
    assert set(fsds.EXPECTED_COLUMNS) == set(fsds.FSDS_TABLES)


def test_reads_all_four_tables_with_the_expected_shapes(fsds_zip: Path):
    quarter = fsds.read_fsds_zip(fsds_zip)
    assert quarter.quarter == "2020q4"
    assert quarter.header_mismatches == {}
    assert quarter.row_counts() == {"sub": 4, "num": 32, "pre": 2, "tag": 12}
    assert tuple(quarter.sub.columns) == fsds.SUB_COLUMNS
    assert tuple(quarter.num.columns) == fsds.NUM_COLUMNS


def test_value_is_numeric_and_identifiers_stay_text(fsds_zip: Path):
    quarter = fsds.read_fsds_zip(fsds_zip)
    assert quarter.num["value"].dtype.kind == "f"
    total_assets = quarter.num.loc[
        (quarter.num["adsh"] == "0009000001-21-000001")
        & (quarter.num["tag"] == "Assets")
        & (quarter.num["ddate"] == "20201231")
        & (quarter.num["version"] == "us-gaap/2020")
        & (quarter.num["segments"] == "")
        & (quarter.num["coreg"] == "")
        & (quarter.num["uom"] == "USD"),
        "value",
    ]
    assert list(total_assets) == [1000.0]
    # codes must not be coerced: a CIK or a ddate that became an int loses its leading zeros
    assert not pd.api.types.is_numeric_dtype(quarter.sub["cik"])
    assert not pd.api.types.is_numeric_dtype(quarter.num["ddate"])
    assert quarter.sub["cik"].iloc[0] == "9000001"
    assert quarter.num["ddate"].iloc[0] == "20191231"
    assert quarter.sub["adsh"].iloc[0] == "0009000001-20-000001"


def test_quarter_label_comes_from_the_file_name(tmp_path: Path, make_fsds_zip):
    path = make_fsds_zip(tmp_path / "2013q1.zip")
    assert fsds.read_fsds_zip(path).quarter == "2013q1"
    assert fsds.quarter_from_path("/somewhere/FSDS/2011Q3.zip") == "2011q3"


def test_a_headers_only_quarter_is_empty_not_broken(tmp_path: Path):
    """The 2009q1 placeholder must parse to zero rows rather than raise."""
    empty = tmp_path / "2009q1.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        for member, columns in fsds.EXPECTED_COLUMNS.items():
            zf.writestr(member, "\t".join(columns) + "\n")
    quarter = fsds.read_fsds_zip(empty)
    assert quarter.is_empty
    assert quarter.row_counts() == {"sub": 0, "num": 0, "pre": 0, "tag": 0}
    assert quarter.header_mismatches == {}


def test_full_quarter_is_not_reported_as_empty(fsds_zip: Path):
    assert not fsds.read_fsds_zip(fsds_zip).is_empty


def test_a_changed_header_is_warned_about_and_recorded_not_raised(
    tmp_path: Path, fixtures_dir: Path
):
    """The SEC regenerated these files once already; a schema drift must be visible."""
    altered = (fixtures_dir / "synthetic_fsds_num.txt").read_text(encoding="utf-8")
    altered = altered.replace("footnote", "footnotes", 1).replace("coreg", "co_reg", 1)
    path = tmp_path / "2020q4.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("num.txt", altered)
        for member in ("sub.txt", "pre.txt", "tag.txt"):
            fixture = f"synthetic_fsds_{member.split('.')[0]}.txt"
            zf.writestr(member, (fixtures_dir / fixture).read_text(encoding="utf-8"))

    with pytest.warns(UserWarning, match="header differs"):
        quarter = fsds.read_fsds_zip(path)
    unexpected, missing = quarter.header_mismatches["num.txt"]
    assert set(unexpected) == {"footnotes", "co_reg"}
    assert set(missing) == {"footnote", "coreg"}


def test_an_absent_member_is_warned_about_and_yields_an_empty_typed_frame(
    tmp_path: Path, fixtures_dir: Path
):
    path = tmp_path / "2020q4.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "sub.txt", (fixtures_dir / "synthetic_fsds_sub.txt").read_text(encoding="utf-8")
        )
    with pytest.warns(UserWarning, match="is absent"):
        quarter = fsds.read_fsds_zip(path)
    assert len(quarter.sub) == 4
    assert len(quarter.num) == 0
    assert tuple(quarter.num.columns) == fsds.NUM_COLUMNS


def test_selecting_fewer_tables_still_returns_typed_frames(fsds_zip: Path):
    quarter = fsds.read_fsds_zip(fsds_zip, tables=("sub.txt",))
    assert len(quarter.sub) == 4
    assert len(quarter.num) == 0
    assert tuple(quarter.pre.columns) == fsds.PRE_COLUMNS


def test_a_non_zip_raises_rather_than_being_swallowed(tmp_path: Path):
    """An error page saved under a .zip name must not be mistaken for an empty quarter."""
    bad = tmp_path / "2020q4.zip"
    bad.write_bytes(b"<html>403 Forbidden</html>")
    with pytest.raises(zipfile.BadZipFile):
        fsds.read_fsds_zip(bad)


def test_read_quarters_concatenates_and_tags_provenance(tmp_path: Path, make_fsds_zip):
    first = make_fsds_zip(tmp_path / "2020q3.zip")
    second = make_fsds_zip(tmp_path / "2020q4.zip")
    combined = fsds.read_quarters([first, second])
    assert combined.quarter == "2020q3..2020q4"
    assert len(combined.sub) == 8
    assert set(combined.sub["quarter"]) == {"2020q3", "2020q4"}
    # the tag dictionary repeats in every quarter and must not be duplicated
    assert len(combined.tag) == 12


def test_read_quarters_on_nothing_returns_empty_typed_frames():
    combined = fsds.read_quarters([])
    assert combined.quarter == ""
    assert tuple(combined.num.columns) == fsds.NUM_COLUMNS
    assert len(combined.sub) == 0


def test_iter_fsds_zips_yields_in_quarter_order(tmp_path: Path, make_fsds_zip):
    for label in ("2020q4", "2019q1", "2020q1"):
        make_fsds_zip(tmp_path / f"{label}.zip")
    assert [q.quarter for q in fsds.iter_fsds_zips(tmp_path)] == ["2019q1", "2020q1", "2020q4"]

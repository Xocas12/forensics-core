"""The yearbook contents-frame parser and the URL builders.

The contents frame is the only part of the yearbook that is machine-readable, and locating a
table by its printed title rather than by a guessed file name is what makes a cross-vintage
panel possible at all. These tests pin both file-naming conventions, the gb18030 decoding and
the refusal to parse a page that is not a contents frame.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from china.acquire.yearbook import (
    EDITION_YEARS,
    edition_index_url,
    edition_toc_url,
    table_url,
)
from china.clean.yearbook import (
    extract_table_image,
    find_tables,
    grp_image_to_panel,
    parse_toc,
    table_number_from_filename,
)

#: Defined here rather than imported from conftest: under pytest's importlib import
#: mode (set in the workspace pyproject) a test module cannot import its own conftest.
FIXTURES = Path(__file__).resolve().parent / "fixtures"


TOC_BYTES = (FIXTURES / "synthetic_csy_toc_en.htm").read_bytes()

#: One CJK character, present in the fixture so the gb18030 decoding path is exercised.
CJK_MIDDLE = "\u4e2d"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("html/E03-09.jpg", "3-9"),
        ("E03-09.jpg", "3-9"),
        ("EN0309.jpg", "3-9"),
        ("E0309.jpg", "3-9"),
        ("C03-09.jpg", "3-9"),
        ("EN1614.jpg", "16-14"),
        ("E16-14.jpg", "16-14"),
        ("E09-14.jpg", "9-14"),
        ("zbe23.pdf", None),
        ("left_.htm", None),
        ("", None),
    ],
)
def test_table_number_survives_both_naming_conventions(filename, expected):
    assert table_number_from_filename(filename) == expected


def test_toc_parses_to_one_row_per_link():
    toc = parse_toc(TOC_BYTES)
    assert len(toc) == 7
    assert list(toc.columns)[:3] == ["href", "filename", "kind"]


def test_toc_recovers_table_number_data_year_and_kind():
    toc = parse_toc(TOC_BYTES).set_index("filename")
    grp = toc.loc["E03-09.jpg"]
    assert grp["table_number"] == "3-9"
    assert grp["file_table_number"] == "3-9"
    assert grp["data_year"] == 2034
    assert grp["kind"] == "jpg"

    electricity = toc.loc["EN0914.jpg"]
    assert electricity["file_table_number"] == "9-14"
    assert electricity["table_number"] == "9-14"
    assert pd.isna(electricity["data_year"]), "a title with no year in brackets gets no year"


def test_toc_counts_formats_which_is_how_the_image_only_finding_was_made():
    toc = parse_toc(TOC_BYTES)
    counts = toc["kind"].value_counts().to_dict()
    assert counts["jpg"] == 4
    assert counts["htm"] == 2
    assert counts["pdf"] == 1
    assert "xls" not in counts and "xlsx" not in counts


def test_appendix_file_has_no_table_number_rather_than_a_wrong_one():
    toc = parse_toc(TOC_BYTES).set_index("filename")
    assert pd.isna(toc.loc["zbe99.pdf", "file_table_number"])
    assert pd.isna(toc.loc["zbe99.pdf", "table_number"])
    assert toc.loc["zbe99.pdf", "kind"] == "pdf"


def test_toc_is_decoded_as_gb18030_not_utf8():
    toc = parse_toc(TOC_BYTES)
    titles = " ".join(toc["title"].tolist())
    assert CJK_MIDDLE in titles
    assert "\ufffd" not in titles


def test_toc_rejects_a_page_that_is_not_a_contents_frame():
    with pytest.raises(ValueError, match="not a yearbook contents frame"):
        parse_toc(b"<html><body>403 Forbidden</body></html>")


def test_find_tables_matches_titles_case_insensitively():
    toc = parse_toc(TOC_BYTES)
    assert len(find_tables(toc, "gross regional product")) == 1
    assert len(find_tables(toc, "Freight")) == 2
    assert len(find_tables(toc, "Bank Credit by Region")) == 0


def test_find_tables_refuses_an_empty_phrase():
    toc = parse_toc(TOC_BYTES)
    with pytest.raises(ValueError, match="non-empty phrase"):
        find_tables(toc, "   ")


def test_url_builders_follow_the_edition_layout():
    assert edition_index_url(2024) == "https://www.stats.gov.cn/sj/ndsj/2024/indexeh.htm"
    assert edition_index_url(2024, "zh") == "https://www.stats.gov.cn/sj/ndsj/2024/indexch.htm"
    assert edition_toc_url(2024) == "https://www.stats.gov.cn/sj/ndsj/2024/left_.htm"
    assert edition_toc_url(2015, "zh") == "https://www.stats.gov.cn/sj/ndsj/2015/left.htm"
    assert table_url(2015, "html/EN0309.jpg") == (
        "https://www.stats.gov.cn/sj/ndsj/2015/html/EN0309.jpg"
    )


def test_url_builders_reject_an_unknown_language():
    with pytest.raises(ValueError, match="language must be"):
        edition_toc_url(2024, "fr")


def test_edition_years_cover_what_the_index_page_lists():
    assert EDITION_YEARS[0] == 2005
    assert EDITION_YEARS[-1] == 2025
    assert len(EDITION_YEARS) == 21


def test_image_extraction_is_a_stub_and_says_what_remains():
    with pytest.raises(NotImplementedError, match="optical-character-recognition"):
        extract_table_image(
            FIXTURES / "synthetic_csy_toc_en.htm", edition_year=2024, table_number="3-9"
        )
    with pytest.raises(NotImplementedError, match="column-layout map"):
        grp_image_to_panel(None, edition_year=2024, source_id="csy_2024_grp")

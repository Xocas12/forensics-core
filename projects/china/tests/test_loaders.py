"""The loaders for the sources that really are machine-readable.

World Bank observations, catalogue responses, central-bank report pages and loan-balance
prose, Figshare metadata and Wayback capture indexes. Every expected value below is
hand-computed from the synthetic fixture, and the unit conversions are the ones the project
depends on: yuan to 100 million yuan, and trillions to 100 million yuan.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from china.acquire.fallback import WORLD_BANK_INDICATORS, worldbank_url
from china.acquire.nightlights import (
    EXPECTED_FILE_COUNT,
    EXPECTED_TOTAL_BYTES,
    figshare_download_url,
    parse_figshare_article,
)
from china.acquire.pbc import find_report_pdfs, find_report_years
from china.acquire.wayback import capture_items, capture_url, cdx_url, parse_cdx_json
from china.clean.nbs_api import CATEGORY_CODES, parse_envelope, parse_index_tree, parse_indicators
from china.clean.pbc_reports import map_province_names, parse_loan_balances, parse_summary_links
from china.clean.schema import NATIONAL, PANEL_COLUMNS, validate_panel
from china.clean.worldbank import (
    YUAN_PER_HUNDRED_MILLION,
    parse_indicator_response,
    to_panel,
    vintage_from_last_updated,
)

#: Defined here rather than imported from conftest: under pytest's importlib import
#: mode (set in the workspace pyproject) a test module cannot import its own conftest.
FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ------------------------------------------------------------------------------ World Bank
def test_worldbank_response_parses_and_drops_null_observations():
    frame = parse_indicator_response((FIXTURES / "synthetic_worldbank_gdp.json").read_bytes())
    assert len(frame) == 2, "the null 2032 observation must be an absent row, not a NaN row"
    assert list(frame["year"]) == [2033, 2034], "observations must come back sorted by year"
    assert frame["last_updated"].iloc[0] == "2034-01-31"


def test_worldbank_panel_converts_yuan_to_hundred_million_yuan():
    frame = parse_indicator_response((FIXTURES / "synthetic_worldbank_gdp.json").read_bytes())
    panel = to_panel(frame)
    assert list(panel.columns) == list(PANEL_COLUMNS)
    values = dict(zip(panel["year"], panel["value"], strict=True))
    assert values[2034] == 100000000000000 / YUAN_PER_HUNDRED_MILLION == 1_000_000.0
    assert values[2033] == 500_000.0
    assert set(panel["province"]) == {NATIONAL}
    assert set(panel["series"]) == {"gdp_national_nominal"}
    assert set(panel["vintage"]) == {"wb2034-01-31"}
    assert validate_panel(panel) == []


def test_worldbank_refuses_an_indicator_with_no_declared_series():
    frame = parse_indicator_response((FIXTURES / "synthetic_worldbank_gdp.json").read_bytes())
    frame["indicator"] = "NY.GDP.MKTP.KN"
    with pytest.raises(ValueError, match="no panel series defined"):
        to_panel(frame)


def test_worldbank_rejects_a_body_that_is_not_the_two_element_array():
    with pytest.raises(ValueError, match="two-element"):
        parse_indicator_response(b'{"message": "synthetic error"}')


def test_vintage_label_is_never_silently_empty():
    assert vintage_from_last_updated("2034-01-31") == "wb2034-01-31"
    assert vintage_from_last_updated("") == "wb-unknown"


def test_worldbank_url_only_builds_indicators_that_were_written_down():
    assert worldbank_url("NY.GDP.MKTP.CN").endswith("date=1990:2024")
    assert "NY.GDP.MKTP.CN" in worldbank_url("NY.GDP.MKTP.CN")
    assert len(WORLD_BANK_INDICATORS) == 3
    with pytest.raises(KeyError, match="not in WORLD_BANK_INDICATORS"):
        worldbank_url("NY.GDP.SYNTHETIC")


# ------------------------------------------------------------------ bureau catalogue API
def test_catalogue_tree_parses_and_prefers_the_leaf_cid():
    frame = parse_index_tree((FIXTURES / "synthetic_nbs_tree.json").read_bytes())
    assert len(frame) == 2
    leaf = frame.loc[frame["is_leaf"]].iloc[0]
    assert leaf["node_id"] == "SYNTHETIC-CID-1", "a leaf is addressed by its cid, not its _id"
    assert leaf["start_year"] == 1999
    assert leaf["end_year"] == 2034
    branch = frame.loc[~frame["is_leaf"].astype(bool)].iloc[0]
    assert branch["node_id"] == "SYNTHETIC-NODE-1"
    assert pd.isna(branch["start_year"])


def test_a_failure_envelope_is_not_mistaken_for_an_empty_catalogue():
    with pytest.raises(ValueError, match="reported failure"):
        parse_envelope((FIXTURES / "synthetic_nbs_tree_failure.json").read_bytes())


def test_a_non_json_body_is_rejected():
    with pytest.raises(ValueError, match="not JSON"):
        parse_envelope(b"<html><title>403 Forbidden</title></html>")


def test_indicator_scope_note_is_carried_through():
    frame = parse_indicators((FIXTURES / "synthetic_nbs_indicators.json").read_bytes())
    assert len(frame) == 1
    assert frame["scope_note"].iloc[0] == "SYNTHETIC scope note"
    assert frame["decimals"].iloc[0] == 2


def test_category_codes_name_the_two_the_project_uses():
    assert CATEGORY_CODES[6] == "provincial annual"
    assert CATEGORY_CODES[3] == "national annual"


# ------------------------------------------------------------------ central bank reports
def test_report_index_yields_one_page_per_year_and_ignores_other_channels():
    years = find_report_years((FIXTURES / "synthetic_pbc_report_index.html").read_bytes())
    assert set(years) == {2033, 2034}
    assert years[2034].startswith("https://www.pbc.gov.cn/zhengcehuobisi/")
    assert "9999991" in years[2034]


def test_report_index_with_no_links_is_an_error_not_an_empty_result():
    with pytest.raises(ValueError, match="no links"):
        find_report_years(b"<html><body>synthetic error page</body></html>")


def test_year_page_yields_the_main_report_and_the_summaries():
    pdfs = find_report_pdfs((FIXTURES / "synthetic_pbc_year_page.html").read_bytes())
    assert len(pdfs) == 3, "the non-PDF link must not be picked up"
    assert all(url.startswith("https://www.pbc.gov.cn/") for url, _text in pdfs)


def test_summary_links_expose_the_published_province_name_and_the_summary_flag():
    frame = parse_summary_links((FIXTURES / "synthetic_pbc_year_page.html").read_bytes())
    assert len(frame) == 3
    assert list(frame["ordinal"]) == [1, 2, 3]
    assert list(frame["province_zh"]) == ["SYNTHETIC-NATIONAL", "PROVINCE-A", "PROVINCE-B"]
    assert list(frame["is_summary"]) == [False, True, True]


def test_province_name_mapping_refuses_to_guess():
    frame = parse_summary_links((FIXTURES / "synthetic_pbc_year_page.html").read_bytes())
    with pytest.raises(ValueError, match="Chinese-to-canonical mapping"):
        map_province_names(frame["province_zh"], {})
    mapped = map_province_names(frame["province_zh"], {"PROVINCE-A": "Liaoning"})
    assert mapped.iloc[1] == "Liaoning"
    assert pd.isna(mapped.iloc[2]), "an unmapped name stays visible rather than becoming a guess"


def test_loan_balance_prose_converts_trillions_and_hundred_millions():
    text = (FIXTURES / "synthetic_pbc_summary_text.txt").read_text(encoding="utf-8")
    frame = parse_loan_balances(text)
    assert len(frame) == 2
    first, second = frame.iloc[0], frame.iloc[1]
    assert first["year"] == 2034
    assert first["value_100m_yuan"] == 9.9 * 10_000 == 99_000.0
    assert first["yoy_growth_pct"] == 2.2
    assert second["year"] == 2033
    assert second["value_100m_yuan"] == 888.8
    assert second["yoy_growth_pct"] == -1.5


def test_text_with_no_balance_sentence_gives_an_empty_frame():
    assert parse_loan_balances("SYNTHETIC main report with no balance sentence").empty


# ------------------------------------------------------------------------- nightlights
def test_figshare_metadata_lists_files_and_carries_the_citation():
    frame = parse_figshare_article((FIXTURES / "synthetic_figshare_article.json").read_bytes())
    assert len(frame) == 2
    assert int(frame["size"].sum()) == 3000
    assert frame["download_url"].iloc[0] == "https://ndownloader.figshare.com/files/111"
    assert frame.attrs["doi"] == "10.0000/synthetic.0000000"
    assert "CC BY" in frame.attrs["license"]


def test_figshare_rejects_a_body_without_a_files_list():
    with pytest.raises(ValueError, match="no 'files' list"):
        parse_figshare_article(b'{"message": "synthetic not found"}')


def test_the_registry_recorded_dataset_size_is_pinned_so_a_new_version_is_noticed():
    assert EXPECTED_FILE_COUNT == 34
    assert EXPECTED_TOTAL_BYTES == 1_091_935_532
    assert figshare_download_url(17626034).endswith("/files/17626034")


# ----------------------------------------------------------------------------- Wayback
def test_capture_index_parses_with_its_own_header_row():
    frame = parse_cdx_json((FIXTURES / "synthetic_cdx.json").read_bytes())
    assert len(frame) == 2
    assert list(frame.columns)[:3] == ["urlkey", "timestamp", "original"]
    assert int(frame["length"].sum()) == 3333


def test_an_empty_capture_index_is_a_real_answer():
    frame = parse_cdx_json((FIXTURES / "synthetic_cdx_empty.json").read_bytes())
    assert frame.empty
    assert parse_cdx_json(b"").empty


def test_capture_index_rejects_a_non_json_body():
    with pytest.raises(ValueError, match="not JSON"):
        parse_cdx_json(b"<html>429 Too Many Requests</html>")


def test_capture_urls_request_the_original_bytes():
    url = capture_url("20340101000000", "http://www.stats.gov.cn/tjsj/ndsj/9999.rar")
    assert "id_/" in url, "without the id_ suffix the archive rewrites the bytes"
    assert url.startswith("https://web.archive.org/web/20340101000000id_/")


def test_capture_items_keep_the_timestamp_so_two_vintages_cannot_collide():
    frame = parse_cdx_json((FIXTURES / "synthetic_cdx.json").read_bytes())
    items = capture_items(frame)
    dests = [dest for _url, dest in items]
    assert dests == ["wayback/20340101000000/9999.rar", "wayback/20330101000000/CH9999.jpg"]
    assert len(set(dests)) == len(dests)


def test_capture_items_reject_a_frame_without_the_needed_columns():
    with pytest.raises(KeyError, match="timestamp"):
        capture_items(pd.DataFrame({"original": ["http://synthetic.example/x"]}))


def test_cdx_url_uses_the_documented_query_string():
    url = cdx_url("stats.gov.cn/tjsj/ndsj/2015/html/*", limit=2000)
    assert "output=json" in url
    assert "filter=statuscode:200" in url
    assert "collapse=urlkey" in url
    assert url.endswith("limit=2000")

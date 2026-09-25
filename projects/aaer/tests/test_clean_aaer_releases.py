"""Parsing the AAER listing. Every value asserted here comes from the synthetic fixture.

The fixture is not a copy of an SEC page and its numbers are deliberately impossible (AAER
numbers in the 9000s, six-digit release numbers, respondents named SYNTHETIC). It encodes the
page structure the registry describes and one defect per row, so the parser's loss accounting
is checked rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from aaer.clean import aaer_releases as ar


def test_total_items_reads_the_pager(listing_html):
    assert ar.total_items(listing_html) == 9


def test_total_items_handles_thousands_separators_and_absence():
    assert ar.total_items("<p>1 to 100 of 3,342 items</p>") == 3342
    assert ar.total_items("<p>no pager here</p>") is None


def test_parse_counts_every_row_and_says_why_one_was_dropped(listing_html):
    parsed = ar.parse_listing_page(listing_html, source_file="page_000.html")
    assert parsed.n_rows_seen == 5, "the <th> header row must not be counted"
    assert parsed.n_releases == 4
    assert parsed.n_dropped == 1
    assert parsed.drop_reasons == {"no_aaer_number_and_no_pdf_link": 1}
    # kept-but-incomplete rows are held, not dropped, and each is counted once
    assert parsed.n_missing_aaer_number == 1
    assert parsed.n_missing_date == 1
    assert parsed.n_missing_pdf == 1


def test_aaer_numbers_and_respondents(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    numbers = sorted(int(n) for n in frame["aaer_number"].dropna())
    assert numbers == [9001, 9002, 9004]

    alpha = frame.loc[frame["aaer_number"] == 9001].iloc[0]
    assert alpha["respondent"] == "SYNTHETIC ALPHA CORP"
    beta = frame.loc[frame["aaer_number"] == 9002].iloc[0]
    assert beta["respondent"] == "SYNTHETIC BETA LLC and SYNTHETIC GAMMA CPA"


def test_relative_pdf_hrefs_are_absolutised(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    alpha = frame.loc[frame["aaer_number"] == 9001].iloc[0]
    assert alpha["pdf_url"] == "https://www.sec.gov/files/litigation/admin/2020/34-900001.pdf"
    beta = frame.loc[frame["aaer_number"] == 9002].iloc[0]
    assert beta["pdf_url"] == "https://www.sec.gov/files/litigation/opinions/2020/33-900002.pdf"


def test_release_numbers_exclude_the_aaer_number_and_are_deduplicated(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    alpha = frame.loc[frame["aaer_number"] == 9001].iloc[0]
    # "34-900001" appears twice in the row (as a release number and inside the file name)
    assert alpha["release_numbers"] == "34-900001"
    beta = frame.loc[frame["aaer_number"] == 9002].iloc[0]
    assert beta["release_numbers"] == "33-900002;34-900003"
    assert "AAER" not in beta["release_numbers"]


def test_two_date_formats_parse_and_an_unparsable_one_becomes_nat(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    alpha = frame.loc[frame["aaer_number"] == 9001].iloc[0]
    assert alpha["date"] == pd.Timestamp("2020-01-02")
    beta = frame.loc[frame["aaer_number"] == 9002].iloc[0]
    assert beta["date"] == pd.Timestamp("2020-02-03")
    epsilon = frame.loc[frame["aaer_number"] == 9004].iloc[0]
    assert pd.isna(epsilon["date"])


def test_row_without_an_aaer_number_is_kept_with_its_pdf(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    orphan = frame[frame["aaer_number"].isna()]
    assert len(orphan) == 1
    assert orphan.iloc[0]["respondent"] == "SYNTHETIC DELTA HOLDINGS"
    assert orphan.iloc[0]["pdf_url"].endswith("34-900004.pdf")


def test_source_file_is_recorded_on_every_row(listing_html):
    frame = ar.parse_listing_page(listing_html, source_file="page_007.html").releases
    assert set(frame["source_file"]) == {"page_007.html"}


def test_columns_and_dtypes_are_fixed(listing_html):
    frame = ar.parse_listing_page(listing_html).releases
    assert tuple(frame.columns) == ar.RELEASE_COLUMNS
    assert str(frame["aaer_number"].dtype) == "Int64"
    assert str(frame["date"].dtype).startswith("datetime64")


def test_markup_the_parser_does_not_understand_yields_zero_rows_not_wrong_rows():
    """A page whose structure changed must be visibly empty, never quietly mis-parsed."""
    parsed = ar.parse_listing_page("<html><body><p>AAER-9001</p></body></html>")
    assert parsed.n_releases == 0
    assert parsed.n_rows_seen == 0


def test_pages_are_concatenated_and_deduplicated_on_aaer_number(tmp_path: Path, listing_html):
    first = tmp_path / "page_000.html"
    second = tmp_path / "page_001.html"
    first.write_text(listing_html, encoding="utf-8")
    second.write_text(listing_html, encoding="utf-8")

    parsed = ar.parse_listing_pages([second, first])
    assert parsed.n_rows_seen == 10
    assert parsed.n_dropped == 2
    numbers = parsed.releases["aaer_number"].dropna()
    assert sorted(int(n) for n in numbers) == [9001, 9002, 9004], "duplicates must collapse"
    # the unlabelled row cannot be deduplicated on a number it does not have, so it survives twice
    assert int(parsed.releases["aaer_number"].isna().sum()) == 2
    assert parsed.total_items == 9


def test_load_listing_reads_only_page_files(tmp_path: Path, listing_html):
    (tmp_path / "page_000.html").write_text(listing_html, encoding="utf-8")
    (tmp_path / "notes.html").write_text(listing_html, encoding="utf-8")
    assert ar.load_listing(tmp_path).n_rows_seen == 5


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2020-01-02", "2020-01-02"),
        ("February 3, 2020", "2020-02-03"),
        ("Feb. 3, 2020", "2020-02-03"),
        ("02/03/2020", "2020-02-03"),
    ],
)
def test_parse_date_accepts_the_documented_formats(text, expected):
    assert ar.parse_date(text) == pd.Timestamp(expected)


def test_parse_date_returns_none_rather_than_guessing():
    assert ar.parse_date("sometime in 2020") is None
    assert ar.parse_date("") is None


def test_summary_mentions_the_drop_count(listing_html):
    parsed = ar.parse_listing_page(listing_html)
    assert "4 releases from 5 table rows" in parsed.summary()

"""The acquisition wiring: what has an acquirer, what must not, and the parsing helpers.

None of these tests makes a network request. They assert three kinds of property: that the
registry and the code agree about which sources a machine can fetch, that the pure parsers
handle the specific malformed inputs the registry warns about, and that a duplicate
registration is refused.
"""

from __future__ import annotations

import pytest
from forensics_core.provenance.manifest import load_sources
from forensics_core.provenance.runner import ATTEMPTABLE_STATUS, NEEDS_HUMAN, plan

# Importing every source module is what populates ACQUIRERS.
from gosplan.acquire import (  # noqa: F401
    agriculture,
    annuals,
    cia_mirror,
    compendia,
    western_estimates,
)
from gosplan.acquire._common import encode_path, hrefs, ia_download_url, ia_num_found, ia_select
from gosplan.acquire.annuals import safe_name, volume_asset_urls
from gosplan.acquire.registry import ACQUIRERS, AcquireResult, register


def test_every_acquirer_has_a_registry_entry(sources_yaml):
    known = {s.id for s in load_sources(sources_yaml)}
    unknown = sorted(set(ACQUIRERS) - known)
    assert unknown == [], f"acquirers registered for ids absent from SOURCES.yaml: {unknown}"


def test_blocked_sources_have_no_acquirer(sources_yaml):
    blocked = {s.id for s in load_sources(sources_yaml) if s.status == "blocked"}
    assert blocked, "the registry should record at least one blocked source"
    assert sorted(blocked & set(ACQUIRERS)) == []


def test_human_gated_sources_have_no_acquirer(sources_yaml):
    gated = {s.id for s in load_sources(sources_yaml) if s.access in NEEDS_HUMAN}
    assert gated, "the registry should record at least one human-gated source"
    assert sorted(gated & set(ACQUIRERS)) == []


def test_unverified_sources_have_no_acquirer(sources_yaml):
    """A source nobody confirmed exists has nothing to fetch, so it gets no code."""
    unverified = {s.id for s in load_sources(sources_yaml) if s.status == "unverified"}
    assert unverified
    assert sorted(unverified & set(ACQUIRERS)) == []


def test_cia_is_acquired_from_the_mirror_not_from_cia_gov(sources_yaml):
    """The reading room blocks scripts; the archive.org mirror is the route of record."""
    sources = {s.id: s for s in load_sources(sources_yaml)}
    cia_direct = [i for i in sources if i.startswith("cia_") and sources[i].status == "blocked"]
    assert cia_direct, "the registry should record the cia.gov block"
    for source_id in cia_direct:
        assert source_id not in ACQUIRERS
    assert "ia_ciareadingroom_mirror" in ACQUIRERS


def test_plan_attempts_exactly_the_reachable_registered_sources(sources_yaml):
    sources = load_sources(sources_yaml)
    attempt, skipped = plan(sources, ACQUIRERS, None)
    attempted = {s.id for s in attempt}
    expected = {
        s.id
        for s in sources
        if s.id in ACQUIRERS and s.status in ATTEMPTABLE_STATUS and s.access not in NEEDS_HUMAN
    }
    assert attempted == expected
    assert len(attempt) + len(skipped) == len(sources)


def test_duplicate_registration_is_refused():
    marker = "ia_narkhoz_collection"
    assert marker in ACQUIRERS
    with pytest.raises(ValueError, match="duplicate acquirer"):
        register(marker)(lambda source, data_dir: None)


def test_acquire_result_reports_failure_without_raising():
    bad = AcquireResult("some_id", False, "HTTP 403: forbidden")
    assert bad.ok is False
    assert "some_id" in str(bad)
    assert str(bad).startswith("[FAIL]")


# --------------------------------------------------------------------------- parsers


UPPERCASE_INDEX = """
<HTML><BODY>
<A HREF="Narodnoe_hozyaystvo_SSSR_v_1960_g.%281961%29.%5Bdjv%5D.zip">1960</A>
<A HREF='other.ZIP'>1990</A>
<a href="notes.txt">notes</a>
<A HREF="#top">top</A>
</BODY></HTML>
"""


def test_hrefs_matches_uppercase_tags_and_filters_by_pattern():
    """The publ.lib.ru index is uppercase windows-1251 HTML; lowercase matching misses it."""
    found = hrefs(UPPERCASE_INDEX, base="http://publ.lib.ru/dir/index.html", pattern=r"\.zip$")
    assert found == [
        "http://publ.lib.ru/dir/Narodnoe_hozyaystvo_SSSR_v_1960_g.%281961%29.%5Bdjv%5D.zip",
        "http://publ.lib.ru/dir/other.ZIP",
    ]


def test_hrefs_drops_fragments_and_deduplicates():
    doc = '<a href="a.csv">1</a><a href="a.csv">2</a><a href="#x">3</a>'
    assert hrefs(doc, pattern=r"\.csv$") == ["a.csv"]


def test_encode_path_leaves_an_encoded_path_alone_and_encodes_a_raw_one():
    already = "http://h/d/Name_%281961%29.%5Bdjv%5D.zip"
    assert encode_path(already) == already
    assert encode_path("http://h/d/a b.zip") == "http://h/d/a%20b.zip"


IA_METADATA = {
    "files": [
        {"name": "vol_hocr.html", "format": "hOCR", "size": "33000000"},
        {"name": "vol.pdf", "format": "Text PDF", "size": "31000000"},
        {"name": "vol_encrypted.pdf", "format": "Text PDF", "size": "31000000"},
        {"name": "vol_djvu.txt", "format": "DjVuTXT", "size": "1500000"},
        {"name": "vol_page_numbers.json", "format": "Page Numbers JSON", "size": "110000"},
        {"name": "vol_meta.xml", "format": "Metadata", "size": "1000"},
    ]
}


def test_ia_select_picks_by_declared_format():
    names = [f["name"] for f in ia_select(IA_METADATA, formats=("hocr",))]
    assert names == ["vol_hocr.html"]


def test_ia_select_falls_back_to_suffix_without_double_counting():
    chosen = ia_select(IA_METADATA, formats=("hocr",), suffixes=("_hocr.html", "_djvu.txt"))
    assert [f["name"] for f in chosen] == ["vol_hocr.html", "vol_djvu.txt"]


def test_volume_asset_urls_skips_the_drm_copy_and_reports_sizes():
    urls = dict(volume_asset_urls("vol_id", IA_METADATA))
    assert all("_encrypted" not in u for u in urls)
    assert ia_download_url("vol_id", "vol.pdf") in urls
    assert urls[ia_download_url("vol_id", "vol_hocr.html")] == 33_000_000


def test_ia_num_found_reads_the_search_envelope():
    assert ia_num_found({"response": {"numFound": 973499, "docs": []}}) == 973499
    assert ia_num_found({"nonsense": 1}) is None


def test_cia_search_url_carries_the_collection_facet_and_json_output():
    url = cia_mirror.search_url("Uzbek cotton", page=2, rows=100)
    assert "collection%3Aciareadingroom" in url
    assert "Uzbek+cotton" in url
    assert "page=2" in url and "rows=100" in url and "output=json" in url


def test_cia_document_urls_drop_the_item_prefix():
    urls = cia_mirror.document_file_urls("cia-readingroom-document-cia-rdp82-00457r008900350003-7")
    assert urls["pdf"].endswith("/cia-rdp82-00457r008900350003-7.pdf")
    assert urls["text"].endswith("/cia-rdp82-00457r008900350003-7_djvu.txt")


def test_safe_name_keeps_a_cyrillic_filename_usable_on_windows():
    """archive.org and publ.lib.ru serve Cyrillic filenames with spaces and quotes."""
    cyrillic = "\u041d\u0430\u0440\u043e\u0434\u043d\u043e\u0435 - OCR.pdf"
    got = safe_name(cyrillic)
    assert got.isascii()
    assert " " not in got
    assert got.endswith("OCR.pdf")
    assert safe_name("plain_name.json") == "plain_name.json"
    assert safe_name("///") == "file"

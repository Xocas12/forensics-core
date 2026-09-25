"""Generate the synthetic test fixtures for projects/china/tests/fixtures.

Run once with `uv run python <this file>` from the repo root. Everything it writes is
obviously artificial: years 2032-2034, values like 9.9 and 888.8, identifiers spelled
SYNTHETIC. The Chinese structural markers come from the module constants rather than being
typed here, so the fixtures cannot drift from the parsers they exercise.
"""

from __future__ import annotations

import json
from pathlib import Path

from china.clean import pbc_reports as pbc

OUT = Path("projects/china/tests/fixtures")
OUT.mkdir(parents=True, exist_ok=True)

CJK_MIDDLE = "\u4e2d"  # one CJK character, so the gb18030 decoding path is exercised

# ---------------------------------------------------------------- yearbook contents frame
toc = f"""<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=gb2312">
<title>SYNTHETIC yearbook contents frame</title></head>
<body>
<a href='html/E03-09.jpg'>3-9 Gross Regional Product (2034)</a><br>
<a href="html/EN0914.jpg">9-14 Electricity Consumption by Region</a><br>
<a href="html/E16-14.jpg">16-14 Freight Traffic by Region (2033)</a><br>
<a href="html/E16-15.jpg">16-15 Freight Ton-kilometers by Region (2033)</a><br>
<a href="html/E01-01.htm">1-1 Synthetic Overview Table {CJK_MIDDLE}</a><br>
<a href="html/zbe99.pdf">Appendix Synthetic Explanatory Notes</a><br>
<a href="../indexeh.htm">Back to the synthetic index</a>
</body></html>
"""
(OUT / "synthetic_csy_toc_en.htm").write_bytes(toc.encode("gb18030"))

# ------------------------------------------------------------- central bank report index
prefix = "/zhengcehuobisi/125207/125227/125960/126049"
index = f"""<html><body>
<a href="{prefix}/9999991/aaaa1111bbbb2222/index.html">SYNTHETIC Report (2034)</a>
<a href="{prefix}/9999992/cccc3333dddd4444/index.html">SYNTHETIC Report (2033)</a>
<a href="/zhengcehuobisi/999/unrelated/index.html">Unrelated channel page 2032</a>
<a href="{prefix}/9999993/eeee5555ffff6666/index.html">SYNTHETIC report with no year</a>
</body></html>
"""
(OUT / "synthetic_pbc_report_index.html").write_text(index, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- one year's report page
pdf_dir = f"{prefix}/9999991/aaaa1111bbbb2222"
title_open, title_close = pbc._BRACKET_OPEN, pbc._BRACKET_CLOSE
report, summary = pbc._FINANCIAL_REPORT, pbc._SUMMARY
year_page = f"""<html><body>
<a href="{pdf_dir}/2034000000000000001.pdf">1.{title_open}SYNTHETIC-NATIONAL{report}(2034){title_close}.pdf</a>
<a href="{pdf_dir}/2034000000000000002.pdf">2.{title_open}PROVINCE-A{report}(2034){title_close}{summary}.pdf</a>
<a href="{pdf_dir}/2034000000000000003.pdf">3.{title_open}PROVINCE-B{report}(2034){title_close}{summary}.pdf</a>
<a href="{pdf_dir}/index.html">Not a PDF at all</a>
</body></html>
"""
(OUT / "synthetic_pbc_year_page.html").write_text(year_page, encoding="utf-8", newline="\n")

# --------------------------------------------------------- one summary's extracted text
text = (
    "SYNTHETIC SUMMARY, NOT A REAL REPORT. "
    f"2034{pbc._YEAR_END}, {pbc._LOAN_BALANCE}9.9{pbc._TRILLION}{pbc._YUAN}, "
    f"{pbc._YOY_GROWTH}2.2%. "
    f"2033{pbc._YEAR_END}, {pbc._LOAN_BALANCE}888.8{pbc._HUNDRED_MILLION}{pbc._YUAN}, "
    f"{pbc._YOY_GROWTH}-1.5%."
)
(OUT / "synthetic_pbc_summary_text.txt").write_text(text, encoding="utf-8", newline="\n")

# --------------------------------------------------------------- World Bank observations
worldbank = [
    {
        "page": 1,
        "pages": 1,
        "per_page": 100,
        "total": 3,
        "sourceid": "2",
        "lastupdated": "2034-01-31",
    },
    [
        {
            "indicator": {"id": "NY.GDP.MKTP.CN", "value": "SYNTHETIC GDP"},
            "country": {"id": "CHN", "value": "SYNTHETIC"},
            "date": "2033",
            "value": 50000000000000,
        },
        {
            "indicator": {"id": "NY.GDP.MKTP.CN", "value": "SYNTHETIC GDP"},
            "country": {"id": "CHN", "value": "SYNTHETIC"},
            "date": "2034",
            "value": 100000000000000,
        },
        {
            "indicator": {"id": "NY.GDP.MKTP.CN", "value": "SYNTHETIC GDP"},
            "country": {"id": "CHN", "value": "SYNTHETIC"},
            "date": "2032",
            "value": None,
        },
    ],
]
(OUT / "synthetic_worldbank_gdp.json").write_text(
    json.dumps(worldbank, indent=1), encoding="utf-8", newline="\n"
)

# -------------------------------------------------------------------- catalogue responses
tree = {
    "data": [
        {
            "_id": "SYNTHETIC-NODE-1",
            "name": "Synthetic Branch",
            "isLeaf": False,
            "treeinfo_pid": "",
            "treeinfo_level": 1,
            "sdate": "",
            "edate": "",
            "type": "6",
        },
        {
            "_id": "SYNTHETIC-NODE-2",
            "cid": "SYNTHETIC-CID-1",
            "name": "Synthetic Leaf",
            "isLeaf": True,
            "treeinfo_pid": "SYNTHETIC-NODE-1",
            "treeinfo_level": 2,
            "sdate": "1999",
            "edate": "2034",
            "type": "6",
        },
    ],
    "success": True,
    "state": 20000,
    "message": "SYNTHETIC OK",
}
(OUT / "synthetic_nbs_tree.json").write_text(
    json.dumps(tree, indent=1), encoding="utf-8", newline="\n"
)

failure = {"data": [], "success": False, "state": 50000, "message": "SYNTHETIC FAILURE"}
(OUT / "synthetic_nbs_tree_failure.json").write_text(
    json.dumps(failure, indent=1), encoding="utf-8", newline="\n"
)

indicators = {
    "data": [
        {
            "_id": "SYNTHETIC-IND-1",
            "i_showname": "Synthetic Indicator (synthetic unit)",
            "i_mark": "SYNTHETIC scope note",
            "du": "synthetic unit",
            "dp": 2,
        }
    ],
    "success": True,
    "state": 20000,
}
(OUT / "synthetic_nbs_indicators.json").write_text(
    json.dumps(indicators, indent=1), encoding="utf-8", newline="\n"
)

# --------------------------------------------------------------------- Figshare metadata
article = {
    "title": "SYNTHETIC harmonized nightlights",
    "doi": "10.0000/synthetic.0000000",
    "license": {"name": "SYNTHETIC CC BY 4.0"},
    "files": [
        {
            "id": 111,
            "name": "SYNTHETIC_NTL_2033.tif",
            "size": 1000,
            "computed_md5": "0" * 32,
        },
        {
            "id": 222,
            "name": "SYNTHETIC_NTL_2034.tif",
            "size": 2000,
            "computed_md5": "1" * 32,
        },
    ],
}
(OUT / "synthetic_figshare_article.json").write_text(
    json.dumps(article, indent=1), encoding="utf-8", newline="\n"
)

# ---------------------------------------------------------------- Wayback capture indexes
cdx = [
    ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    [
        "cn,gov,stats)/tjsj/ndsj/9999.rar",
        "20340101000000",
        "http://www.stats.gov.cn/tjsj/ndsj/9999.rar",
        "application/x-rar-compressed",
        "200",
        "SYNTHETICDIGEST1",
        "1111",
    ],
    [
        "cn,gov,stats)/tjsj/ndsj/9998/html/ch9999.jpg",
        "20330101000000",
        "http://www.stats.gov.cn/tjsj/ndsj/9998/html/CH9999.jpg",
        "image/jpeg",
        "200",
        "SYNTHETICDIGEST2",
        "2222",
    ],
]
(OUT / "synthetic_cdx.json").write_text(json.dumps(cdx, indent=1), encoding="utf-8", newline="\n")
(OUT / "synthetic_cdx_empty.json").write_text("[]\n", encoding="utf-8", newline="\n")

print("wrote", len(sorted(OUT.iterdir())), "fixtures to", OUT)
for path in sorted(OUT.iterdir()):
    print("  ", path.name, path.stat().st_size, "bytes")

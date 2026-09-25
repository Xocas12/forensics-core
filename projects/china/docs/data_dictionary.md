# Data dictionary - china

What the panel looks like, what each series means, which units it is in, which row labels are
traps, and what an extraction has to reproduce before its numbers are allowed in.

Everything quoted below with a figure attached was **read from `data/SOURCES.yaml`**, whose
entries record what an actual fetch returned. Nothing here was computed in this session. No
analysis has been run in this tree.

## 1. The panel

One tidy frame, defined in `src/china/clean/schema.py`.

| Column | Type | Meaning |
|---|---|---|
| `province` | string | One of the 31 provincial-level units, or the reserved value `China` for the national aggregate |
| `year` | int64 | **Data** year, not the year of publication |
| `series` | string | A name from the series catalogue below; nothing else is admissible |
| `value` | float64 | The number as published, converted only into the series' declared unit |
| `unit` | string | Must equal the series' declared unit; validated |
| `vintage` | string | Which publication the value came from |
| `source_id` | string | The `SOURCES.yaml` id it was acquired under |

**The key is `(province, year, series, vintage)`.** Not `(province, year, series)`. Two values
for one province-year-series are legal and expected, and the difference between them is the
measurement. `validate_panel` rejects a duplicate key, because two values under one vintage
label means two vintages that were not labelled.

Other rules the validator enforces, each of which exists because breaking it silently
corrupts a provincial sum:

- an unrecognised province label is an error, not a row to drop, because it almost always
  means the extraction went wrong;
- a missing observation is an **absent row**, never a `NaN` row;
- a series must carry its declared unit;
- when a registry id set is supplied, every `source_id` must be in it. A row that cannot be
  traced to `SOURCES.yaml` is not evidence.

### Vintage labels

| Form | Meaning | Example |
|---|---|---|
| `csy<edition year>` | A China Statistical Yearbook edition. The **edition** year, not the data year: the 2015 edition carries data years 2010 to 2014 | `csy2015` |
| `wb<lastupdated>` | A World Bank indicator response, labelled with the `lastupdated` field it carries | `wb2026-07-13` |
| `pbc<report year>` | A central bank regional financial operation report | `pbc2024` |

## 2. Why the vintage column is the project

Revisions overwrite history. The bureau and the provincial bureaus serve the current vintage
only, and the padded Liaoning figures for 2011 to 2014 are not in it. They are in the 2015
edition of the yearbook, which is a frozen snapshot that was never retro-revised.

From the registry entry `csy_2015_grp_vintage`, which records reading the image directly: the
Liaoning row of table 3-9 in the 2015 edition gives levels of 18457.27, 22226.70, 24846.43,
27213.22 and 28626.58 for 2010 to 2014, with indices 114.2, 112.2, 109.5, 108.7 and 105.8.
The same entry records that the 2024 edition reports Liaoning at 30209.4 for 2023.

Those two numbers, nine data years apart, are the project's anchor, and the archive of
editions is what makes them both visible. Without a vintage column a loader keeps whichever
was read last.

## 3. Series catalogue

Units are as printed by the publisher. Conversion happens once, in the loader, and never
downstream.

| Series | Unit | Source ids | Coverage and cautions |
|---|---|---|---|
| `grp_nominal` | 100 million yuan | `csy_2015_grp_vintage`, `csy_2024_grp`, `csy_web_editions` | Current prices. Recent editions footnote the latest year "preliminary data", so the same data year reappears revised in the next edition: a first-release against second-release pair per province per year, free |
| `grp_index_preceding_year` | index, preceding year = 100 | same | Constant prices. This is real growth. It is **not** the growth rate of `grp_nominal` |
| `gdp_national_nominal` | 100 million yuan | `csy_web_editions`, `worldbank_chn_gdp` | Take it from the **same edition** as the provincial rows for a gap. The World Bank series is the current vintage only |
| `electricity_consumption` | 100 million kWh | `csy_electricity_by_region`, `nbs_yearbook_2023_html_tables` | Selected years per edition only, not annual. Data since 2000 are the China Electricity Council's, per the table footnote |
| `freight_total` | 10 000 tons | `csy_freight_by_region`, `nbs_yearbook_2023_html_tables` | One cross-section per edition |
| `freight_rail` | 10 000 tons | same | The proxy of interest. Exclude the residual row before summing |
| `freight_ton_km` | **TO CONFIRM** | `csy_freight_by_region` | Table 16-15. Listed in the 2017 and 2024 contents frames but never opened, so the unit is unconfirmed. Better than tonnage because it embeds distance |
| `loans_outstanding` | 100 million yuan | `pbc_regional_financial_operation_reports` | Published as rounded prose, about two significant figures. 2004 to 2015 and 2017 to 2024; there is no 2016 edition |
| `loans_outstanding_national` | 100 million yuan | `pbc_credit_statistics` | National only. The table has no region dimension at all |
| `nightlights_dn_sum` | digital number, dimensionless | `figshare_li2020_harmonized_ntl` | **No provincial series exists yet**: there is no boundary source in the registry, so there is no zonal-statistics step |

### Units, prices and deflators

- Money is **100 million yuan** throughout, because that is what the yearbook prints. The
  World Bank prints yuan, so its loader divides by 1e8 and nothing else does any conversion.
- The central bank publishes in trillions and in hundreds of millions within a single
  sentence. Both are converted to 100 million yuan at parse time and the printed figure and
  its printed unit are kept alongside, so the rounding stays visible.
- Nominal levels and real growth are **different quantities and must never be mixed**. The
  provincial gap in nominal levels and the gap in real growth rates behave differently, and
  the provincial index is at provincial deflators while the national growth rate is at
  national ones.
- **There is no provincial deflator series in the registry.** That is a gap, not an oversight:
  it is why `china.analysis.gap.mechanical_gap_components` refuses to run and says the
  residual can only be bounded, not decomposed.

## 4. The province list problem

Defined in `src/china/clean/provinces.py`. Three separate hazards.

### 4.1 Names drift between editions

The 2015 edition labels one row `Tibet`; the 2024 edition labels the same row `Xizang`
(recorded in the `csy_2015_grp_vintage` evidence). Stack two vintages without a name map and
one province becomes two.

| Published label | Canonical | Attested? |
|---|---|---|
| `Tibet`, `Tibet Autonomous Region` | `Xizang` | Yes, in `SOURCES.yaml` |
| `Nei Mongol`, `Inner Mongolia Autonomous Region` | `Inner Mongolia` | TO CONFIRM |
| `Guangxi Zhuang Autonomous Region` | `Guangxi` | TO CONFIRM |
| `Ningxia Hui Autonomous Region` | `Ningxia` | TO CONFIRM |
| `Xinjiang Uygur Autonomous Region` | `Xinjiang` | TO CONFIRM |
| `Shannxi` | `Shaanxi` | TO CONFIRM |

The TO CONFIRM entries are the conventional forms and have not been seen in an extracted
table. Confirm them against real row labels before relying on them. `Shanxi` and `Shaanxi`
are different provinces and the alias table keeps them apart explicitly.

An extraction that produces a label matching nothing must be **reported**, never dropped.

### 4.2 Some rows are not provinces

Registry entry `csy_freight_by_region` records that table 16-14 carries a `National Total`
row and a `Not Classified by Region` residual row, the latter being civil aviation and
pipelines. Summing a column as printed double counts the national total and adds the residual
on top. `is_non_province_row` removes both.

### 4.3 The admitted revisions happened below the provincial level

| Unit | Parent | Why it matters |
|---|---|---|
| Binhai New Area | Tianjin | **Where the January 2018 Tianjin revision actually happened**: 2016 gross regional product revised down 33.4 percent to 665 billion yuan (Xinhua, 20 January 2018). Tianjin's provincial series absorbs only part of that |
| Baotou | Inner Mongolia | Named alongside the region in the same episode: fiscal revenues cut 49 percent to 13.7 billion yuan (Caixin, paywalled, visible text only) |
| Shenzhen | Guangdong | The central bank publishes 32 report summaries: the 31 provincial units **plus Shenzhen**. A naive file-per-province mapping produces 32 provinces |

None of these may enter a provincial panel.

### 4.4 Boundary changes and rebasing

| Year | Event |
|---|---|
| 1988 | Hainan separated from Guangdong |
| 1997 | Chongqing separated from Sichuan |
| 2004, 2008, 2013, 2018 | Economic censuses, which rebase and back-revise both national and provincial series |

A series that crosses one of these is two series. Test around them, not across them.

### 4.5 Region codes

Only four are hard-coded, and only because `SOURCES.yaml` records them: Beijing 110000,
Tianjin 120000, Inner Mongolia 150000, Liaoning 210000. The remaining twenty-seven are **not**
typed from memory. The bureau's catalogue API returns its own region list with 12-digit codes
(the 6-digit code zero padded); harvest it from there.

## 5. What is machine-readable, and what is not

| Artefact | Format | Loader |
|---|---|---|
| Yearbook contents frames (`left_.htm`, `left.htm`) | HTML, declared gb2312, decoded gb18030 | `clean.yearbook.parse_toc`, implemented |
| **Yearbook tables** | **JPEG scans** | `clean.yearbook.extract_table_image`, **stub, raises** |
| World Bank indicator responses | JSON | `clean.worldbank`, implemented |
| Bureau catalogue tree and indicators | JSON | `clean.nbs_api`, implemented |
| Central bank report index and year pages | HTML | `acquire.pbc`, implemented |
| Central bank summary loan sentences | PDF text | `clean.pbc_reports.parse_loan_balances`, implemented |
| Figshare article metadata | JSON | `acquire.nightlights.parse_figshare_article`, implemented |
| Wayback capture indexes | JSON | `acquire.wayback.parse_cdx_json`, implemented |

**Every actual provincial number is in the image row.** That is the bottleneck. See
`data/ACCESS_NOTES.md`.

The contents frames matter more than they look: the file-naming convention changed between
editions (2017 `html/EN0309.jpg`, 2020 `html/E0309.jpg`, 2024 `html/E03-09.jpg`) and the
registry warns that the table **number** also drifts, so a table must be located by its
printed title and never by a guessed file name. `find_tables` does that;
`table_number_from_filename` handles both conventions.

## 6. What an extraction has to reproduce before its numbers are used

These are acceptance checks, not results. Every figure is quoted from the `evidence` field of
the registry entry named beside it, where an agent recorded reading the image.

| Check | Target | From |
|---|---|---|
| The Liaoning pre-revision row, 2015 edition table 3-9 | levels 18457.27, 22226.70, 24846.43, 27213.22, 28626.58; indices 114.2, 112.2, 109.5, 108.7, 105.8 | `csy_2015_grp_vintage` |
| Sum of the 31 published 2014 levels in that table | 684 349.4 (100 million yuan) | `csy_2015_grp_vintage` |
| Inner Mongolia row, same table | 11672.00, 14359.88, 15880.58, 16916.50, 17770.19 | `csy_2015_grp_vintage` |
| Tianjin row, same table | 9224.46, 11307.28, 12893.88, 14442.01, 15726.93 | `csy_2015_grp_vintage` |
| 2024 edition table 3-9, sample cells | Beijing 43760.7, Tianjin 16737.3, Inner Mongolia 24627.0 (index 107.3), Liaoning 30209.4 (index 105.3), Guangdong 135673.2, Jiangsu 128222.2, Xizang 2392.7 | `csy_2024_grp` |
| 2024 edition table 16-14, national total row | 5 570 636 total; 503 535 railways; 4 033 681 highways; 936 746 waterways; 96 674 not classified by region | `csy_freight_by_region` |
| 2024 edition table 16-14, rail by province | Liaoning 20 073; Inner Mongolia 90 250; Tianjin 11 673; Shanxi 101 001; Shaanxi 46 129; Xizang 104 | `csy_freight_by_region` |
| 2023 edition table 16-14, rail | national 498 424; Shanxi 104 514; Liaoning 22 394; Beijing 368 | `nbs_yearbook_2023_html_tables` |
| 2024 edition table 9-14, Liaoning across selected years | 623, 749, 1111, 1715, 1985, 2423, 2551, 2663 | `csy_electricity_by_region` |
| Arithmetic, every table | provincial rows plus the excluded residual reconcile to the printed national total row | structural |
| Cross-edition, every overlapping data year | the same data year read from two editions differs only by a documented revision | structural |

A table that fails any of these has an extraction error, and no cell from it may enter the
panel. Note also that once extraction is by optical character recognition, a digit test on the
extracted values is partly a test of the recogniser, not of the publisher.

## 7. Files under `data/raw`

```
csy/index_zh.htm, csy/index_en.htm       the two yearbook index pages
csy/<edition>/index_{en,zh}.htm          per-edition framesets
csy/<edition>/toc_{en,zh}.htm            per-edition contents frames: the manifest
csy/<edition>/html/<file>.jpg            table images, named as the publisher names them
news/<slug>.html                         the six documentary pages
pbc/report_index.html                    the regional report channel index
pbc/<year>/index.html                    one year's report page, which holds the file-to-province map
pbc/<year>/<publisher id>.pdf            the main report and the 32 summaries
pbc/credit/<publisher id>.xlsx           the national credit spreadsheet
nbs_api/tree/code<n>/<pid>.json          catalogue levels
nbs_api/indicators/<cid>.json            per-leaf indicator lists
worldbank/<indicator>.json               national gross domestic product series
mot/bulletin_2023.html, mot/railway_bulletin_2023.pdf   national freight control totals
wayback/cdx_root.json, wayback/cdx_<year>.json          capture indexes
nightlights/figshare_article_9828827.json               dataset metadata (rasters are opt-in)
```

Nothing under `data/` is in version control. The registry is.

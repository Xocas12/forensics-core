# Validation anchors - china

What a working method must reproduce. Every fact below was read from the source cited during
the scaffolding session; items marked **TO CONFIRM** were not, and must be checked before use.

## Tier 1 - the natural experiment

**The unified regional GDP accounting reform.** This is the most interesting single test in
the project: if part of the provincial-sum minus national gap is misreporting rather than
method, the gap should contract discontinuously when the centre took over the calculation.

Verified from the National Bureau of Statistics' own question-and-answer page
(`https://www.stats.gov.cn/sj/sjjd/202302/t20230202_1896273.html`):

- The reform plan was approved in **June 2017** by the 36th meeting of the Central Leading
  Group for Comprehensively Deepening Reform.
- Unified accounting was **implemented in early 2020, and the first data year computed under
  it was 2019**.
- What changed: from graded accounting, in place since 1985, in which provincial bureaus
  computed their own gross regional product, to accounting organised, led and implemented by
  the national bureau with provincial bureaus participating.

Corroborated by Xinhua (13 November 2019) and by China Daily (7 January 2020) quoting the
bureau's head on 5 January 2020.

**Design consequence.** The break is at the 2019 data year, not at the 2017 approval. Test
sensitivity to ±1 year, and remember that provinces revised back-series at different times
(`known_traps.md`).

## Tier 2 - the admitted-falsification episodes

These are the project's positives. They give a province, a window and a direction, though
mostly for fiscal and industrial rather than GDP series.

| Episode | Date | Magnitude as stated | Source read |
|---|---|---|---|
| Liaoning | 17 Jan 2017 | City and county **fiscal** data falsified 2011 to 2014; revenues exaggerated by around 20 % overall, some counties reporting more than double actual income | China Daily 18 Jan 2017; Caixin Global 18 Jan 2017 |
| Inner Mongolia | Jan 2018 | 2016 fiscal revenue cut by 53 bn yuan (26.3 %); 2016 industrial added value cut by 290 bn yuan (40 %) | Xinhua 20 Jan 2018; Caixin 29 Jan 2018 |
| Tianjin, Binhai New Area | Jan 2018 | 2016 GDP revised down 33.4 % to 665 bn yuan | Xinhua 20 Jan 2018 |

**Read the fine print before using these as labels.**

- Liaoning's admission, in the governor's work report to the provincial people's congress,
  concerned **fiscal** data. No GDP-specific magnitude was stated in the sources read. Treating
  it as a GDP label imports an assumption; state it.
- The 20 % figure comes from Caixin's visible text on a paywalled page. Search snippets
  attribute "at least 20 %" and "as much as 23 % in 2014" to other outlets that were not read.
- The exact announcement dates for Inner Mongolia and Tianjin were not confirmed; only the
  20 January 2018 Xinhua report that describes them.
- Binhai New Area is a sub-provincial unit. The pre-revision figure of roughly 1 trillion yuan
  appears only in search snippets, not in text that was read.

## Tier 3 - the loader must reproduce the gap

Before any inference, the pipeline must reproduce the summed-provincial versus national GDP
gap year by year, in nominal levels and in real growth rates separately, and print it. If the
gap does not appear at all, the deflators or the vintages are wrong, not the hypothesis.

**A hard obstacle to record here.** The national bureau's portal cannot be asked for a
provincial series. Every request to its `easyquery.htm` endpoint, in Chinese and in English,
returned HTTP 403 from the site's web application firewall ("reason:UrlACL"), from two
different egress addresses, with any user agent. This is not a certificate problem, and it is
not the whole host: `https://data.stats.gov.cn/` returns 200, and the replacement catalogue
API under `/dg/website/publicrelease/web/external` answered anonymous requests with 200 in one
unverified pass. What is missing there is the **values** endpoint, which is unknown: thirteen
candidate paths were probed and all thirteen returned the application's own 404 page. The yearbook pages are reachable, but the 2023 edition publishes
its provincial tables **only as JPEG images** (the Chinese index has 706 `.jpg` references and
no spreadsheet references), which turns the spine of this project into an image-extraction
problem. See `data/ACCESS_NOTES.md` for the fallbacks being pursued.

## Tier 4 - the physical proxies, and what is actually free

| Proxy | Provincial breakdown available free? | Note |
|---|---|---|
| Electricity consumption | Yes, in the yearbook (table 9-14 in the 2023 edition), as an image | Footnote states data since 2000 come from the China Electricity Council, whose own site was unreachable from this network |
| Rail freight | Partly: yearbook table 16-14 gives provincial freight traffic including railways, as an image. The Ministry of Transport's annual bulletin gives national totals only | Provincial rail-freight time series need the yearbook images or the railway statistical bulletin |
| Bank credit | Not in the yearbook: the 2023 edition has no by-region deposits and loans table. The central bank's free regional financial operation reports (2012 to 2024) give provincial year-end loan balances in prose | Extraction from 33 PDFs per year, not a table download |
| Nightlights | Yes: the harmonised DMSP and VIIRS product (Figshare, DOI 10.6084/m9.figshare.9828827, CC BY 4.0, version 10, 1992 to 2024, 34 GeoTIFFs, about 1.09 GB) downloads anonymously | The original Earth Observation Group products now require an account, and as of 1 June 2026 programmatic access is limited to paid subscribers |

The harmonised product is therefore the nightlights path of record for this project. It also
avoids the DMSP-to-VIIRS seam being a break in the middle of the series, though the seam
remains a modelled join and must be tested separately (`known_traps.md`).

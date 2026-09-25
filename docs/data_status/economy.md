# DATA_STATUS: forensic-economy

Recomputed on 2026-09-07 directly from `projects/aaer/data/SOURCES.yaml`,
`projects/china/data/SOURCES.yaml` and `projects/gosplan/data/SOURCES.yaml`. Every count in
this file was produced by reading those registries with a YAML parser and counting, not by
copying a number out of prose. Where a registry and a README disagree, the registry wins; see
[Registry against prose](#registry-against-prose).

## What this session did, and did not do

This session did scaffolding and acquisition wiring only. It read the three source registries,
each project's `data/ACCESS_NOTES.md` and `README.md`, ran `python -m <project>.acquire
--list` for all three (which makes no network request), recounted every figure below from the
registries themselves, and wrote this file. **No analysis was run.** Every module under
`src/aaer/analysis/`, `src/china/analysis/` and `src/gosplan/analysis/` is still a stub that
raises `NotImplementedError`, and nothing in this file is a result about a firm, a province or
a Soviet series: the only numbers here are counts of registry rows. **No data was
downloaded.** `data/raw/`, `data/interim/` and `data/processed/` are untouched in all three
projects, no fetch was attempted, and the only acquisition commands used were `--list` and
`--dry-run`, which make no requests. **Nothing was invented.** Every source id, URL claim,
access tier and status below comes from a registry entry that was itself built from a real
fetch attempt; where a registry records a gap, this file records the gap rather than filling
it from memory, and where a claim was never independently checked this file says so. Nothing
under `packages/forensics_core` was edited, and no `pyproject.toml`, lockfile or git state was
touched.

## Summary

**136 sources across three projects.** 73 have an acquirer. 25 sit in an access tier
that a machine cannot resolve at all.

| project   | verified | partial | blocked | unverified | total   | with an acquirer | in a gated tier |
|-----------|----------|---------|---------|------------|---------|------------------|-----------------|
| aaer      | 33       | 4       | 2       | 3          | 42      | 28               | 8               |
| china     | 24       | 5       | 6       | 2          | 37      | 22               | 7               |
| gosplan   | 31       | 10      | 13      | 3          | 57      | 23               | 10              |
| **total** | **88**   | **19**  | **21**  | **8**      | **136** | **73**           | **25**          |

| project   | free    | registration | paywalled | archive_visit | total   |
|-----------|---------|--------------|-----------|---------------|---------|
| aaer      | 34      | 2            | 6         | 0             | 42      |
| china     | 30      | 3            | 4         | 0             | 37      |
| gosplan   | 47      | 8            | 0         | 2             | 57      |
| **total** | **111** | **13**       | **10**    | **2**         | **136** |

Independent second-pass verification, across all three registries: **46 confirmed,
1 refuted, 89 not checked**. That last number is dominated by one project: **every
one of `gosplan`'s 57 entries carries `not_verified`**, so no second agent
re-checked any claim in it. `aaer` has 16 unchecked and
`china` 16, and in `china` the unchecked set includes the
whole `csy_*` yearbook family that the project depends on. The single refuted entry is
`sec_fsds_archive_page` in `aaer`: the URL returns HTTP 404 and does not exist. It is kept at
status `unverified` rather than deleted so the next person to find the same search result does
not repeat the attempt.

Read the gated column carefully. **"Not free" and "not found" are different**, and both differ
again from "not reachable from this network". Of the 25 gated entries, 10 are
paywalled, 13 need a registration, and 2 need someone to be physically present in a
reading room or to order a library copy. Separately, 11
free entries are blocked by a firewall, a geographic rule or a dead host, which is a different
failure and is recorded differently.

## The main table

All 136 sources, sorted by project, then access tier, then status, then id. The `acquirer`
column is the asterisk column of `python -m <project>.acquire --list`. The `2nd-pass check`
column is `verification.verdict` from the registry entry.

<details>
<summary><b>Full per-source table (136 rows)</b> - click to expand</summary>

| id                                                       | project | access tier   | status     | acquirer | 2nd-pass check |
|----------------------------------------------------------|---------|---------------|------------|----------|----------------|
| `aaer_listing_secgov`                                    | aaer    | free          | verified   | yes      | confirmed      |
| `aaer_release_pdf_sample`                                | aaer    | free          | verified   | yes      | confirmed      |
| `aaer_rss_feed`                                          | aaer    | free          | verified   | yes      | confirmed      |
| `bao2020_jar_metadata`                                   | aaer    | free          | verified   | yes      | confirmed      |
| `bao_analysis_csv`                                       | aaer    | free          | verified   | yes      | not checked    |
| `bao_commits`                                            | aaer    | free          | verified   | yes      | not checked    |
| `bao_labels_csv`                                         | aaer    | free          | verified   | yes      | not checked    |
| `bao_readme`                                             | aaer    | free          | verified   | yes      | not checked    |
| `bao_repo_api`                                           | aaer    | free          | verified   | yes      | not checked    |
| `beneish_1999_working_paper_pdf`                         | aaer    | free          | verified   | yes      | confirmed      |
| `crossref_jar_erratum`                                   | aaer    | free          | verified   | yes      | not checked    |
| `ejw_bao_response_page`                                  | aaer    | free          | verified   | yes      | not checked    |
| `ejw_walker_2021_critique`                               | aaer    | free          | verified   | yes      | confirmed      |
| `ejw_walker_2022`                                        | aaer    | free          | verified   | yes      | not checked    |
| `ejw_walker_2022_erroneous_erratum`                      | aaer    | free          | verified   | yes      | confirmed      |
| `hf_edgar_corpus`                                        | aaer    | free          | verified   | no       | not checked    |
| `jarfraud_github_repo`                                   | aaer    | free          | verified   | yes      | confirmed      |
| `sec_accessing_edgar_data`                               | aaer    | free          | verified   | yes      | confirmed      |
| `sec_companyfacts_api_sample`                            | aaer    | free          | verified   | yes      | confirmed      |
| `sec_edgar_apis_page`                                    | aaer    | free          | verified   | yes      | confirmed      |
| `sec_edgar_fullindex_1994q3`                             | aaer    | free          | verified   | no       | not checked    |
| `sec_efts_fulltext_search`                               | aaer    | free          | verified   | no       | confirmed      |
| `sec_fsds_2009q1`                                        | aaer    | free          | verified   | yes      | not checked    |
| `sec_fsds_listing`                                       | aaer    | free          | verified   | yes      | not checked    |
| `sec_fsds_page`                                          | aaer    | free          | verified   | yes      | confirmed      |
| `sec_fsds_quarterly_zips`                                | aaer    | free          | verified   | yes      | confirmed      |
| `sec_fsds_readme`                                        | aaer    | free          | verified   | yes      | confirmed      |
| `sec_fsn_page`                                           | aaer    | free          | verified   | yes      | confirmed      |
| `sec_fsn_readme`                                         | aaer    | free          | verified   | yes      | confirmed      |
| `sec_rate_control_announcement_2021`                     | aaer    | free          | verified   | yes      | confirmed      |
| `sec_webmaster_faq`                                      | aaer    | free          | verified   | yes      | confirmed      |
| `wikipedia_beneish_mscore`                               | aaer    | free          | verified   | no       | confirmed      |
| `jar_online_supplements_page`                            | aaer    | free          | partial    | no       | confirmed      |
| `sec_fsds_archive_page`                                  | aaer    | free          | unverified | no       | refuted        |
| `fmp`                                                    | aaer    | registration  | partial    | no       | not checked    |
| `simfin`                                                 | aaer    | registration  | partial    | no       | not checked    |
| `wrds_compustat_access`                                  | aaer    | paywalled     | verified   | no       | confirmed      |
| `usc_marshall_aaer_dataset`                              | aaer    | paywalled     | partial    | no       | confirmed      |
| `beneish_1999_faj_publisher`                             | aaer    | paywalled     | blocked    | no       | confirmed      |
| `jar_erratum_2022`                                       | aaer    | paywalled     | blocked    | no       | confirmed      |
| `faj_beneish_published`                                  | aaer    | paywalled     | unverified | no       | not checked    |
| `wrds_compustat`                                         | aaer    | paywalled     | unverified | no       | not checked    |
| `china_statistical_yearbook_online`                      | china   | free          | verified   | yes      | confirmed      |
| `chinadaily_liaoning_2017_01_18`                         | china   | free          | verified   | yes      | confirmed      |
| `chinadaily_reform_2020_01_07`                           | china   | free          | verified   | yes      | confirmed      |
| `csy_2015_grp_vintage`                                   | china   | free          | verified   | yes      | not checked    |
| `csy_2024_grp`                                           | china   | free          | verified   | yes      | not checked    |
| `csy_electricity_by_region`                              | china   | free          | verified   | yes      | not checked    |
| `csy_freight_by_region`                                  | china   | free          | verified   | yes      | not checked    |
| `csy_web_editions`                                       | china   | free          | verified   | yes      | not checked    |
| `figshare_li2020_harmonized_ntl`                         | china   | free          | verified   | yes      | confirmed      |
| `mcp_cnbs_repo`                                          | china   | free          | verified   | no       | not checked    |
| `nbs_dg_api_query_search`                                | china   | free          | verified   | yes      | not checked    |
| `nbs_dg_api_tree`                                        | china   | free          | verified   | yes      | not checked    |
| `nbs_provincial_finance_branch`                          | china   | free          | verified   | yes      | not checked    |
| `nbs_qa_unified_accounting_2019_12_27`                   | china   | free          | verified   | yes      | confirmed      |
| `nbs_qa_unified_accounting_plan_2017`                    | china   | free          | verified   | yes      | confirmed      |
| `nbs_yearbook_2023_html_tables`                          | china   | free          | verified   | yes      | confirmed      |
| `pbc_credit_statistics`                                  | china   | free          | verified   | yes      | not checked    |
| `pbc_regional_financial_operation_reports`               | china   | free          | verified   | yes      | confirmed      |
| `wayback_nbs_yearbooks`                                  | china   | free          | verified   | yes      | not checked    |
| `worldbank_chn_gdp`                                      | china   | free          | verified   | yes      | not checked    |
| `xinhua_data_inflation_2018_01_20`                       | china   | free          | verified   | yes      | confirmed      |
| `xinhua_reform_2019_11_13`                               | china   | free          | verified   | yes      | confirmed      |
| `mot_transport_statistical_bulletins`                    | china   | free          | partial    | yes      | confirmed      |
| `nbs_data_portal_new_spa`                                | china   | free          | partial    | no       | confirmed      |
| `cec_china_electricity_council`                          | china   | free          | blocked    | no       | confirmed      |
| `nbs_data_portal_english_easyquery`                      | china   | free          | blocked    | no       | confirmed      |
| `nbs_data_portal_fsnd`                                   | china   | free          | blocked    | no       | confirmed      |
| `nbs_easyquery_legacy`                                   | china   | free          | blocked    | no       | not checked    |
| `harvard_dataverse_search`                               | china   | free          | unverified | no       | not checked    |
| `nbs_dg_api_values`                                      | china   | free          | unverified | no       | not checked    |
| `archive_org_csy_scans`                                  | china   | registration  | partial    | no       | not checked    |
| `eog_dmsp_v4_composites`                                 | china   | registration  | blocked    | no       | confirmed      |
| `eog_viirs_vnl_annual`                                   | china   | registration  | blocked    | no       | confirmed      |
| `ceic_china_economic_database`                           | china   | paywalled     | verified   | no       | confirmed      |
| `wind_economic_database`                                 | china   | paywalled     | verified   | no       | confirmed      |
| `caixin_fudged_numbers_2018_01_29`                       | china   | paywalled     | partial    | no       | confirmed      |
| `caixin_liaoning_2017_01_18`                             | china   | paywalled     | partial    | no       | confirmed      |
| `cia_readingroom_home`                                   | gosplan | free          | verified   | no       | not checked    |
| `cucciolla_2017_cahiers_monde_russe`                     | gosplan | free          | verified   | yes      | not checked    |
| `cucciolla_2017_phd_thesis_imt_lucca`                    | gosplan | free          | verified   | yes      | not checked    |
| `dtic_ada121312_rand`                                    | gosplan | free          | verified   | no       | not checked    |
| `duke_treml_webfiles`                                    | gosplan | free          | verified   | no       | not checked    |
| `faostat_qcl_bulk_asia_uzbekistan`                       | gosplan | free          | verified   | yes      | not checked    |
| `faostat_qcl_bulk_europe_ussr`                           | gosplan | free          | verified   | yes      | not checked    |
| `harrison_data_index`                                    | gosplan | free          | verified   | yes      | not checked    |
| `harrison_greatwar_munitions_pdf`                        | gosplan | free          | verified   | yes      | not checked    |
| `harrison_plan_fraud`                                    | gosplan | free          | verified   | yes      | not checked    |
| `harrison_sovietgrowth`                                  | gosplan | free          | verified   | yes      | not checked    |
| `harrison_ussr_ww2`                                      | gosplan | free          | verified   | yes      | not checked    |
| `harvard_dataverse_soviet_io_search`                     | gosplan | free          | verified   | no       | not checked    |
| `hokudai_sess`                                           | gosplan | free          | verified   | yes      | not checked    |
| `ia_ciareadingroom_mirror`                               | gosplan | free          | verified   | yes      | not checked    |
| `ia_khanin_western_estimates`                            | gosplan | free          | verified   | yes      | not checked    |
| `ia_narkhoz_1985_item`                                   | gosplan | free          | verified   | yes      | not checked    |
| `ia_narkhoz_collection`                                  | gosplan | free          | verified   | yes      | not checked    |
| `istmat_ru_not_istmat`                                   | gosplan | free          | verified   | no       | not checked    |
| `jec_ussr_measures_1982`                                 | gosplan | free          | verified   | yes      | not checked    |
| `maddison_mpd2023`                                       | gosplan | free          | verified   | yes      | not checked    |
| `nasa_eo_aral_world_of_change`                           | gosplan | free          | verified   | no       | not checked    |
| `no_machine_readable_tables`                             | gosplan | free          | verified   | no       | not checked    |
| `publ_lib_ru_narkhoz`                                    | gosplan | free          | verified   | yes      | not checked    |
| `pwt_110`                                                | gosplan | free          | verified   | no       | not checked    |
| `usda_psd_cotton_bulk`                                   | gosplan | free          | verified   | yes      | not checked    |
| `usgs_eros_earthshots_aral`                              | gosplan | free          | verified   | no       | not checked    |
| `wb_soviet_economic_decline`                             | gosplan | free          | verified   | yes      | not checked    |
| `wb_wdi_country_api`                                     | gosplan | free          | verified   | no       | not checked    |
| `wikipedia_uzbek_cotton_scandal`                         | gosplan | free          | verified   | no       | not checked    |
| `cawater_aral_database`                                  | gosplan | free          | partial    | yes      | not checked    |
| `hathitrust_narkhoz`                                     | gosplan | free          | partial    | no       | not checked    |
| `istmat_org`                                             | gosplan | free          | partial    | yes      | not checked    |
| `jec_gorbachev_economic_plans_1987`                      | gosplan | free          | partial    | yes      | not checked    |
| `jec_soviet_economy_1980s_1982`                          | gosplan | free          | partial    | yes      | not checked    |
| `rand_soviet_national_income`                            | gosplan | free          | partial    | no       | not checked    |
| `rgae_opisi_online`                                      | gosplan | free          | partial    | no       | not checked    |
| `cia_foia_uzbek_cotton`                                  | gosplan | free          | blocked    | no       | not checked    |
| `cia_reading_room_soviet_io`                             | gosplan | free          | blocked    | no       | not checked    |
| `cia_readingroom_caesar_polo_esau`                       | gosplan | free          | blocked    | no       | not checked    |
| `cia_readingroom_document_pdf`                           | gosplan | free          | blocked    | no       | not checked    |
| `cia_readingroom_search`                                 | gosplan | free          | blocked    | no       | not checked    |
| `istmat_info_dead`                                       | gosplan | free          | blocked    | no       | not checked    |
| `jec_senate_gov_reports`                                 | gosplan | free          | blocked    | no       | not checked    |
| `github_search_soviet_data`                              | gosplan | free          | unverified | no       | not checked    |
| `khanin_lukavaya_tsifra`                                 | gosplan | free          | unverified | no       | not checked    |
| `osu_thesis_cotton_scandal_uzbek_national_consciousness` | gosplan | free          | unverified | no       | not checked    |
| `grdc_portal`                                            | gosplan | registration  | partial    | no       | not checked    |
| `rsl_search`                                             | gosplan | registration  | partial    | no       | not checked    |
| `faostat_api`                                            | gosplan | registration  | blocked    | no       | not checked    |
| `hathitrust_full_view`                                   | gosplan | registration  | blocked    | no       | not checked    |
| `icpsr_soviet_search`                                    | gosplan | registration  | blocked    | no       | not checked    |
| `openicpsr_100666_soviet_macro`                          | gosplan | registration  | blocked    | no       | not checked    |
| `rusneb_uzbek_annual`                                    | gosplan | registration  | blocked    | no       | not checked    |
| `usda_psd_opendata_api`                                  | gosplan | registration  | blocked    | no       | not checked    |
| `rgae_reading_room`                                      | gosplan | archive_visit | verified   | no       | not checked    |
| `hathitrust_ge_tempo_1966_io`                            | gosplan | archive_visit | partial    | no       | not checked    |

</details>

## Access tier: paywalled (10 sources)

Money, or an institution that has already spent it. None of these can be resolved by any
amount of code.

### `aaer` (6)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `jar_erratum_2022` | **Get the PDF through a university subscription** (Wiley returns HTTP 403 to scripts) or by interlibrary loan. This is a publisher paywall, not a registration and not a purchase the project would make directly | The Tier 1 validation target in `docs/validation_anchors.md`, currently marked TO CONFIRM because its figures were read from a critic quoting the erratum rather than from the erratum. **Highest-value single action in this repository** |
| `usc_marshall_aaer_dataset` | **Buy it.** The dataset's "Buy the Data" page links a USC CashNet storefront at `https://commerce.cashnet.com/LEVAAER`; that storefront redirects immediately to a login with **no price visible anywhere on the public site**. There is no free registration, no academic application form and no published eligibility rule, so calling this "registration" would be wrong. If the price or an academic rate is unclear, email `USCLeventhal.AAER.Data@marshall.usc.edu` from an institutional address stating affiliation and intended use. Delivery after purchase is not stated on the site. Its Terms of Use forbid sharing beyond co-authors, so the files must never be committed | The curated Dechow, Ge, Larson and Sloan misstatement-event label set, as an alternative to parsing AAER PDFs. Optional: the project already has a free label path |
| `wrds_compustat` | **An institutional WRDS subscription.** Note the honest status: this entry is `unverified`, carried over from a prior inventory and **not fetched during scaffolding**, so it records no HTTP status. Its own entry states the conclusion that Compustat is **not required** to reproduce the published benchmark, and becomes necessary only for `xsga`, firms outside the benchmark sample, or fiscal years after 2014 | A structured-financials panel that predates 2009, if the data-path decision goes that way |
| `wrds_compustat_access` | The registration and account-type pages for the same, and the only one of the pair actually fetched. **Registering is free; the subscription behind it is not.** Register choosing the institution and a matching user type; the registry records that the institution dropdown holds 523 subscribing institutions and that Carnegie Mellon University is one of them. The request is routed to that institution's WRDS representative for approval. **Then confirm `comp.funda` is in the subscription**: the registry is explicit that whether it is cannot be seen without logging in and was not checked | Confirming, before any work is planned around it, whether Compustat is actually available at all |
| `beneish_1999_faj_publisher` | Publisher landing page for the typeset article; `doi.org` resolves to tandfonline.com, which returned HTTP 403 with a bot-block page. A university subscription or an interlibrary loan gets it | Nothing structural. The free working-paper version is verified and acquired, and the coefficients in `aaer.features.beneish` were read from it. Nobody on the project has read the typeset version |
| `faj_beneish_published` | Same article, the publisher's own record. Never confirmed reachable at all | As above |

### `china` (4)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `ceic_china_economic_database` | **Ask a librarian whether the institution licenses CEIC** (now under ISI Markets). No public pricing exists; the product page offers only a login and a demo request. If licensed, a librarian-provided login is needed and exports are bound by CEIC's terms | A ready-made provincial series, which would sidestep the image-extraction problem. Not required: the free spine covers the same series with a lag |
| `wind_economic_database` | **An institutional Wind terminal licence**, typically held by a mainland Chinese university. Not a consumer purchase | As above |
| `caixin_liaoning_2017_01_18` | **A Caixin Global subscription** for the full article text | Nothing structural. The visible portion already carries the figure quoted in `docs/validation_anchors.md`; the subscription would confirm it in context |
| `caixin_fudged_numbers_2018_01_29` | As above | As above, for the second admitted-falsification episode |

## Access tier: registration (13 sources)

An account, not money, unless stated. Two of these need no action at all, and saying so is
part of an honest status.

### `aaer` (2)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `fmp` | **Register for an API key and answer one question before any code is written: what is the earliest fiscal year the free tier returns for a test ticker?** The pricing page returned HTTP 403 to a script and the docs state no history depth, so the registry refuses to guess. Also check whether redistributing derived data is permitted | A vendor route to pre-2009 fundamentals. If the free tier does not reach 1990, the vendor is useless here and should be closed out |
| `simfin` | As above. Its pricing page returned HTTP 500 and its bulk-download path 404, so coverage years are undeterminable without registering | As above |

### `china` (3)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `archive_org_csy_scans` | **Create a free archive.org account and borrow in the browser reader.** The registry says explicitly: **do not automate this.** The loan endpoints need an authenticated session and automated borrowing would breach the terms | A last resort for a yearbook year that exists only on paper. Only three usable national yearbook years are held there against thirteen live editions, so this is a fallback, not a route |
| `eog_dmsp_v4_composites` | **A free Earth Observation Group account** for the browser path. The scripted path is different: the register page states that from 1 June 2026 programmatic access via OpenID Client is limited to **paid** subscribers. So: free to register, paid to script | Nothing the project needs. The harmonised DMSP and VIIRS product on Figshare covers 1992 to 2024, is CC BY 4.0, and downloads anonymously |
| `eog_viirs_vnl_annual` | As above | As above |

### `gosplan` (8)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `rusneb_uzbek_annual` | **The obstacle is geographic before it is a registration.** The 403 body is an interstitial telling the user to switch off their VPN, so Russian-network egress is needed even to read the catalogue record. Then a person must judge whether the scan is openly viewable or restricted to a physical reading-room terminal, which is what the national digital library typically does with in-copyright items even for Russian users. Do not build retry logic: the block is deterministic | The catalogue record for the Uzbek republic annual, the volume this project most needs. The record surfaced by search is a 1957 edition, outside the anchor window; other editions appear in search snippets but **nobody has read the page**, so the edition list is an unverified lead |
| `openicpsr_100666_soviet_macro` | **A free ICPSR account** is enough for openICPSR public deposits (no institutional login), plus a browser to get past a Cloudflare challenge. Download the archive by hand and record the file list, sizes and terms | A deposited Soviet macroeconomic dataset. Not evaluated: nobody has seen its contents, and its existence rests on web-search snippets |
| `icpsr_soviet_search` | **Membership of an ICPSR member institution** for ICPSR-processed studies, not merely an account. Search from a university network and check "Access Restrictions" on each study | Searching for Soviet studies at all; the search page itself returns 403. The study numbers in this entry's own name came only from web-search result titles and were never fetched, so they are unverified leads |
| `hathitrust_full_view` | **A HathiTrust account**, and full-view rights that depend on each item's rights status. Whole-book download needs a logged-in session; the site also serves a Cloudflare JavaScript challenge to scripts | Page images of catalogued volumes. The bibliographic API answers without the challenge and is already used for metadata |
| `rsl_search` | **A Russian State Library account**, and for 20th-century material often an on-site terminal. **Nobody read a page stating those terms**, so no claim is made about them here. `search.rsl.ru` is a client-rendered application returning zero record links to a non-browser client | Resolving shelf marks. It is a catalogue lead, not a bulk source |
| `grdc_portal` | **Submit a data request** through a JavaScript portal; delivery is by e-mailed link. The Centre states its data are free of charge, so this is a request, not a purchase. **Check the period of record first**: whether it holds Amu Darya or Syr Darya stations covering the 1970s and 1980s was not confirmed | The one remaining candidate for a pre-1992 hydrological correlate, which is the independent physical check the anchor window currently lacks |
| `faostat_api` | **Nothing.** Returns 401 "Missing Authorization Header", but the FAOSTAT bulk zips carry identical data with no auth and both have acquirers | Nothing. Recorded so nobody spends time on a key |
| `usda_psd_opendata_api` | **Nothing.** Returns 403 and needs an API key, but the PSD bulk CSV carries the same data and has an acquirer | Nothing. Same reason |

## Access tier: archive visit (2 sources)

Physical presence, or a library that will lend. Not a purchase and not an account.

### `gosplan` (2)

| Source | What the person must do | What it unblocks |
|---|---|---|
| `rgae_reading_room` | **Travel to the Russian State Archive of the Economy in Moscow, or to its Voronovskoe reading room, and order files in person.** On the pages actually read there is no remote access: electronic images made to order in the reading rooms are handed to the user on the user's **own physical media**, and copying to tablets and smartphones is not performed. Before booking anything, open the two leads nobody has opened: the archive's GIS UIAD system and the site's electronic pre-ordering page, either of which could change this picture | Enterprise-level and Gosplan-level records from fond 4372 (Gosplan) and fond 1562 (the Central Statistical Administration). Both fonds are listed by name in a public, no-login online finding aid, so what exists can be established from here; none of it can be obtained from here |
| `hathitrust_ge_tempo_1966_io` | **Order a library copy or an interlibrary loan.** The GE-TEMPO transformation of the 1966 Soviet input-output table is digitised but search-only | The one input-output table this project has a concrete lead on. The same applies to the Treml volumes |

## Actions requiring a human, most valuable first

1. **Put a real name and email in `config/forensics.toml` (`[http].contact`).** Unblocks:
   `aaer`, `china` and `gosplan`, all at once. It still holds `REPLACE_ME <you@example.org>`,
   and every fetcher refuses to touch the network until it does not, so all 73 acquirers in
   this repository are inert. A machine must not invent a contact address, which makes this a
   human action by construction. SEC EDGAR additionally requires a real contact in the
   `User-Agent`, and answered a generic one with HTTP 403 during scaffolding. Cheapest and
   highest-value item on this list by a wide margin.
2. **Get the 2022 erratum PDF (`jar_erratum_2022`) through a university subscription and
   rewrite the Tier 1 table in `docs/validation_anchors.md` from it.** Unblocks: `aaer`.
   Everything that project is currently aiming at was read second-hand from a critic quoting
   the erratum. The project's own access notes call this its single highest-value human action,
   and nothing found in the registry contradicts that.
3. **Settle the China extraction path, in two steps.** Unblocks: `china`, which cannot read a
   single provincial number today. First **decide whether a mainland vantage point is in
   scope**: if it is, the portal's unknown values endpoint can be captured from a browser's
   network panel in minutes and the image problem may become optional. If it is not, say so,
   and then **choose the image-extraction back end** for the yearbook JPEGs and gate it on the
   arithmetic checks in `docs/data_dictionary.md` before a single cell enters the panel. This
   is that project's critical path and everything downstream waits on it.
4. **Decide the `aaer` data path.** Unblocks: `aaer`. Three options, not mutually exclusive:
   the free SEC Financial Statement Data Sets, whose first quarter holding any rows is 2009q2
   (2009q1 is an empty placeholder by design) while the labels concentrate in fiscal 1991 to
   2008, so most labelled positives fall outside the free window; the Bao et al. replication
   CSV, which is free, covers fiscal
   1990 to 2014, is what the published benchmark itself used, and is missing three of the
   twelve Beneish inputs; or buying the curated AAER dataset and obtaining Compustat. The
   choice belongs to the owner, not to the code.
5. **Run `make data` once, per project, and read the failures.** Unblocks: verification of
   89 entries no second agent ever checked, including the whole `csy_*` family in `china`
   and every single entry in `gosplan`. The first real run is also the check on them. It is a
   human action only because it depends on item 1.
6. **Find the Uzbek republic annual, or write up its absence as a design constraint.**
   Unblocks: `gosplan`'s republic-level work, which currently rests on whatever the union
   volumes print by republic. No digitised copy anyone can open has been located on
   archive.org, in HathiTrust, or on publ.lib.ru; istmat.org lists six editions of which only
   two fall near the anchor decade; and the one national digital library holding a copy refuses
   non-Russian egress. This is a library and archive search by a person, not a crawl.
7. **Transcribe `gosplan` target 1 twice, independently, and publish the per-digit-position
   disagreement rate.** Unblocks: the decision on whether any digit-based method is usable in
   `gosplan` at all. Transcription error mimics every signature the programme looks for, so
   this number gates the method transfer. Cheapest informative thing that project can do, and
   it needs human eyes on a scanned page.
8. **Read Cucciolla (2017) and settle the anchor's internal inconsistency.** Unblocks:
   `gosplan`'s only anchor. The article gives an aggregate and a per-year figure that do not
   reconcile, and choosing between them by preference rather than by reading is not acceptable.
   The article is free, verified and acquired, so this is reading, not access.
9. **Check whether the institution's WRDS subscription includes Compustat Fundamentals
   Annual.** Unblocks: item 4. One login answers it. Do it before planning any work that
   assumes Compustat.
10. **Price the curated AAER dataset at the CashNet storefront.** Unblocks: item 4, by
    replacing a shrug with a number. The price is published nowhere.
11. **Open the two unopened RGAE leads: the GIS UIAD system and the electronic file
    pre-ordering page.** Unblocks: the assessment of whether a Moscow trip is the only route
    into fonds 4372 and 1562. Cheap, and it should precede any travel decision.
12. **Chase a pre-1992 hydrological series**: open the two unopened CAWater-Info pages the
    acquirer already fetches in both languages, and if they yield nothing, submit a GRDC
    request after checking its period of record. Unblocks: `gosplan`'s independent physical
    check on the anchor window, which today is FAOSTAT against USDA and nothing else, both of
    them outside estimates of the same reported quantity.
13. **Build the Chinese-to-canonical province map** from the `province_zh` column of a fetched
    central bank year page and record it. Unblocks: the `china` loader, which refuses to guess
    it. Needs data on disk first, so it follows item 1.
14. **Find a source for provincial growth targets, or accept that the bunching test can only be
    a scan over round numbers.** Unblocks: one of `china`'s five tests. The registry has
    nothing for them, and that is a recorded gap, not an oversight.
15. **Optional, low value: register with FMP or SimFin** only to answer the earliest-fiscal-year
    question, and close both out if neither reaches 1990. **Optional: a Caixin Global
    subscription** for the two paywalled articles, whose visible portions are already quoted.
    **Optional: ask a librarian about CEIC or Wind**, which would shortcut `china` but is not
    required.
16. **Most expensive, and last: a reading-room visit to RGAE in Moscow.** Unblocks: primary
    Gosplan and Central Statistical Administration records, which nothing else in this
    programme can substitute for. Only after item 11.

## What is bottlenecked on something a machine cannot fix

All three projects in this repository need a human before they can produce anything, but they
are stuck in three different ways and to three different degrees.

**`aaer` is the least stuck.** Its benchmark replication path is free and complete: the Bao et
al. replication CSV covers fiscal 1990 to 2014 with the labels attached, needs no Compustat
subscription, and has an acquirer. What a human is holding up is the **validation anchor, not
the data**: the target this project aims at was read from a critic quoting an erratum nobody
here has opened. It also needs one decision (item 4) that only the owner can make. Neither is
an access failure. With the contact string filled in, 28 acquirers
run today.

**`china` is bottlenecked on an extraction problem that money would not obviously solve.** Its
provincial spine is published as photographs of tables: the 2024 edition's contents frame holds
762 links, 702 of them JPEG, and not one spreadsheet. The bureau's legacy API is retired and
firewalled, its replacement's values endpoint is unknown after thirteen probed candidate paths,
and `src/china/clean/yearbook.py` therefore ships a stub that raises rather than a
plausible-looking parser. **No provincial number can be read by any code in this tree today.**
The paywalled vendors (CEIC, Wind) would sidestep this, which makes them the one place where
money genuinely buys progress in this repository, but both need an institution rather than a
credit card, and the free yearbook vintages remain the better source because they were never
retro-revised.

**`gosplan` is the worst off of the three, and it is not close.** Naming the reasons rather
than hedging:

- **Its input is transcription, not download.** The primary reported series exists only as
  scanned Russian printed tables whose bundled optical character recognition is unusable for
  numbers: on the volume actually inspected the cover title came out garbled and numeric rows
  arrive with column separators merged or dropped, so row and column alignment is gone. No
  curated machine-readable transcription of the Soviet annuals exists on Zenodo, GitHub or
  Harvard Dataverse; the registry records those searches as negatives. Human eyes on pages are
  the acquisition method.
- **The volume that covers the anchor at republic level has not been located in any openable
  form anywhere.** Not on archive.org, not in HathiTrust, not on publ.lib.ru; istmat.org lists
  six editions of which only two fall near the anchor decade; the one national digital library
  holding an edition refuses non-Russian egress, and that edition is outside the window anyway.
- **It carries the largest obstructed set in this repository**: 13
  blocked and 10
  gated, 17 distinct entries once the 6 that are both are counted once,
  against 11 of 37 for `china` and 8 of
  42 for `aaer`. As a share of its own registry that is level with `china` and
  not worse, so this bullet is a statement about volume, not about proportion: `gosplan` has
  more of everything obstructed, and it is the only one of the three whose obstruction includes
  a physical archive.
- **Nothing in it has been independently checked.** All 57 entries carry
  `not_verified`. `aaer` and `china` each had a second agent re-fetch and confirm a majority of
  their entries; `gosplan` had none. Every claim in that registry is one careful session's
  finding.
- **The intended independent physical check does not cover the anchor window.** The
  irrigation-withdrawal table actually fetched begins in 1992, nine years after the padding
  ended, so the only physical corroboration available today is FAOSTAT against USDA, and both
  are outside estimates of the same reported quantity rather than a driver the falsifiers could
  not touch.
- **Its deepest remaining route is a trip to Moscow.** On the evidence actually read there is
  no remote access to RGAE documents at all.

That `gosplan` has almost no ground truth is by design: it is the target project, and the
programme's whole shape is calibrate-then-transfer. Its **data access position is a separate
problem**, and the two compound. A project with one anchor event, a transcription-only input
path, and no independently verified source claim is the one to worry about, and no amount of
code changes any of it.

## Registry against prose

Every count in the three `README.md` files and the three `data/ACCESS_NOTES.md` files was
recomputed from the registries. **They agree**, with one presentational wrinkle worth naming:

- `aaer`'s README and access notes say "28 have an acquirer; 8 need a human; 6 have none".
  That is a three-way partition of 42 and it is arithmetically right, but the registry gives
  **14 entries with no acquirer**, because the 8
  gated entries have no acquirer either. A reader counting unmarked rows in
  `python -m aaer.acquire --list` will find 14,
  not 6. The registry is the authority: 28 acquirers,
  14 without.
- `china` ("22 of 37, the other 15") and `gosplan` ("23 acquirers", "10 needing a human",
  14 free and reachable without one, plus 7
  blocked-free and 3 unverified) both partition their
  registries exactly, and every status and tier count in all three projects matches.

No count in this file needed to override a project's own prose, and no figure here was carried
over from prose without being recomputed.

## Operational notes

- **`python -m china.acquire --list` and `python -m gosplan.acquire --list` crash on a Windows
  console** with `UnicodeEncodeError: 'charmap' codec can't encode characters`, raised inside
  `forensics_core/provenance/runner.py` when it prints registry `name` fields containing
  Chinese or Cyrillic to a cp1252 stream. Run them with `PYTHONIOENCODING=utf-8`. This is a
  limitation of the shared library, which this repository vendors as a submodule and must not
  edit, so it is reported upstream rather than patched here. `elections` in
  `forensic-elections` is affected identically.
- **After the first `make data`, do not read a family entry's `sha256` out of `SOURCES.yaml`.**
  The shared library's `fetch` overwrites an entry's `sha256`, `bytes`, `local_path` and
  `status` on every success, and several `china` and `gosplan` acquirers fetch a family of
  files under one source id, so the entry then holds whichever member was fetched last. The
  per-file provenance record is `data/fetch_log.jsonl`. This is a library limitation, already
  raised upstream by the `china` access notes.

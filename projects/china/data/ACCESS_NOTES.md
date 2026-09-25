# Access notes - china

What failed, what is gated, and what needs a human. Every claim here has a corresponding entry
in `SOURCES.yaml` and will have a line in `fetch_log.jsonl` once `make data` has run. Nothing
in this file was inferred; it is the registry's own record of real fetch attempts.

## The bottleneck, stated plainly

**The National Bureau of Statistics portal cannot deliver a provincial series: its legacy
easyquery API is blocked from this network and its replacement, which does answer, has an
unknown values endpoint. Meanwhile the yearbook publishes its provincial tables only as JPEG
images. So the spine of this project is currently an image-extraction problem, and no
provincial number can be read by any code in this tree today.**

Both halves of that sentence are load-bearing. Note that the first half is about the
**easyquery** API, not about the host: `https://data.stats.gov.cn/` itself returns 200, and
the new catalogue API under it answered anonymously in one unverified pass. That half of the
story is in "The half of the portal story that is not settled" below, and it is why three
`data.stats.gov.cn` acquirers exist.

1. Every request to `data.stats.gov.cn/easyquery.htm`, in Chinese and in English, returned
   HTTP 403 from the site's web application firewall with `reason:UrlACL`. Reproduced across
   every combination of user agent, cookie jar and request header, from **two different egress
   addresses** (80.102.39.188 and 90.166.134.227) and through **two different tools**. It is
   not a certificate problem: the TLS chain verified and `-k` was never needed. It is not
   purely geographic either: a fetch from unrelated United States infrastructure got the same
   403. The sibling legacy paths `tablequery.htm` and `adv.htm` return HTTP 404 with a Spring
   Boot JSON body, so the legacy application is **retired**, not merely firewalled.
2. The yearbook editions **are** reachable. The 2024 edition's contents frame holds 762 links,
   of which 702 are `.jpg`, 33 `.htm` and 27 `.pdf`, and **not one is a spreadsheet**. The
   2023 Chinese contents frame has 706 `.jpg` and zero `.xls`. Provincial gross regional
   product, electricity and freight are all photographs of tables.

`src/china/clean/yearbook.py` therefore ships `extract_table_image` as a stub that raises. It
has not been replaced by a plausible-looking parser, and it must not be.

## Counts

| | Count |
|---|---|
| Verified (fetched, content confirmed) | 24 |
| Partial (landing page reached, full dataset not confirmed) | 5 |
| Blocked (exists, cannot be fetched from here) | 6 |
| Unverified (could not be confirmed at all) | 2 |
| **Total** | **37** |

| Access tier | Count |
|---|---|
| Free | 30 |
| Paywalled | 4 |
| Registration | 3 |

Acquirers are implemented for **22** of the 37. The other 15 are listed at the end of this
file with the reason.

## A caution about the verification column

Sixteen of the 37 entries carry `verification.verdict: not_verified`, meaning no independent
second agent re-checked them. **That includes the whole `csy_*` family, which is the project's
spine**: `csy_web_editions`, `csy_2015_grp_vintage`, `csy_2024_grp`,
`csy_electricity_by_region` and `csy_freight_by_region`. The evidence recorded for them is
detailed and internally consistent, and the sibling entry
`nbs_yearbook_2023_html_tables` describing the same site **was** independently confirmed,
including two table images by digest. But the specific digests and cell values for the 2015
and 2024 tables rest on one pass, so the first real acquisition run is also the check on them.
The acquirers check each verified file against the digest recorded for it, for exactly that
reason: a mismatch is reported rather than absorbed.

Read the next section before relying on that check a second time.

## The recorded digests do not survive the first run

`forensics_core.provenance.manifest.fetch` writes back to the registry: on every success it
overwrites the entry's `sha256`, `bytes`, `local_path` and `status` with the file it just
fetched. An entry has one such slot, and most acquirers in this project fetch a **family** of
files under a single source id: `csy_web_editions` is 84 pages, `csy_2024_grp`,
`csy_electricity_by_region` and `csy_freight_by_region` sweep a table across 21 editions,
`wayback_nbs_yearbooks` is 22 files, `worldbank_chn_gdp` is 3,
`mot_transport_statistical_bulletins` 2, and
`pbc_regional_financial_operation_reports` is several hundred. So after `make data` each of
those entries holds the digest of whichever member was fetched last, and the digest the
registry shipped with is gone from `SOURCES.yaml`.

What this does and does not cost:

- **The per-file provenance record is not lost.** `data/fetch_log.jsonl` logs every attempt
  with its own url, byte count, sha256 and outcome. For anything fetched as a family that log,
  not `SOURCES.yaml`, is the provenance record. Read it there.
- **The digests that are worth checking are pinned in code, not read from the registry at run
  time.** `china.acquire.yearbook.ANCHOR_SHA256`, `TOC_2024_EN_SHA256` and `TOC_2023_SHA256`
  hold the values the registry was written with. `tests/test_acquire_registry.py` checks them
  against the registry for as long as the entry is still un-fetched (`local_path` null), and
  checks the three contents-frame digests against the evidence prose, which a successful
  fetch never rewrites. Reading `source.sha256` for a family member instead would,
  on the second run, compare a good file against another file's digest and report a mismatch
  that is an artefact of the bookkeeping.
- **What is genuinely lost is `SOURCES.yaml` as a digest record for the family entries after
  run one.** Do not read a family entry's `sha256` and call it that entry's digest.

This is behaviour of the shared library, which this project vendors as a submodule at
`packages/forensics_core` and must not edit. It is raised upstream as a library change:
`fetch` needs a way to log a family member without rewriting the entry's integrity fields.

## Blocked, with the actual failure

### The legacy statistics portal (three entries)

`nbs_easyquery_legacy`, `nbs_data_portal_english_easyquery`, `nbs_data_portal_fsnd`. HTTP 403,
292-byte firewall page, `reason:UrlACL`, reproduced as described above. **No acquirer exists
for any of them and none should be written.** A script built against `easyquery.htm` will fail
100 percent of the time.

### The China Electricity Council

`cec_china_electricity_council`. `www.cec.org.cn` does not accept a TCP connection from here:
curl times out after roughly 21 seconds (exit 28, HTTP 000) and a second tool gets
`ECONNREFUSED` on 211.160.76.55:443. `english.cec.org.cn` returns 200 but serves a 2,610-byte
JavaScript shell with no data links. This is unreachable, not gated.

It matters because the yearbook's electricity table footnotes the council as its upstream
source, so the yearbook is a free mirror of council data, but only for the handful of years
each edition prints. A continuous annual provincial electricity series needs the council, and
the council needs a different network.

### The Earth Observation Group nightlight products (two entries)

`eog_dmsp_v4_composites`, `eog_viirs_vnl_annual`. Both product pages are public; both data
directories redirect to a Keycloak login. **This is a registration wall, not an absence**, and
the register page states: "Effective June 1 2026 EOG is limiting programmatic access via
OpenID Client to paid subscribers." So the browser path needs a free account and the scripted
path now needs a paid one.

The project does not need them: the harmonised DMSP and VIIRS product on Figshare covers 1992
to 2024, is CC BY 4.0, and downloaded anonymously in a ranged request with no cookie.

## The half of the portal story that is not settled

A later scaffolding pass reported that the portal's **new** API under
`data.stats.gov.cn/dg/website/publicrelease/web/external` answers anonymous requests with HTTP
200, and recorded a drill-down from the provincial annual root to two named leaves, gross
regional product from 1992 and its index. Those entries (`nbs_dg_api_tree`,
`nbs_dg_api_query_search`, `nbs_provincial_finance_branch`) are marked free and verified, and
**they carry `not_verified` on the independent check**.

They are given acquirers, because the registry is the authority on what exists and the honest
way to resolve a contradiction is to attempt the fetch and record what comes back. If they
return 403 the run reports it, the registry entries are downgraded to blocked with a reason,
and the picture is simply the blocked one.

Either way the portal cannot deliver a provincial series today, because **the values endpoint
is unknown**. Thirteen candidate paths were probed; every one returned the application's own
404 page (3,046 bytes) while a control path returned 200. The reverse-engineered documentation
that named `getEsDataByCidAndDt` is right about the base URL and right about the tree and
indicator endpoints, and stale about this one. `nbs_dg_api_values` is `unverified` and has no
acquirer.

## Needs a human

Seven sources, none of which a machine can resolve.

| Source | Tier | What a person would have to do |
|---|---|---|
| `ceic_china_economic_database` | Paywalled | Check whether the institution's library licenses CEIC. If so a librarian-provided login is needed and exports are subject to CEIC's terms |
| `wind_economic_database` | Paywalled | Only via an institutional Wind terminal licence, typically at a mainland university |
| `caixin_liaoning_2017_01_18` | Paywalled | A Caixin Global subscription for the full text. The visible portion carries the "exaggerated by around 20 percent" figure and is already quoted in `docs/validation_anchors.md` |
| `caixin_fudged_numbers_2018_01_29` | Paywalled | As above, for the 290 billion yuan / 40 percent industrial figure |
| `archive_org_csy_scans` | Registration | A free archive.org account and borrowing in the browser reader. Only three usable national yearbook years exist there against thirteen live editions, so this is a last resort for a paper-only year. **Do not automate**: the loan endpoints need an authenticated session and automated borrowing would breach the terms |
| `eog_dmsp_v4_composites` | Registration | A free Earth Observation Group account for the browser path; the scripted path is paid from 1 June 2026. Not needed, see above |
| `eog_viirs_vnl_annual` | Registration | As above |

**Not free is not the same as not found.** All seven of these exist and were reached; what is
missing is money or an account. Conversely the China Electricity Council site was not reached
at all, and the values endpoint was not found. Those are different failures and are recorded
differently.

## Things that will surprise whoever runs this first

- **`python -m china.acquire --list` crashes on a Windows console** with
  `UnicodeEncodeError: 'charmap' codec can't encode characters`. Several registry `name`
  fields are in Chinese and the shared runner prints them to a cp1252 console. Set
  `PYTHONIOENCODING=utf-8` before running. This is a limitation of the shared runner, not of
  this project; it is reported upstream rather than patched here, because
  `packages/forensics_core` is a submodule.
- **The first run of any yearbook table acquirer also fetches 21 contents frames**, one per
  edition from 2005 to 2025, in English.
  That is deliberate: a table is located by its printed title in the edition's own menu,
  because file names and table numbers both drift between editions. The frames are attributed
  to `csy_web_editions`, whichever acquirer triggers them, and later runs make no request for
  them. The `csy_web_editions` acquirer itself is larger than that prelude: it takes both
  languages and both pages per edition, 21 x 2 x 2 = **84 pages**.
- **The central bank crawl is large, and larger than the registry's own figure.** The
  registry's download plan says "~33 files/year, ~430 total", but it attached that total to
  the 2012-2024 window named in the entry's title, while the same entry's verification field
  records that the index lists the report for **2004-2015 and 2017-2024**. The acquirer
  applies no year filter, so it crawls all twenty of those years, not thirteen. At roughly 33
  files a year, a main report of about 5.3 MB plus 32 summaries of about 100 KB each, expect
  on the order of **660 files and 170 MB**, not the registry's 430 and not 100 MB. Both
  per-year figures are the registry's; the multiplication is arithmetic on the year list it
  verified. It is fully resumable; a file already on disk is skipped without a request.
- **The nightlights rasters are not downloaded by default.** 34 GeoTIFFs, 1,091,935,532 bytes.
  The default run takes only the 13 KB article metadata, which is what enumerates the files
  and carries the licence. Set `CHINA_ACQUIRE_NIGHTLIGHTS=1`, or call
  `china.acquire.nightlights.download_rasters`, to take the rest. There is no point doing so
  yet: **no provincial boundary source is registered**, so there is no way to turn a global
  raster into a provincial series.
- **`config/forensics.toml` has no rate limit for `web.archive.org`**, so it falls back to two
  requests a second while the archive's own guidance in the registry asks for one every two to
  three seconds. The Wayback acquirer is deliberately kept to about twenty requests. Add a
  `"web.archive.org" = 0.4` line before doing anything larger. That file is at the repository
  root and was not edited from this project.
- **The contact string must be filled in first.** `config/forensics.toml` still holds
  `REPLACE_ME <you@example.org>` and every fetcher refuses to run until it does not.
  `--dry-run` and `--list` work without it and make no requests.

## Free and confirmed

- Thirteen or more yearbook editions on the live server, each a frozen vintage that was never
  retro-revised. This is the project's most valuable asset and the reason a pre-revision
  Liaoning series is observable at all.
- Provincial electricity and provincial rail freight, in the yearbook, free, as images, one
  cross-section (electricity: a handful of selected years) per edition.
- Provincial year-end loan balances, free, as rounded prose in the central bank's report
  summaries.
- Harmonised DMSP and VIIRS nightlights, 1992 to 2024, CC BY 4.0, anonymous download.
- National gross domestic product from the World Bank as JSON, in one request, with a vintage
  warning attached.
- Six documentary pages fixing the reform's dates and the three admitted falsification
  episodes.

## The confirmed negative that shapes the credit proxy

Provincial bank credit is **not** available as a table anywhere free, and that was established
three independent ways: the bureau's provincial annual database has exactly one leaf in its
finance branch and it is insurance premiums; the yearbook's finance chapter has no by-region
deposits or loans table in either the 2017 or the 2024 edition; and the central bank's own
sources-and-uses of credit funds spreadsheet has no region dimension at all. What exists free
is prose, rounded to about two significant figures. Anything built on provincial credit has to
survive that precision, and saying so is part of the result.

## Sources with no acquirer, and why

| Source | Reason |
|---|---|
| `nbs_easyquery_legacy`, `nbs_data_portal_english_easyquery`, `nbs_data_portal_fsnd` | Blocked: 403 UrlACL, reproduced |
| `cec_china_electricity_council` | Blocked: TCP connection times out or is refused |
| `eog_dmsp_v4_composites`, `eog_viirs_vnl_annual` | Blocked behind a login; scripted access paid since 1 June 2026 |
| `ceic_china_economic_database`, `wind_economic_database`, `caixin_liaoning_2017_01_18`, `caixin_fudged_numbers_2018_01_29` | Paywalled |
| `archive_org_csy_scans` | Registration, and the registry explicitly says not to automate the loan endpoints |
| `nbs_dg_api_values` | Unverified: the endpoint path is unknown, so there is nothing to fetch |
| `harvard_dataverse_search` | Unverified, and recorded as an honest negative: the search returned 10,926 results and not one provincial gross product panel. It is a search, not a source |
| `mcp_cnbs_repo` | Third-party documentation, not data. Its own download plan uses the GitHub API rather than a plain URL fetch, and the registry warns one of its three documented endpoints is already wrong |
| `nbs_data_portal_new_spa` | A 3,198-byte JavaScript shell with no data in it. What it loads is the API covered by `nbs_dg_api_tree` |

## What a human should do next, in order

1. **Fill in the contact string** in `config/forensics.toml`. Nothing fetches until then.
2. **Run `make data` once** and read the failures. The first run is also the test of the
   sixteen entries that were never independently verified, and of the digests pinned in
   `china.acquire.yearbook`. After that run, read digests out of `data/fetch_log.jsonl`
   rather than out of `SOURCES.yaml`, for the reason given above.
3. **Decide the extraction back end** for the yearbook images. This is the project's critical
   path and everything downstream waits on it. Whatever is chosen, gate it on the arithmetic
   checks in `docs/data_dictionary.md` section 6 before a single cell enters the panel.
4. **Build the Chinese-to-canonical province map** from the `province_zh` column of a fetched
   central bank year page, and record it. The loader refuses to guess it.
5. **Find a source for provincial growth targets**, or accept that the bunching test can only
   be a scan over round numbers. The registry has nothing for them.
6. **Decide whether a mainland vantage point is in scope.** If it is, the portal's values
   endpoint can be captured from a browser's network panel in a few minutes and the whole
   image-extraction problem may become optional. If it is not, say so, and the images are the
   project.

# china

**Question.** Measure the gap between summed provincial gross regional product and reported
national gross domestic product, and test whether provincial series track physical proxies.

Provincial bureaus computed their own figures from 1985 until the centre took the calculation
over. The summed provincial total exceeded the national one, and the bureau's own deputy head
gave that gap as the reason for the reform, saying the two were "too far apart". Part of the
gap is method. Part of it has been admitted to be fabrication. The reform is the natural
experiment that separates them, if anything can.

| | |
|---|---|
| Unit of observation | Province-year, 31 provincial-level units |
| Ground truth | Partial: three self-admitted falsification episodes, and one accounting-reform discontinuity |
| Blocked on a human? | **Yes.** See below |
| Sources in the registry | 37 |
| Acquirers implemented | 22 |

## Data status: read this before anything else

**The bureau's legacy easyquery API is blocked from this network, its replacement answers but
cannot yet be asked for a series, and the yearbook publishes its provincial tables only as
JPEG images. The spine of this project is currently an image-extraction problem, and no
provincial number can be read by any code in this tree today.**

- Every request to `data.stats.gov.cn/easyquery.htm` returned HTTP 403 from the site's web
  application firewall, from two different egress addresses, through two different tools, with
  any user agent. Not a certificate problem. The sibling legacy paths return 404 with an
  application error body, so the legacy API is retired, not merely firewalled.
- **The portal's new API is not blocked, and the registry says so.** In one scaffolding pass
  the catalogue endpoints under `data.stats.gov.cn/dg/website/publicrelease/web/external`
  answered anonymous requests with HTTP 200, one of them returning actual numeric values;
  `nbs_dg_api_tree`, `nbs_dg_api_query_search` and `nbs_provincial_finance_branch` are
  recorded free and verified, all three have acquirers, and all three appear in
  `--all --dry-run`. None of the three carries an independent second check, so the
  contradiction with the 403s above is unresolved and the first real run is what settles it.
  Either way the portal still cannot deliver a provincial series, because **the values
  endpoint is unknown**: thirteen candidate paths were probed and every one returned the
  application's own 404 page while a control path returned 200. See
  [data/ACCESS_NOTES.md](data/ACCESS_NOTES.md), "The half of the portal story that is not
  settled".
- The yearbook editions **are** reachable, and they are the better source anyway: each edition
  is a frozen snapshot that was never retro-revised, so the archive of editions **is** the
  vintage series this project needs. The 2015 edition still carries Liaoning's pre-revision
  figures for 2011 to 2014.
- But the 2024 edition's contents frame holds 762 links, 702 of them `.jpg`, and not one
  spreadsheet. The tables are photographs.

`src/china/clean/yearbook.py` ships the extraction **interface** and a stub that raises. It has
not been replaced with a plausible-looking parser, and it must not be. Everything that could
honestly be built around it has been.

| Status | Sources |
|---|---|
| Verified | 24 |
| Partial | 5 |
| Blocked | 6 |
| Unverified | 2 |

Sixteen entries carry `verification.verdict: not_verified`, meaning no second agent re-checked
them, and that **includes the whole `csy_*` family that the project depends on**. The first
real acquisition run is therefore also the check on them, which is why each verified file is
checked against the digest recorded for it. Those digests are pinned in code, not read back
from the registry: most acquirers here fetch a family of files under one source id and the
shared library rewrites an entry's `sha256` on every success, so after run one a family
entry's recorded digest belongs to whichever member was fetched last. The per-file record
lives in `data/fetch_log.jsonl`. Details, and every failure verbatim, in
[data/ACCESS_NOTES.md](data/ACCESS_NOTES.md).

## What is actually free

| Series | Free? | Form |
|---|---|---|
| Provincial gross regional product and its index | Yes | JPEG, one table per edition, every edition a vintage |
| National gross domestic product | Yes | JPEG in the same edition; also JSON from the World Bank, but current vintage only |
| Provincial electricity consumption | Yes | JPEG, and only selected years per edition |
| Provincial rail freight | Yes | JPEG, one cross-section per edition |
| Provincial bank credit | Only as prose | PDF summaries, rounded to about two significant figures, no 2016 edition |
| Nightlights | Yes | 34 GeoTIFFs, 1.09 GB, CC BY 4.0, anonymous. **But no provincial boundary source is registered**, so there is no provincial series |

The registry's most useful negative: provincial bank credit is not published as a table
anywhere free, confirmed three independent ways. That is a finding about the data, and it
constrains what any credit-based test can claim.

## What is here

```
src/china/
  acquire/     22 acquirers over 7 modules; blocked and gated sources get none, by design
  clean/       the tidy panel, the province list, and loaders for what is machine-readable
  analysis/    five modules of STUBS. Every function raises NotImplementedError
docs/          research question, known traps, validation anchors, data dictionary
data/          SOURCES.yaml (37 entries) and ACCESS_NOTES.md
tests/         129 tests, no network, synthetic fixtures only
```

The panel is `province, year, series, value, unit, vintage, source_id`, keyed on
`(province, year, series, **vintage**)`. The vintage column is not bookkeeping: revisions
overwrite history, so the anchor is only visible in a pre-revision vintage, and the same
province-year legitimately holds several values. A panel without it keeps whichever was loaded
last. See [docs/data_dictionary.md](docs/data_dictionary.md).

## The five tests, and the one date that decides one of them

`src/china/analysis/` fixes the signatures. **No analysis has been run and no findings exist
in this tree.**

1. `gap` - the provincial sum minus national gap, in nominal levels and in real growth
   separately, and its reconciliation against the national total to say **which** province.
2. `reform` - the discontinuity at the accounting reform. Verified from the bureau's own
   question-and-answer page: the plan was approved in June 2017, unified accounting was
   implemented in early 2020, and the first data year computed under it was **2019**. So the
   break is at the **2019 data year**, not the 2017 approval. Using 2017 tests a different and
   much weaker hypothesis, and doing so by accident is the most likely way to get a wrong
   answer that looks right. `REFORM_FIRST_DATA_YEAR = 2019` is asserted in the test suite.
3. `proxies` - provincial product against electricity, rail freight, credit and nightlights.
4. `dispersion` - underdispersion of provincial growth against a proxy-implied variance floor.
5. `bunching` - excess mass at the provincial growth target.

Two of these carry a caveat that has to travel with any result they ever produce. The proxy
residual and the bunching estimate cannot separate a province that fabricated its report from
one that genuinely managed credit and construction to hit its target; only the combination
can, and only weakly. And the sample is roughly 31 provinces over about a decade, so the
bunching and discontinuity tests may have no power at all. Establishing that is itself a
result and should be reported, not worked around.

## Ground truth, and its fine print

Three admitted episodes: Liaoning (2011 to 2014), Inner Mongolia (2016) and Tianjin (2016).
Read [docs/validation_anchors.md](docs/validation_anchors.md) before using any of them as a
label. Liaoning's admission concerned **fiscal** data, not gross product. The Tianjin revision
was of **Binhai New Area**, a sub-provincial development zone, so a provincial series absorbs
only part of it. Three positives, two of which are not gross-product labels, can corroborate a
detector but cannot score one; the scoring happens in the shared harness against the
`elections` and `aaer` projects.

## Running it

```sh
# from the repository root
uv run python -m china.acquire --list              # the registry, marked
uv run python -m china.acquire --all --dry-run     # what would be attempted; no requests
uv run python -m china.acquire --all               # needs the contact string first
uv run pytest -q projects/china/tests
```

On Windows, set `PYTHONIOENCODING=utf-8` first: several registry names are in Chinese and the
shared runner prints them to a cp1252 console.

Each yearbook table acquirer fetches the 21 English contents frames, one per edition from
2005 to 2025, before any table, because a table is located by its printed title in the
edition's own menu rather than by a guessed file name. The `csy_web_editions` acquirer is
bigger than that prelude: it takes the frameset and the contents frame for every edition in
both languages, 84 pages. The run also crawls roughly 660 central bank PDFs, on the order of
170 MB, over the twenty report years the index lists (2004-2015 and 2017-2024). It does
**not** fetch the 1.09 GB of nightlight rasters; that needs `CHINA_ACQUIRE_NIGHTLIGHTS=1`.

## Current state

Scaffolded. The registry, access notes, data dictionary and validation anchors are written
from verified fetches; the acquisition modules are in place and their wiring is proved by
`--list` and `--all --dry-run`; the loaders for everything machine-readable are implemented
and tested against synthetic fixtures. `src/china/analysis/` holds stubs with fixed signatures
only. Nothing has been fetched, no panel exists, and no number in this tree is a result.

## Next actions

1. Fill in the contact string in `config/forensics.toml`. Nothing fetches until you do.
2. `make data`, then read the failures. That run is also the check on the sixteen
   never-independently-verified registry entries and on the digests pinned in
   `china.acquire.yearbook`. Afterwards read digests from `data/fetch_log.jsonl`, not from
   `data/SOURCES.yaml`.
3. Choose the extraction back end for the yearbook images and gate it on the arithmetic checks
   in `docs/data_dictionary.md` section 6. This is the critical path.
4. Reproduce the provincial sum against the national total, year by year, in nominal levels
   and in real growth separately, and print it before any inference. If the gap does not
   appear at all, the vintages or the deflators are wrong, not the hypothesis.

## Open questions a person has to settle

- **Is a mainland vantage point in scope?** If it is, the portal's values endpoint can be
  captured from a browser's network panel in minutes, and the image-extraction problem may
  become optional. If it is not, the images are the project. This single decision changes the
  shape of everything downstream.
- **Where do provincial growth targets come from?** They are announced in provincial
  government work reports, one province a year, and there is no source for them in the
  registry. Without one, the bunching test can only scan round numbers.
- **Where does a provincial boundary file come from?** Nightlights are free and downloadable
  and completely unusable without one. Do not solve this by reaching for the nearest
  shapefile; register a source.
- **What are the 31 Chinese province names as the central bank publishes them?** The loader
  extracts the published name mechanically and then refuses to map it, because no
  Chinese-to-English province table in this project was read from a source. Build it once from
  a fetched report page and record it.
- **Is there any free source for cross-province double counting, or for provincial
  deflators?** Neither is in the registry. Until they are, the mechanical component of the gap
  cannot be estimated and the residual is an upper bound on misreporting, which is how it must
  be reported.

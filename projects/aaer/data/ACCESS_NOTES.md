# Access notes - aaer

What is free, what costs money, what needs an institution, and what nobody has confirmed.
Every claim here has a corresponding entry in `SOURCES.yaml`; once `make data` has run, every
attempt also has a line in `fetch_log.jsonl`. Nothing below is an inference about a source that
was not actually probed, and where a probe did not happen it says so.

## Summary

| Registry status | Count |
|---|---|
| Verified (reached, and the content confirmed to be what it claims) | 33 |
| Partial (landing page or part of the dataset reached; the rest not confirmed) | 4 |
| Blocked (exists, cannot be fetched from here) | 2 |
| Unverified (existence never confirmed) | 3 |
| **Total** | **42** |

| Access tier | Count |
|---|---|
| Free | 34 |
| Paywalled (money or an institutional subscription) | 6 |
| Registration (an account, terms not established) | 2 |

28 sources have an acquirer and are fetched by `python -m aaer.acquire --all`. 8 need a human.
6 have no acquirer: **5 are free and reachable and are deliberately left alone**, and **1 was
refuted** by verification (HTTP 404, the URL does not exist). The reasons are in
[Free or refuted: no acquirer, and why](#free-or-refuted-no-acquirer-and-why).

An independent verification pass re-fetched and **confirmed 25** entries, **refuted 1**, and
did not run on **16**. The 16 unchecked entries include most of the Bao et al. replication
files, so treat their recorded row counts as first-pass claims rather than as double-checked
facts until the files are on disk and counted locally.

## The bottleneck, stated in numbers

**The free structured-financials path and the labelled period barely overlap.**

- The SEC Financial Statement Data Sets begin at **2009q1**, and that quarter is an empty
  placeholder by design: its documentation says the file "contains data sets with column
  headings only and no rows", and unzipping it confirms 0 submissions and 0 numeric facts. The
  **first quarter with rows is 2009q2**, with 22 submissions. Scope is filings submitted from
  **15 April 2009** onward. Nothing earlier exists in this series at any price.
- The labelled violations are from the 1990s and 2000s. In the Bao et al. label file, **1,283
  of 1,746 firm-year labels fall in 1991-2008 and only 179 fall in 2009 or later**, with the
  peak years 1999-2003 (116, 139, 135, 119, 101 labels).
- In their analysis file, **2009 onward holds 112 positives across 33,064 firm-years**, against
  964 positives across 146,045 firm-years in total.

So: on the free SEC path, roughly **12 per cent of the labelled positives** are reachable, in a
different enforcement regime from the one the published benchmark was built on. This is a
constraint on the project, not a defect in the scaffolding, and it forces a decision that
`docs/research_question.md` sets out.

**There is a way around it, and it is free, but it is partial.** The Bao et al. replication
CSV ships 28 raw Compustat annual items for 146,045 firm-years covering fiscal years 1990-2014
with the labels attached, so **reproducing their benchmark needs no Compustat subscription**.

Computing the Beneish M-score from the same file is a weaker story. Three of the twelve inputs
`aaer.features.beneish` needs are absent: `xsga` (so SGAI is impossible), `ppent` (the file
carries gross `ppegt`, and `xbrl_map` refuses a gross-for-net substitution, so AQI and DEPI are
impossible), and `oancf` (so TATA needs the balance-sheet definition, which is the one Beneish
(1999) actually uses). That leaves **four of the eight components as shipped, five with a
balance-sheet TATA**. The file also stops at fiscal 2014.

## Free and acquirable now

Fetched by `python -m aaer.acquire --all`. Fill in `contact` in `config/forensics.toml` first:
every fetcher refuses to run while it holds the placeholder.

**SEC enforcement releases.** The AAER listing at
`www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases`, 3,342 rows over
34 pages of 100, addressed by `?page=N`. Each row carries a date, respondent, release numbers
and a link to the order PDF. The RSS feed carries only the 10 newest items and does **not**
include AAER numbers, so it is an incremental trigger, not a backfill route. The ~3,342
individual PDFs are roughly 0.5-1 GB in total and are not downloaded by `--all`; drive that
from the parsed listing table when the label set is actually needed.

**SEC Financial Statement Data Sets.** About 69 quarterly zips from 2009q2 to 2026q2, 145 KB to
~120 MB each, several GB in total, each holding `sub.txt`, `num.txt`, `pre.txt`, `tag.txt` and
`readme.htm`. Plus the empty 2009q1 placeholder and the documentation PDF.

**The Bao et al. (2020) replication repository.** Ten files, of which this project takes six:
the 47.8 MB analysis CSV, the 33 KB label file, `identifiers.csv` (the CIK-to-gvkey bridge,
without which the other two cannot be joined), the README, the JAR datasheet, and the SAS
coding document. The repository has **no LICENSE file**: treat redistribution as
all-rights-reserved and cite Bao et al. (2020), as the README asks.

**The papers.** Beneish (1999) as a working-paper PDF from a third-party mirror; both Walker
*Econ Journal Watch* papers; the Crossref records for the JAR article and its erratum; the
authors' EJW response page.

**The SEC access-policy pages**, kept as dated evidence of the rule the fetchers obey.

## SEC fair-access policy

Not optional, and not something this project decided:

- **10 requests per second**, total, across all machines. Stated on the *Accessing EDGAR Data*
  page ("Current max request rate: 10 requests/second."), in the Webmaster FAQ, and in the
  27 July 2021 announcement ("regardless of the number of machines used to submit requests").
- **A descriptive `User-Agent` containing a contact address**, in the form
  `Sample Company Name AdminContact@<sample company domain>.com`, plus
  `Accept-Encoding: gzip, deflate`.

This is enforced. A HEAD request with a generic `User-Agent` was answered with **HTTP 403 by
Akamai** during scaffolding. `config/forensics.toml` sets the SEC hosts to 4 requests per
second, below the ceiling, and `forensics_core.provenance.fetch` refuses to make any request at
all until the contact string is real.

## Paywalled: money, and how much is not published

### The curated AAER dataset must be bought, not requested

The **Dechow, Ge, Larson & Sloan (2011) AAER Dataset**, hosted by the USC Leventhal School of
Accounting, covers **4,278 AAERs and 1,816 firm misstatement events issued between 17 May 1982
and 31 December 2021**, of which 1,087 affect at least one quarterly or annual financial
statement. It ships as three files: Details (one row per misstatement event, with firm
identifiers, AAER numbers, reason and accounts affected), Annual, and Quarterly.

**This is a purchase.** The site's "Buy the Data" page links a USC CashNet storefront at
`https://commerce.cashnet.com/LEVAAER`. That storefront was reached during verification and
**redirects immediately to a login page with no price visible**, so the cost is not known and
is not stated anywhere on the public site. There is no free registration, no academic
application form, and no eligibility rule published. Describing this source as "registration"
would be wrong.

The Terms of Use forbid sharing: "You may not reveal, disclose, transfer or share the dataset
with anyone, with the exclusion of co-authors of papers and collaborators of projects properly
citing use of the dataset." So the files must never be committed to a repository. Use of the
data requires citing Dechow, Ge, Larson & Sloan (2011), *Contemporary Accounting Research*
28: 17-82.

**What a human does:** open the CashNet storefront and complete the purchase; if the price or
eligibility is unclear, email `USCLeventhal.AAER.Data@marshall.usc.edu` from an institutional
address stating affiliation and intended use. Delivery mechanism after purchase is not stated
on the site.

### Compustat is an institutional subscription, and CMU's coverage is unconfirmed

**Compustat Fundamentals Annual** is reached through WRDS. Access is entirely institutional:
no page on the WRDS site offers it to individuals. The registration form's institution
dropdown holds 523 subscribing institutions and **"Carnegie Mellon University" is one of
them**, as `<option value='18'>`.

**But that is not the same as saying CMU has Compustat.** WRDS is a platform with per-dataset
subscriptions, and **whether CMU's subscription includes Compustat Fundamentals Annual is not
visible without logging in**. It was not checked, and this document does not claim either way.

Account types, from the WRDS page: standing permanent faculty, current PhD candidates,
research assistants working for a faculty member at the same institution, full-time master's
and undergraduate students (no disk storage, disabled between semesters), visiting faculty, and
class accounts set up by a faculty member.

**What a human does:** register at `https://wrds-www.wharton.upenn.edu/register/` choosing
Carnegie Mellon University and the matching user type, with an `@andrew.cmu.edu` address; the
request goes to CMU's WRDS representative for approval; **then confirm that `comp.funda` is in
the subscription** before planning anything around it. Compustat extracts must never be
committed to a public repository.

### Paywalled publisher pages

- **Beneish (1999)**, *Financial Analysts Journal* 55(5): 24-36. `doi.org` resolves to
  tandfonline.com, which returned **HTTP 403** with a bot-block page. The working-paper version
  is free and is what the coefficients in `aaer.features.beneish` were read from; the typeset
  version has not been read by anyone on this project.
- **The 2022 erratum**, *JAR* 60(4): 1635-1646. Wiley returned **HTTP 403**. Its Crossref
  record is free and confirms the erratum exists and what it corrects, but the numbers this
  project treats as its Tier 1 target were read from Walker (2022) quoting it, not from the
  erratum itself. `docs/validation_anchors.md` marks that TO CONFIRM. **Getting this PDF
  through the university subscription is the single highest-value human action available.**

## Registration: two vendors, and neither can be used yet

Both are marked `partial` because the thing that matters about them could not be established.

- **Financial Modeling Prep.** The developer docs load, but the pricing page returned
  **HTTP 403** to a scripted client and the docs state no history depth anywhere. Every
  endpoint needs an API key. Whether the free tier reaches back to 1990 is **unknown**, and the
  registry explicitly refuses to guess.
- **SimFin.** The homepage loads; the pricing page returned **HTTP 500** with a page titled
  "simfin error"; the bulk-download path returned 404; the v3 API returned 401 without a key.
  Coverage years are **undeterminable without registering**.

**What a human does, for either:** register, read the current plan terms, and answer one
question before any code is written - what is the earliest fiscal year the free tier returns
for a test ticker? If it does not reach 1990, the vendor is useless for this project. Also
check whether redistribution of derived data is permitted.

## Free or refuted: no acquirer, and why

Six entries have no acquirer. **Five are free and reachable** and are left alone on purpose;
**one is refuted** - `sec_fsds_archive_page`, whose URL returns HTTP 404 and does not exist, so
"reachable" would be the wrong word for it. The runner reports all six so the gap is visible.

**Free and reachable, deliberately not acquired (5):**

- **`hf_edgar_corpus`** - a real, Apache-2.0, 1993-2020 academic redistribution of EDGAR 10-K
  **section text**. It covers the pre-2009 gap in years but not in kind: it is prose, not
  structured financials, and cannot substitute for Compustat. Worth acquiring if the project
  ever grows a textual-features arm; 84 jsonl files, total size never measured.
- **`sec_edgar_fullindex_1994q3`** - proves a free pre-2009 path exists at the *filing* level.
  But pre-XBRL 10-Ks are untagged ASCII and HTML: extracting 28 line items from 1994-2008
  filings is an NLP research project with unquantified error rates, not an acquisition step,
  and the complete submission texts run to hundreds of gigabytes.
- **`sec_efts_fulltext_search`** - the registry URL is one ad-hoc query against the full-text
  search backend, not a dataset. Its pagination parameters were never verified, and it indexes
  only filings since 2001.
- **`wikipedia_beneish_mscore`** - a secondary corroboration of the eight-variable formula. Its
  own registry entry says "Not needed for acquisition; reference only", and its byte count
  already drifted between two probes.
- **`jar_online_supplements_page`** - a case-insensitive search of the served HTML for "Bao" or
  "Detecting Accounting Fraud" returns **zero matches**, so the supplement is not reachable
  from it. The GitHub repository carries the same files.
**Refuted, so not reachable at all (1):**

- **`sec_fsds_archive_page`** - **refuted during verification**: the URL returns HTTP 404 and
  does not exist. It is kept in the registry with status `unverified` rather than deleted, so
  that the next person who finds the same search result does not repeat the attempt.

## Actions requiring a human, in priority order

1. **Get the 2022 erratum PDF** through the university subscription
   (`https://doi.org/10.1111/1475-679X.12454`) and replace the Tier 1 table in
   `docs/validation_anchors.md` with figures read from it directly. Everything the project is
   currently aiming at was read second-hand from a critic quoting it.
2. **Decide the data path.** Free SEC 2009+, with about 12 per cent of the positives and a
   different enforcement regime; or the Bao et al. CSV, which is free, covers 1990-2014, and is
   what the benchmark itself used, but has no `xsga` and stops in 2014; or buy the curated AAER
   dataset and obtain Compustat. The three are not exclusive, and the choice belongs to the
   owner, not to the code.
3. **Confirm the XBRL tag mapping.** Eleven of the twelve mappings in `aaer.clean.xbrl_map` are
   the implementer's assumption. One quarter of acquired data and
   `aaer.clean.xbrl_map.tag_frequency` settles most of them in an afternoon. Until then, no
   number computed from the SEC path means anything. See `docs/data_dictionary.md`.
4. **Check whether CMU's WRDS subscription includes Compustat Fundamentals Annual.** One login
   answers it. Do this before planning any work that assumes Compustat.
5. **Price the curated AAER dataset** at the CashNet storefront, so that step 2 can be decided
   with a number rather than a shrug.
6. **Optional:** register with FMP or SimFin only to answer the earliest-year question. If
   neither reaches 1990, close both out.

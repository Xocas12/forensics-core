# aaer

**Question.** Reproduce the Beneish M-score baseline and the published machine-learning
benchmark for detecting accounting misstatement, using SEC Accounting and Auditing Enforcement
Releases as labels.

This is the calibration project for supervised and positive-unlabeled learning and for
rank-metric evaluation under a base rate under 1 per cent. Its labels are real but *selected*:
they record what the SEC chose to prosecute, not what firms did. Learning how much that
selection costs is the point, and it is the part that transfers to `gosplan`, where the
selection cannot be measured at all.

| | |
|---|---|
| Unit of observation | Firm-year |
| Labels | SEC AAERs, 3,342 releases as of the last probe |
| Published benchmark | Bao, Ke, Li, Yu & Zhang (2020), *JAR* 58(1), **as corrected by the 2022 erratum** |
| Ground truth | Real but selected: enforcement, not misstatement |
| Blocked on a human? | **No, but a decision is needed** |

## Data status

**Acquirable and free**, with one large caveat about coverage.

| Registry status | Count |
|---|---|
| Verified | 33 |
| Partial | 4 |
| Blocked | 2 |
| Unverified | 3 |

The registry is [data/SOURCES.yaml](data/SOURCES.yaml), 42 entries. Nothing enters a pipeline
without an entry there. 28 have an acquirer; 8 need a human; 6 have none - **5 free and
reachable, deliberately left without one, and 1 refuted** (HTTP 404, the URL does not exist) -
with the reason for each in [data/ACCESS_NOTES.md](data/ACCESS_NOTES.md).

An independent second pass confirmed 25 entries, refuted 1 (a Financial Statement Data Sets
"archive" URL that returns 404 and does not exist), and did not run on 16. Most of the Bao et
al. replication files are in that unchecked 16.

## The constraint that decides the project

**The free structured-financials path and the labelled period barely overlap.**

- SEC Financial Statement Data Sets begin at **2009q1**, and that file is empty by design - its
  own documentation says it "contains data sets with column headings only and no rows". The
  first quarter with rows is **2009q2**. Scope starts with filings submitted 15 April 2009.
- The labelled violations are from the 1990s and 2000s. Of 1,746 firm-year labels in the Bao et
  al. file, **1,283 fall in 1991-2008 and 179 in 2009 or later**. In their analysis file,
  fiscal 2009 onward holds **112 positives across 33,064 firm-years** against 964 across
  146,045 in total.
- So the free SEC path reaches roughly **12 per cent of the labelled positives**, in a
  different enforcement regime from the one the benchmark was built on.

**There is a free way around it, but a partial one.** The Bao et al. replication CSV ships 28
raw Compustat annual items for 146,045 firm-years, fiscal 1990-2014, labels attached, so
reproducing their benchmark needs no Compustat subscription. Computing the Beneish M-score
from it is a different matter. Of the twelve inputs `aaer.features.beneish` needs, three are
absent: `xsga`, `ppent` (the file has `ppegt`, which is *gross* PP&E, and `xbrl_map` refuses a
gross-for-net substitution), and `oancf`.

| Beneish component | From this file? | Blocked by |
|---|---|---|
| DSRI, GMI, SGI, LVGI | yes | |
| TATA | only with the balance-sheet definition Beneish (1999) actually uses | `oancf` absent |
| AQI, DEPI | no | `ppent` absent; only gross `ppegt` is shipped |
| SGAI | no | `xsga` absent |

So the file supports **four of the eight components as shipped, five with a balance-sheet
TATA** - not seven. It also stops at fiscal 2014.

The curated Dechow, Ge, Larson & Sloan AAER dataset (4,278 releases, 1,816 misstatement events,
1982-2021) must be **purchased** - there is a CashNet storefront and no published price, not a
free registration. Compustat via WRDS is an institutional subscription; Carnegie Mellon appears
in the WRDS institution list, but **whether that subscription includes Compustat Fundamentals
Annual could not be seen without logging in**. Both are set out precisely in
[data/ACCESS_NOTES.md](data/ACCESS_NOTES.md).

## What must be reproduced

Targets and their provenance are in [docs/validation_anchors.md](docs/validation_anchors.md).

1. **Tier 0 - the Beneish arithmetic.** The eight coefficients and the intercept in
   `aaer.features.beneish` were confirmed against Table 3 Panel A, unweighted probit row, of the
   June 1999 working paper. The -1.78 threshold is not a constant of nature: it encodes an
   assumed 20:1 or 30:1 cost ratio, and at 10:1 the paper gives -1.49. Any table that flags at
   -1.78 must say which assumption it is making.
2. **Tier 1 - the corrected benchmark.** AUC 0.7428 and NDCG@1% 0.0394 for 2003-2005, AUC
   0.7228 and NDCG@1% 0.0237 for 2003-2008. **The original published figures are not the
   target; the erratum's are.** And these were read from Walker (2022) in *Econ Journal Watch*
   quoting the erratum, because the erratum itself is paywalled and Wiley returns 403 to
   scripts. Walker's own re-runs got 8 hits in both windows rather than 9 and 10. Getting that
   PDF through the university subscription is the highest-value human action open to this
   project.

## The trap that decides the analysis

**Unflagged firm-years are unlabeled, not clean.** The SEC prosecutes what is detectable, large
and litigable. Treating the 145,081 unflagged rows as negatives tells a classifier that every
undetected misstatement is an example of honesty, and what it then learns to predict is
enforcement. Hence the positive-unlabeled formulation, and hence rank metrics with the base
rate printed beside them: at 0.66% positives, a model that flags nothing is 99.3% accurate.
This and six other confounds are in [docs/known_traps.md](docs/known_traps.md).

## The weakest link, named

`aaer.clean.xbrl_map` maps us-gaap tags to the twelve items the Beneish indices need.
**Eleven of the twelve mappings are unconfirmed.** Exactly one element name in the table -
`AccountsReceivableNetCurrent` - was observed in a response actually fetched from the SEC; the
rest are the implementer's knowledge of the taxonomy, written down and flagged as assumptions.
Three selection rules (the meaning of `qtrs`, the `ddate == period` convention, and the
exclusion of filer extension tags) are unconfirmed too.

The loader is built to make that visible: `map_beneish_items` returns per-step loss counts,
per-item coverage with the tag that actually supplied each value, and an explicit list of items
that matched nothing. `tag_frequency` checks the mapping against a downloaded quarter in one
call. Until that check is run, no number computed from the SEC path means anything. See
[docs/data_dictionary.md](docs/data_dictionary.md).

## Layout

```
src/aaer/
  acquire/     registry-driven downloads; one module per source family
  clean/       listing HTML -> release table; FSDS zips -> SUB/NUM/PRE/TAG -> the twelve items
  features/    beneish.py: complete, tested, coefficients confirmed. Do not change it casually.
  analysis/    STUBS ONLY. Fixed signatures, NotImplementedError bodies.
```

## Current state

Scaffolded. The registry, access notes, data dictionary and validation anchors are written from
verified fetches; the acquisition and cleaning code is in place and tested against synthetic
fixtures.

**No analysis has been run and no finding exists in this tree.** `src/aaer/analysis/` holds
stubs, and `tests/test_analysis_stubs.py` fails if any of them stops being one. Nothing has been
downloaded either: `data/raw`, `data/interim` and `data/processed` are empty, and the tests use
only `tests/fixtures/synthetic_*`.

## Next actions

1. Put a real contact string in `config/forensics.toml`. Every fetcher refuses to run while it
   holds the placeholder, because the SEC requires a descriptive `User-Agent` with a contact
   address and enforces 10 requests per second.
2. `python -m aaer.acquire --list` to see the registry, then `--all --dry-run` to see the plan.
   **Read the dry run knowing that it understates three entries.** It prints one line per
   source carrying that source's registry URL, and three acquirers fetch a family of files
   under one id, which the line cannot show:
   - `sec_fsds_quarterly_zips` shows as one `2009q2.zip` but requests **about 69 quarterly
     zips**, 145 KB to ~120 MB each, **several GB in total**;
   - `aaer_listing_secgov` shows as one page but requests **34 listing pages** at the last
     count, and more as releases are added (page 0 is re-fetched on every run so the count is
     re-read; the rest are skipped when already held);
   - `jarfraud_github_repo` shows as one URL but requests **3 files**, the largest being the
     1.6 MB `identifiers.csv`.

   Everything else is one request per line. This is a limitation of the shared runner in
   `forensics_core.provenance.runner`, not of this project's registry. To start smaller, run
   `python -m aaer.acquire bao_analysis_csv bao_labels_csv jarfraud_github_repo`.
3. **Confirm the tag mapping** against one downloaded quarter with
   `aaer.clean.xbrl_map.tag_frequency`, and correct `BENEISH_TAG_MAP`. Do this before anything
   else that touches the SEC path.
4. **Decide the data path**: free SEC 2009+, the Bao et al. CSV, or buy the curated dataset and
   get Compustat. `docs/research_question.md` states the trade-off; the choice is the owner's.
5. Solve the label join. The AAER listing gives a respondent name, not a CIK.
6. Get the erratum PDF and replace the Tier 1 table with figures read from it directly.
7. Only then implement `analysis/beneish_baseline.py`, and report the base rate next to every
   number.

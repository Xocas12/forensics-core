# Data dictionary - aaer

Three vocabularies meet in this project and none of them agrees with the others: the SEC's XBRL
taxonomy, Compustat's item codes, and the twelve names that `aaer.features.beneish` wants. This
file is the translation table, and it is explicit about which rows of it are known and which are
assumed.

Read the honesty summary first.

> **Eleven of the twelve XBRL mappings below are unconfirmed.** Exactly one us-gaap element
> name used by this project was observed in a response actually fetched from the SEC during
> scaffolding. Every other element name is the implementer's knowledge of the taxonomy written
> down, and has not been checked against a real filing. No number computed from the SEC path
> means anything until they are checked, and checking them takes one downloaded quarter and one
> function call.

---

## 1. The twelve Beneish items

`aaer.features.beneish.REQUIRED_COLUMNS` fixes the names. Ten of them are also needed for year
`t-1`, as `<item>_lag` (`LAGGED_COLUMNS`); income from continuing operations and cash from
operations are flows of year `t` only, because TATA has no lagged term.

| Item | Enters | Balance-sheet or flow | Compustat item used in the literature |
|---|---|---|---|
| `receivables` | DSRI | stock | `rect` |
| `sales` | DSRI, GMI, SGI, SGAI | flow | `sale` |
| `cogs` | GMI | flow | `cogs` |
| `current_assets` | AQI | stock | `act` |
| `ppe_net` | AQI, DEPI | stock | `ppent` |
| `total_assets` | AQI, LVGI, TATA | stock | `at` |
| `depreciation` | DEPI | flow | `dp` |
| `sga` | SGAI | flow | `xsga` |
| `long_term_debt` | LVGI | stock | `dltt` |
| `current_liabilities` | LVGI | stock | `lct` |
| `income_continuing_ops` | TATA | flow | `ib` |
| `cash_from_operations` | TATA | flow | `oancf` |

The Compustat column is context, not a mapping this project uses: the free paths are the SEC
data sets and the Bao et al. CSV. It is here because the published literature is written in
those item codes and a replication argument has to be conducted in them.

## 2. XBRL tag candidates, and their confirmation status

Defined in `aaer.clean.xbrl_map.BENEISH_TAG_MAP`, one entry per item, tags in priority order
(first one present for a filing wins). `mapping_table()` returns the same content as a frame.

**Legend.** *Seen* = the element name appeared in a response fetched from the SEC and recorded
in `data/SOURCES.yaml`. *Assumed* = the implementer's knowledge of the us-gaap taxonomy,
unverified in this project.

| Item | Candidate tags, in priority order | Status | The specific doubt |
|---|---|---|---|
| `receivables` | `AccountsReceivableNetCurrent`, `ReceivablesNetCurrent`, `AccountsReceivableGrossCurrent` | **Seen** (first tag) | Which of the three filers actually use; net vs gross of allowance (Beneish uses net) |
| `sales` | `RevenueFromContractWithCustomerExcludingAssessedTax`, `...IncludingAssessedTax`, `Revenues`, `SalesRevenueNet`, `SalesRevenueGoodsNet`, `SalesRevenueServicesNet` | Assumed | The dominant element changed with the ASC 606 revenue standard, so quarters before and after roughly 2018 use different tags for the same quantity. The priority order puts post-606 first, which biases filings that report both. **The riskiest row in the table.** |
| `cogs` | `CostOfGoodsAndServicesSold`, `CostOfRevenue`, `CostOfGoodsSold`, `CostOfServices` | Assumed | These are not the same quantity for firms with a service segment, and GMI is a ratio of ratios, so a tag switch between `t-1` and `t` fabricates an index far from 1 |
| `current_assets` | `AssetsCurrent` | Assumed | Firms with an unclassified balance sheet (banks, insurers, some REITs) report no current/noncurrent split, so this is missing for an entire industry block, not at random |
| `ppe_net` | `PropertyPlantAndEquipmentNet` | Assumed | No gross-PP&E fallback is listed on purpose: substituting gross for net changes the quantity |
| `total_assets` | `Assets` | Assumed | Least likely row to be wrong. It is the denominator of AQI, LVGI and TATA, so losing it costs three of the eight components |
| `depreciation` | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, `Depreciation` | Assumed | DEPI wants depreciation *excluding* amortisation; the first two candidates include it. Compustat `dp` also combines them, so this may be the right kind of wrong for comparability - state which is used |
| `sga` | `SellingGeneralAndAdministrativeExpense`, `GeneralAndAdministrativeExpense` | Assumed | Most likely to be simply absent: many filers report only `OperatingExpenses` or split the costs across custom tags |
| `long_term_debt` | `LongTermDebtNoncurrent`, `LongTermDebt`, `LongTermDebtAndCapitalLeaseObligations` | Assumed | `LongTermDebt` includes the current portion, `LongTermDebtNoncurrent` excludes it; LVGI pairs long-term debt with current liabilities, so the wrong choice double-counts. Whether ASC 842 operating-lease liabilities (2019 onward) belong here is unresolved |
| `current_liabilities` | `LiabilitiesCurrent` | Assumed | Same unclassified-balance-sheet problem as `current_assets`, missing for the same filers, so the two gaps are perfectly correlated |
| `income_continuing_ops` | `IncomeLossFromContinuingOperations`, `IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest`, `ProfitLoss`, `NetIncomeLoss` | Assumed | The last two are **not** income from continuing operations. They coincide only for firms with no discontinued operations - which is exactly not the population where restructuring and manipulation cluster. Consider dropping the fallbacks and accepting the missingness |
| `cash_from_operations` | `NetCashProvidedByUsedInOperatingActivities`, `...ContinuingOperations` | Assumed | Needed only because `beneish.tata` implements the cash-flow definition of accruals. Beneish (1999) computes them from balance-sheet changes and needs no cash-flow item at all; switching TATA is the cheaper fix if this mapping proves unreliable |

### Three selection rules that are also unconfirmed

1. **`qtrs`.** The loader assumes `qtrs == 0` marks a point-in-time (balance sheet) fact and
   `qtrs == 4` a four-quarter (annual) duration. That convention is defined in **section 5.3 of
   the Financial Statement Data Sets documentation PDF, which was not read** during scaffolding
   - only its section headings and the NUM primary key were. `python -m aaer.acquire
   sec_fsds_readme` downloads it; confirm before trusting any flow item.
2. **`ddate == sub.period`.** The current year's figure is taken to be the fact dated at the
   filing's own period end, which discards the prior-year comparatives the same filing carries.
   That is deliberate - comparatives are *restated* values and using them for `t-1` would mix
   vintages silently - but it means the lag has to come from the previous year's own filing, so
   a firm's first XBRL year has no lag at all.
3. **`version` beginning with `us-gaap`.** Filer extension tags are excluded this way.
   `TAG.custom` is the authoritative flag and is the better test once the TAG table is loaded.

### How to confirm the mapping

```python
from aaer.clean.fsds import read_fsds_zip
from aaer.clean.xbrl_map import annual_submissions, tag_frequency

q = read_fsds_zip("data/raw/fsds/2015q1.zip")
annual = annual_submissions(q.sub)
print(tag_frequency(q.num, adsh=annual["adsh"], top=100))
```

Every row where `in_mapping` is false and the count is large is a tag this project should
probably know about. Repeat on an early quarter and a late one: the point is to see the tags
change over time, not to see one snapshot.

## 3. What the loader reports rather than hides

`aaer.clean.xbrl_map.map_beneish_items` returns a `MappingResult` whose whole purpose is the
loss accounting.

- **`steps`** - one row per pipeline stage with `n_rows`, `n_lost` and a note. The stages are:
  submissions in input; annual filings deduplicated to one per `(cik, fy)`; firm-years with at
  least one mapped fact; firm-years complete on all twelve items.
- **`item_coverage`** - per item: `confirmed`, `n_present`, `n_missing`, `share_present`, and
  `tags_used` (which candidate tag actually supplied the value, with counts). If `tags_used`
  shows a low-priority fallback dominating, the priority order is wrong.
- **`unmapped_items`** - items for which **no** candidate tag matched a single fact. This is
  reported, never dropped. An item that maps to nothing means the mapping is wrong, not that
  the item does not exist.
- `add_lags` returns `LagResult` with `n_input_rows`, `n_with_any_lag`, `n_with_all_lags`.

Nothing is imputed anywhere in this project. A firm-year missing an item keeps a `NaN`.

## 4. SEC Financial Statement Data Sets: the four tables

Confirmed by unzipping 2009q2 and re-confirmed independently. Format, quoting the documentation
PDF: "Tab Delimited Value (.txt): utf-8, tab-delimited, \n-terminated lines, with the first line
containing the column names in lowercase."

| Table | Key | Columns |
|---|---|---|
| `sub.txt` | `adsh` | `adsh, cik, name, sic, countryba, stprba, cityba, zipba, bas1, bas2, baph, countryma, stprma, cityma, zipma, mas1, mas2, countryinc, stprinc, ein, former, changed, afs, wksi, fye, form, period, fy, fp, filed, accepted, prevrpt, detail, instance, nciks, aciks` (36) |
| `num.txt` | `adsh, tag, version, ddate, qtrs, uom, segments, coreg` | those plus `value, footnote` (10) |
| `pre.txt` | `adsh, report, line` | those plus `stmt, inpth, rfile, tag, version, plabel, negating` (10) |
| `tag.txt` | `tag, version` | those plus `custom, abstract, datatype, iord, crdr, tlabel, doc` (9) |

Fields this project depends on: `sub.form` (`10-K` only), `sub.fp` (`FY`), `sub.fy`,
`sub.period`, `sub.filed` (breaks ties between amended filings), `sub.cik` (the firm key across
years - `adsh` is per filing and cannot be used for lagging), `num.uom` (`USD`), `num.segments`
and `num.coreg` (must be empty for a consolidated total), `num.qtrs`, `num.ddate`,
`num.version`, `tag.custom`.

`sub.prevrpt` is **not** used as a filter. Its exact meaning was not read from the
documentation, and filtering on a field whose semantics are guessed is how a panel silently
loses a fifth of its rows. Open question.

**Scale.** 2009q1 has zero rows by design. 2009q2 has 22 submissions and 4,000 numeric facts in
a 145 KB zip. Recent quarters are ~120 MB. The whole series 2009q2-2026q2 is 69 files and
several GB; `read_quarters` loads them into memory and `iter_fsds_zips` does not.

## 5. AAER labels

### 5.1 The listing, as parsed by `aaer.clean.aaer_releases`

One row per enforcement release. Columns (`RELEASE_COLUMNS`):

| Column | Type | Meaning |
|---|---|---|
| `aaer_number` | `Int64`, nullable | The AAER serial number, e.g. 4599. Null when the row carried a PDF link but no recognisable AAER number |
| `date` | `datetime64[ns]`, may be `NaT` | Release date, **not** the date of the misstatement |
| `respondent` | str | The party charged, as printed. May be several parties in one string |
| `release_numbers` | str | Securities Act / Exchange Act release numbers, `;`-separated. Only `33-` and `34-` prefixes were observed |
| `pdf_url` | str, may be null | Absolute URL of the order PDF |
| `source_file` | str | Which saved page the row came from |

The listing reported **3,342 items over 34 pages** when it was probed. The parser was developed
against a synthetic fixture and has **not been run against a real page**; check
`ListingParse.n_dropped` and `n_rows_seen` before trusting its output.

**What the listing does not give you: a CIK.** The respondent is a name. Joining the label side
to the financial side therefore requires either parsing the release PDFs, or the curated Dechow
et al. dataset, or the Bao et al. label file below. This join is an open task, not a solved one.

### 5.2 The release PDFs

Header lines are reliably extractable. From the one sample fetched, page 1 reads:

```
SECURITIES EXCHANGE ACT OF 1934 Release No. 106274 / September 3, 2026
ACCOUNTING AND AUDITING ENFORCEMENT Release No. 4599 / September 3, 2026
ADMINISTRATIVE PROCEEDING File No. 3-22701
In the Matter of PAUL FRENKIEL, Respondent.
```

So the AAER number, the release number, the proceeding file number and the respondent are all
extractable with a text-layer PDF reader. The **misstated fiscal years** and the **firm's CIK**
are not in the header and would have to come out of the body text.

### 5.3 The Bao et al. label file (`AAER_firm_year.csv`)

| Column | Meaning |
|---|---|
| `P_AAER` | Case identifier. Groups the firm-years of one enforcement case, which is how serial fraud is handled |
| `CIK` | SEC central index key of the firm |
| `YEARA` | Fiscal year **of the misstatement**, not of the release |
| `UNDERSTATEMENT` | 0 = overstatement (the class the paper models), 1 = understatement, and one row coded 3 |

1,746 rows, 716 distinct CIKs, 716 distinct `P_AAER`, `YEARA` from 1971 to 2015. 1,694 rows are
overstatements, 51 understatements, 1 coded 3. Labels are dense in 1999-2003 (116, 139, 135,
119, 101 per year) and thin afterwards: 1,283 rows fall in 1991-2008 and 179 in 2009 or later.

Provenance, from the repository README: AAERs compiled by the UC-Berkeley Center for Financial
Reporting and Management, covering announcements from 17 May 1982 to 30 September 2016,
hand-extended to 31 December 2018 (AAER #4012).

**This file is keyed on CIK. The analysis file is keyed on gvkey. `identifiers.csv` is the
bridge and both acquirers fetch it.**

### 5.4 The Bao et al. analysis file (`data_FraudDetection_JAR2020.csv`)

146,045 rows, fiscal years 1990-2014, 18,444 distinct `gvkey`, 46 columns:

- `fyear, gvkey, p_aaer, misstate` - keys and the label. `misstate = 1` on 964 rows spanning
  412 distinct `p_aaer`; `misstate = 0` on 145,081.
- 28 raw Compustat annual items: `act, ap, at, ceq, che, cogs, csho, dlc, dltis, dltt, dp, ib,
  invt, ivao, ivst, lct, lt, ni, ppegt, pstk, re, rect, sale, sstk, txp, txt, xint, prcc_f`.
- 14 derived ratios: `dch_wc, ch_rsst, dch_rec, dch_inv, soft_assets, ch_cs, ch_cm, ch_roa,
  issue, bm, dpi, reoa, EBIT, ch_fcf`.

**Two absences that matter.** `xsga` is not there, so **SGAI cannot be computed from this
file** - one of the eight Beneish components is simply unavailable on the free 1990-2014 path.
`oancf` is not there either, but Beneish (1999) defines TATA from balance-sheet changes, so
that one is a choice rather than a gap. Note also that `ppegt` is *gross* PP&E while AQI and
DEPI want net.

`EBIT` is the only capitalised column, and `at` is a SQL reserved word.

The file's sha256 pins the **post-erratum** version. If it stops matching, the repository has
been changed again and no comparison with the erratum's figures is valid until that is
investigated.

## 6. The base rate problem

Arithmetic on the counts recorded in `SOURCES.yaml`, not a result of any analysis:

| Population | Firm-years | Labelled positives | Share |
|---|---|---|---|
| Bao et al. analysis file, 1990-2014 | 146,045 | 964 | 0.66% |
| The same file, fiscal 2009 onward | 33,064 | 112 | 0.34% |

**Consequences, which are not optional.**

1. **Accuracy is meaningless.** A model that flags nothing is over 99% accurate on either row.
   Report rank metrics only - AUC, average precision, NDCG@k, precision@k - with the base rate
   printed next to them, following the published benchmark's own choice of NDCG at k = 1% of
   test firm-years.
2. **The zeros are not zeros.** An unflagged firm-year is one nobody charged, not one that was
   clean. Treating the 145,081 as negatives tells a classifier that every undetected
   misstatement is an example of honesty. Use the positive-unlabeled formulation
   (`forensics_core.labels.pu`); this project's `Dataset` objects encode unlabeled rows as
   `NaN`, not 0.
3. **Everything measured against these labels is prediction of enforcement**, not of
   misstatement. Say so in every table. The gap between the two is precisely the quantity that
   the `gosplan` project has no way to measure at all, which is why it is worth estimating here.
4. **The second row is the free SEC path.** Fewer positives, thinner base rate, and a different
   enforcement regime from the one the benchmark was built on.

## 7. Names that do not mean what they look like

- **`fy` vs the fiscal year of a violation.** `sub.fy` is the fiscal year of a *filing*.
  `YEARA` is the fiscal year of a *misstatement*. An AAER's release date is a third thing
  again, usually years later. Splits must use the violation year; letting a release issued
  after the test cutoff influence training is exactly the leakage the 2022 erratum was about.
- **`adsh` vs `cik`.** `adsh` identifies one filing; `cik` identifies the firm. Lagging and
  grouped splits use `cik`.
- **`p_aaer` vs `aaer_number`.** `p_aaer` is a *case* identifier in the Bao et al. files that
  groups the firm-years of one enforcement action. The AAER number on a release is a serial
  number of a document. One case can produce several releases.
- **`prcc_f`** is a price, not an accounting item; `bm` is a ratio built from it. Both are
  point-in-time market data mixed into an accounting panel.
- **`misstate` vs `UNDERSTATEMENT`.** `misstate` is the binary label. `UNDERSTATEMENT` is a
  direction flag on the raw label file; the paper models overstatements
  (`UNDERSTATEMENT == 0`).

## 8. Open questions

1. What is `sub.prevrpt` exactly, and should amended filings be excluded on it?
2. Does `qtrs == 4` mean what this project assumes? Section 5.3 of the FSDS README settles it.
3. Which revenue tag dominates in which years, and does the ASC 606 transition create a break
   in SGI that looks like a real change in sales growth?
4. How is a respondent name in the AAER listing turned into a CIK without buying a dataset?
5. Should `income_continuing_ops` keep its `NetIncomeLoss` fallback, or accept the missingness?
6. Do the SEC path and the Bao et al. path agree on the firm-years they share (fiscal
   2009-2014)? That comparison is the only free check available on the tag mapping's accuracy,
   and it should be run before either path is used alone.

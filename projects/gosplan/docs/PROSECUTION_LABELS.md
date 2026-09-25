# Prosecution labels: assessment of the Harrison plan-fraud dataset

**Verdict: undetermined. Treat it as context until the file is read, not as labels.** WO-505
writes no loader and builds no label set. The registry does not record whether a case can be
linked to any reported series the project holds. The card says that without that link the
dataset is context, not labels, and the card stops there. The open questions are in
`workorders/AMBIGUITY-WO-505-1.md`.

This document uses only what the registry and the whitelisted documents record. Every claim
about the file's contents comes from the `evidence` and `notes` fields of the
`harrison_plan_fraud` entry in `data/SOURCES.yaml`. Where those fields are silent, the answer
below says **not recorded**. It does not guess.

It is not a second anchor under any outcome of this assessment. The project's only anchor is
the one described in `docs/research_question.md` and sealed by `gosplan.seal`.

## What the registry records

From `harrison_plan_fraud` in `projects/gosplan/data/SOURCES.yaml`:

- The source is the replication dataset for Harrison, "Forging Success: Soviet Managers and
  Accounting Fraud, 1943 to 1962", *Journal of Comparative Economics* 39:1 (2011), pp. 43-64,
  as quoted from the landing page. The file is `dataset.xlsx`, 159,964 bytes, and its sha256
  is recorded.
- The workbook has three sheets: 'Fond R-9492 Case Index', 'Fond R-8131 Case Index' and
  'Fond 6 Case Index'.
- "Column headers **include** Establishment, Accused, #Accused, Where, Branch." This is not the
  full header list. The header row's position is not recorded, and the registry does not say
  which sheets have which columns.
- Three sample rows:
  - 'Mechanic Ishnazarov | Uzbekistan | Overstated ploughing by 93 hectares | 18 months LS'
  - 'Director Diuisekov | Reported 515 instead of 315 tons | Six years LS'
  - 'Planner Zavarnitsina and accountant Semenova | Bonuses for the artel, 8,847 rubles | Two
    years LS each'
- Notes: the file "includes Uzbek and Kazakh agricultural cases". The notes also describe it as
  recording "who falsified what, by how much, in which branch and republic, and what sentence
  followed". That note is a description written when the file was found. It is not a list of
  columns.

`verification.verdict` is `not_verified`. No local copy is recorded (`local_path: null`), and
the file has not been acquired into this repository.

## 1. What is the unit, and can it be linked to a series the project holds?

**Unit: a prosecution case in an archival case index.** Each sheet is named as the case index
of one archival fond. The recorded columns describe people and a place of work: Establishment,
Accused, #Accused, Where and Branch. The sample rows name individuals (a mechanic, a director,
a planner and an accountant) and one establishment, an artel. So the observation
is a case against one or more accused people at one establishment. It is not an enterprise-
year, a republic-year or a series value.

**Linkability to a reported series: undetermined, and doubtful on what is recorded.**

According to `docs/research_question.md`, the project's reported series are published
aggregates: sectoral sums, input-output balances, harvest and output series, and
plan-fulfilment percentages by sector, year and republic. The best link a case could have to
one of those series is a key made of three parts:

| Needed to link | What the registry records |
|---|---|
| Year of the case | **Not recorded.** No year column is named. The paper's title period (1943-1962) is a statement about the paper, not a field on each row. |
| Region, to match a republic series | Probably `Where`. The first sample row shows 'Uzbekistan', but the registry does not say which cell that value came from. |
| Sector, to match a sectoral series | Probably `Branch`. Its values are not recorded, and no mapping to the project's sector classification exists. |
| A quantity in the series' units | **Not recorded as a column.** The sample quantities are prose inside a cell: "Reported 515 instead of 315 tons", "Overstated ploughing by 93 hectares", "8,847 rubles". |

Even if all three key parts existed, the link would be weak in kind. A prosecuted
establishment sits inside a republic-by-branch aggregate. The strongest label it could give
that aggregate cell is "this cell contains at least one prosecuted falsification". That is not
the same as "this cell's reported value is distorted by a detectable amount". One
establishment's overstatement, such as the sample row's "515 instead of 315 tons", may be far
too small to move a republic total. Whether it can is a magnitude question, and nothing recorded answers
it.

A second route would train a detector at the unit of the case itself, comparing reported and
actual quantities for each establishment. That route needs a case-level feature set the
project does not hold. The project holds published aggregate series, not establishment
reports. It also needs reported and actual quantities as separate values, and the registry
shows them only as prose.

The registry cannot settle this question. Reading the file would settle it by showing:

1. the full header row of each sheet and its position (the gap WO-504 already reported in
   `workorders/AMBIGUITY-WO-504-4.md`);
2. whether any column records the year of the offence or of the case, and whether that is the
   year the misreporting refers to;
3. whether reported and actual quantities are separate columns, or appear only as prose, and
   in what units;
4. the distinct values of `Where` and `Branch`, set against the region and sector keys and
   the year coverage of the series the project actually holds for 1943-1962.

If (2) finds no year, or (4) finds no held series at the matching region, sector and year,
the verdict becomes final: **context, not labels.**

## 2. What does selection do here?

It does the same thing it does to the AAER labels, and it is probably stronger here.
`projects/aaer/docs/known_traps.md`, trap 1: enforcement "pursues cases that are detectable,
large and litigable", so a model trained on it "learns *what gets prosecuted*, not *what
happens*". Unflagged units are "**unlabeled, not negative**".

In this dataset, before a case appears in these rows, all of the following had to happen:

- **Detection.** An auditor or inspector found the discrepancy. That required someone with
  the access, and a reason, to compare a report with the underlying physical quantity.
- **A decision to prosecute.** Someone chose to take this case to court instead of settling
  it administratively or ignoring it. That choice was made in a particular period, under its
  own politics.
- **Archival survival and indexing.** The case is in one of three fonds, and it was entered in
  that fond's case index. The registry does not record how the fonds were chosen or how
  complete the indexes are.

Every one of these filters depends on the case's features: its size, its sector, its
region, how visible the falsified quantity was, and the political salience of the branch.
`forensics_core.labels.pu` corrects for unlabelled positives only under SCAR, where "labeled
positives are Selected Completely At Random among the true positives". The module's own
docstring says its estimates inherit that assumption. Prosecution selection breaks SCAR by
construction. So even if a label set were built:

- the estimated labelling frequency `c` and any class prior derived from it would be
  uninterpretable as rates of falsification;
- a detector's score would rank "resembles what got prosecuted" and not "falsified";
- **a non-prosecuted establishment, region, branch or year is unlabelled, never honest.** In
  `pu.py`'s encoding that is `s = 0`, "unlabeled", and that module rejects any other value
  with "Negatives are never observed in a PU problem - encode them as 0."

## 3. Period transfer: cases 1943-1962, anchor 1978-1983

The cases cover 1943-1962, according to the paper's title; per-row years are not recorded.
The anchor affair runs from 1978 to 1983, and the seal widens that to 1976-1985. A detector
calibrated on the first period has no guarantee of transferring to the second. For it to
transfer, all of the following would have to be true, and nothing recorded shows any of them:

1. **Same mechanism.** The falsification in the cases would have to be the same kind as the
   anchor's: a producer overstating physical output against a plan target. It could not be,
   for example, the bonus-fund misappropriation in the third sample row, which has no
   reported-versus-actual quantity at all.
2. **Same reporting instrument.** The quantity falsified, the reporting form and the
   definitions would have to be comparable between the two periods. Otherwise features
   computed on one period mean something different on the other.
3. **Same incentive structure.** The plan-fulfilment and bonus rules that create the motive
   (sub-question 3 in `research_question.md` concerns bunching at the 100% bonus threshold)
   would have to be similar enough that falsification leaves the same traces.
4. **Selection stable across periods.** Whatever made a case detectable and prosecutable in
   1943-1962 would have to relate to the detector's features the same way it would in
   1978-1983. Even then, the detector learns prosecution, not falsification (section 2).
5. **Same level of aggregation.** A detector fitted on case-level rows cannot be applied to
   the anchor's republic-level series, or the reverse, without a model of how case-level
   distortion aggregates. No such model exists here.

If a label set is ever built, every result that uses it must say that it measures prediction
of 1943-1962 prosecution. A transfer claim to the anchor period rests on assumptions 1-5, and
those must be stated.

## What the label set can and cannot support

**It cannot support, under any outcome:**

- calling it a second anchor;
- any negative label, including treating a non-prosecuted unit as honest;
- a rate or prevalence of falsification (SCAR is violated);
- a claim about 1978-1983 without assumptions 1-5 above;
- validating a detector on the anchor. The anchor stays sealed, and these cases are not a
  substitute for it.

**It could support, only if section 1 resolves in favour of linkage:** a positive-unlabelled
label set (`s = 1` for prosecuted units, `s = 0` for everything else). Its results would be
reported as performance at predicting prosecution in 1943-1962.

**It supports now:** context. It is qualitative, case-level evidence that reporting fraud
existed, what forms it took (the sample rows show overstated physical output, a reported
figure against an actual figure, and misused bonuses) and that it was prosecuted. None of
this can be counted or tabulated until the file is acquired and read.

## Seal and the Uzbek cases

The registry says the file includes Uzbek agricultural cases. Their stated period is outside
the sealed years, but without a year column no code can verify that. `gosplan.seal` therefore
refuses the frame unless the caller asserts `declare_clean=True`. Making that assertion on the
strength of a paper's title would be the route to the anchor that CONTRACT rule 5 forbids
(this is WO-504-4's option A). Any future loader must pass a real year column, region column
and series column through `filter_sealed`.

A separate question is for the lead, not for this card. Suppose these cases later pass the
seal. Would using Uzbek agricultural fraud cases to shape a detector that is then tested on
Uzbek agricultural reporting make the anchor test less independent, even though the sealed
rows were never touched? The seal does not cover this, because the rows are outside its years.
The question is recorded in `workorders/AMBIGUITY-WO-505-1.md`.

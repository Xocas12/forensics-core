# gosplan-env coupling: a data contract for estimator robustness

WO-506 | Phase P1 | Gate G1 | Status: **specification with open questions** (section 5)

This document says how output from the sibling simulator
[`Xocas12/gosplan-env`](https://github.com/Xocas12/gosplan-env) is scored by `forensics_core`.
It covers three things and nothing else: what the simulator emits (section 1), what the
library consumes (section 2), and what may and may not be claimed from the result (section 3).

## 0. Standing and direction

**Nothing here describes what the simulator already does.** The gosplan-env documents this
card may read (`README.md`, `ROADMAP.md`, `CONTRACT.md`) do not give the simulator's output
columns, dtypes or per-period semantics, and every function body in that repository still
raises `NotImplementedError` (its README, "THIS REPOSITORY IS A SKELETON"). So every field in
section 1 is a **requirement the simulator's output must meet** to be scored by the library.
None of it is a description of existing behaviour. What the library needs is fixed by
`forensics_core.eval.harness.Dataset`, `forensics_core.inject.InjectionRecord` and
`forensics_core.power.atlas`, and section 1 is derived from those.

gosplan-env's own roadmap says the `forensics-core` interface "is not agreed until G1"
(gosplan-env gate G1) and that every `forensics_core` call site there is provisional until
then (ROADMAP section 8). This document is the library side's proposal for that agreement. It
does not amend gosplan-env's plan, and it asks for no change to it. Anything in it that the
sibling cannot meet is raised as an issue on that repository.

**Direction of dependency.** `forensics_core` never imports `gosplan` or anything else from
gosplan-env, not even optionally or in tests. The coupling is a **data contract, not a code
dependency**. The simulator writes a frame, and the library reads a frame. Library tests for
the coupling build synthetic frames that meet section 1. gosplan-env scopes its own dependency
on the library to estimator robustness (its README, "The coupling to `forensic-stats` /
`forensics_core` is scoped to **estimator robustness** (PLAN §7.3) and to nothing else"), and
that scoping is theirs to keep.

**Scope inherited from the sibling.** gosplan-env's ROADMAP section 8 summarises its PLAN §7.3
as scoping the coupling to "bunching bias, reconciliation, dispersion". It "excludes digit
tests" and "admits ministry-level series only from P2". This document therefore does not
cover the rounding mechanism (`inject_rounding`) or any `forensics_core.digits` test.

## 1. What the simulator emits

For each simulated run, one tidy frame with **one row per enterprise per period**, plus the
run's manifest.

### 1.1 Columns

The column names are fixed by this contract. The dtypes are pandas dtypes. No column may hold
a missing value.

| Column | dtype | Requirement |
|---|---|---|
| `enterprise_id` | `int64` | Identifier of the enterprise, stable across the periods of one run. |
| `period` | `int64` | Period index within the run. Comparable with `<=` (the harness's `"temporal"` split needs that). |
| `reported_quantity` | `float64` | The quantity the enterprise reported to the planner for that period. Finite. |
| `true_quantity` | `float64` | The quantity the report purports to measure, as it actually was: same units, same enterprise, same period. Finite. What it measures exactly is open (OQ-5). |
| `plan_target` | `float64` | The planner's target for that enterprise and period, in the units of `reported_quantity`. Finite and `> 0`, because fulfilment `reported_quantity / plan_target` is the running variable of the bunching estimators. |
| `audited` | `bool` | `True` iff the planner audited that enterprise's report for that period. |

Row invariants:

- `(enterprise_id, period)` is unique.
- Every numeric value is finite. `forensics_core.inject` rejects non-finite input rather than
  dropping it, because dropping it changes the unit count the record is audited against. The
  same holds here.
- The frame carries no label column and no gap column. The label is derived library-side
  from `reported_quantity` and `true_quantity` (section 2.2), so the rule lives in exactly one
  place.
- Rows may come in any order. The library sorts them (section 2.1).

### 1.2 Run-level metadata

Each frame travels with the gosplan-env run manifest (gosplan-env CONTRACT rule 10:
`runs/<hash>/manifest.json`, carrying config hash, spec version, git hash, seeds, estimator
version and flags). The library needs from it, and copies into `Dataset.meta`:

- the run hash and config hash, to name the dataset and to keep two runs from being compared
  silently;
- the spec version;
- the seeds (see OQ-2 on how they map onto `InjectionRecord.seed`);
- the flags, and in particular `BOUND_BINDING`. gosplan-env CONTRACT rule 8 bounds
  `report_ratio` at `rho_max = 10` and flags a run where more than 1% of reports sit at the
  bound. A result computed on such a run carries the flag wherever the result goes;
- the location of the bonus notch, in the units of `reported_quantity / plan_target`. A
  bunching estimator needs the threshold from outside the data, as the injector does. Whether
  the simulator's notch is defined on that ratio is part of OQ-5.

The on-disk transport (file format, path) is not fixed here. It does not change any number.
The in-memory contract is a `pandas.DataFrame` meeting 1.1 plus a dict carrying 1.2.

## 2. What the library consumes

One simulated run becomes one `Dataset` plus one `InjectionRecord`. This is exactly the shape
an injected series has (`values, InjectionRecord`), so a simulated run is scored by the same
code path as an injected one. The injection contract is reused and no parallel one is
invented.

### 2.1 `Dataset` (forensics_core.eval.harness)

The frame is sorted by `(enterprise_id, period)` and given a fresh `RangeIndex`. From then on,
"position" means a row position in that order, which is what `Dataset.take` and
`InjectionRecord.indices` both use.

| `Dataset` field | Built from | Notes |
|---|---|---|
| `unit_id` | `f"{enterprise_id}:{period}"` (str) | Unique by the row invariant. `Dataset` raises on duplicates. |
| `X` | `reported_quantity`, `plan_target` | Only what an archive could show. `true_quantity`, and anything computed from it, **never** enters `X`: a detector that sees the truth measures nothing. Whether `audited` enters `X` is open (OQ-4). |
| `y` | label rule applied to `reported_quantity`, `true_quantity` | `float64`, values in {0.0, 1.0}. No `NaN`, since the simulator knows the truth for every row. The rule itself is open (OQ-1). |
| `groups` | `enterprise_id` | For `split="group_kfold"`: an enterprise sits wholly on one side. |
| `time` | `period` | For `split="temporal"`. |
| `meta` | section 1.2, plus `{"project": "gosplan_env", "name": "gosplan_env:<run hash>", "simulated": True}` | `name` makes reports tabulate by run. `simulated` marks the dataset as not an observation of anything. |

Because `y` has no `NaN`, a `PUDetector` sees no unlabeled pool beyond the `y == 0` rows it
already treats as unlabeled. A `SklearnDetector` takes the 0s as true negatives, which is the
correct reading here: on simulated data a 0 is verified, not merely presumed.

### 2.2 `InjectionRecord` (forensics_core.inject)

| Field | Value | Status |
|---|---|---|
| `mechanism` | `"gosplan_env"` | Fixed here. The `InjectionRecord` docstring lists four mechanisms, and adding this fifth name to it is library-side documentation work for whichever card builds the adapter. |
| `indices` | `np.flatnonzero(reported_quantity != true_quantity)`, `int64`, ascending | Determined by the existing contract. `InjectionRecord.indices` is "positions where the returned series differs from the input". Here the input is `true_quantity` and the returned series is `reported_quantity`. |
| `effect_size` | a single float | **Open (OQ-3).** The simulator has no single distortion knob, so the scalar must be defined. |
| `seed` | `int \| None` | **Open (OQ-2).** A gosplan-env run has two seeds, and the field holds one. |

If the label rule (OQ-1) is anything other than `y = (reported_quantity != true_quantity)`,
then `y == 1` and `indices` pick out different rows. Section 5 records this under OQ-1.

### 2.3 Scoring paths

Both of the library's existing paths apply, unchanged:

- **Ranking power of a per-unit detector:** `eval.harness.evaluate(detector, ds, spec)` on
  the `Dataset` of 2.1. The split policy belongs to the card that runs the evaluation. The
  metrics are the rank metrics with the base rate beside them (forensics-core CONTRACT
  rule 10).
- **Power of a test on a collection:** the output takes the shape of an atlas,
  `forensics_core.power.atlas.ATLAS_COLUMNS`, including the zero-effect row that makes the
  rest readable. `power_curve` as written draws from a clean population and applies an
  injector. A simulated run arrives already distorted, so `power_curve` cannot take it as it
  stands. How simulator runs populate an atlas is part of OQ-3, and it is not designed here.

False positives (forensics-core CONTRACT rule 9): a detection on simulated data is reported
beside the same fitted detector's behaviour on runs where nothing was distorted. The runs that
count as "nothing distorted" are defined in OQ-3.

Simulated frames are handled like injected data. They are held in memory during evaluation
and are **never written under any project's `data/` directory**, which holds real
observations only (the `forensics_core.inject` discipline).

## 3. What may be claimed

**Only this:** whether an estimator recovers a distortion that was really there, in data with
this shape and at this sample size.

Two outputs follow from that, and only two:

1. **A power curve on realistic data:** detection rate against distortion size and sample
   size, on the enterprise-by-period shape gosplan faces, with the false-positive rate at zero
   distortion printed beside it.
2. **A falsification:** a detector that cannot find a distortion the simulator generated will
   not find one in the archives either. This is the strongest negative result available to
   this project. It binds only when the distortion is known to be present in the run
   (`indices` non-empty) and the detector's false-positive rate on undistorted runs is
   reported next to the miss (forensics-core CONTRACT rules 8 and 9).

## 4. What may not be claimed

**No number from the simulator is evidence about the historical USSR.** The simulator's
parameters were not estimated from Soviet data. gosplan-env's own documents say the Phase-1
values are provisional defaults chosen at its gate G1 from a regime map, and that "no quantity
produced here is an estimate of anything that happened". A detector validated on the simulator
is validated against a model's assumptions and nothing more.

Specifically:

- No absolute magnitude transfers, in either direction, on either side. Examples are a
  distortion share, a padding rate, a bunching mass, or a minimum detectable effect read off a
  simulated curve and quoted as a bound on Soviet reporting.
- A detector's success on simulated data is not evidence that it succeeds on the archives.
  Only the negative direction of section 3 item 2 transfers, and only as a statement about the
  detector.
- Nothing here bears on gosplan-env's Claim A (emergence) or Claim B (counterfactual). Nothing
  from `forensics_core` scored on simulated data is reported as evidence for either.
- Nothing here bears on the held-out anchor (forensics-core CONTRACT rule 5). No simulated
  output is compared with, tuned on, or plotted alongside the Uzbek cotton series.

## 5. Open questions

Each question below changes behaviour or a reported number. None of them is settled here, and
each has an ambiguity report under `workorders/`. Code that builds the adapter in section 2
cannot be written until OQ-1 to OQ-3 are answered.

- **OQ-1: label rule** (`workorders/AMBIGUITY-WO-506-1.md`). This is how `y` follows from the
  gap between `reported_quantity` and `true_quantity`. The options are any nonzero gap,
  over-reporting only, or a relative threshold, with or without a float tolerance. The choice
  interacts with gosplan-env's held-out phenomena: "hidden reserves and shaving" (under-
  reporting) is held out until its Phase-2 acceptance run, so a label that isolates
  under-reporting would measure a held-out phenomenon.
- **OQ-2: which seed** (`workorders/AMBIGUITY-WO-506-2.md`). gosplan-env keeps `seed_env` and
  `seed_policy` separate (its CONTRACT rule 9), but `InjectionRecord.seed` holds one
  `int | None`.
- **OQ-3: effect size, the zero-effect arm and the atlas route**
  (`workorders/AMBIGUITY-WO-506-3.md`). The questions are which scalar is
  `InjectionRecord.effect_size` and forms the power curve's x-axis (a realised gap statistic,
  or a configured incentive parameter), which runs count as zero distortion, and whether
  `power_curve` is reused or a separate entry point is written.
- **OQ-4: `audited` in `X`** (`workorders/AMBIGUITY-WO-506-4.md`). The question is whether a
  detector may see the audit indicator, which depends on whether an archive would show one.
- **OQ-5: grain and meaning of the true quantity** (`workorders/AMBIGUITY-WO-506-5.md`). The
  questions are whether one scalar per enterprise and period is the simulator's reporting
  grain (sectors and quality exist in its design), what `true_quantity` measures, and whether
  the notch is defined on `reported_quantity / plan_target`. The frame here also carries no
  accounting identities across nodes, so it does not serve a reconciliation estimator. What
  such an estimator would need is not specified here.
- **OQ-6: which truth is the ground truth** (`workorders/AMBIGUITY-WO-506-6.md`). The card
  derives the label from the same-run true quantity. gosplan-env's roadmap has its
  estimator-bias study (its WO-034) "scored against the DP's exact no-manipulation
  counterfactual". The two are different references, and they give different bias numbers.

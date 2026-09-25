# Method transfer

How a detector calibrated on a project with ground truth is carried onto a project without
it, using `forensics_core.eval.harness`.

Everything named here is real: the class names, field names and signatures below were read
from `src/forensics_core/eval/harness.py` and `src/forensics_core/eval/metrics.py`. The
pseudo-code marks clearly which identifiers are library API and which are placeholders for
project code that does not exist yet.

This document contains no results. No number in it is a finding.

---

## 1. Why transfer is the point

The programme has four projects and one asymmetry:

| Project | Repository | Ground truth |
|---|---|---|
| `elections` | `forensic-elections` | Published, replicable falsification signatures, plus genuine control elections |
| `aaer` | `forensic-economy` | Enforcement actions as positives (SEC Accounting and Auditing Enforcement Releases) |
| `china` | `forensic-economy` | Partial: admitted falsification, a reform discontinuity |
| `gosplan` | `forensic-economy` | Almost none: one anchor event |

Three of them can answer "did the detector rank the right units at the top?" because
somebody outside the data already knows the answer. `gosplan` cannot. There is no archive
reachable from here that confirms an individual Soviet figure, and there is exactly one
validated event to check against.

So the design is not "run a detector on Soviet data and see what it says". It is:

1. Develop the method where the answer is knowable.
2. Score it out of sample there, with rank metrics and a stated base rate, and keep that
   record.
3. Carry the *same fitted object* onto the Soviet rows.
4. Read the Soviet ranking against the source project's score-to-precision curve, and say
   plainly that the curve belongs to the source.

The harness exists so that step 3 is mechanical and step 2 travels with it. `transfer()`
returns the target ranking and the source `EvalReport` in one object precisely so that a
Soviet ranking cannot be shown without the evidence for the method that produced it.

The gosplan project states the same constraint from its own side: see
`projects/gosplan/docs/validation_anchors.md` ("Detector calibration must come from
elsewhere") and `projects/gosplan/docs/research_question.md` (the honest output is a bound
under a stated assumption, not a point estimate).

---

## 2. The objects

All of these are importable from `forensics_core.eval`.

### `Dataset`

A dataclass holding the rows to be scored, plus whatever labels, groups and timestamps
exist. Fields:

| Field | Type | Meaning in this programme |
|---|---|---|
| `unit_id` | `pandas.Series` | The scored unit. A precinct in `elections`, a firm-year in `aaer`, a province-year in `china`, a transcribed table row in `gosplan`. Must be unique; duplicates raise. |
| `X` | `pandas.DataFrame` | Features. For an unsupervised statistic this is usually the precomputed per-unit statistic and the ingredients it needs. |
| `y` | `pandas.Series` or `None` | `1` = confirmed distortion, `0` = **presumed** clean, `NaN` = unlabeled. No other value is accepted. `None` means the dataset carries no labels at all, which is the normal state of a `gosplan` scoring set. |
| `groups` | `pandas.Series` or `None` | Grouping key for `split="group_kfold"`: firm, region, year. Keeps a whole firm on one side of the split. |
| `time` | `pandas.Series` or `None` | Period key for `split="temporal"`. Anything comparable with `<=`. |
| `meta` | `dict` | Free-form provenance, e.g. `{"name": ..., "project": ..., "anchor_events": [...]}`. |

The distinction between `0` and `NaN` is the whole label model of the programme. In `aaer`,
a firm-year with no enforcement action is not a clean firm-year; it is a firm-year nobody
prosecuted. Which of the two you write into `y` decides which detector wrapper is correct
(section 2.3).

Construction validates rather than aligns: a companion Series whose index does not match
`X.index` raises, because silent pandas alignment is how labels end up attached to the wrong
rows. Lists and arrays are wrapped in a Series carrying `X.index` as a convenience.

Methods and properties:

- `len(ds)` and `ds.n`: row count.
- `ds.name`: `meta["name"]`, else `meta["project"]`, else `"dataset"`. This is the string
  that appears in `EvalReport.dataset` and `TransferResult.source` / `.target`.
- `ds.y_values() -> np.ndarray`: labels as float with `NaN` for unlabeled. Raises if
  `y is None`.
- `ds.take(positions) -> Dataset`: positional subset of every aligned field, `meta` copied.
- `ds.labeled() -> Dataset`: rows whose label is not `NaN`, so both the confirmed positives
  and the presumed-clean zeros.
- `ds.positives() -> Dataset`: rows with `y == 1`.

### `Detector`

A `runtime_checkable` Protocol with three members:

```python
name: str


def fit(self, ds: Dataset) -> Detector: ...
def score(self, ds: Dataset) -> np.ndarray: ...
```

`score` returns one float per row, higher = more suspicious. `fit` may ignore the labels
entirely, which is what every unsupervised method in this library does, and should return
`self`. Because the protocol has a non-method member (`name`), `isinstance` works but
`issubclass` does not.

`evaluate` and `transfer` both check `isinstance(detector, Detector)` and raise a
`ValueError` naming the three required members if the object does not satisfy it. Scores are
then checked by an internal helper: a detector whose `score` returns the wrong number of
values, or any non-finite value, raises rather than silently producing a ranking with a
`NaN` in it. A digit test that is undefined for a unit with too few digits must therefore be
mapped to a finite floor value by the project before it reaches the harness.

### The three wrappers

**`FunctionDetector(func, name="function", *, higher_is_suspicious=True)`**

Wraps a plain `f(X: DataFrame) -> scores`. `fit` is a documented no-op that ignores `ds`
entirely. This is how an unsupervised statistic enters the harness without pretending to be
an estimator, and it is the main path in this library. Section 3 covers it in full.

`higher_is_suspicious=False` negates the returned scores, so a statistic whose natural sign
runs the other way (a p-value, a dispersion index that is suspicious when *low*) does not
have to be rewritten to satisfy the harness convention.

**`SklearnDetector(estimator, name=None, *, score_method="auto")`**

Wraps any scikit-learn estimator exposing `decision_function` or `predict_proba`. The
estimator is `clone`d before fitting, so the instance handed in is never mutated and folds
cannot leak into each other. Fitting uses the **labeled rows only**, and requires both
classes to be present; the zeros are taken at face value as negatives.

That is the correct wrapper when a zero really means "checked and clean". In `elections`,
where the control elections are ordinary democratic elections rather than un-prosecuted
ones, that reading is defensible. In `aaer` it is not.

**`PUDetector(kind="elkan_noto", base_estimator=None, name=None, **estimator_kwargs)`**

Wraps a positive-unlabeled estimator from `forensics_core.labels.pu`. `kind` selects
`ElkanNotoPU` or `BaggingPU`, imported lazily inside `fit`. The label mapping is the point
of the class, and it is deliberately different from `SklearnDetector`:

```
y == 1   -> s = 1   (confirmed distortion)
y == 0   -> s = 0   (presumed clean: treated as UNLABELED, not as a negative)
y is NaN -> s = 0   (unlabeled)
```

`pu_labels(ds)` exposes that vector. `fit` raises if there is no positive, and raises again
if *every* row is positive, because the unlabeled pool is what the method learns from.
`PUDetector` needs an entirely numeric `X` (it converts through a float matrix and raises
with a message telling you to encode or drop the non-numeric columns first);
`FunctionDetector` does not, since it hands `ds.X` straight to your function.

### `EvalSpec`

How a detector is to be evaluated. Defaults shown:

```python
EvalSpec(
    split="temporal",  # "temporal" | "group_kfold" | "anchor_holdout" | "none"
    train_end=None,  # temporal: last training period, inclusive
    n_splits=5,  # group_kfold: number of folds, at least 2
    anchor_mask=None,  # anchor_holdout: boolean Series, True = rows that ARE the anchor
    ks=(0.01, 0.05, 0.10),  # ints are counts, floats in (0, 1) are fractions of the test set
    metrics=("roc_auc", "average_precision", "ndcg_at_k", "precision_at_k"),
)
```

The four splits, in this programme's terms:

- `"temporal"` trains on rows with `time <= train_end` and tests on everything later. This
  is the `aaer` split: it is the design used by the Bao et al. (2020) benchmark that
  `projects/aaer` replicates, precisely because a random split leaks the future into the
  past. A missing value in `time` raises rather than being assigned to a side.
- `"group_kfold"` wraps `sklearn.model_selection.GroupKFold` so a whole firm, province or
  year sits on one side of the split. This is the guard against a detector learning a
  region's fixed characteristics instead of its distortion.
- `"anchor_holdout"` holds out an anchor event and trains on the rest. Section 5.
- `"none"` fits and scores the same labeled rows. The resulting metrics are in-sample, and
  the report says so in `EvalReport.in_sample` and in a note attached to the numbers.

`metrics` accepts only these names: `"roc_auc"`, `"average_precision"`, `"ndcg_at_k"`,
`"precision_at_k"`, `"recall_at_k"`. Anything else raises with the list of known names. Note
that the `@k` entries are *spec* names: in the report they appear expanded per cut-off, so
`metrics=("ndcg_at_k",)` with `ks=(0.01,)` produces the report key `"ndcg@1%"`.

Rank metrics, not accuracy, because the base rate is tiny in every project here. A detector
that flags nothing is right almost always. `EvalSpec.to_dict()` gives a JSON-friendly view
in which `anchor_mask` is summarised by `{"n_rows": ..., "n_anchor": ...}` rather than
copied.

### `EvalReport`

What `evaluate` returns:

| Field | Meaning |
|---|---|
| `detector`, `dataset` | Names, so several runs tabulate together. |
| `spec` | The `EvalSpec` that produced this report. |
| `metrics` | `dict[str, float]`, the unweighted mean over usable folds. Keys look like `"roc_auc"`, `"average_precision"`, `"ndcg@1%"`, `"precision@5"`. |
| `per_fold` | One dict per fold with `fold`, `n_train` (rows given to `fit`), `n_test` (labeled test rows scored), `n_test_rows` (all test rows scored), `n_pos_test`, `metrics`, `test_unit_ids`, `skipped`, `reason`. |
| `n_train`, `n_test`, `n_pos_test` | Sums over folds. Under `group_kfold`, `n_train` counts a row once per fold that trained on it, so it exceeds the sample size. |
| `in_sample` | `True` when `spec.split == "none"`. |
| `notes` | Warnings worth carrying with the numbers: skipped folds, in-sample scoring. |

`report.summary_table()` returns a tidy one-row-per-metric DataFrame carrying `detector`,
`dataset`, `split`, `in_sample`, `n_train`, `n_test`, `n_pos_test`, `metric`, `value`.
`pandas.concat` several of those to compare detectors across projects. `report.to_dict()`
serialises the whole thing.

`per_fold[i]["test_unit_ids"]` is the field that makes a claim auditable: it names the
labeled units the metrics were computed on, so a reviewer can ask what those specific
precincts or firm-years were.

### `evaluate(detector, ds, spec) -> EvalReport`

The mechanics, which matter for reading any number it returns:

- The detector is **deep-copied per fold**, so the instance you pass in is never fitted.
- Each fold's copy is fitted on **all** training rows, labeled or not, so a `PUDetector`
  keeps its unlabeled pool.
- It scores the test rows, and metrics are computed on the **labeled test rows only**.
- A fold whose labeled test rows lack either a positive or a negative is skipped, recorded
  in `per_fold` with a reason, added to `notes`, and left out of the averages. Rank metrics
  are undefined there, and the harness says so instead of inventing a value.
- If no fold was usable, `evaluate` raises rather than returning an empty report.

### `transfer(...) -> TransferResult`

```python
transfer(
    detector, source, target,
    source_spec=None,
    *,
    fit_on="labeled",             # or "all"
    max_calibration_points=100,
)
```

- `source` is the project the detector was developed on and must carry labels with at least
  one positive. `target` is the project to score; **its labels are not needed and are
  ignored**, which is exactly the `gosplan` situation.
- If `source_spec` is given, `evaluate` runs on the source first and the report is carried
  in the result, so the transferred ranking travels with an out-of-sample record of what the
  detector did at home. Pass it. A transfer without a `source_report` is a ranking with no
  evidence behind it.
- `fit_on="labeled"` (the default, and what `INTERFACES.md` specifies) fits on the labeled
  source rows. `fit_on="all"` fits on every source row, which is what a `PUDetector` wants
  when the unlabeled pool is informative.
- The detector is deep-copied before fitting, so again your instance is untouched.

`TransferResult` fields:

| Field | Meaning |
|---|---|
| `scores` | DataFrame with columns `unit_id`, `score`, `rank`, one row per target unit, sorted by score descending, rank 1 = most suspicious. |
| `source_report` | The `EvalReport` from the source project, or `None` if `source_spec` was omitted. |
| `calibration` | DataFrame with columns `score_threshold`, `precision`, `recall`, `n_selected`, thresholds ascending, computed on the **source** labels. |
| `detector`, `source`, `target` | Names carried through for tabulation. |
| `n_source_fit` | Number of source rows the detector was fitted on. |

The calibration curve answers exactly one question: "on the source project, taking
everything that scored at least this had precision p and recall r, selecting `n_selected`
units". Thresholds are the distinct observed source scores, so a threshold always selects
whole tie groups, thinned to at most `max_calibration_points` evenly spaced values. `recall`
is non-increasing in the threshold by construction; `precision` is not monotone in general,
and it is noisy in the top few rows where `n_selected` is small.

The library's own docstring states the caveat, and it should be repeated in any write-up:
the calibration curve is computed on the source rows the detector was fitted on, so it is
in-sample and optimistic. It is a translation table for score levels, not a performance
claim. The performance claim is `source_report`.

### The registry

```python
DETECTOR_REGISTRY: dict[str, Callable[..., Detector]]

@register_detector("benford_chi2")          # overwrite=False by default
def ...

make_detector("function", func=f, name="benford")
```

`register_detector` refuses to overwrite an existing key unless `overwrite=True`, so two
projects cannot silently claim the same name. `make_detector` takes its `name` argument
positionally-only, so `**kw` can carry a detector's own `name=` without colliding with the
registry key, and it validates that the factory actually returned something satisfying the
`Detector` protocol.

Four detectors ship registered: `"function"` (`FunctionDetector`), `"sklearn"`
(`SklearnDetector`), `"pu_elkan_noto"` and `"pu_bagging"` (both `PUDetector`, with `kind`
bound). The registry is what lets a config file name a detector as a string, so that a
transfer run is specified by data rather than by import path.

---

## 3. The main path: an unsupervised detector, wrapped and then scored

The core methods in this library are unsupervised. `digits.benford_test`,
`digits.integer_excess`, `bunching.bunching_estimator`, `dispersion.too_smooth_test` and
`dispersion.variance_floor_test` all compute a statistic from the numbers alone. None of
them needs a label to run.

They need labels for something else: to establish that the statistic ranks distorted units
above honest ones. That is what the labelled projects are for, and `FunctionDetector` is how
such a statistic gets scored.

### The shape problem, and the two idioms that solve it

Every library routine takes a *collection* of numbers and returns one result. `Detector.score`
must return *one number per row*. So the wrapping step is where you decide what a unit is
and how its numbers are gathered.

**Idiom A: precompute in the project, read a column.** The project's feature builder calls
the library routine once per unit and writes the statistic into a column of `X`; the
`FunctionDetector` just reads it. This is the idiom the library's own harness tests use:

```python
FunctionDetector(lambda X: X["signal"].to_numpy(), name="signal_column")
```

**Idiom B: loop inside the function.** `X` carries one array-valued column per unit (a
precinct's digit counts, an enterprise's series of annual figures), and the wrapped function
calls the routine per row. `FunctionDetector` passes `ds.X` straight through without
coercing it to a float matrix, so an object column of arrays is allowed here (it is not
allowed for `PUDetector`).

Idiom A is preferable when the statistic is expensive, because `evaluate` calls `score` once
per fold. Idiom B keeps the method definition in one place.

### Choosing the sign

The harness convention is higher = more suspicious. Three cases:

- `benford_test(...).chi2.statistic` and `integer_excess(...).test.statistic`: already
  higher = more suspicious. Wrap with the default `higher_is_suspicious=True`.
- A p-value from `TestResult.pvalue`: lower = more suspicious. Wrap with
  `higher_is_suspicious=False` rather than negating by hand inside the function, so the sign
  convention is visible at the call site.
- `dispersion.dispersion_index`: suspicious when *low*, since too little noise is the
  signal. Same treatment, `higher_is_suspicious=False`.

`bunching_estimator` returns a `BunchingResult` whose `normalized_excess` (`b`) is the
natural per-unit score, higher = more mass piled at the threshold.

### Scoring it on a labelled project before transferring

```python
from forensics_core.eval import Dataset, EvalSpec, FunctionDetector, evaluate

# LIBRARY: FunctionDetector, Dataset, EvalSpec, evaluate
# PLACEHOLDER: build_elections_dataset is illustrative project code, not an existing function.
elections = build_elections_dataset()  # unit_id = precinct, y from the published signatures

detector = FunctionDetector(
    lambda X: X["integer_excess_z"].to_numpy(),
    name="integer_pct_excess",
)

report = evaluate(
    detector,
    elections,
    EvalSpec(
        split="group_kfold",
        n_splits=5,
        ks=(0.01, 0.05),
        metrics=("roc_auc", "average_precision", "ndcg_at_k"),
    ),
)
report.summary_table()
```

Two honest notes about doing this with an unsupervised detector.

First, `FunctionDetector.fit` is a no-op, so nothing is learned from the training rows and
there is no fitting leakage across a split. That does **not** make `split="none"` safe. The
leakage in an unsupervised method happens outside the harness, when the analyst chooses the
statistic, the tolerance, the bin width or the exclusion window after looking at the labelled
data. The harness cannot see that choice, so `in_sample` being `False` is not a claim that
no tuning happened. Record the choices.

Second, an unsupervised detector produces the same ranking whatever the split, so the split
here is not protecting the detector. It is protecting the *estimate* of how well the
detector ranks: `group_kfold` prevents one enormous region from carrying the whole metric,
and `temporal` prevents a statistic tuned on late years from being scored on them.

Once scored, the same wrapped object goes through `transfer` unchanged. Because
`FunctionDetector.fit` ignores its argument, `fit_on` is irrelevant for this path, and the
`calibration` curve is simply the source's score-to-precision mapping for that statistic.

---

## 4. Worked example: a PU detector from `aaer` to `gosplan`

This is pseudo-code. It does not run, it fetches nothing, and it creates no data. Loader
functions are placeholders for project code; everything imported from `forensics_core` is
real API.

The label facts behind it: AAER firm-year labels are registered in
`projects/aaer/data/SOURCES.yaml` (the Bao et al. replication file, id `bao_labels_csv`),
and the curated Dechow et al. dataset must be **purchased**, not merely requested, which is
recorded in `projects/aaer/data/ACCESS_NOTES.md`. The coverage constraint between the
labelled period and the free structured-financials path is stated in
`projects/aaer/docs/validation_anchors.md`. Read those before assuming this example is
runnable today.

```python
from forensics_core.eval import Dataset, EvalSpec, PUDetector, transfer

# ---------------------------------------------------------------- source: aaer
# PLACEHOLDER: load_aaer_firm_years is illustrative project code. The column names
# gvkey / fyear / misstate are those of the Bao et al. analysis file documented in
# projects/aaer/docs/data_dictionary.md; FEATURE_COLUMNS is a placeholder.
firm_years = load_aaer_firm_years()  # one row per firm-year

aaer = Dataset(
    unit_id=firm_years["gvkey"].astype(str) + "_" + firm_years["fyear"].astype(str),
    X=firm_years[FEATURE_COLUMNS],  # entirely numeric: PUDetector requires it
    y=firm_years["misstate"],  # 1 = enforcement action; 0 = NOT prosecuted
    time=firm_years["fyear"],
    groups=firm_years["gvkey"],  # a firm never straddles a fold
    meta={"name": "aaer", "project": "aaer"},
)

# ---------------------------------------------------------------- target: gosplan
# PLACEHOLDER: load_gosplan_rows is illustrative project code.
soviet = load_gosplan_rows()  # enterprise-year (or sector-year) rows,
# assembled from transcribed table cells

gosplan = Dataset(
    unit_id=soviet["unit_year_id"],
    X=soviet[FEATURE_COLUMNS],  # SAME columns, SAME order, SAME construction
    y=None,  # no labels, and that is the point
    time=soviet["year"],
    meta={"name": "gosplan", "project": "gosplan", "anchor_events": ["uzbek_cotton_1978_1983"]},
)

# ---------------------------------------------------------------- fit, score, calibrate
detector = PUDetector(kind="elkan_noto", name="pu:aaer_financials")

result = transfer(
    detector,
    source=aaer,
    target=gosplan,
    source_spec=EvalSpec(
        split="temporal",
        train_end=LAST_TRAINING_YEAR,  # the benchmark's own design
        ks=(0.01, 0.05),
        metrics=("roc_auc", "average_precision", "ndcg_at_k"),
    ),
    fit_on="all",  # keep the unlabeled pool: this is why PU exists
)

# ---------------------------------------------------------------- read the output
result.source_report.summary_table()  # what the detector did on aaer, out of sample
result.scores.head(50)  # unit_id, score, rank: the Soviet ranking
result.calibration  # score_threshold, precision, recall, n_selected

# Reading a Soviet score against the aaer curve: find the highest source threshold the
# target score clears, and quote that row's precision AS AN AAER NUMBER.
top = result.scores.iloc[0]["score"]
curve = result.calibration  # thresholds ascending
row = curve[curve["score_threshold"] <= top].iloc[-1]  # last row it clears
# row["precision"] is the precision that threshold achieved ON AAER FIRM-YEARS.
# It is NOT the probability that this Soviet unit is distorted.
```

Three things this example depends on, all of them substantive.

**`fit_on="all"` is not a detail.** The default is `"labeled"`, which fits on
`source.labeled()` and therefore discards every `NaN` row. For a `PUDetector` the unlabeled
rows are the negative-ish pool the Elkan-Noto correction is estimated against, so dropping
them changes the method. Pass `"all"` deliberately, and note that even with `"all"` the
`calibration` curve is still computed on the labeled source rows, because you cannot compute
precision without labels.

**The feature vector must mean the same thing in both projects.** Nothing in the harness
checks this. `PUDetector.score` calls the fitted estimator on `target.X` and will happily
produce a ranking from columns that happen to have the right names and the wrong content.
An accruals ratio built from a 10-K and a ratio built from a transcribed `Narkhoz` table are
not the same variable. If the columns cannot be made comparable, the transferable object is
not the fitted PU model at all, and you should be transferring an unsupervised statistic
(section 3) instead, where the only thing carried across is the definition of the test.

**The fitted detector is not returned.** `transfer` fits a deep copy internally and hands
back only `TransferResult`. If you need to score a third dataset (a control sample, see
section 6) with the *same* fitted instance, fit a copy yourself and call `score` on both,
rather than calling `transfer` twice and hoping a stochastic estimator lands identically.

---

## 5. `anchor_holdout`, and why one anchor forces it

```python
EvalSpec(split="anchor_holdout", anchor_mask=mask, ks=(10,), metrics=("roc_auc",))
```

`anchor_mask` is a boolean Series, `True` for the rows that **are** the anchor. Those rows
become the test set; training uses everything else. The mask must select at least one row
and must not select every row; both cases raise.

The `gosplan` anchor is the **Uzbek cotton affair, 1978-1983**: reported Uzbek raw cotton
output was systematically padded across roughly a decade, exposed in the 1980s, followed by
prosecutions and revised figures. The magnitude, the internal inconsistency between two
figures in the same source, and the sources they come from are recorded in
`projects/gosplan/docs/validation_anchors.md`, which is the only place this programme
should be quoting them from.

Why the split exists. With a single anchor there is no fold structure available. There is
one region-and-period where the answer is known and a large body of rows where it is not.
`temporal` would put the anchor on whichever side of a date it happens to fall.
`group_kfold` would need several known-distorted groups and there is one. `none` would fit
and score on the same rows and say so. `anchor_holdout` at least states the design
explicitly: hold out the event, train on everything else, and see whether the anchor rows
rise.

What it buys, and what it does not:

- It buys a **direction check**. The claim it can support is "the detector, trained without
  the anchor rows, ranks them above the rest". `projects/gosplan/docs/validation_anchors.md`
  puts it as: direction and window are what the detector must recover, an upward bias
  concentrated in the late 1970s and early 1980s, ending with the exposure.
- It does not buy an out-of-sample validation, because the anchor is also the event the
  method was designed against. Fit and validation touch the same event.
- The mask itself is a modelling choice. Which rows "are" the anchor (which republic, which
  crop, which years, whether the exposure year is inside or outside) changes both the test
  set and the training set. Record the definition of the mask next to the result;
  `EvalSpec.to_dict()` records only its size (`n_rows`, `n_anchor`), not its logic.
- Under `anchor_holdout` there is exactly one fold, so `EvalReport.metrics` is that fold's
  metrics and nothing is averaged. If the held-out anchor rows contain no negative among the
  labeled rows, the fold is skipped and `evaluate` raises because no fold was usable. That
  failure is informative: it means the mask defines a test set with no contrast in it.

---

## 6. Caveats, stated plainly

These belong in the write-up, not only in this file.

**1. Enforcement labels teach a model what gets prosecuted, not what happens.** An AAER
positive is a firm the SEC acted against. The zeros are firms nobody acted against, which is
why `Dataset.y` distinguishes `0` (presumed clean) from `NaN`, and why `PUDetector` collapses
both to "unlabeled". A model fit on these labels learns the selection process of an
enforcement agency together with the distortion. Anything transferred to `gosplan` on that
basis carries the selection process of the 1990s and 2000s SEC into a Soviet ministry. Say
so; do not let `roc_auc` stand in for it.

**2. A single anchor caps the claim.** The detector is fit and validated on the same event.
No held-out positive exists, no within-project false-positive rate can be estimated, and no
amount of harness discipline changes that. The strongest honest output is a bound under a
stated assumption, in the form `projects/gosplan/docs/research_question.md` specifies:
distortion is at least X in sector S over years Y, assuming the padding mechanism resembles
the anchor.

**3. A transferred score is a ranking, not a probability.** `TransferResult.scores` gives
`rank` for a reason. The `calibration` frame is a source-project object: its `precision`
column is the precision that threshold achieved on labelled source rows, and it transfers
only under the assumption that the score distribution and the base rate are comparable across
projects, which is precisely what cannot be checked on `gosplan`. On top of that the curve is
computed in-sample on the fitted rows, so it is optimistic even as a statement about the
source. Quote it as "this score level corresponded to precision p on `aaer`", never as "this
Soviet enterprise-year is p likely to be distorted".

**4. Report false positives, not only hits.** A detector is characterised by what it does on
data known to be clean, and a list of the top-ranked Soviet units is not a result on its own.

The `elections` project is the template, because it has real control data. The Kobak,
Shpilkin and Pshenichnikov supplement registered in `projects/elections/data/SOURCES.yaml`
as `figshare_kobak_aoas2016_supp` ships `poland2010.txt` and `spain2011.txt` alongside the
Russian files. `projects/elections/docs/validation_anchors.md` makes the control an explicit
pass criterion for the integer-percentage test: the excess must vanish on Poland 2010 and
Spain 2011 under the same test, and that check is the one showing the method is not merely
detecting arithmetic.

Transferring that discipline is a matter of building the control as its own `Dataset` and
scoring it with the same fitted detector, then reporting the share of control units above
whatever threshold was used on the target.

Two objects do this, and they answer different questions.

`transfer(..., controls=[...])` takes control `Dataset`s and returns `control_reports`: for
each control, the share of its rows at or above every threshold on the source calibration
curve, computed with the *same fitted instance* that scored the target — which is returned as
`fitted_detector`. Scoring a control with a refitted copy would measure a sibling of the
object that made the claim. This is the right object when the detector produces scores and
the threshold came from the source curve. A `TransferResult` whose `control_reports` is empty
is not publishable under CONTRACT rule 9, and the empty list is the visible signal that the
claim has not been made.

`forensics_core.control` is for the case where the detector produces calibrated p-values and
there is a nominal alpha to hold it to. `control_report` returns a rejection rate per control
with a verdict — `calibrated`, `anticonservative` or `conservative` — decided against the
Monte Carlo error at that control's sample size, so the same 8% against a nominal 5% is
unremarkable at n = 200 and damning at n = 8000. It names the three kinds of control and
insists they are not equivalent: only an external one is real evidence, and
`has_external_control()` is what a write-up should check before claiming the rule is
satisfied. There is deliberately no corpus average, because one anticonservative control is
the finding and a mean would hide it.

**5. Read the report's own warnings.** `EvalReport.notes` carries skipped folds and the
in-sample warning; `EvalReport.in_sample` is `True` for `split="none"`; `n_pos_test` says how
many positives the metrics actually rest on. A `precision@1%` computed on a handful of
positives is not a stable number, and `metrics.bootstrap_metric` (percentile pairs bootstrap,
returning a `BootstrapResult` with `point`, `se`, `ci_low`, `ci_high`, `n_failed`) exists so
that the uncertainty travels with the point estimate. A large `n_failed` means the interval
is unreliable and should be reported as such.

---

## 7. Layout

`forensics-core` is a standalone git repository: the shared method library, its tests and
this document.

It is vendored into both project repositories as a git submodule at
`packages/forensics_core`:

```
forensics-core/                     the library, edited here
  src/forensics_core/eval/harness.py
  src/forensics_core/eval/metrics.py
  docs/method_transfer.md           this file

forensic-elections/
  packages/forensics_core/          submodule, read-only from this repo
  projects/elections/

forensic-economy/
  packages/forensics_core/          the same submodule
  projects/aaer/
  projects/china/
  projects/gosplan/
```

Nothing under `packages/forensics_core` is edited from a project repository. A method that
needs changing is changed in this repository, and the projects update their submodule
pointer. That is what makes a transfer claim meaningful: `elections` and `gosplan` are
scored by the same code at the same commit, not by two versions of an idea that drifted
apart.

The public surface of the library is fixed in `INTERFACES.md` at the repository root.

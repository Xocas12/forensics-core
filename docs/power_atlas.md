# The power atlas

The question this document exists to answer, for a project that did not measure the curve
itself:

> Is this method detectable at my sample size?

`elections` has on the order of 95,000 precincts. `gosplan` has a few hundred sector-years.
A detector calibrated at one of those sizes says nothing by itself about the other, so the most
valuable thing the calibration projects can hand the target project is not a detector but a
curve. This document is the citable summary of that curve: the format a published atlas is
stored in, the two queries it answers, and the conditions under which it refuses to answer at
all.

The library-side API is `forensics_core.power.lookup`; the storage contract is
`data/atlas/README.md`.

## What a row means

For one method, sample size and effect size: draw `n` units from a population believed clean,
inject a distortion of that size with a mechanism the method did not help design, run the
method, and record whether it rejects at `alpha`. Repeat. The rejection fraction is the power.

The row at effect size zero is the **false-positive rate**, and it is not optional. A power
number without it cannot be read: a method that rejects everything has power 1.0 and is
useless. `power_curve` always measures it, and every lookup refuses to answer from an atlas
whose false-positive rate at that sample size is more than twice nominal.

## The frozen format

One parquet file per atlas, with the columns of `ATLAS_COLUMNS` —

```
method, n, effect_size, power, power_se, n_replicates, alpha, false_positive_rate
```

— and the measurement record in the `_spec` column. The record carries the method, `alpha`,
`n_replicates`, the seed and the estimator settings, and two keys are required on top of those:

- **`library_version`**, `forensics_core.__version__` at the moment of publication. The
  estimator code is not frozen when the atlas is. Two releases are two different atlases, and a
  reader checking a number needs to know which one produced it.
- **`aggregation`**, the rung the curve was measured at: `"unit"` for an unaggregated
  `power_curve`, or a ladder level name.

An atlas carrying no version is refused at load. A number whose source release cannot be named
is not citable, and the refusal is the point.

## Querying it

```python
from forensics_core.power.lookup import power_lookup

lookup = power_lookup("data/atlas")  # a file, a directory, or a list
lookup.minimum_detectable_effect("integer_excess", 300)  # smallest detectable effect
lookup.detectable("integer_excess", 300, 0.02)  # whether a given effect clears it
lookup.describe()  # what is loaded, with release + seed
```

`minimum_detectable_effect(method, n, *, aggregation="unit", power=0.8)` returns the smallest
**measured** effect size reaching the target power at `n`. For an atlas published from an
aggregation ladder, `n` is the number of *aggregate* units at that rung, and the recorded
`mean_group_size` says how many units each one covers.

`detectable(method, n, effect, *, aggregation="unit")` answers yes/no. It is `False`, not an
exception, when the atlas does not cover `n`: an atlas that has not shown the effect detectable
has not shown it. A method or rung the lookup holds no atlas for at all is a different failure —
there is no curve to read — and raises.

## The refusals, which are the substance

Nothing interpolates and nothing extrapolates.

- **A sample size the atlas never measured raises.** `n = 200` when the atlas measured
  `50, 100, 300` gets an answer for the measured points and an exception for the unmeasured
  one; `n = 12` below the whole range raises too. A power number invented between measured
  points is not a measurement, and putting one into a claim about the historical record is the
  specific failure this programme exists to avoid.
- **An effect that never reaches the target power raises.** The honest answer is that the
  method has no useful power at that sample size, not a number.
- **An out-of-control false-positive rate raises.** The power column cannot be read while the
  method fires on data with nothing injected into it.
- **A method or rung the library holds no atlas for raises**, naming what it does hold.
- **Two atlases that differ are never merged.** Library version, seed and estimator settings
  are part of an atlas's identity; two that differ are two entries, and a query matching both
  raises rather than choosing. Answering from the wrong atlas is the same failure as answering
  by extrapolation, one step further from view.

Each `PowerAtlas` carries a `cite()` line naming the method, the rung, the library release, the
seed and the settings. A number quoted in a card carries that line.

## What is published, and what is not

**Nothing is committed under `data/atlas/` yet.** `WO-200` has not run, so no elections
hierarchy has been acquired, and the curves measured so far are synthetic measurements of the
methods on generated data (WO-100, WO-101). Publishing those is permitted — synthetic is one of
the two allowed populations — but the first real atlas lands only when there is a measurement
worth citing. An empty directory is the honest state.

Only atlases computed on **elections data or synthetic data** are published at all.

## What the measured curves say so far

Everything below is a characteristic of a method **on synthetic data**, recorded in the source
or in the commit that produced it. None of it is a finding about any real dataset, and none of
it is extrapolated beyond the grid that was measured.

**Aggregation destroys the integer-percentage signal.** Measured on unequal denominators with
every unit snapped onto an exact integer percentage (share of units still within 0.05 of an
integer; the background rate is 0.10), from the `forensics_core.power.aggregation` module
docstring:

| group size | `sum_then_ratio` | `mean_of_ratios` |
|---|---|---|
| 1 | 1.000 | 1.000 |
| 2 | 0.256 | 0.489 |
| 3 | 0.141 | 0.334 |
| 4 | 0.089 | 0.235 |
| 8 | 0.100 | 0.150 |

Averaging retains *more* than summing counts, the opposite of what the WO-101 card expected.
The finding that constrains a card is neither direction: **both collapse to the background rate
by a group size of four to eight**, so the integer-percentage test does not survive aggregation
under either semantics and a gosplan card must not run it on aggregates at all. That is what
`aggregation=` in a query is for — and, for this method, the rung at which the answer becomes
"no".

**The underdispersion family is weak on synthetic data.** Recorded in the WO-100 commit: the
too-smooth test gives power 0.00 against variance losses of 50 per cent and 80 per cent at every
sample size up to 1000, and detects only a 95 per cent loss; at `n = 50` it does not reach power
0.8 even there. Its false-positive rate is 0.00 throughout, so the test is extremely
conservative rather than broken. This is one of the two signals gosplan was counting on, which
is exactly the kind of thing the atlas exists to surface before P4 rather than after.

**The common effect-size axis splits two ways.** From `forensics_core.effect`: on the common
scale, `padding` and `bunching` measure a directionality of 1.000, while `rounding` measures
about 0.02 and `smoothing` about −0.005. All four are comparable as an axis for detection power;
only padding and bunching may be read as a statement about how much output was misreported.

## What this is not

This is the power of a test on a **collection** — at what sample size a method can see an effect
at all. It is not the ranking power of a per-unit detector, which the labelled projects answer
through `eval.harness.evaluate`. Both are needed and they are not interchangeable.

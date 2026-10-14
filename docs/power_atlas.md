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
seed and the settings. A number quoted anywhere carries that line.

## What is published, and what is not

**Nothing is committed under `data/atlas/` yet.** the elections hierarchy has not been generated here, so no elections
hierarchy has been acquired, and the curves measured so far are synthetic measurements of the
methods on generated data . Publishing those is permitted — synthetic is one of
the two allowed populations — but the first real atlas lands only when there is a measurement
worth citing. An empty directory is the honest state.

Only atlases computed on **elections data or synthetic data** are published at all.

## What the measured curves say so far

Everything below is a characteristic of a method **on synthetic data**, recorded in the source
or in the commit that produced it. None of it is a finding about any real dataset, and none of
it is extrapolated beyond the grid that was measured.

**Whether the integer-percentage signal survives aggregation depends on the semantics and the
group size.** Measured with `integer_excess` run on the aggregates (its defaults: tolerance
0.05, `n_mc=200`, `seed=0`), on 4800 synthetic units with denominators uniform on 600-1399 and
an honest share of 0.55, every unit snapped onto an exact integer percentage, contiguous
groups of `k`. `z` is the near-integer count against its binomial null; "rejects" is at
α = 0.05. The settings are those of `full_snap_results` in `tests/test_power_aggregation.py`,
which recomputes this table and fails if it drifts:

| group size | `sum_then_ratio` z | rejects | `mean_of_ratios` z | rejects |
|---|---|---|---|---|
| 1 | 198.02 | yes | 198.02 | yes |
| 2 | 25.46 | yes | 61.01 | yes |
| 3 | 5.04 | yes | 33.25 | yes |
| 4 | -1.13 | no | 16.25 | yes |
| 6 | -0.04 | no | 6.56 | yes |
| 8 | 0.19 | no | 3.92 | yes |
| 12 | -2.06 | no | -1.13 | no |
| 16 | -0.59 | no | -3.62 | no |

The same panel without snapping is rejected at no group size under either semantics. One
panel is one draw, so the same test over panel seeds 0-29 (`integer_excess` seeded with the
panel seed), counting rejections out of 30:

| group size | 2 | 3 | 4 | 6 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|---|
| `sum_then_ratio`, every unit snapped | 30 | 30 | 9 | 2 | 1 | 0 | 1 |
| `mean_of_ratios`, every unit snapped | 30 | 30 | 30 | 30 | 20 | 1 | 0 |
| either semantics, honest | 2 | 1 | 1-2 | 0-2 | 2-3 | 0-1 | 3 |

And with only a share of the units snapped (the test fixture's `round_injector`, units chosen
by `default_rng(1000 + seed)`), rejections out of the same 30 panels:

| group size | semantics | share 0 | 0.3 | 0.5 | 0.8 |
|---|---|---|---|---|---|
| 2 | `sum_then_ratio` | 2 | 23 | 30 | 30 |
| 2 | `mean_of_ratios` | 2 | 30 | 30 | 30 |
| 3 | `sum_then_ratio` | 1 | 2 | 8 | 25 |
| 3 | `mean_of_ratios` | 1 | 7 | 29 | 30 |
| 4 | `sum_then_ratio` | 1 | 3 | 1 | 0 |
| 4 | `mean_of_ratios` | 2 | 2 | 9 | 30 |
| 6 | `sum_then_ratio` | 2 | 1 | 3 | 2 |
| 6 | `mean_of_ratios` | 1 | 0 | 2 | 14 |
| 8 | `sum_then_ratio` | 3 | 2 | 4 | 0 |
| 8 | `mean_of_ratios` | 2 | 3 | 3 | 4 |

Averaging retains *more* than summing counts, the opposite of what the plan expected: the mean
of `k` integer percentages sits on a `1/k` lattice that contains every integer, while a sum of
counts over unequal denominators has no lattice at all.

What constrains a card is a rule per semantics and group size, not a ban. On counts summed over
four or more units the test rejects 0 to 4 panels in 30 at every share up to 80 per cent of
units snapped, which is what it does on honest panels. A non-rejection there is not evidence
that nothing was rounded, and sector-year totals summed over many enterprises are in that
regime. Below four units, and on
averaged percentages up to about six units (eight when every unit is snapped), the test still
has power against heavy snapping. That is what `aggregation=` in a query is for.

**The underdispersion family is weak on synthetic data.** Recorded when the atlas was built: the
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

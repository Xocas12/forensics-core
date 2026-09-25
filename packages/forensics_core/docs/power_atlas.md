# The power atlas

This is the document other repositories cite when they say whether a method can detect an
effect at the sample size they have. It describes what an atlas measures, how to query one, and
when a query is refused. It contains no power numbers, because none has been published yet
(see `data/atlas/README.md`); when an atlas is published, the numbers are read from its file,
not copied into this page.

## What an atlas measures

For one method: draw `n` units from a population believed clean, inject a distortion of a given
effect size, run the method's test, and record whether it rejects at `alpha`. The rejection
fraction over the replicates is the power at `(n, effect_size)`
(`forensics_core.power.atlas.power_curve`).

The row at effect size zero is the false-positive rate and is always measured. A power number
cannot be read without it: a method that rejects everything has power 1.0. A query at a sample
size whose false-positive rate exceeds twice the nominal `alpha`
(`forensics_core.power.atlas.FPR_TOLERANCE`) is refused rather than answered.

This is the power of a test on a *collection*, which answers "at what sample size can this
method see the effect at all". It is not the ranking power of a per-unit detector.

## Querying

```python
from forensics_core.power.lookup import detectable, minimum_detectable_effect

minimum_detectable_effect(method, n, *, aggregation="unit", power=0.8, atlas=path)
detectable(method, n, effect, *, aggregation="unit", power=0.8, atlas=path)
```

- `minimum_detectable_effect` returns the smallest **measured** effect size whose power at `n`
  reaches `power`. It never interpolates between measured effect sizes.
- `detectable` returns whether `effect` is at least that.

## When a query is refused

Refusing to extrapolate is the purpose of the lookup. Each of these raises `AtlasError` with the
reason; none returns a number:

- `n` below the smallest or above the largest sample size the atlas measured. The error names
  the measured range.
- No measured effect reaches `power` at `n`. The honest answer is that the method has no useful
  power there, not a number. (`detectable` answers `False` for an effect no bigger than the
  largest one measured, and refuses a larger effect, whose detection was never measured.)
- The false-positive rate at `n` is too far above nominal.
- The atlas has no rows for `method`.

## Citing a number

Cite the atlas file, its spec (`method`, `alpha`, `n_replicates`, `seed`, `settings`), and the
`forensics-core` release it was computed with. An atlas measured with different estimator
settings is a different atlas, and a number from one is not a number from the other.

## Not settled yet

These parts of the query raise `NotImplementedError` naming the report that has to decide them:

| question | report |
|---|---|
| where stored atlases live, and which answers when several cover one method (`atlas=None`) | `workorders/AMBIGUITY-WO-111-1.md` |
| how an unmeasured `n` inside the measured range is answered | `workorders/AMBIGUITY-WO-111-2.md` |
| what `aggregation` other than `"unit"` selects | `workorders/AMBIGUITY-WO-111-3.md` |

The library version is not yet recorded inside a stored atlas (`AMBIGUITY-WO-111-4.md`), so
until that is resolved a citation must state the release separately.

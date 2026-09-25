# A common effect-size scale

Integer excess is a count. Bunching is normalised excess mass. Underdispersion is a variance
ratio. Without a common scale the power atlas is three incomparable tables, and the question
this programme actually asks for elections — *which method family gives the most detection
power per unit of distortion* — cannot be posed at all.

This document proposes a scale, measures it against all four injectors, and records the place
where it stops working, which turned out to be more interesting than the place where it works.

## The scale

    displacement  =  share of units touched  ×  mean relative displacement of a touched unit

Both factors are read off the data, before and after, without consulting the injector's own
parameter. That is what makes the four comparable: a scale defined per mechanism would be four
scales wearing one name.

It reads as a sentence — *about x per cent of the reported numbers were moved, by about y per
cent each* — and that sentence is the form a gosplan bound eventually wants to take.

## It behaves, measured against all four injectors

`forensics_core.inject`, defaults as in `tests/test_effect.py`.

| mechanism | native parameter | displacement | net / gross |
|---|---|---|---|
| `rounding` | fraction = 0.25 | 0.001154 | +0.016 |
| `rounding` | fraction = 0.5 | 0.002308 | +0.023 |
| `rounding` | fraction = 1.0 | 0.004598 | +0.018 |
| `bunching` | mass = 0.3 | 0.001610 | +1.000 |
| `bunching` | mass = 0.6 | 0.003138 | +1.000 |
| `bunching` | mass = 0.9 | 0.004886 | +1.000 |
| `padding` | magnitude = 0.1 | 0.026667 | +1.000 |
| `padding` | magnitude = 0.3 | 0.080000 | +1.000 |
| `padding` | magnitude = 0.6 | 0.160000 | +1.000 |
| `smoothing` | retain = 0.5 | 0.010848 | −0.005 |
| `smoothing` | retain = 0.2 | 0.020474 | −0.005 |
| `smoothing` | retain = 0.02 | 0.031800 | −0.005 |

Displacement is monotone in every one of the four native parameters — increasing in `fraction`,
`mass` and `magnitude`, decreasing in `retain`, which is the no-op at 1. It is linear in
`fraction` and in `mass`, and for padding it is exactly `block_share × magnitude`: the mean
relative displacement recovers the magnitude to nine figures, because the block is fixed and
every year in it is inflated by the same factor.

So the first half of the card is answered plainly. Four parameters in four units land on one
axis, and the power atlas can be built against it.

## Where it stops working

Look at the last column.

`displacement` is a **gross** quantity: it sums movement without regard to direction. For two
mechanisms that is also the net misreporting. For the other two it is not, and the gap is not
marginal — it is two orders of magnitude.

| mechanism | net / gross | what the movement does |
|---|---|---|
| `padding` | +1.000 | every touched year inflated; gross **is** net |
| `bunching` | +1.000 | every mover crosses the threshold the same way |
| `rounding` | +0.018 | units round up and down about equally |
| `smoothing` | −0.005 | deviations shrink both ways around a preserved level |

At `fraction = 1.0`, rounding moves 0.46% of the reported total in gross terms and 0.008% in
net terms. **A sentence quoting the first as misreported output would overstate it by a factor
of about 55.** Smoothing is worse still: its net displacement is not merely small but
sign-unstable, because the mechanism preserves the level exactly and only shrinks the noise
around it.

This is a real distinction between the mechanisms, not an artefact of the scale:

- Padding and bunching move **quantity**. Someone reported more output than existed, or moved
  a unit across a threshold to collect a bonus. The total changed.
- Rounding moves **digits**. A count of 1,647 becomes the count that makes the percentage come
  out at 65 exactly. The number is falsified; the quantity barely moves.
- Smoothing moves **variance**. The series keeps its level at every `retain`; what disappears
  is the noise a real process would have had.

## Consequence: one axis, two readings

The scale is kept, and its use is split.

**As a comparison axis for detection power** — all four mechanisms, without qualification.
This is what the power atlas needs, and it needs only that the mechanisms be ordered on one
number. Nothing above threatens that.

**As a substantive claim about how much output was misreported** — `padding` and `bunching`
only. `effect.as_quantity_claim` refuses to write the sentence otherwise, either because the
caller named a shape mechanism or because the measured directionality is below 0.5.
Everything observed sits at 1.000 or below 0.03, so the cut has a wide margin either side; a
mechanism that ever landed near it would need its own discussion rather than a tie-break.

The gosplan bound this programme is aiming at — *distortion is at least X in sector S over
years Y* — is a padding claim. It falls in the half where the reading holds, which is the
reason this split is a limitation worth stating rather than one that blocks the programme.

### Was a forced equivalence available?

Yes, and it would have been worse. Rounding and smoothing could each be given their own
conversion — an "effective net displacement" scaled up by the reciprocal of their
directionality, say — and all four would then read as quantity claims. The number produced for
rounding would be a quantity of output that no one ever reported. The card explicitly allows
the conclusion that two families are not commensurable in a particular respect, and they are
not: they are commensurable for power, and not for quantity.

## Native units are never replaced

The common scale is an **additional reporting column**. Kobak's integer excess is reported as
a count, Chetty's excess mass as a normalised ratio, and the displacement sits beside them.
`effect.effect_table` builds that pairing and prints native values unchanged.

Nothing in `effect.py` rescales an estimator's output. A reader comparing this programme's
numbers against a source paper must be able to find the source paper's number, in the source
paper's units, or the comparison cannot be made at all.

## Reproducing

```
uv run pytest -q tests/test_effect.py
```

Every figure in the tables above is asserted in that file, and each assertion names the number
here that it guards.

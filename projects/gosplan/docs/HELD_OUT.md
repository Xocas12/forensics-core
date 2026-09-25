# The held-out anchor

**Nobody looks at Uzbek cotton for 1976 to 1985 until gate G3 is signed.**

This is the most important rule in the project and the one its only real claim depends on.

## Why

This project has exactly one validation anchor. A detector chosen, tuned, or merely eyeballed
while its single test case is visible is fit and validated on the same event. Whatever it then
reports about that event is not evidence, because the event is what shaped it.

With one anchor there is no way to recover from a peek. There is no second event to test on and
no way to unsee the first. So the protection has to be preventive, and it has to survive
somebody simply forgetting the rule exists, which is how it will actually be broken.

## What is sealed

| | |
|---|---|
| Series | anything whose name contains `cotton` |
| Region | Uzbek SSR, under any of the spellings the sources use |
| Years | **1976 to 1985 inclusive** |

The window is deliberately wider than the affair's own 1978 to 1983. A detector tuned on 1977
and 1984 is still a detector tuned around the anchor, so the shoulder years are sealed too.

## What you may and may not do

**Permitted while sealed.** Acquiring the data. Transcribing it. Validating and checksumming
it. Loading it through `filter_sealed` so the rest of a table stays usable. Counting how many
rows were withheld, and reporting that count.

**Not permitted.** Any plot, statistic, score, distributional summary, or power curve fitted on
it. Any breakdown that isolates it. Any frame passing through code that cannot tell whether it
contains held-out rows.

## The aggregate question, which is the interesting part

A union-level cotton total for 1980 contains the Uzbek figure inside it. If the rule were "no
number that a held-out value contributed to", the project would be impossible: the union-level
series is most of what exists, and the anchor is inside nearly all of it.

The rule drawn here is narrower:

> An aggregate is permitted. A breakdown that isolates the held-out unit is not.

Summing cotton across republics is allowed, because the total does not tell you the Uzbek
figure. Grouping the same frame **by republic** is refused, because one of the resulting rows
*is* the anchor. The line is whether the output lets a reader read off, or closely bound, the
held-out quantity.

`check_grouping` implements this conservatively: if the grouping keys include the region column
and held-out rows are still present, it refuses. Something subtler would have to reason about
what a given aggregate reveals, and being wrong in that direction is the expensive mistake.

**This is a judgement, not a fact, and it is the part of the seal most worth arguing with.**
Two known soft spots, recorded rather than hidden:

1. **Differencing.** A union total with Uzbekistan and the same total without it discloses the
   Uzbek figure exactly. `check_grouping` does not detect that, because it inspects one call at
   a time. Do not construct such a pair.
2. **A small number of large units.** If the union total were dominated by two republics, the
   total plus one of them bounds the other tightly. For Soviet cotton this is a real risk, not
   a hypothetical, since production was concentrated in Central Asia.

Neither is machine-checkable here. They are why the rule is stated in prose as well as code.

## How the seal lifts

Only by a human act at G3 that leaves a committed artefact: a file at
`projects/gosplan/docs/G3_UNSEAL.md` containing, exactly,

```
GATE G3 IS SIGNED AND THE GOSPLAN ANCHOR IS UNSEALED
```

There is deliberately **no code path that creates that file**, and a test asserts as much. Code
may check the seal; only a person may lift it.

## What the seal is not

It is a guard against forgetting, not against a determined bypass. Anyone with write access can
create the record by hand. That is unavoidable: the owner must be able to lift the seal at G3,
and nothing available here can distinguish the owner doing that deliberately from the owner
doing it early.

What it buys is that lifting the seal becomes a separate, deliberate, auditable act that leaves
something in the history, instead of happening silently because a notebook cell had no filter
on it. That is the realistic threat model, and overstating it would be its own small dishonesty.

## Using it

```python
from gosplan.seal import filter_sealed, check_grouping

frame, n_withheld = filter_sealed(frame)
if n_withheld:
    print(f"{n_withheld} rows withheld: the held-out anchor (see docs/HELD_OUT.md)")

check_grouping(frame, ["region", "year"])  # raises while the anchor is present
```

Call `filter_sealed` unconditionally. After G3 it becomes a no-op returning `(frame, 0)`, so
analysis code does not become correct only because somebody remembered to change it.

A table that legitimately has no region or series column cannot be checked, and is **refused**
rather than passed through, because a table with no region column may well be the Uzbek series
itself. If you know such a frame is clean, say so explicitly with `declare_clean=True`. That is
an assertion recorded at the call site, not a bypass; using it on a frame that does contain the
anchor is a violation of `CONTRACT.md` rule 5.

## After G3

`held_out_mask` still identifies the anchor rows once the seal is lifted, and must: WO-510 needs
exactly that mask to build the `anchor_holdout` split, where detectors are fitted without ever
seeing the anchor and then asked to rank it. The seal hides the anchor; it does not forget where
it is.

# The notch catalogue

The programme's unifying hypothesis is that **distortion concentrates at discontinuities in the
incentive function**. Every project has one: the 100 per cent plan-fulfilment bonus, the round
vote share, the analyst consensus, the provincial growth target.

Until now that claim lived in four project READMEs as prose, which made it four separate
stories. A catalogue makes it one experiment: each project writes `notches.yaml`, `scan_all`
runs the same estimator over all of them, and the hypothesis becomes something that can be
refuted rather than illustrated.

## A notch is not a round number

This is the distinction the whole module exists to enforce, and it is enforced in code:
`incentive` and `evidence` are mandatory, and an entry without them raises.

> A notch is a place where **somebody gained something** by reporting a number on one side of a
> line. If nobody can say what they gained, it is a round number.

Round numbers are worth testing. That is what the digit family is for, and
`digits/integer_pct.py` handles them with a null that accounts for unit size. But a round
number dressed up as an incentive is a fishing expedition with a story attached: scan enough
thresholds and something always looks like a spike, and a `notches.yaml` full of unsourced
round numbers would give that exercise a respectable name.

So each entry must say what is discontinuous, for whom, and where that is documented. An entry
whose institutional basis is inferred rather than sourced must carry `status: unverified` and
say in `evidence` what was tried. **Recording a weak entry honestly is fine. Dressing a round
number up as a documented incentive is not.**

## The schema

```yaml
- id: plan_fulfilment_100
  variable: plan_fulfilment_pct      # the column; a threshold means nothing without it
  threshold: 100.0
  kind: notch                        # notch = payoff jumps; kink = slope changes
  side: above                        # where the REWARD lies, so where mass piles
  incentive: >                       # REQUIRED
    A bonus is paid on reported fulfilment of 100 per cent or more, so an enterprise just
    short of plan gains by reporting just over it.
  evidence: >                        # REQUIRED
    Where that rule is documented, or what was tried and failed.
  confounds:                         # traps from the project's known_traps.md
    - genuine effort to reach the plan
  status: verified                   # or unverified, when the incentive is inferred
  notes: anything else worth carrying
```

`validate_notches` returns every problem at once rather than the first, so a project can fix a
catalogue in one pass. It also warns on an entry with no confounds: bunching at a threshold
almost always has an innocent explanation, and an empty list is itself a claim.

## The side matters, and getting it wrong inverts the answer

`bunching_estimator` sums `excess_mass` over the excluded bins **on the bunching side**. So an
estimator told to look below a threshold where the mass actually piles above reports a large
*negative* excess.

That is not a hypothetical. The programme's flagship notch, the 100 per cent plan-fulfilment
bonus, rewards being **above** the threshold. Measured on synthetic data with 60 per cent of the
nearby mass moved across:

| Injected side | Scanned as `below` | Scanned as `above` |
|---|---|---|
| above (bonus notch) | **−2.24** | **+2.89** |
| below (tax notch) | **+2.95** | −2.30 |

A `scan_all` that did not pass the side through would rank the programme's most important notch
*last*. It passes `bunching_side=entry.side`, and a test asserts all three cells above, including
the mislabelled one, so the inversion cannot come back unnoticed.

A kink has no rewarded side and is scanned as `below`, the estimator's own default.

## The four canonical notches

| Project | Notch | Reward side | Strength of the incentive claim |
|---|---|---|---|
| `gosplan` | 100 per cent plan fulfilment | above | **Strongest.** A bonus schedule is an institutional fact, not an inference |
| `aaer` | zero earnings, last year's earnings, analyst consensus | above | Strong in the literature, but this repository has not yet recorded a source, so `unverified` |
| `china` | the provincial growth target | above | Real, but provinces also *manage real activity* to hit targets, so bunching is consistent with honesty |
| `elections` | round vote shares and turnout | above | **Weakest.** The incentive is a convention or a target rather than a documented bonus |

That ordering is itself worth stating plainly. The hypothesis is strongest exactly where the
data is worst (`gosplan`) and weakest where the data is best (`elections`), which is an
uncomfortable shape for a research programme and is why the catalogue records `status` per
entry rather than treating all four as equivalent instances of one phenomenon.

## Using it

```python
from forensics_core.notches import load_notches, scan_all, validate_notches

problems = validate_notches("projects/gosplan/notches.yaml")
if problems:
    raise SystemExit("\n".join(problems))

catalogue = load_notches("projects/gosplan/notches.yaml")
table = scan_all(frame, catalogue, bin_width=1.0, exclude_below=4.0, exclude_above=4.0)
```

`scan_all` returns one row per notch, sorted by `normalized_excess` descending, and skips
entries whose `variable` is not a column or whose threshold falls outside the observed range.
That second skip is deliberate: a threshold the data never reaches produces a number that looks
like a result and is not one.

## What this does not do

It does not test whether the bunching it finds is misreporting. Every entry's `confounds` list
exists because bunching at an incentive threshold has innocent explanations, and the Chinese
growth target is the clearest case: a province that hits its target by building roads has bunched
without misreporting anything. Separating the two needs the physical-proxy residual, not a
bigger catalogue.

Nor does it establish the unifying hypothesis. It makes the hypothesis *testable across four
datasets with one estimator*, which is the necessary first step and not the same thing.

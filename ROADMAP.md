# ROADMAP

The order in which this programme gets built, and why that order.

This document is a map, not a specification. Where it summarises `CONTRACT.md`, the contract
wins. Nothing in this file is a result,
and no number in any of these repositories may be cited as one.

## The programme

Statistical forensics of strategically reported data: detecting distortion in numbers produced
by agents with an incentive to distort them. Three repositories:

| Repository | Holds | Role |
|---|---|---|
| [`forensics-core`](https://github.com/Xocas12/forensics-core) | the shared method library | vendored into the other two as the submodule `packages/forensics_core` |
| [`forensic-elections`](https://github.com/Xocas12/forensic-elections) | `projects/elections` | the calibration project for digit and bunching methods |
| [`forensic-economy`](https://github.com/Xocas12/forensic-economy) | `projects/aaer`, `projects/china`, `projects/gosplan` | enforcement labels, provincial statistics, and the transfer target |

**Three projects have ground truth and one does not, and that asymmetry is the whole design.**
Methods are developed and scored where truth is knowable, then carried to the Soviet case where
it is not.

| Project | Labels | Role |
|---|---|---|
| `elections` | strong: three published, replicable signatures | calibrate digit and bunching methods |
| `aaer` | strong but selection-biased: enforcement actions | calibrate supervised and positive-unlabelled learning |
| `china` | partial: admitted episodes and a reform discontinuity | calibrate cross-source reconciliation |
| `gosplan` | almost none: **one** anchor event | **the target** |

**Unifying hypothesis.** Distortion concentrates at discontinuities in the incentive function.
Every project has a notch: the 100 per cent plan-fulfilment bonus, the round vote share, the
analyst consensus, the provincial growth target. The notch catalogue makes that a single experiment run
across four datasets instead of four separate stories.

**Second signal, weighted equally.** Fabricated series contain too little noise. A reported
yield series with less year-on-year variance than rainfall permits is impossible regardless of
its level.

## What each phase can establish

The "cannot establish" column is binding. An artefact from an early phase is not evidence for a
later claim, however suggestive it looks.

| Phase | Establishes | Cannot establish |
|---|---|---|
| **P0** acquisition | what is obtainable, at what cost, with what provenance | anything statistical whatsoever |
| **P1** calibration infrastructure | power as a function of sample size, effect size and aggregation; false-positive behaviour on controls | anything about whether a real dataset is honest |
| **P2** replication | that the implementation reproduces published results where labels are strong | anything about china or gosplan |
| **P3** reconciliation | whether the methods recover the admitted Chinese episodes | Soviet distortion |
| **P4** transfer | a bound under explicitly stated assumptions | a point estimate of aggregate Soviet distortion, or any causal claim |
| **P5** synthesis | what the programme learned, including what failed | |

## The gates

Each gate is a tracking issue in `forensics-core`, signed by the owner. Nothing downstream
starts until it is signed.

| Gate | Signs off that | Unblocks |
|---|---|---|
| **G0** data | the data is in hand or its absence is explained; the money decisions are made | P1 |
| **G1** methods frozen and pre-registered | the calibration infrastructure exists and the analysis plan is committed **before** any project-level result | P2, P3 |
| **G2** replication | elections and aaer hit or missed their published targets, documented either way | P5 |
| **G3** reconciliation | china is done, **and the gosplan anchor is unsealed** | P4 |
| **G4** transfer | the gosplan analysis has run once and been reported | P5 |
| **G5** final report | every claim carries its false-positive behaviour and its assumptions | |

## The held-out anchor

**This is the most important methodological rule in the programme.**

The Uzbek cotton affair, 1978 to 1983, is gosplan's only anchor. With one anchor, any peeking
destroys the claim, because a detector tuned while looking at its only test case is fit and
validated on the same event.

Therefore the cotton series, its physical correlates, and any breakdown that isolates it **must
not be plotted, tested, scored or summarised before G3 is signed.** Acquiring, transcribing and
validating that data is permitted. Looking at its distributional properties is not.

The held-out seal enforces this in code rather than in prose, because the person who breaks the rule will
be someone who forgot it. The seal refuses to return held-out rows without a token that does not
exist until G3 is signed.

## The ideas this roadmap is built around

Five things worth knowing before reading the plan, because most of the work exists to serve
one of them.

1. **The power atlas.** elections has about 95,000 precincts; gosplan
   will have a few hundred sector-years. The most valuable thing the calibration projects can
   hand the target project is not a detector, it is a power curve. If integer-percentage excess
   has no power at n = 300, gosplan cannot use it, and knowing that before P4 saves a phase.
   The aggregation ladder answers the companion question: Soviet data is aggregate, so how much
   power survives aggregation? elections can answer that because it has a real hierarchy.

2. **The injection harness.** gosplan has no labels, so make some: inject a distortion
   of known magnitude into a series believed clean and measure recovery. This is the only way to
   get an operating characteristic on the target's own data shape. The harness is deliberately
   built so an injector is not the estimator run backwards, because otherwise the power curve
   measures self-consistency.

3. **The false-positive budget.** A detector that fires everywhere is
   useless. elections holds the programme's only genuine external controls, two non-Russian
   elections shipped in the same supplement as a replication target. Every claim ships with its
   behaviour on data where nothing should be found, and gosplan inherits that number because it
   cannot compute one of its own.

4. **The `gosplan-env` coupling.** The sibling repository simulates enterprises
   facing a plan, a bonus notch, an audit and a ratchet, and it knows the true quantity behind
   every reported one. That is a detector test bench for exactly the data shape gosplan faces.
   Its own plan scopes this coupling to **estimator robustness and nothing else**, and that
   scope is a feature: a detector that cannot find a distortion the simulator generated will not
   find one in the archives either, which is the strongest negative result available here. No
   number from a simulator is evidence about the historical USSR.

5. **A second, weaker label set.** A case-level dataset of Soviet plan-fraud
   prosecutions, 1943 to 1962, recording reported against actual quantities. It is not a second
   anchor: it is prosecution-selected exactly as the enforcement releases are, and it covers a
   different period. But it may convert gosplan from one anchor to one anchor plus a
   positive-unlabelled label set, which would be a real upgrade to a project whose central
   weakness is having no labels. It should be approached sceptically.


## The gates, as issues

| Gate | Issue |
|---|---|
| G0 | [GATE G0](https://github.com/Xocas12/forensics-core/issues/1) |
| G1 | [GATE G1](https://github.com/Xocas12/forensics-core/issues/2) |
| G2 | [GATE G2](https://github.com/Xocas12/forensics-core/issues/3) |
| G3 | [GATE G3](https://github.com/Xocas12/forensics-core/issues/4) |
| G4 | [GATE G4](https://github.com/Xocas12/forensics-core/issues/5) |
| G5 | [GATE G5](https://github.com/Xocas12/forensics-core/issues/6) |

## Plan for this repository (forensics-core)

The library is built. Every item below that is marked done has a module and a test suite
behind it; "done" here means implemented and covered, not that it has been used on a research
question. Where it has been used, the elections calibration is the evidence.

| # | Task | Status |
|---|---|---|
| 1 | `CONTRACT.md`, the standards the programme is held to | **done** - thirteen rules, frozen by `test_contract.py` |
| 2 | Submodule release and bump discipline, so the project repositories cannot diverge | **done** - `scripts/bump_core.sh` |
| 3 | Pre-registration document and the analysis plan G1 requires | open - needs a human. A programme about motivated misreporting has no standing to criticise anyone if its own analyses are chosen after seeing the data |
| 4 | Power atlas: detection power as a function of sample size | **done** - `power/atlas.py` |
| 5 | Aggregation ladder: the power lost when data is aggregated | **done** - `power/aggregation.py`. Measuring it contradicted the plan that specified it, and the measurement won |
| 6 | Distortion injection harness: turn a clean dataset into a labelled test bed | **done** - `inject.py` |
| 7 | Control corpus and the false-positive budget | **done** in code - `control.py`. The *external* control tables (Poland 2010, Spain 2011) are still not acquired, so `has_external_control()` returns `False`, which is the honest state |
| 8 | Notch catalogue: make the unifying hypothesis one experiment instead of four stories | **done** - `notches.py` |
| 9 | Give `transfer()` a control path and return the fitted detector | **done** - `eval/harness.py`, `controls=` parameter |
| 10 | Fix the `fit_on` default so positive-unlabelled learning sees the unlabelled pool | **done** - the default is now `auto` |
| 11 | Make `evaluate()` and `transfer()` agree about what the detector sees at fit time | **done** - one fitting regime, shared |
| 12 | Null corpus and a standing red-team pass against the detectors | **done** - `redteam.py` |
| 13 | A common effect-size vocabulary, so power curves from different methods compare | **done** - `effect.py` |
| 14 | Register the unsupervised methods as detectors, so they run through one harness | **done** - `detectors.py` |
| 15 | Publish the power atlas as a lookup other repositories can cite | **done** - `power/lookup.py` |

What is left here is not code. It is item 3, and it is the one that cannot be delegated: the
analysis plan has to be written down before the remaining projects are run, or the programme
fails its own first rule.

## Plans in the other repositories

- [forensic-elections](https://github.com/Xocas12/forensic-elections) - run; see its `RESULTS.md`
- [forensic-economy](https://github.com/Xocas12/forensic-economy) - not run

## Working rules

One task, one branch, one pull request, scoped to the files that task needs.

When the plan and the data do not determine a choice, stop and write the question down rather
than picking the reasonable default. Recording an unresolved question is a complete outcome.

The full rules are in [`CONTRACT.md`](CONTRACT.md): thirteen of them, each stating what a
violation looks like concretely and what catches it. The file is identical in all three
repositories, and `test_contract.py` freezes the rule numbers, because `gosplan/seal.py`
cites rule 5 and `eval/harness.py` cites rule 9 by number.

## Where this stands

This library has been run on real data: it carried the elections calibration, reproducing two
of the three published signatures on 192,924 precinct protocols
([RESULTS.md](https://github.com/Xocas12/forensic-elections/blob/main/RESULTS.md)). The
projects that carry the programme's actual question - Chinese provincial statistics and the
Soviet series - have not been run, and say so.

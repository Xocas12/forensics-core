# ROADMAP

The order in which this programme gets built, and why that order.

This document is a map, not a specification. Where it summarises `CONTRACT.md`, the contract
wins. Every card below is a GitHub issue; the issue body is the card. Nothing here is a result,
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
analyst consensus, the provincial growth target. WO-104 makes that a single experiment run
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

WO-500 enforces this in code rather than in prose, because the person who breaks the rule will
be someone who forgot it. The seal refuses to return held-out rows without a token that does not
exist until G3 is signed.

## The ideas this roadmap is built around

Five things worth knowing before reading the card list, because most of the cards exist to serve
one of them.

1. **The power atlas (WO-100, WO-101, WO-111).** elections has about 95,000 precincts; gosplan
   will have a few hundred sector-years. The most valuable thing the calibration projects can
   hand the target project is not a detector, it is a power curve. If integer-percentage excess
   has no power at n = 300, gosplan cannot use it, and knowing that before P4 saves a phase.
   The aggregation ladder answers the companion question: Soviet data is aggregate, so how much
   power survives aggregation? elections can answer that because it has a real hierarchy.

2. **The injection harness (WO-102).** gosplan has no labels, so make some: inject a distortion
   of known magnitude into a series believed clean and measure recovery. This is the only way to
   get an operating characteristic on the target's own data shape. The harness is deliberately
   built so an injector is not the estimator run backwards, because otherwise the power curve
   measures self-consistency.

3. **The false-positive budget (WO-103, WO-108, WO-204).** A detector that fires everywhere is
   useless. elections holds the programme's only genuine external controls, two non-Russian
   elections shipped in the same supplement as a replication target. Every claim ships with its
   behaviour on data where nothing should be found, and gosplan inherits that number because it
   cannot compute one of its own.

4. **The `gosplan-env` coupling (WO-506).** The owner's sibling repository simulates enterprises
   facing a plan, a bonus notch, an audit and a ratchet, and it knows the true quantity behind
   every reported one. That is a detector test bench for exactly the data shape gosplan faces.
   Its own plan scopes this coupling to **estimator robustness and nothing else**, and that
   scope is a feature: a detector that cannot find a distortion the simulator generated will not
   find one in the archives either, which is the strongest negative result available here. No
   number from a simulator is evidence about the historical USSR.

5. **A second, weaker label set (WO-505).** A case-level dataset of Soviet plan-fraud
   prosecutions, 1943 to 1962, recording reported against actual quantities. It is not a second
   anchor: it is prosecution-selected exactly as the enforcement releases are, and it covers a
   different period. But it may convert gosplan from one anchor to one anchor plus a
   positive-unlabelled label set, which would be a real upgrade to a project whose central
   weakness is having no labels. The card is written to be sceptical of it.


## The gates, as issues

| Gate | Issue |
|---|---|
| G0 | [GATE G0](https://github.com/Xocas12/forensics-core/issues/1) |
| G1 | [GATE G1](https://github.com/Xocas12/forensics-core/issues/2) |
| G2 | [GATE G2](https://github.com/Xocas12/forensics-core/issues/3) |
| G3 | [GATE G3](https://github.com/Xocas12/forensics-core/issues/4) |
| G4 | [GATE G4](https://github.com/Xocas12/forensics-core/issues/5) |
| G5 | [GATE G5](https://github.com/Xocas12/forensics-core/issues/6) |

## Cards in this repository (forensics-core)


### The shared method library

| Card | Phase | Gate | Diff | Depends on | What it buys |
|---|---|---|---|---|---|
| [WO-000](https://github.com/Xocas12/forensics-core/issues/7) Write CONTRACT.md, the rules that bind every session in the programme | P0 | G0 | 2 | - | Every other card assumes a shared discipline that is currently only implicit in three READMEs. |
| [WO-001](https://github.com/Xocas12/forensics-core/issues/8) Create workorders/ with TEMPLATE.md and AMBIGUITY_TEMPLATE.md in all three repositories | P0 | G0 | 1 | WO-000 | The issues in these repositories are card summaries; the cards themselves need a home in the tree so a session can read one without network access, and so the ambiguity route is a form rather than a suggestion. |
| [WO-002](https://github.com/Xocas12/forensics-core/issues/9) Submodule release and bump discipline so the two project repositories cannot diverge | P0 | G0 | 3 | WO-001 | forensic-elections and forensic-economy each pin packages/forensics_core at a commit. |
| [WO-003](https://github.com/Xocas12/forensics-core/issues/10) Write the pre-registration document and the analysis plan that G1 requires | P1 | G1 | 4 | WO-100, WO-102, WO-103, WO-104 | (needs a human) A programme whose subject is motivated misreporting has no standing to criticise anyone if its own analyses are chosen after seeing the data. |
| [WO-100](https://github.com/Xocas12/forensics-core/issues/11) Power atlas: measure detection power as a function of sample size | P1 | G1 | 4 | WO-102 | elections has about 95,000 precincts; gosplan will have a few hundred sector-years. |
| [WO-101](https://github.com/Xocas12/forensics-core/issues/12) Aggregation ladder: measure the power lost when data is aggregated | P1 | G1 | 3 | WO-100 | Soviet statistics are aggregate; elections are not. |
| [WO-102](https://github.com/Xocas12/forensics-core/issues/13) Distortion injection harness: turn any clean dataset into a labelled test bed | P1 | G1 | 4 | - | gosplan has one anchor, so power and false-positive rates cannot be estimated there from labels. |
| [WO-103](https://github.com/Xocas12/forensics-core/issues/14) Control corpus and the false-positive budget | P1 | G1 | 3 | WO-102 | A detector that fires everywhere is useless, and the programme's own CONTRACT requires every claim to ship with its behaviour on data where nothing should be found. |
| [WO-104](https://github.com/Xocas12/forensics-core/issues/15) Notch catalogue: make the unifying hypothesis one experiment instead of four stories | P1 | G1 | 3 | - | The programme's unifying hypothesis is that distortion concentrates at discontinuities in the incentive function, and every project has one: the plan-fulfilment bonus, the round vote share, the analyst consensus, the provincial growth target. |
| [WO-105](https://github.com/Xocas12/forensics-core/issues/16) Give transfer() a control path and return the fitted detector | P1 | G1 | 3 | WO-103 | The library's own method_transfer. |
| [WO-106](https://github.com/Xocas12/forensics-core/issues/17) Fix the PUDetector fit_on default so positive-unlabelled learning sees the unlabelled pool | P1 | G1 | 2 | - | transfer() defaults to fit_on='labeled', which calls source. |
| [WO-107](https://github.com/Xocas12/forensics-core/issues/18) Make evaluate() and transfer() agree about what the detector sees at fit time | P1 | G1 | 2 | WO-106 | The two entry points currently use different fitting regimes, so a source_report is not strictly a report on the object that scored the target. |
| [WO-108](https://github.com/Xocas12/forensics-core/issues/19) Null corpus and a standing red-team pass against the detectors | P1 | G1 | 3 | WO-103 | Reporting a false-positive rate on a control chosen by the same person who built the detector is weak evidence. |
| [WO-109](https://github.com/Xocas12/forensics-core/issues/20) A common effect-size vocabulary so power curves from different methods can be compared | P1 | G1 | 3 | WO-102 | Integer excess is a count, bunching is normalised excess mass, underdispersion is a variance ratio. |
| [WO-110](https://github.com/Xocas12/forensics-core/issues/21) Register the unsupervised methods as detectors so they run through one harness | P1 | G1 | 2 | - | The library's core methods are unsupervised, but the harness is built around Detector objects and the registry currently holds only the four generic wrappers. |
| [WO-111](https://github.com/Xocas12/forensics-core/issues/22) Publish the power atlas as a lookup other repositories can cite | P1 | G1 | 2 | WO-100, WO-101, WO-109 | An atlas nobody can query is a private artefact. |

## Cards in the other repositories

This roadmap is shared; the full card list lives in each repository's own copy.

- [forensic-elections](https://github.com/Xocas12/forensic-elections/issues) (11 cards)
- [forensic-economy](https://github.com/Xocas12/forensic-economy/issues) (27 cards)

## Working rules

One card, one branch, one pull request. Read only what the card's whitelist names, write only
what its "Write only" list names, run the completion command verbatim, and report in the card's
format.

When the card and its whitelist do not determine a choice, **file an ambiguity report and end
the session.** Choosing the reasonable default is a violation. Filing an ambiguity report is
correct behaviour, not failure.

The full rules are in [`CONTRACT.md`](CONTRACT.md), written by WO-000.

## Standing warning

Nothing in these repositories has been run. There are no results, no estimates and no findings.
Every module under any `analysis/` raises `NotImplementedError`, every `data/raw` is empty, and
all six gates are unsigned.

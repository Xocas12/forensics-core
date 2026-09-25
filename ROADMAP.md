# ROADMAP

The order in which this programme gets built, and why that order.

This document is a map, not a specification. Where it summarises `CONTRACT.md`, the contract
wins. Every card below is a GitHub issue; the issue body is the card. Nothing here is a result,
and no number in any of these repositories may be cited as one.

## The programme

Statistical forensics of strategically reported data: detecting distortion in numbers produced
by agents with an incentive to distort them. One repository:

| Path | Holds | Role |
|---|---|---|
| `packages/forensics_core` | the shared method library | used by all four projects from the same commit |
| `projects/elections` | Russian federal elections | the calibration project for digit and bunching methods |
| `projects/aaer`, `projects/china`, `projects/gosplan` | enforcement labels, provincial statistics, Soviet statistics | enforcement labels, provincial statistics, and the transfer target |

Until September 2026 these were three repositories (`forensics-core`, `forensic-elections`,
`forensic-economy`) joined by a git submodule. They were merged with full history; the submodule,
its release tags and the `submodule-parity` check went with them: with one tree there is only
one version of the library to run.

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

## Cards

Each card is a GitHub issue; the issue body is the card. The library and gate issues live in
this repository. The project cards were filed before the merge and still live in the former
project repositories, so their links point there until they are transferred.

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

### elections

| Card | Phase | Gate | Diff | Depends on | What it buys |
|---|---|---|---|---|---|
| [WO-200](https://github.com/Xocas12/forensic-elections/issues/1) Run the acquisition for real and populate data/raw | P0 | G0 | 1 | - | (needs a human) Nothing has been downloaded into any tree. |
| [WO-201](https://github.com/Xocas12/forensic-elections/issues/2) Build the tidy artefact and run the acceptance checks against the real 2018 file | P0 | G0 | 2 | WO-200 | The 2011 file was validated during scaffolding; the 2018 file never was. |
| [WO-202](https://github.com/Xocas12/forensic-elections/issues/3) Decide the 2018 national anchor | P0 | G0 | 1 | - | (needs a human) The commission's own portal summary and its Resolution 152/1255-7 disagree by 4,313 votes and 7,122 registered voters, reportedly after four polling stations were cancelled. |
| [WO-203](https://github.com/Xocas12/forensic-elections/issues/4) Obtain the Klimek supplementary material and fill in two TO CONFIRM anchors | P0 | G0 | 1 | - | (blocked, needs a human) This single blocked source holds two of the three replication targets hostage. |
| [WO-204](https://github.com/Xocas12/forensic-elections/issues/5) Extract the Poland and Spain control tables from the acquired supplement | P1 | G1 | 2 | WO-200 | These two elections are the only genuine external controls the whole programme has: real elections, real data, from a supplement whose Russian half is a documented replication target. |
| [WO-205](https://github.com/Xocas12/forensic-elections/issues/6) Expose elections as the substrate for the power atlas and the aggregation ladder | P1 | G1 | 2 | WO-201 | The library's atlas cards need a real dataset with a large sample and a genuine hierarchy, and this is the only one in the programme that has both. |
| [WO-206](https://github.com/Xocas12/forensic-elections/issues/7) Populate the elections notch catalogue | P1 | G1 | 2 | WO-104 | Round vote shares and round turnout are this project's instance of the unifying hypothesis, and the catalogue schema requires each notch to record what someone actually gained by reporting on one side of the line. |
| [WO-207](https://github.com/Xocas12/forensic-elections/issues/8) Replicate the integer-percentage sawtooth, conditioned on precinct size | P2 | G2 | 3 | WO-201, WO-204, WO-110 | This is the cleanest published result in the programme and the first replication target. |
| [WO-208](https://github.com/Xocas12/forensic-elections/issues/9) Replicate the comet tail | P2 | G2 | 4 | WO-203, WO-207 | (blocked) The second published signature, and the one that yields an anomalous-vote count rather than a test statistic. |
| [WO-209](https://github.com/Xocas12/forensic-elections/issues/10) Replicate turnout bimodality | P2 | G2 | 3 | WO-203, WO-207 | (blocked) The third signature, and the weakest on its own: honest heterogeneity produces bimodality too. |
| [WO-210](https://github.com/Xocas12/forensic-elections/issues/11) Decompose detection power by method family, the project's actual research question | P2 | G2 | 4 | WO-207, WO-208, WO-209, WO-111 | The project's research question is not 'were these elections falsified', which the literature already answers, but 'how much detection power comes from each family of method'. |

### aaer

| Card | Phase | Gate | Diff | Depends on | What it buys |
|---|---|---|---|---|---|
| [WO-300](https://github.com/Xocas12/forensic-economy/issues/1) Acquire the SEC data and record what actually arrived | P0 | G0 | 2 | - | (needs a human) 28 acquirers exist and none has run. |
| [WO-301](https://github.com/Xocas12/forensic-economy/issues/2) Parse the enforcement listing into a structured table | P0 | G0 | 3 | WO-300 | The listing is 3,342 entries of HTML across 34 pages and is the project's label source. |
| [WO-302](https://github.com/Xocas12/forensic-economy/issues/3) Validate the XBRL tag mapping against real filings | P0 | G0 | 4 | WO-300 | The project's own data dictionary records that eleven of the twelve Beneish input mappings are unconfirmed and that the four-quarter convention for flow items was never read out of the documentation. |
| [WO-303](https://github.com/Xocas12/forensic-economy/issues/4) Build the label join, or establish that it cannot be built from free sources | P0 | G0 | 5 | WO-301, WO-302 | The enforcement listing carries a respondent name and no company identifier, while the financial data is keyed on a company identifier. |
| [WO-304](https://github.com/Xocas12/forensic-economy/issues/5) Decide the two access questions that determine what aaer can be | P0 | G0 | 1 | WO-303 | (needs a human, needs money) Two purchases stand between this project and full coverage, and both are the owner's call. |
| [WO-305](https://github.com/Xocas12/forensic-economy/issues/6) Beneish baseline on whatever path the access decision opened | P2 | G2 | 3 | WO-302, WO-303, WO-304 | The M-score is the standard baseline and its coefficients are already confirmed against the paper with each component separately tested. |
| [WO-306](https://github.com/Xocas12/forensic-economy/issues/7) Positive-unlabelled benchmark against the corrected published figures | P2 | G2 | 4 | WO-305, WO-106 | This is the project's replication target and the programme's only chance to calibrate PU learning against a published number. |
| [WO-307](https://github.com/Xocas12/forensic-economy/issues/8) Populate the aaer notch catalogue and test earnings bunching | P2 | G2 | 3 | WO-104, WO-305 | The earnings thresholds are this programme's cleanest documented incentive notch: unlike round vote shares, there is a real and well-understood reward for landing on the right side. |

### china

| Card | Phase | Gate | Diff | Depends on | What it buys |
|---|---|---|---|---|---|
| [WO-400](https://github.com/Xocas12/forensic-economy/issues/9) Find the statistics portal's values endpoint | P0 | G0 | 3 | - | The legacy query interface is blocked by a firewall, but the replacement catalogue interface answered anonymous requests and one probe returned actual numeric values. |
| [WO-401](https://github.com/Xocas12/forensic-economy/issues/10) Vintage archaeology: harvest frozen yearbook editions before the revisions | P0 | G0 | 3 | - | Revisions overwrite history. |
| [WO-402](https://github.com/Xocas12/forensic-economy/issues/11) Image extraction with a measured accuracy rate | P0 | G0 | 5 | WO-400, WO-401 | The 2023 yearbook publishes its provincial tables only as images, 706 of them, and the extractor is currently a stub that raises. |
| [WO-403](https://github.com/Xocas12/forensic-economy/issues/12) Build the province name mapping the loaders already depend on | P0 | G0 | 2 | - | map_province_names needs a Chinese-to-canonical table that does not exist, so the central bank loan balances cannot be stamped with a province and cannot enter the panel at all. |
| [WO-404](https://github.com/Xocas12/forensic-economy/issues/13) Assemble and validate the provincial panel | P0 | G0 | 3 | WO-401, WO-402, WO-403 | Everything in P3 operates on one panel of province by year by series by vintage. |
| [WO-405](https://github.com/Xocas12/forensic-economy/issues/14) Decompose the provincial-sum gap into its mechanical and residual parts | P3 | G3 | 4 | WO-404 | Part of the gap between summed provincial product and the national figure is double counting and differing deflators, not fraud. |
| [WO-406](https://github.com/Xocas12/forensic-economy/issues/15) Test the reform discontinuity at the 2019 data year | P3 | G3 | 3 | WO-405 | This is the project's natural experiment and the most interesting single test in it. |
| [WO-407](https://github.com/Xocas12/forensic-economy/issues/16) Physical proxies, underdispersion and growth-target bunching | P3 | G3 | 4 | WO-404, WO-104 | These are the two signals that carry to gosplan, tested here where there are admitted episodes to check them against. |

### gosplan

| Card | Phase | Gate | Diff | Depends on | What it buys |
|---|---|---|---|---|---|
| [WO-500](https://github.com/Xocas12/forensic-economy/issues/17) Build the seal: make the held-out anchor unreachable in code, not just in prose | P0 | G0 | 3 | - | gosplan has exactly one anchor, so a detector chosen while looking at it is fit and validated on the same event and the project's only real claim collapses. |
| [WO-501](https://github.com/Xocas12/forensic-economy/issues/18) Settle the question that decides this project's cost by an order of magnitude | P0 | G0 | 2 | - | The historical-materials site is recorded as the only near-machine-readable form of the Soviet annuals anywhere. |
| [WO-502](https://github.com/Xocas12/forensic-economy/issues/19) Measure the transcription disagreement rate and set the digit-test gate | P0 | G1 | 3 | WO-501, WO-108 | Digit tests on transcribed tables detect the transcription unless gated. |
| [WO-503](https://github.com/Xocas12/forensic-economy/issues/20) Re-recognise the annuals from page images | P0 | G0 | 4 | WO-501, WO-502 | The registry records that the archive's own text layer garbles numeric tables badly enough that even a cover title came out wrong, so it cannot be used as a data source. |
| [WO-504](https://github.com/Xocas12/forensic-economy/issues/21) Write loaders for the series that are already machine-readable | P0 | G0 | 3 | - | Several verified gosplan sources have no loader at all: the crop production series, the agricultural production and distribution series, the historical national accounts workbooks and the Warwick datasets. |
| [WO-505](https://github.com/Xocas12/forensic-economy/issues/22) Assess the prosecution dataset as a second, weaker label set | P1 | G1 | 4 | WO-504 | The research turned up a case-level dataset of Soviet plan-fraud prosecutions from 1943 to 1962, recording reported against actual quantities. |
| [WO-506](https://github.com/Xocas12/forensic-economy/issues/23) Specify the gosplan-env coupling, scoped to estimator robustness and nothing else | P1 | G1 | 4 | WO-102, WO-100 | The sibling repository simulates enterprises facing a plan, a bonus notch, an audit and a ratchet, and it knows the true quantities behind every reported one. |
| [WO-507](https://github.com/Xocas12/forensic-economy/issues/24) Update the sibling repository's references to the now-split repositories | P1 | G1 | 1 | WO-506 | gosplan-env's documents refer to forensic-stats as a single repository. |
| [WO-508](https://github.com/Xocas12/forensic-economy/issues/25) Three-way cotton reconciliation | P4 | G4 | 4 | WO-500, WO-504, WO-003 | (blocked) Soviet official cotton output, the FAO series and the US agriculture series are three measurements of one quantity and all three are verified in the registry with the anchor window covered. |
| [WO-509](https://github.com/Xocas12/forensic-economy/issues/26) Plan-fulfilment bunching, physical against value divergence, and harvest underdispersion | P4 | G4 | 4 | WO-502, WO-504, WO-104, WO-003 | (blocked) These are the three transferable signals, arriving at the target having been calibrated on projects where they could be checked. |
| [WO-510](https://github.com/Xocas12/forensic-economy/issues/27) Transfer the calibrated detectors and state the bound | P4 | G4 | 5 | WO-508, WO-509, WO-105, WO-111 | (blocked) This is what the whole programme is for. |

## Working rules

One card, one branch, one pull request. Read only what the card's whitelist names, write only
what its "Write only" list names, run the completion command verbatim, and report in the card's
format.

When the card and its whitelist do not determine a choice, **file an ambiguity report and end
the session.** Choosing the reasonable default is a violation. Filing an ambiguity report is
correct behaviour, not failure.

The full rules are in [`CONTRACT.md`](CONTRACT.md): thirteen of them, each stating what a
violation looks like concretely and what catches it. `test_contract.py` freezes the rule
numbers, because `gosplan/seal.py` cites rule 5 and `eval/harness.py` cites rule 9 by number.

## Standing warning

Nothing in this repository has been run. There are no results, no estimates and no findings.
Every module under any `analysis/` raises `NotImplementedError`, every `data/raw` is empty, and
all six gates are unsigned.

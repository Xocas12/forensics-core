# Research question: elections

**Reproduce known falsification signatures in Russian federal elections at precinct (UIK)
level, and quantify how much detection power comes from each family of method.**

Scope: the 2011 State Duma election and the 2018 presidential election, roughly 95,000
precincts each. This is by far the programme's largest *n* and the best environment for
digit-based tests; it is also the project with the strongest ground truth, because several
signatures have been published, replicated, and are reproducible from the same public data.

Sub-questions this project must answer before its methods are transferred:

1. Which of the three published signatures (integer-percentage sawtooth, comet tail,
   turnout bimodality) does each method family in `forensics_core` recover, and at what
   effective sample size does the signal vanish?
2. How much of the apparent signal survives conditioning on precinct size (the arithmetic
   confound in `known_traps.md`)?
3. What do the digit and bunching tests say about a *sub-sample* in which the published
   literature finds no anomalies (e.g. large cities in 2018)? This is the false-positive check.
4. What is the smallest unit of aggregation (precinct → territorial commission → region) at
   which each method still has power? The Soviet data will be aggregated; this project tells
   us what aggregation costs.

Out of scope: any claim about who falsified what. The deliverable is calibrated detectors and
their power curves, not an electoral verdict.

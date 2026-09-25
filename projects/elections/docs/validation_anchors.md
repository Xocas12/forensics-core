# Validation anchors: elections

What a working method must reproduce. A detector that fails these is broken, whatever else it
finds. Nothing here is an analysis result: these are published targets and the arithmetic
facts a loader must match before any test is run.

Every fact below was read from the source cited, in this scaffolding session. Items marked
**TO CONFIRM** were not read from a primary source and must be checked before use.

## Tier 0: the data must load correctly

Before any statistical claim, the loader must reproduce these totals. They are the cheapest
possible test that the scrape, the encoding and the column mapping are right.

| Election | Precinct rows | Registered voters (sum) | Check |
|---|---|---|---|
| 2011 State Duma, 4 Dec 2011 | 95,225 | 109,229,337 | United Russia 32,371,737 = 49.31 % |
| 2018 presidential, 18 Mar 2018 | 97,699 | 109,008,428 | Putin 56,430,712 = 76.69 % |

Sources: row counts and column counts were counted locally from
`dkobak/elections` `data/2011.csv.zip` (29 columns) and `data/2018.csv.zip` (24 columns).
The 2011 national totals were read from the archived Central Election Commission portal page
(Wayback snapshot 2021-12-29 of the `vybory.izbirkom.ru` results root for the 2011 Duma). The
2018 totals are those of Central Election Commission Resolution 152/1255-7 of 23 March 2018,
read from the archived English results page on `cikrf.ru`.

**A discrepancy to decide about, not to paper over.** The archived commission portal's own
2018 summary shows 56,426,399 votes for Putin and 109,001,306 registered voters, 4,313 votes
and 7,122 voters fewer than the resolution, reportedly after four polling stations were
cancelled. Pick one as the anchor, record which, and expect precinct sums to match that one.

## Tier 1: the three published signatures

These are the replication targets, in the order they should be attempted.

### 1. Integer-percentage excess mass (the sawtooth)

**Claim.** Turnout and vote-share percentages pile up at integer values far more often than
binomial noise allows, and the excess is concentrated in specific regions.

**Reference.** Kobak, Shpilkin & Pshenichnikov (2016), "Integer percentages as electoral
falsification fingerprints", *Annals of Applied Statistics* 10(1): 54–73. The supplementary
dataset is on Figshare (DOI 10.6084/m9.figshare.3126883.v2, CC BY 4.0) and covers Russia
2000–2012 plus Poland 2010 and Spain 2011 in a reduced ten-column format.

**Method.** `forensics_core.digits.integer_pct.integer_excess`, whose Monte-Carlo null redraws
each precinct's numerator as Binomial(registered voters, observed share). This is the paper's
own null model.

**What counts as reproduced.** A significant positive excess in 2011 and 2018 nationally; the
excess concentrated in the same regions the paper names; and the excess vanishing when the
test is applied to the Poland 2010 and Spain 2011 control data in the same supplement. That
last check is the one that shows the method is not detecting arithmetic.

### 2. The comet tail (turnout versus vote share)

**Claim.** In the two-dimensional histogram of precinct turnout against the winner's vote
share, honest precincts form a single cloud, while a tail extends toward the (100 %, 100 %)
corner. Shpilkin's estimator takes the vote total in the tail, above the level implied by the
distribution at ordinary turnout, as a count of anomalous votes.

**Reference.** Sergey Shpilkin's method, described in Kobak, Shpilkin & Pshenichnikov (2016)
and in their *Significance* article of the same year. **TO CONFIRM:** the exact estimator
definition and the published anomalous-vote counts for 2011 and 2018 were not read from a
primary source in this session; read the papers before treating any number as a target.

**Known fragility.** The estimate is sensitive to which regions are included. Report it with
and without the largest contributing regions, and at territorial-commission as well as
precinct level.

### 3. Turnout bimodality

**Claim.** The distribution of precinct turnout has a second mode near 100 % that honest
elections do not produce.

**Reference.** Klimek, Yegorov, Hanel & Thurner (2012), "Statistical detection of systematic
election irregularities", *PNAS* 109(41): 16469–16473. **TO CONFIRM:** whether the paper's
supplementary material contains the underlying election data or only code and figures was not
established; the follow-up hunt covering this was still running when this file was written.

**Caveat that belongs in the result.** Bimodality alone is not a signature; genuine urban and
rural heterogeneity produces it too. The claim is about the *joint* turnout–vote-share
distribution and the location of the second mode. See `known_traps.md`.

## Tier 2: the false-positive check

A detector that fires everywhere is useless. Before transferring any method to another
project, run it on a subsample where the published literature reports no anomaly, and on the
Poland and Spain control data in the Kobak et al. supplement. Record the false-positive rate
alongside every power number. This is what the `gosplan` project will inherit and cannot
compute for itself.

## Provenance of the data used

`dkobak/elections` states in its own README that the precinct data was scraped from the
official commission portal by Sergey Shpilkin (through 2021) and Ivan Shukshin (2024). The
sum of registered voters in the 2011 file matches the commission's own national total, which
is consistent with that provenance but is not an independent verification of it. The live
commission portal is unreachable from outside Russia, so re-scraping to check is not
available here; see `data/ACCESS_NOTES.md`.

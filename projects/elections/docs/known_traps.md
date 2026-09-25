# Known traps: elections

Confounds that mimic the falsification signal. Every result must be shown robust to these
before it is believed.

## 1. Small precincts produce round percentages honestly

A precinct with 100 registered voters can legitimately report exactly 70.0 % turnout. With
250 voters, 4 in 10 possible turnout values land within 0.05 of an integer; with 2,500 voters,
fewer than 1 in 20 do. **Any integer-percentage test that does not weight or condition on
precinct size detects arithmetic, not fraud.** Military units, hospitals, ships, remote
settlements and prison precincts are the usual small-*n* cases.

Mitigation encoded in `forensics_core.digits.integer_pct.integer_excess`: units below
`min_denominator` are excluded and counted; the Monte-Carlo null redraws the numerator as
Binomial(denominator, p) so that the expected integer mass is computed per precinct size.

## 2. Turnout bimodality has honest sources too

Turnout distributions can be bimodal because of genuine heterogeneity (urban vs rural, ethnic
republics with different mobilisation patterns), not only because of ballot stuffing. The
Klimek et al. (2012) argument is about the *joint* distribution of turnout and vote share and
about the location of the second mode near 100 %; a second mode alone is not a signature.

## 3. The comet tail depends on which precincts are on the tail

Shpilkin's turnout–vote-share relationship can be inflated by a handful of regions. Report
the tail estimate with and without the top contributing regions, and at the territorial
commission level, before quoting a national anomalous-vote count.

## 4. Data-entry and scraping artefacts

Precinct tables are scraped from a hierarchical portal. Missing leaves, duplicated territorial
commissions, encoding errors in Cyrillic names and column-order changes between elections all
produce "impossible" rows (turnout above 100 %, votes exceeding ballots issued). Run the
`00_data_audit` notebook checks (row counts against the CEC's published totals, arithmetic
identities per row) before any test; log every row dropped.

## 5. Different rules, different denominators

"Turnout" can be ballots issued / registered voters, or ballots found in boxes / registered
voters; 2011 and 2018 tables differ in which columns exist (absentee certificates, mobile
boxes). Fix the definition in `docs/data_dictionary.md` and use it consistently across years.

## 6. Multiple testing

With ~85 regions × several statistics × two elections, some region-level tests will reject by
chance. Use rank metrics against the published regional rankings rather than counting
rejections; pre-register which statistics are the replication targets (see
`validation_anchors.md`).

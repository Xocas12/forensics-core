# Validation anchors — gosplan

## Read this first: one anchor is not enough, and the project cannot pretend otherwise

This project has **exactly one** validation anchor. A single anchor means any detector will be
fit and validated on the same event. There is no held-out positive, no way to estimate a
false-positive rate from within the project, and therefore a hard ceiling on the strength of
any claim this project can make.

Two consequences, to be written into every result:

1. Detector calibration must come from elsewhere. The `elections`, `aaer` and `china`
   projects supply the score-to-precision mapping; here the score is a **ranking**, not a
   probability. See `docs/method_transfer.md` in the shared library.
2. The honest output is a **bound under a stated assumption** — "reported distortion is at
   least X in sector S over years Y, assuming the padding mechanism resembles the anchor" —
   not a point estimate of aggregate distortion.

## The anchor: the Uzbek cotton affair

**Claim.** Cotton harvest figures for the Uzbek Soviet Socialist Republic were systematically
padded over roughly a decade, exposed in the 1980s, followed by prosecutions and revised
figures.

**Magnitude, from the best accessible academic source.** During **1978–1983**, about
**4.548 million tons** of non-existent raw cotton were reported, for which the state paid
**2.866 billion rubles** (1.178 billion of it in bonuses).

Source: Cucciolla, R. (2017), *Cahiers du monde russe* 58/4, freely readable at
`https://journals.openedition.org/monderusse/10133`, paragraph 23, quoting the Soviet
investigation; corroborated in the author's doctoral thesis at IMT Lucca.

**An internal inconsistency to resolve before using the number.** The same article's
paragraph 11 gives 270,000–340,000 tons per year, which does not reconcile with 4.548 Mt over
six years (that would be about 758,000 t/yr). Both figures are in the same text. Establish
which refers to what — total padding versus a particular subset or period — before treating
either as a target. A Wikipedia figure of 981,000 tons for 1983 alone is **unverified**
against any primary or academic source and must not be used as it stands.

**Direction and window are what the detector must recover:** an upward bias in reported Uzbek
cotton output, concentrated in the late 1970s and early 1980s, ending with the exposure.

## Physical correlates the falsifiers did not control

The anchor is testable only because output was reported while some physical quantities were
recorded independently. What is actually obtainable:

| Correlate | Status | Note |
|---|---|---|
| FAOSTAT seed cotton, USSR | **Verified, and it covers the window.** Area code 228, item 328, element 5510: 31 years, 1961–1991, official flag. 1975: 7,864,000 t; 1980: 9,100,000 t; 1983: 9,221,000 t; 1985: 8,755,000 t; 1990: 8,305,000 t | Union-level, not republic-level. Cotton lint for the same area is flagged unofficial |
| FAOSTAT, Uzbekistan | Verified, but **starts in 1992** with no back-cast | Useless for the anchor window; useful for the post-Soviet comparison |
| USDA Foreign Agricultural Service, production supply and distribution | **Verified, and it covers the window.** USSR 1960–1986, Uzbekistan from 1987, twelve attributes including area and yield. USSR production, thousand 480-lb bales: 1978: 11,907; 1980: 12,401; 1983: 9,976; 1985: 12,777 | An independent Western estimate of the same quantity: the natural cross-source reconciliation partner for the FAOSTAT series |
| Amu Darya water delivery | **Does not cover the window.** The CAWater-Info Aral database table is 1992–2025 only | The irrigation-withdrawal correlate that the design assumed is not available for 1978–1983 from this source. A different hydrology source must be found or the correlate dropped |
| Ginning capacity, rail freight, textile inputs | Not yet located in machine-readable form | Transcription targets |

**Note what this does to the design.** Two independent value series covering the window
(FAOSTAT and the USDA) plus Soviet official figures give a three-way reconciliation, which is
exactly what `forensics_core.reconcile` is for. The hydrological correlate, which was to be
the *independent* physical check, is currently missing for the anchor period. That gap is a
finding about feasibility and belongs in the project README, not buried here.

## The corpus that makes the project possible at all

**The CIA declassified estimates are reachable, but not from the CIA.** `cia.gov/readingroom`
blocks scripted access outright: the first request is denied with an Akamai-style "Access
Denied" redirect, identical across user agents, headers, cookies and paths, for search pages,
document pages and PDF URLs alike. It is a block, not a rate limit.

The mirror is the path of record: the archive.org collection `ciareadingroom` holds
**973,499 documents** with per-document PDFs and optical-character-recognition text, and is
queryable through the standard archive.org search and metadata APIs. Searches returned 784
hits for "Soviet economy GNP", 328 for "Soviet agricultural statistics cotton" and 33 for
"Soviet economic statistics falsification". Three PDFs were fetched and checksummed.
**Caveat:** it is a third-party upload from October 2024 and its completeness relative to the
CIA's own holdings has not been verified.

**Congressional compendia**, free and confirmed downloadable: *USSR: Measures of Economic
Growth and Development, 1950-80* (Joint Economic Committee, 1982) at archive.org
(32,136,371 bytes); *Soviet Economy in the 1980s: Problems and Prospects* part 1
(43,421,807 bytes; part 2 unconfirmed); *Gorbachev's Economic Plans* (1987), both volumes in
HathiTrust full view. The committee's own site returns 403 to scripts, so archive.org and the
Wayback Machine are the routes.

**Western reconstructions**, verified: the Maddison Project Database 2023 includes a "Former
USSR" series (code SUN, 158 GDP-per-capita observations, 1860 and 1900–2022). Mark Harrison's
Warwick pages host seven downloadable spreadsheets, including 1928–1985 GNP, employment and
capital basic data drawn from Bergson-school and CIA sources, and six annual input–output
matrices for 1940–45. The Penn World Table, checked rather than assumed, contains **no** USSR
series at all.

## What a transferred detector must do here

1. Rank the Uzbek cotton sector in the 1978–1983 window at or near the top when applied blind
   to the full panel.
2. Not rank it top for the wrong reason: the same detector must not fire equally on sectors
   and periods with no independent evidence of padding, and any such firing must be reported
   rather than filtered away.
3. Survive the weighting-scheme robustness check and the currency-reform and boundary-change
   controls in `known_traps.md`. A result that depends on base-year weights is not a result.

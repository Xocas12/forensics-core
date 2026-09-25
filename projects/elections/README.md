# elections

**Question.** Reproduce known falsification signatures in Russian federal elections at
precinct level, and quantify how much detection power comes from each family of method.

This is the calibration project for digit tests and bunching at round numbers. It has the
strongest ground truth in the programme, the largest sample, and no gated data. It runs first,
and it is where the shared interfaces get shaken out before the other three projects use them.

| | |
|---|---|
| Unit of observation | Polling station (UIK) |
| Elections | State Duma, 4 December 2011; presidential, 18 March 2018 |
| Sample | 95,225 and 97,699 stations |
| Ground truth | Strong: three published, replicable signatures |
| Blocked on a human? | **No** |

## Data status

**Acquirable and validated.** The precinct data is a published re-scrape of the Central
Election Commission's portal whose national totals reproduce the commission's own exactly, and
whose ballot-accounting identity holds for all 95,225 rows of the 2011 file. Details and the
full column schema are in [docs/data_dictionary.md](docs/data_dictionary.md).

**The commission's own portal is unreachable from outside Russia** :  a network-level block,
not a policy one, so the data cannot be re-derived from the authority. The Wayback Machine
holds usable snapshots but with coverage that collapses outside Moscow. Both are documented
with the actual failures in [data/ACCESS_NOTES.md](data/ACCESS_NOTES.md).

| Status | Sources |
|---|---|
| Verified | 14 |
| Partial | 6 |
| Blocked | 4 |
| Unverified | 2 |
| **Total** | **26** |

All 26 are free: nothing in this project is paywalled or registration-gated.

The registry is [data/SOURCES.yaml](data/SOURCES.yaml). Nothing enters a pipeline without an
entry there.

## What must be reproduced

Three published signatures, in the order to attempt them, with the exact targets and their
provenance in [docs/validation_anchors.md](docs/validation_anchors.md):

1. **Integer-percentage excess mass** :  the sawtooth. The cleanest published result and the
   first replication target. The supplement that ships with it includes Poland 2010 and Spain
   2011, which are the false-positive control.
2. **The comet tail** :  the turnout against vote-share relationship, with a tail estimator
   giving an anomalous-vote count.
3. **Turnout bimodality** :  a second mode near complete turnout.

## The trap that decides the analysis

A station with 100 registered voters can honestly report exactly 70 %. In the 2011 file,
**4,228 stations have 100 or fewer registered voters and 17,299 have 250 or fewer**, about
18 % of all stations. An integer-percentage test that ignores station size measures
arithmetic, not fraud. There is no station-type column in the data, so size conditioning is
the only control available. This and five other confounds are in
[docs/known_traps.md](docs/known_traps.md).

## Current state

Scaffolded, with the pipeline up to the tidy frame written and tested.
**No analysis has been run and no findings exist in this tree.** `src/elections/analysis/`
holds stubs with fixed signatures only, and every one of them raises `NotImplementedError`.

| Layer | State |
|---|---|
| `data/SOURCES.yaml` | 26 sources, written from verified fetches |
| `src/elections/acquire/` | acquirers for 12 sources; the other 14 are blocked, unverified, or reference material a machine should not fetch |
| `src/elections/clean/` | column map, loader, derived quantities, acceptance checks that raise |
| `src/elections/features/` | precinct-size bands and the size-conditioning helpers |
| `src/elections/analysis/` | stubs only, one module per validation anchor |
| `notebooks/00_data_audit.ipynb` | coverage, missingness, units, size distribution, arithmetic identity. No inference |
| `tests/` | 118 tests on synthetic fixtures; the real files are not in this repository |

`data/raw/` is empty: nothing has been downloaded into this tree.

## Commands

```
make list       the registry, with the sources an acquirer exists for marked
make dry-run    what `make data` would fetch; makes no request
make data       acquire everything acquirable (needs a real contact string first)
make tidy       build data/processed/precincts.parquet, running the acceptance checks
make test       run the test suite
```

## Next actions

1. Put a real contact string in `config/forensics.toml`; the fetchers refuse to run while it
   holds the placeholder. Then `make data` to populate `data/raw/`, and `make tidy`.
2. Run `notebooks/00_data_audit.ipynb` for coverage, missingness, units and breaks. No
   inference.
3. Decide the 2018 national anchor. The commission's portal summary and its own Resolution
   152/1255-7 disagree, so `elections.clean.checks.check_winner_total` deliberately has no
   2018 value and raises `NoAnchorError` instead of guessing. See
   [data/ACCESS_NOTES.md](data/ACCESS_NOTES.md), action 1.
4. Read the two source papers and replace the TO CONFIRM entries in the validation anchors
   with values read from them. The comet-tail stub is blocked on exactly this.
5. Replicate signature 1, conditioned on station size, and report the false-positive rate on
   the Poland and Spain controls in the same run.

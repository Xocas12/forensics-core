# forensics-core

Statistical forensics of strategically reported data: detecting distortion in numbers produced
by agents with an incentive to distort them.

This repository holds the whole research programme: the shared method library and the four
projects that use it. It used to be three repositories (`forensics-core`, `forensic-elections`
and `forensic-economy`) held together by a git submodule. They were merged with their full
history, so `git log` on any file continues from where it was.

## The programme

Three of the four projects have ground truth and one does not. That asymmetry is the whole
design: methods are developed and scored where truth is knowable, then carried to the Soviet
case where it is not.

| Project | Labels | Role |
|---|---|---|
| [`elections`](projects/elections/README.md) | Strong (published signatures, replicable prior findings) | Calibrate digit and bunching methods |
| [`aaer`](projects/aaer/README.md) | Strong (SEC enforcement actions as positives) | Calibrate supervised / PU learning, benchmark against published AUC |
| [`china`](projects/china/README.md) | Partial (self-admitted falsification, a statistical-reform discontinuity) | Calibrate cross-source reconciliation against physical proxies |
| [`gosplan`](projects/gosplan/README.md) | Almost none (one anchor event) | **The target.** Methods validated above are transferred here |

**Unifying hypothesis.** Distortion concentrates at discontinuities in the incentive
function: the round vote share, the 100 % plan-fulfilment bonus threshold, the
analyst-consensus EPS, the provincial growth target.
`forensics_core.bunching.notch.scan_candidate_notches` makes "find the notch, estimate excess
mass around it" a first-class operation.

**Second signal, equally weighted.** Fabricated series contain *too little* noise. A reported
yield series with less year-on-year variance than rainfall permits is impossible regardless
of level (`forensics_core.dispersion`).

## The four projects

| | Question | Docs |
|---|---|---|
| `elections` | Reproduce known falsification signatures in Russian federal elections (2011 State Duma, 2018 presidential) at precinct level, and quantify how much detection power comes from each family of method | [README](projects/elections/README.md) · [docs](projects/elections/docs/) |
| `aaer` | Reproduce the Beneish M-score baseline and the Bao et al. (2020) ML benchmark with SEC enforcement releases as labels | [README](projects/aaer/README.md) · [docs](projects/aaer/docs/) |
| `china` | Measure the provincial-sum vs national GDP gap; test provincial series against physical proxies; use the unified-accounting reform as a natural experiment | [README](projects/china/README.md) · [docs](projects/china/docs/) |
| `gosplan` | Bound the volume of reporting distortion in Soviet statistics using methods calibrated above. Mostly transcription, not downloads | [README](projects/gosplan/README.md) · [docs](projects/gosplan/docs/) |

## The method library

`packages/forensics_core` is the shared library. Its public surface is fixed in
[INTERFACES.md](packages/forensics_core/INTERFACES.md) and its history in
[CHANGELOG.md](packages/forensics_core/CHANGELOG.md).

| Subpackage | Purpose |
|---|---|
| `digits` | Benford first / second / first-two digits (χ², MAD, Kuiper); terminal-digit uniformity; excess mass at integer percentages (Kobak–Shpilkin–Pshenichnikov) |
| `bunching` | Polynomial counterfactual density and excess-mass estimator; notch vs kink; **`scan_candidate_notches`**, the programme's first-class "find the notch" operation; bootstrap and placebo inference |
| `dispersion` | **Underdispersion**: variance below a physical floor is a fabrication signal regardless of level; too-smooth series; Carlisle too-good-to-be-true balance |
| `reconcile` | Flow-conservation reconciliation on a graph and gross-error detection, in the vocabulary of process data reconciliation (global test, measurement test, serial elimination) |
| `labels` | Positive-unlabeled learning (Elkan–Noto, bagging PU) |
| `eval` | Rank metrics (AUC, average precision, NDCG@k, precision@k) and the `Dataset` / `Detector` / `evaluate` / `transfer` harness |
| `inject`, `power`, `effect` | Distortion injection, the power atlas and aggregation ladder, and the common effect-size scale |
| `control`, `redteam`, `notches` | The false-positive budget, the adversarial null corpus, and the notch catalogue |
| `provenance` | `SOURCES.yaml` registry model and validation, append-only fetch log, checksums, contact-header and rate-limit policy, never-fetch-twice cache |

Every statistical routine is pure (no I/O, no globals, no plotting) and returns a
`TestResult` or a frozen dataclass containing them. Library tests use synthetic data only.

Design notes:

- `dispersion/underdispersion.py` matters more than it looks. Fabricated series
  characteristically contain *too little* noise.
- `reconcile/` is lifted from chemical process data reconciliation. "Reported flows violate
  conservation; find the minimum perturbation restoring feasibility; flag the nodes needing
  large corrections" is mature engineering, and its vocabulary is used deliberately.

## Layout

```
forensics-core/
├── CONTRACT.md                  the thirteen rules that bind every session
├── ROADMAP.md                   build order, gates, and every work-order card
├── DATA_STATUS.md               source × project × access tier × status
├── workorders/                  card and ambiguity-report templates
├── config/forensics.toml        contact string (REQUIRED before any fetch) and per-host rate limits
├── packages/forensics_core/     the shared method library
│   ├── INTERFACES.md · CHANGELOG.md · docs/
│   ├── src/forensics_core/
│   └── tests/
└── projects/{elections,aaer,china,gosplan}/
    ├── README.md                question, data status, current state, next actions
    ├── data/SOURCES.yaml        the source registry — nothing enters a pipeline without an entry
    ├── data/ACCESS_NOTES.md     what failed, what is gated, what needs a human
    ├── data/{raw,interim,processed}/   gitignored; rebuilt by `make data`
    ├── src/<name>/{acquire,clean,features,analysis}/
    ├── notebooks/00_data_audit.ipynb
    ├── docs/{research_question,data_dictionary,validation_anchors,known_traps}.md
    └── tests/
```

## How to run

Requirements: [`uv`](https://docs.astral.sh/uv/), GNU make, git. Python 3.12 is pinned.

```sh
make setup          # uv sync --all-packages + pre-commit hooks
make test           # the library and all four projects
make test-core      # the library only
make test-gosplan   # one project
make lint
# Put a real name and email in config/forensics.local.toml ([http].contact) first — every
# network script refuses to run while the placeholder is in place (SEC EDGAR requires it).
make data           # all four projects; never fabricates; fails loudly per source
make data-aaer      # one project
make validate-sources
```

`make data` is idempotent: every successful fetch is checksummed and recorded in
`data/SOURCES.yaml`, every attempt is appended to `data/fetch_log.jsonl`, and a source is
never fetched twice unless forced.

## Rules

The rules are in [CONTRACT.md](CONTRACT.md). The ones the code enforces directly:

1. No invented URLs: sources are verified by an actual fetch (HTTP status, bytes, SHA-256,
   timestamp) or recorded as `unverified` / `blocked` with a reason.
2. Every fetch attempt is logged.
3. No synthetic data under `data/`; fixtures live in `tests/fixtures/` with a `synthetic_` prefix.
4. Fail loudly and continue.
5. Raw data never enters git (`.gitignore` plus a pre-commit hook).
6. Access policies are respected: contact header, per-host rate limits, aggressive caching.
7. "Not found" and "not free" are different statuses.

## Status

Scaffold, shared library, source registries and acquisition pipelines built; free sources
attempted. **No analysis has been run and no findings exist in this tree.** See
[DATA_STATUS.md](DATA_STATUS.md) and [ROADMAP.md](ROADMAP.md).

## Related repositories

| Repository | What it is | State |
|---|---|---|
| [psephos](https://github.com/Xocas12/psephos) | standalone election anomaly-detection tool, CLI and library | **works** |
| [forensics-core](https://github.com/Xocas12/forensics-core) | this repository: the method library and all four research projects | scaffold; no analysis run |
| [gosplan-env](https://github.com/Xocas12/gosplan-env) | multi-agent environment where reporting pathologies emerge from incentives | skeleton; nothing run |
| [forensic-elections](https://github.com/Xocas12/forensic-elections), [forensic-economy](https://github.com/Xocas12/forensic-economy) | the former project repositories, merged into this one | superseded; their open issues still hold the elections and economy cards |

This repository works under a discipline that forbids running anything before its gate, and it
contains no result. psephos is deliberately the opposite: it is meant to be run today.

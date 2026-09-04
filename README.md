# forensics-core

Shared method library for a programme in **statistical forensics of strategically reported
data**: detecting distortion in numbers produced by agents with an incentive to distort them.

It is vendored as a git submodule (`packages/forensics_core`) into the two project
repositories:

| Repository | Projects | Labels |
|---|---|---|
| `forensic-elections` | `elections` — Russian federal elections, precinct level | Strong: published, replicable falsification signatures |
| `forensic-economy` | `aaer` — SEC enforcement as labels for accounting misstatement | Strong: enforcement actions as positives |
| | `china` — provincial vs national GDP, physical proxies | Partial: admitted falsification, a reform discontinuity |
| | `gosplan` — Soviet economic statistics | Almost none: one anchor event. **The target.** |

Methods are developed and scored where truth is knowable, then carried to the Soviet case.
This library is what makes the transfer mechanical: shared code, shared interfaces, shared
evaluation harness ([docs/method_transfer.md](docs/method_transfer.md)).

## What is in it

| Subpackage | Purpose |
|---|---|
| `digits` | Benford first / second / first-two digits (χ², MAD, Kuiper); terminal-digit uniformity; excess mass at integer percentages (Kobak–Shpilkin–Pshenichnikov) |
| `bunching` | Polynomial counterfactual density and excess-mass estimator; notch vs kink; **`scan_candidate_notches`** — the programme's first-class "find the notch" operation; bootstrap and placebo inference |
| `dispersion` | **Underdispersion**: variance below a physical floor is a fabrication signal regardless of level; too-smooth series; Carlisle too-good-to-be-true balance |
| `reconcile` | Flow-conservation reconciliation on a graph and gross-error detection, in the vocabulary of process data reconciliation (global test, measurement test, serial elimination) |
| `labels` | Positive-unlabeled learning (Elkan–Noto, bagging PU) |
| `eval` | Rank metrics (AUC, average precision, NDCG@k, precision@k) and the `Dataset` / `Detector` / `evaluate` / `transfer` harness |
| `provenance` | `SOURCES.yaml` registry model and validation, append-only fetch log, checksums, contact-header and rate-limit policy, never-fetch-twice cache |

The public surface is fixed in [INTERFACES.md](INTERFACES.md).

## Use

```sh
make setup   # uv sync (+ pre-commit hooks)
make test
make lint
```

Every statistical routine is pure (no I/O, no globals, no plotting) and returns a
`TestResult` or a frozen dataclass containing them. Tests use synthetic data only.

## Design notes

- `dispersion/underdispersion.py` matters more than it looks. Fabricated series
  characteristically contain *too little* noise. Reported yields with less year-on-year
  variance than rainfall permits are impossible regardless of level.
- `reconcile/` is lifted from chemical process data reconciliation. "Reported flows violate
  conservation; find the minimum perturbation restoring feasibility; flag the nodes needing
  large corrections" is mature engineering, and its vocabulary is used deliberately.

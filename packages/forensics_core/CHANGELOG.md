# Changelog

Changes to `forensics_core`, the method library at `packages/forensics_core`.

Every entry names the `INTERFACES.md` changes it carries, because all four projects code
against that contract and a silent change there breaks them.

Versions 0.1.0 to 0.3.0 were tagged `core-vX.Y.Z` while the library was a separate repository
vendored into two project repositories as a submodule. Since the merge the projects use the
library at the same commit, so there is nothing to tag or bump.

## Unreleased

- The library, `forensic-elections` and `forensic-economy` are one repository. The library
  moved to `packages/forensics_core/`; `scripts/release.sh`, the projects' `bump_core.sh`
  and the `submodule-parity` CI job are gone. No INTERFACES change.
- The projects were pinned to 0.3.0 and now run against the library as it is on `main`, which
  adds `effect.py` (WO-109), `power/aggregation.py` (WO-101) and `redteam.py` (WO-108) and
  reads `__version__` from installed metadata. All four project suites pass against it.

## 0.3.0

- `CONTRACT.md`: the thirteen rules that bind every session, identical in all three
  repositories (WO-000). No INTERFACES change. Two files already cited it by rule number
  before it existed — `gosplan/seal.py` cites rule 5, `eval/harness.py` cites rule 9 — and
  `tests/test_contract.py` freezes the numbering so those citations cannot silently come to
  mean something else.
- `control.py`: the control corpus and the false-positive budget (WO-103). INTERFACES change:
  new public module. `Control`, `ControlReport`, `control_report`, `from_rejections`,
  `worst_verdict`, `has_external_control`, `format_control_table`. The verdict is decided
  against the Monte Carlo error at the control's own sample size, so the same excess is
  calibrated at small n and anticonservative at large n. There is deliberately no corpus
  average.
- `eval/harness.py`: `transfer` gained `controls=`, and `TransferResult` gained
  `fitted_detector` and `control_reports` (WO-105). INTERFACES change: two new fields and one
  new keyword argument, both additive. Controls are scored with the instance that scored the
  target, because a false-positive rate belongs to the object that made the claim rather than
  to a refitted sibling of it. Also imports `Sequence`, which the new signature used without
  it; lazy annotations hid this from every test.
- `pyproject.toml`: version corrected to match the tag. It read `0.1.0` throughout the 0.2.0
  release.

## 0.2.0

- `notches.py`: the declarative notch catalogue (WO-104). `NotchEntry`, `load_notches`,
  `validate_notches` and `scan_all`. INTERFACES change: new public module. `incentive` and
  `evidence` are mandatory on every entry, so a catalogue cannot record a bare round number.
  `scan_all` passes `bunching_side` through, without which a reward-above notch scores
  negative and ranks last.
- CI, a release procedure and the `submodule-parity` job (WO-002).

## 0.1.0

First release. The library as built during scaffolding, plus the P1 work landed since.

- `inject.py`: the distortion injection harness (WO-102). Four injectors returning an
  `InjectionRecord`. Injectors are deliberately independent of the estimators that catch them.
- `provenance/runner.py`: the shared acquisition CLI every project delegates to.
- `provenance/manifest.py`: `Source` gained `evidence`, `download_plan` and `verification`;
  the `verified` rule now accepts a successful probe as well as an acquired file.
- `reconcile/gross_error.py`: `measurement_test` sizes the multiple-comparison family by the
  number of testable measurements rather than all of them.
- `workorders/`: card and ambiguity templates (WO-001).
- CI (WO-002).

Both project repositories are pinned to this release. The `submodule-parity` job fails if they
ever pin different commits, because the two halves of the programme would then run different
method code and their results would silently stop being comparable.

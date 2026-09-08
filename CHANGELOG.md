# Changelog

Releases of `forensics_core`, the method library vendored into `forensic-elections` and
`forensic-economy` as the submodule `packages/forensics_core`.

Every entry names the `INTERFACES.md` changes it carries, because the two project repositories
code against that contract and a silent change there breaks them both.

Tags are `core-vX.Y.Z`. A project repository moves to a release with `scripts/bump_core.sh`.

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

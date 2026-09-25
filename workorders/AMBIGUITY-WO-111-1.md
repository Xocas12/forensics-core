AMBIGUITY REPORT   WO-111   src/forensics_core/power/lookup.py:minimum_detectable_effect, detectable

Question (one sentence):
With no atlas argument in `minimum_detectable_effect(method, n, *, aggregation="unit", power=0.8)`,
where do stored atlases live, and which one answers when several stored atlases cover the same
method?

What the spec says / does not say (quote):
The card fixes the signature with only a method name, and says "Every stored atlas records the
library version, the estimator settings and the seed. Two atlases with different settings are
different atlases and the loader keeps them apart." It lists `data/atlas/README.md` in the write
list, which implies `packages/forensics_core/data/atlas/` is the store. It does not say how a
file is found there (naming scheme? an index? the spec's `method` field?), whether the store is
read from the source tree or from installed package data (a `data/` directory outside
`src/forensics_core/` is not in the built wheel: pyproject builds only `src/forensics_core`), or
which atlas wins when two with different settings, seeds or library versions both cover
`method`. `atlas.py` has `save_atlas(atlas, path)` / `load_atlas(path)` with an explicit path and
nothing that discovers atlases.

Options considered (A/B/...), and why the spec does not decide:
A. A fixed directory (`data/atlas/`) scanned for `*.parquet`, selecting by spec `method`, and
   refusing when more than one matches (caller must disambiguate by settings/seed/version).
B. As A, but "newest library version wins".
C. An explicit index file (e.g. `data/atlas/index.yaml`) naming the canonical atlas per method.
D. Ship atlases as package data under `src/forensics_core/` (read via importlib.resources), so
   other repositories can query an installed library, which is the card's stated purpose.
The card picks none of these; B silently prefers one measurement over another, and A/C/D differ
in public behaviour and in whether a cross-repository user can query at all.

Impact if the wrong option is picked:
A gosplan or china card would cite a minimum detectable effect from an atlas measured with
different estimator settings than the ones it runs, which is exactly the silent comparison the
PowerSpec exists to prevent; or the lookup would not work at all from another repository.

Tests blocked:
None of the card's must-pass conditions, provided the atlas is passed explicitly. As built, both
functions take an extra keyword `atlas: DataFrame | str | Path | None = None` (INTERFACES
permits added keywords with defaults). `atlas=None` raises NotImplementedError citing this
report. Once decided, `atlas=None` should resolve through the chosen rule.

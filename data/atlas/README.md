# data/atlas — the published power atlases

This directory is where a **published** power atlas lives: a measured curve, on disk, that
`forensic-elections` and `forensic-economy` can load and cite. The human-readable summary is
`docs/power_atlas.md`; this file is the storage contract.

No atlas is committed here yet. `WO-200` has not run, so no elections hierarchy has been
acquired and the curves that exist so far are synthetic measurements of the methods on
generated data (WO-100, WO-101). Publishing those is permitted — synthetic is one of the two
allowed populations — but nothing has been published into this directory, and an empty
directory is the honest state rather than a gap. The first real atlas lands here when there is
a measurement worth citing.

## What may be published

Only atlases computed on **elections data or synthetic data**. Nothing else. A curve measured
on any other population does not go in this directory, whatever it shows.

## The format

A published atlas is one parquet file, written by
`forensics_core.power.lookup.publish_atlas`:

- one row per `(n, effect_size)` with the columns of
  `forensics_core.power.atlas.ATLAS_COLUMNS`:
  `method, n, effect_size, power, power_se, n_replicates, alpha, false_positive_rate`;
- the record of how it was measured in the `_spec` column, a JSON `PowerSpec`.

Two keys are required in that record's `settings`, and `publish_atlas` writes both:

| key | what it is |
|---|---|
| `library_version` | `forensics_core.__version__` at publication. Two releases are two different atlases. |
| `aggregation` | The rung measured: `"unit"`, or a ladder level name. |

An atlas whose spec carries no `library_version` is refused at load. A number whose source
release cannot be named is not citable, which is the whole reason this directory exists.

A ladder rung is reduced to one atlas per file at publication: `n` becomes the number of
aggregate units at that rung, and `mean_group_size` and `semantics` move into the settings. A
rung carrying two aggregation semantics that disagree is two atlases, and publishing it without
naming which one is refused.

## Publishing one

```python
from forensics_core.power.lookup import publish_atlas

publish_atlas(frame, "data/atlas/integer_excess.parquet", method="integer_excess")
```

`frame` is a `power_curve` result, or an `aggregation_ladder` result with `aggregation=` naming
the rung. All validation runs before anything is written, so a refused publication leaves no
partial file.

## Loading one

```python
from forensics_core.power.lookup import power_lookup

lookup = power_lookup("data/atlas")  # a directory, a file, or a list of either
lookup.minimum_detectable_effect("integer_excess", 300)
```

The loader keeps atlases apart by their recorded version, seed and estimator settings. Two
atlases that differ are two entries, and a query matching both raises rather than choosing.
`lookup.describe()` prints what is loaded, with the release and seed on every line.

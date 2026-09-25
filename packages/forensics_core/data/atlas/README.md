# data/atlas

Stored power atlases for `forensics_core.power`. **No atlas is published here yet.** This
directory holds the format description until the first atlas is computed, and each atlas that
is added later goes in as one parquet file beside this README.

## What may be stored here

Only atlases measured on **elections data or synthetic data** (WO-111). An atlas measured on
any other source — Soviet, Chinese or AAER series in particular — is forbidden here, because a
power number calibrated on the data a later claim is made about makes that claim circular.

Test atlases are not stored here. Tests build synthetic atlases in a temporary directory.

## Format

One parquet file per atlas, written by `forensics_core.power.atlas.save_atlas` and read by
`load_atlas`. Parquet needs the optional extra: `pip install 'forensics-core[parquet]'`.

Columns, in order (`forensics_core.power.atlas.ATLAS_COLUMNS`), one row per
`(n, effect_size)`:

| column | meaning |
|---|---|
| `method` | the method name a query asks for |
| `n` | sample size, drawn without replacement from a population believed clean |
| `effect_size` | injected effect; `0.0` is always present and is the false-positive row |
| `power` | rejection fraction at `alpha` |
| `power_se` | binomial standard error of `power` |
| `n_replicates` | replicates per cell |
| `alpha` | nominal level |
| `false_positive_rate` | the `power` of the `effect_size == 0` row at the same `n` |

plus one `_spec` column, a JSON string repeated on every row, holding the `PowerSpec` the atlas
was measured with: `method`, `alpha`, `n_replicates`, `seed`, `settings` (estimator settings).
`load_atlas` removes the column and restores the spec into `frame.attrs["spec"]`.

Two atlases whose specs differ are different atlases and are stored as different files.

## Open questions

- The library version is **not yet recorded** in a stored atlas, although WO-111 requires it:
  `PowerSpec` has no version field. See `workorders/AMBIGUITY-WO-111-4.md`.
- How a file here is found by a query that names only a method, and which file answers when
  several cover the same method, is open: `workorders/AMBIGUITY-WO-111-1.md`. Until it is
  settled, queries pass the atlas path explicitly.
- Aggregated atlases (`aggregation` other than `"unit"`) have no format yet:
  `workorders/AMBIGUITY-WO-111-3.md`.

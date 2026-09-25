# DATA_STATUS

Source status for all four projects. The detailed reports were written separately for the two
former project repositories and are kept verbatim:

- [docs/data_status/elections.md](docs/data_status/elections.md): `elections`, recomputed
  2026-09-07 from `projects/elections/data/SOURCES.yaml`
- [docs/data_status/economy.md](docs/data_status/economy.md): `aaer`, `china` and `gosplan`,
  recomputed 2026-09-07 from their three registries

The summary below was recounted from the four `SOURCES.yaml` registries with a YAML parser when
the repositories were merged, and matches both reports. Where a registry and any prose
disagree, the registry wins.

**162 sources across four projects.** No data has been downloaded into this tree and no
analysis has been run.

| project   | verified | partial | blocked | unverified | total   |
|-----------|----------|---------|---------|------------|---------|
| elections | 14       | 6       | 4       | 2          | 26      |
| aaer      | 33       | 4       | 2       | 3          | 42      |
| china     | 24       | 5       | 6       | 2          | 37      |
| gosplan   | 31       | 10      | 13      | 3          | 57      |
| **total** | **102**  | **25**  | **25**  | **10**     | **162** |

`make data-status` prints the live version of this table from the registries.

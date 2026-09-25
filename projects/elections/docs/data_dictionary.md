# Data dictionary: elections

Source of record: `dkobak/elections`, files `data/2011.csv.zip` and `data/2018.csv.zip`.
Precinct-level (UIK) protocol lines re-scraped from the Central Election Commission portal.
Everything below was read from the files themselves during scaffolding, not inferred.

## Files

| File | Rows | Columns | Election |
|---|---|---|---|
| `2011.csv` | 95,225 | 29 | State Duma, 4 December 2011 |
| `2018.csv` | 97,699 | 24 | Presidential, 18 March 2018 |

Encoding UTF-8, comma-separated, header row present, one row per polling station.

## Columns, 2011 file

Column names are the Russian protocol line labels as published by the commission. The
canonical English names in the right-hand column are what `elections.clean` emits; use those
downstream so the 2011 and 2018 files share a schema.

| # | Original label (abbreviated) | Canonical name | Meaning |
|---|---|---|---|
| 0 | `region` | `region` | Federal subject, Russian name |
| 1 | `tik` | `tik` | Territorial election commission |
| 2 | `uik` | `uik` | Polling station number within the commission |
| 3 | Число избирателей, внесенных в список | `registered` | **Registered voters. The denominator for turnout and the size variable for the small-precinct trap.** |
| 4 | бюллетеней, полученных УИК | `ballots_received` | Ballots received by the station |
| 5 | выданных проголосовавшим досрочно | `ballots_early` | Issued to early voters |
| 6 | выданных в помещении | `ballots_in_station` | Issued in the polling place |
| 7 | выданных вне помещения | `ballots_outside` | Issued away from the polling place |
| 8 | погашенных | `ballots_cancelled` | Unused, cancelled |
| 9 | в переносных ящиках | `in_mobile_boxes` | Found in mobile boxes |
| 10 | в стационарных ящиках | `in_stationary_boxes` | Found in fixed boxes |
| 11 | недействительных | `invalid` | Invalid ballots |
| 12 | действительных | `valid` | Valid ballots |
| 13–20 | absentee-certificate and loss lines | `abs_*`, `lost_*` | Eight administrative lines; present in 2011, largely absent in 2018 |
| 21–27 | seven party lists | `party_<n>_<slug>` | Votes per party list, in ballot order |
| 28 | `url` | `source_url` | The commission portal URL the row was scraped from |

The seven 2011 party lists in ballot order: Just Russia, Liberal Democratic Party, Patriots of
Russia, Communist Party, Yabloko, **United Russia** (column 26), Right Cause.

The 2018 file has 24 columns: the same station identifiers, twelve protocol lines and the
eight presidential candidates. The absentee-certificate lines do not carry over, because the
absentee system was replaced for that election. **This is why the two files cannot be stacked
without an explicit column map**; `elections.clean` owns that map.

## Verified integrity checks

These ran against the real file during scaffolding and all passed. They belong in
`tests/` as the loader's acceptance criteria.

| Check | Result on `2011.csv` |
|---|---|
| Row count | 95,225, matching the source README |
| Sum of `registered` | 109,229,337, matching the commission's national total exactly |
| Sum of United Russia votes | 32,371,737 (49.31 % of the commission's reported total) |
| Ballot identity `invalid + valid == in_mobile_boxes + in_stationary_boxes` | Holds for **all 95,225 rows**, zero violations |
| Station labels | All numeric; no free-text station names in the `uik` column |

## Derived quantities

Fix these definitions once and use them everywhere; the 2011 and 2018 protocols differ, so an
implicit definition will silently change meaning between elections.

- **Turnout (ballots-in-boxes basis)** = (`in_mobile_boxes` + `in_stationary_boxes`) /
  `registered`. Preferred, because it is available in both files and matches the quantity the
  published literature analyses.
- **Turnout (ballots-issued basis)** = (`ballots_early` + `ballots_in_station` +
  `ballots_outside`) / `registered`. Differs from the above by lost and uncounted ballots.
- **Vote share** = party or candidate votes / (`valid` + `invalid`). State whether the
  denominator includes invalid ballots; the literature usually does.

## Precinct-size distribution, and why it decides the analysis

Measured on the 2011 file:

| Statistic | Registered voters |
|---|---|
| Minimum | 2 |
| 10th percentile | 161 |
| Median | 996 |
| Maximum | 22,671 |

**4,228 stations have 100 or fewer registered voters, and 17,299 have 250 or fewer**, about
18 % of all stations. At 100 voters, whole-number vote counts land exactly on integer
percentages by arithmetic necessity. Any integer-percentage test that ignores this measures
station size. `forensics_core.digits.integer_pct.integer_excess` takes `min_denominator` for
exactly this reason, and reports how many units it dropped.

**There is no precinct-type column.** Military, hospital, prison and remote stations cannot be
identified directly from this file, and the `uik` column is purely numeric, so they cannot be
identified from names either. Size conditioning is the only control available from this
source. If type identification matters, it needs a separate source; see `known_traps.md`.

## Provenance and its limit

The source README states the data was scraped from the commission portal by Sergey Shpilkin
(through 2021) and Ivan Shukshin (2024), and documents per-election discrepancies against the
portal's own totals, mostly attributed to results cancelled after publication. The 2011 sums
reproduce the portal total exactly. Independent re-verification against the portal is **not
possible from outside Russia**: the portal is unreachable at the network level. See
`data/ACCESS_NOTES.md`.

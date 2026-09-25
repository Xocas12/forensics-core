# Data dictionary - gosplan

Two things live here: the schema for a transcribed printed table, and the queue of tables to
transcribe. Both are generated from code (`gosplan.transcribe.schema`,
`gosplan.transcribe.targets`), so this document describes them but is not their definition.
If the two ever disagree, the code is right and this file is stale.

Everything below concerns **transcription**. The machine-readable sources this project also
uses (FAOSTAT, USDA, Maddison, Harrison, the World Bank archive, the Hokkaido series) keep
their publishers' own schemas and are documented in `data/SOURCES.yaml`; the only field this
project adds to them is the registry id.

---

## Why the schema is shaped the way it is

The primary reported series exist as scanned Russian printed tables. The optical character
recognition bundled with those scans is not usable for numbers: the registry's inspection of
the 1985 annual found the cover title itself garbled and numeric rows arriving with column
separators merged or dropped, so row and column alignment is lost. No curated
machine-readable transcription of the annuals exists on Zenodo, GitHub or Harvard Dataverse.
The series has to be created by people typing from page images.

That decides the design. The unit of transcription is not a number; it is a **cell carried
with everything needed to know what the number means**. A figure separated from its currency
basis, its territorial basis, its definition and its page is not recoverable later, and the
four confounds that would silently destroy a result all live in exactly those fields.

---

## Table schema

One filled file is one printed table. The table-level fields repeat on every row, and the
validator checks they never vary within a file. The column order is
`gosplan.transcribe.schema.FIELD_NAMES`, derived from the pydantic models, so a generated
template cannot drift from what the validator enforces.

### Table-level fields

| Column | Type | Required | Meaning |
|---|---|---|---|
| `source_id` | string | yes | id of the `SOURCES.yaml` entry the scan came from |
| `volume` | string | yes | volume as printed on the title page, transliterated |
| `edition_year` | integer 1900-1995 | yes | year the edition covers (1985 for the 1985 annual) |
| `page` | integer | yes | printed page number the table starts on |
| `table_number` | string | yes | as printed; the literal `unnumbered` when there is none |
| `title_ru` | string | yes | table heading copied character for character |
| `title_translit` | string | yes | the same heading transliterated to ASCII |
| `territorial_basis` | enum | yes | `pre_1939_boundaries`, `present_boundaries`, `other_stated`, `unstated` |
| `transcriber` | string | yes | who typed it; a transcription nobody signs cannot be double-checked |
| `transcription_date` | ISO date | yes | `YYYY-MM-DD` |

### Cell-level fields

| Column | Type | Required | Meaning |
|---|---|---|---|
| `row_label` | string | yes | row stub as printed |
| `row_label_translit` | string | no | transliteration, when it helps |
| `column_label` | string | yes | column head as printed |
| `column_label_translit` | string | no | transliteration |
| `period` | string | yes | `YYYY`, `YYYY-YYYY` for a plan period, `YYYY/YY` for a crop year |
| `value_raw` | string | yes | the cell exactly as printed: separators, decimal comma, conventional marks |
| `value` | float | no | the parsed number; **blank** when the cell holds a mark rather than a figure |
| `unit` | string | yes | unit of measurement as the table states it |
| `currency_basis` | enum | yes | `not_monetary`, `old_roubles`, `new_roubles`, `foreign_currency` |
| `row_role` | enum | yes | `data`, `subtotal`, `total` |
| `column_role` | enum | yes | `data`, `subtotal`, `total` |
| `definition_note` | string | no | what the table says it is measuring, copied not paraphrased |
| `confidence` | enum | yes | see below |
| `notes` | string | no | anything a second transcriber would need |

### `confidence`

The last three values are not degrees of doubt. They record what was printed.

| Value | Meaning | `value` |
|---|---|---|
| `clear` | digits unambiguous | required |
| `ambiguous_digit` | one or more digits uncertain; alternatives go in `notes` | required |
| `damaged_print` | print damaged or blurred but read | required |
| `illegible` | could not be read | blank |
| `nil_printed` | the cell carried a nil mark (a dash) | blank |
| `no_data_printed` | the cell carried a no-data mark (an ellipsis) | blank |

**A nil mark is not a zero.** "The phenomenon did not occur" and "the value was zero" are
different statements, and a parser that returns 0.0 for a dash invents data. The parser
returns `kind="nil"` with no value, and the validator rejects a row that puts a number in a
marked cell.

The default marker sets are a **default, not a finding**: each volume prints its own key of
conventional signs, and `parse_printed_number` takes the marker sets as arguments so a
transcriber who finds a different key can pass it.

### Printed-number conventions the parser handles

| Printed | Parses to | Digits kept | Decimals |
|---|---|---|---|
| `9221` | 9221.0 | `9221` | 0 |
| `9 221` (any space width) | 9221.0 | `9221` | 0 |
| `12,1` | 12.1 | `121` | 1 |
| `1 234,5` | 1234.5 | `12345` | 1 |
| `-` | no value, `nil` | | |
| `...` | no value, `no_data` | | |
| `1O,5` (letter O) | refused, `unparsable` | | |

`digits` is what a first-digit or first-two-digit test would consume, and what the
double-transcription comparison counts disagreements over.

---

## What the validator checks

`python -m gosplan.transcribe validate <file>`. Errors mean do not use the file; warnings mean
a person must look and then either fix the cell or record why it is right.

**Structural.** Header exactly matches the schema columns (`missing_column`,
`unknown_column`); required fields present (`missing_required`); enumerations hold declared
members (`bad_enum`); table-level fields constant within the file (`table_field_varies`);
integers and dates well formed (`bad_integer`, `out_of_range`, `bad_date`, `bad_period`); no
cell transcribed twice (`duplicate_cell`).

**Semantic.** A monetary-looking unit must declare which rouble (`currency_basis_missing`, an
error); a rouble basis on a physical unit is queried (`currency_basis_unexpected`, a warning,
because the monetary-unit test is a heuristic); pre-reform periods in new roubles must be
explained (`new_roubles_before_reform`); territorial basis must be stated, fatally so for any
period spanning 1939-40 (`territorial_basis_unstated`); the confidence flag must match what
`value_raw` actually holds (`confidence_marker_mismatch`, `value_present_without_number`,
`value_missing`, `value_mismatch`, `unparsable_value`).

**Arithmetic.** Every printed total is checked against the sum of the `data` cells in its
group, along both axes, with subtotals excluded so they cannot double-count
(`total_mismatch`). The tolerance is not a chosen epsilon: a figure printed to `d` decimals
differs from the truth by at most `0.5 * 10**-d`, so `n` addends plus one printed total give
a bound of `(n + 1) * 0.5 * 10**-d`. A total whose addends are not all numbers is reported as
`total_unchecked` rather than silently skipped.

**Distributional.** A value about ten, a hundred, a tenth or a hundredth of its own series
median is flagged `decimal_shift_suspected`. This is the only check that can fire on a correct
transcription, so it is a warning: a real order-of-magnitude jump in a Soviet series is
interesting and the validator must not be able to erase it.

---

## Double transcription, and the gate on digit tests

`known_traps.md` trap 9 is the rule: digit tests on badly transcribed tables detect the
transcription. Two independent readings of the same table are compared with
`python -m gosplan.transcribe compare a.csv b.csv`, which reports:

- **cell disagreement rate**, the share of jointly transcribed cells read differently at all;
- **digit disagreement rate, per position**, which is what a digit test actually consumes.

Digits are aligned from the most significant end by default, because that is the position a
Benford-type test reads. Where two readings differ in length, every position past the shorter
string counts as compared and disagreeing: a dropped digit displaces everything after it, and
counting it any other way would understate the damage.

**There is no built-in threshold.** No published standard exists for an acceptable
transcription error rate in this setting, and inventing one would be exactly the kind of
borrowed number this programme refuses. `digit_tests_permitted` requires the threshold as an
argument, so whoever runs a digit test has to write down what they consider acceptable and
defend it next to the result.

The third source of a second reading, where one exists, is not a second person: the Hokkaido
SRC series are an independent existing transcription of the same Narkhoz tables and can be
compared against directly. Two caveats travel with them, both recorded in the registry:
missing values are coded `0.0`, and at least one series' unit label disagrees with its
magnitudes.

---

## Transcription targets, in priority order

Generated from `gosplan.transcribe.targets`; `python -m gosplan.transcribe targets` prints the
current list. "Seen" means somebody opened the volume and found the table. Everything else is
a place to look.

| # | Target | Source | Seen? | Why it is in this position |
|---|---|---|---|---|
| 1 | `narkhoz_1985_raw_cotton` | `ia_narkhoz_1985_item` | **yes** | The anchor's physical series in the one volume actually inspected. Worked example, and the first table on which to measure a transcription error rate. |
| 2 | `narkhoz_raw_cotton_1975_1989` | `ia_narkhoz_collection` | no | One year is an example; the series is what a detector runs on. Successive editions restate earlier years, and the restatements are themselves evidence. |
| 3 | `uzbek_ssr_annual_cotton` | `rusneb_uzbek_annual` | no | The anchor is a republic-level event. **No copy anyone can open has been located.** See `data/ACCESS_NOTES.md`. |
| 4 | `narkhoz_plan_fulfilment` | `ia_narkhoz_collection` | no | Without a distribution of fulfilment percentages the bunching question cannot be asked. Whether the annuals print anything fine enough to bin is unknown. |
| 5 | `narkhoz_national_income_produced_and_used` | `ia_narkhoz_collection` | no | The reconciliation test. Cross-checkable against the Hokkaido sections 121 (national income produced) and 122 (national income used); read the file names off SESS.html rather than constructing them. |
| 6 | `narkhoz_gross_output_by_branch` | `ia_narkhoz_collection` | no | The numerator of the hidden-inflation comparison. Currency basis and output definition are the whole game here. |
| 7 | `narkhoz_physical_output_selected` | `ia_narkhoz_collection` | no | Its denominator, and the input to the underdispersion test. |
| 8 | `soviet_input_output_table` | `hathitrust_ge_tempo_1966_io` | no | Print only, and blocked on a library visit. Harrison's 1940-45 matrices are the only machine-readable Soviet I-O tables and cover the war economy alone. |

Targets 4 and 8 are the two where the project may find that the printed source does not exist
in an accessible form. That would be a result about feasibility and belongs in the README, not
in a quiet deletion from this table.

---

## Pitfalls: units, territory, definitions

### 1. The 1961 currency reform

The rouble was redenominated 10 to 1. A value series crossing 1961 shows a discontinuity of
exactly one order of magnitude, and later volumes sometimes restate pre-1961 figures in new
roubles and sometimes do not. `currency_basis` is mandatory on every cell and has no
"unstated" member: a transcriber who cannot tell leaves the cell blank and says why.

### 2. Territorial changes, 1939-40

The annexations changed the territory "USSR" refers to. Yearbooks often print both bases side
by side. `territorial_basis` is a table-level field, and leaving it unstated is a hard error
for any table whose periods span 1939 or 1940.

### 3. Physical units are not one unit

The three cotton series this project can compare measure three different things:

| Source | Quantity | Unit | Coverage |
|---|---|---|---|
| FAOSTAT, area 228 | seed cotton, unginned (item 328) | tonnes | USSR 1961-1991, official flag |
| FAOSTAT, area 235 | seed cotton | tonnes | Uzbekistan 1992 onward only |
| USDA FAS PSD | cotton **lint** | thousands of 480 lb bales | USSR 1960-1986, Uzbekistan 1987 onward |
| Soviet annuals | raw cotton (khlopok-syrets) | thousand tonnes, to be confirmed per table | as transcribed |

One 480 lb bale is 217.72 kg. Lint is not seed cotton: converting between them needs a
ginning outturn ratio, which is itself a reported quantity. Reconciling the three is a units
problem before it is a forensics problem, and the conversion used must be stated with every
result. Note also that FAOSTAT flags USSR cotton **lint** as unofficial while flagging seed
cotton as official, so the flag column has to survive into any derived table.

The USDA file carries no "Former Soviet Union" aggregate, so union totals for 1987-1991 have
to be summed across successor republics. Whichever republics are included is a choice that
must be recorded.

### 4. Definitional revisions mid-series

Gross output, net output, "normative net output", and the 1988 shift toward net material
product presentations are different quantities under similar headings; enterprises were also
reclassified between ministries. Copy what the table says into `definition_note` and never
splice across an unrecorded change.

### 5. Index numbers

Soviet growth rates swing enormously with base-year weights: early-year (1926/27) prices
weight the goods that later expanded most. Any result must be shown robust across weighting
schemes, and any comparison of official with Western growth rates must align the weights
first. A single index number is not a result.

### 6. Missing coded as zero

The Hokkaido SRC files code missing values as `0.0`. A loader that does not handle this turns
"not published" into "the value was zero", which is the same error the nil-mark rule exists to
prevent, arriving through a different door.

---

## Where files live

| Path | Contents |
|---|---|
| `data/SOURCES.yaml` | the registry; nothing enters a pipeline without an entry |
| `data/raw/` | downloads, exactly as fetched, never edited, never in git |
| `data/fetch_log.jsonl` | one line per fetch attempt, successful or not |
| `data/transcription/templates/` | generated blank forms (created at runtime) |
| `data/transcription/filled/` | filled forms and their validation reports (created at runtime) |
| `data/interim/`, `data/processed/` | derived tables |

The two `data/transcription/` directories are created by whoever runs
`python -m gosplan.transcribe template --out ...`; this repository ships neither them nor any
data.

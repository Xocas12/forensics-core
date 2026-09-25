# gosplan

**Question.** Bound the volume of reporting distortion in Soviet economic statistics, with a
magnitude and a sectoral distribution, using methods calibrated on the three projects that
have ground truth.

This is the target project. It runs last, it has almost no labels, and its job is to say
honestly how far methods validated elsewhere can be pushed where nothing can be checked.

| | |
|---|---|
| Unit of observation | Sector-year, or republic-year, depending on what can be transcribed |
| Period | 1928-1990, with the anchor in 1978-1983 |
| Ground truth | One anchor event, plus one partial second labelled source |
| Blocked on a human? | **Yes**, for the republic-level volume that covers the anchor |
| Analysis run? | **No.** `src/gosplan/analysis/` is stubs only |

## This is a transcription project, not a download project

Most of the source material exists only as scanned Russian-language printed tables, and the
optical character recognition bundled with those scans is not usable for numbers. The
registry's inspection of the 1985 annual is the finding that shapes everything else: the cover
title itself came out garbled, and numeric rows arrive with column separators merged or
dropped, so row and column alignment is gone. No curated machine-readable transcription of
the Soviet annuals exists on Zenodo, GitHub or Harvard Dataverse; searches for one came back
empty.

So the deliverable here is a **transcription and validation pipeline**, plus whatever is
already machine-readable:

- `src/gosplan/transcribe/` builds forms from the schema, validates a filled form against
  the schema, the traps and the table's own printed totals, and compares two independent
  transcriptions to measure the per-digit-position disagreement rate;
- `src/gosplan/acquire/` fetches the 23 registry sources a machine can actually get;
- `src/gosplan/analysis/` holds the five analysis entry points, every one a stub.

## Data status

| Status | Sources |
|---|---|
| Verified | 31 |
| Partial | 10 |
| Blocked | 13 |
| Unverified | 3 |
| **With an acquirer** | **23** |
| **Needing a human** | **10** |

The registry is [data/SOURCES.yaml](data/SOURCES.yaml); nothing enters a pipeline without an
entry there. Every entry's `verification.verdict` is `not_verified`: no independent second
agent re-checked any of the 57 claims, so treat them as one careful session's findings.
What is free, what is gated and what is unreachable is set out bluntly in
[data/ACCESS_NOTES.md](data/ACCESS_NOTES.md).

**What is free and ready.** The physical cotton series that bracket the anchor (FAOSTAT seed
cotton for the USSR 1961-1991, USDA FAS lint 1960-1986), the Western reconstructions (Maddison
2023, Harrison's Bergson-school compilation, the World Bank archive that juxtaposes official
net material product with Khanin's alternative and the CIA's GNP estimate), the congressional
compendia (part 1 of the 1982 *Soviet Economy in the 1980's* and volume 1 of *Gorbachev's
Economic Plans* only; the second halves of both were never located in a confirmed form), 145
machine-readable transcriptions of official Narkhoz series from Hokkaido, and 28 scanned
volumes of the union annual.

**The CIA Reading Room blocks scripted access outright**, with an Akamai denial on the first
request, identical across user agents and paths. The acquirer targets the archive.org mirror
collection instead, which holds 973,499 documents and answers anonymously. That mirror is a
third-party upload from October 2024 whose completeness against the CIA's own holdings has
not been verified, and its search matches item metadata rather than document text.

## The two things this project is actually blocked on

**1. The Uzbek republic annual.** *Narodnoe khoziaistvo Uzbekskoi SSR* is the republic-level
source for the padded series, and no digitised copy anyone can open has been located: not on
archive.org, not in HathiTrust, not on publ.lib.ru. istmat.org lists six editions, of which
only 1988 and 1990 fall near the padding decade, so **most of the padding decade is missing
from every digitised source found**. The 1957 edition is catalogued at the Russian national
digital library, which refuses non-Russian egress. Republic-level work therefore rests on
whatever the union volumes print by republic, which is less.

**2. The physical correlate for the anchor window.** The design assumed river-withdrawal data
would give a check the falsifiers did not control. The series actually fetched begins in
1992, nine years after the padding ended. Two unopened pages of the same database and a
registration-gated runoff archive are the remaining candidates. Until one of them yields a
pre-1992 series, the independent physical check on the anchor is FAOSTAT against USDA and
nothing else, and both are outside estimates of the same reported quantity rather than a
driver nobody could touch.

The Russian State Archive of the Economy is a third constraint of a different kind. Its
electronic inventories list both target collections, Gosplan (fond 4372) and the Central
Statistical Administration (fond 1562), publicly and without a login, although only the
fond-level list was reached, so whether the opis and delo listings inside those two fonds are
populated is unverified. On the evidence actually read, **there is no remote access to
documents**: scans ordered in the reading room are handed over on the user's own physical
media. So you can learn what exists from here and obtain none of it, with one lead unopened:
the archive's GIS UIAD system and its electronic file-pre-ordering page were never fetched,
and the registry names GIS UIAD as the one thing that could change this picture.

## What the project has instead of labels

One anchor: the Uzbek cotton affair, roughly 1978-1983. The best accessible academic source
gives 4.548 million tonnes of non-existent raw cotton over that window, for which the state
paid 2.866 billion roubles. **The same article gives a per-year figure that does not reconcile
with it**, and settling which refers to what is a prerequisite, not a footnote. See
[docs/validation_anchors.md](docs/validation_anchors.md).

One partial second source: Mark Harrison's plan-fraud replication dataset, a case-level index
of prosecuted Soviet reporting fraud for 1943-1962, with establishment, branch, republic, what
was falsified and the sentence. It is not a second anchor. It labels what was *prosecuted*, in
a different period, which makes it a positive-unlabelled problem.

With one anchor, any detector is fitted and validated on the same event. The strongest honest
claim this project can make is a **bound under a stated assumption**, not a point estimate of
aggregate distortion.

## Traps that decide the analysis

Nine confounds are in [docs/known_traps.md](docs/known_traps.md). The four that decide this
project's design are below, and two of them are built into the transcription schema as
mandatory fields, `currency_basis` and `territorial_basis`, because a basis nobody wrote
down while looking at the page cannot be recovered afterwards.

- **The 1961 currency reform** rescaled every monetary series by ten, and later volumes
  sometimes restate pre-1961 figures and sometimes do not. `currency_basis` is mandatory and
  has no "unstated" value.
- **The 1939-40 territorial changes** mean pre-war and post-war "USSR" are different
  territories. `territorial_basis` is mandatory and leaving it unstated is a hard error for
  any table spanning those years.
- **Padding was pervasive and often anticipated by the ministries receiving the reports.** If
  everyone distorts there is no honest control group, so the analysis is designed around
  *relative* comparison: which sectors, years or republics distort more than their peers.
- **Transcription error mimics everything.** A digit test on a badly transcribed table detects
  the transcription, so a table may not go near a digit test until two independent readings
  have been compared and the disagreement rate written down.

## Usage

```
uv run python -m gosplan.acquire --list          # the registry, marked with what has code
uv run python -m gosplan.acquire --all --dry-run # what would be fetched; makes no requests
uv run python -m gosplan.acquire --all           # fetch (fill in the contact string first)

uv run python -m gosplan.transcribe targets                              # the queue
uv run python -m gosplan.transcribe template --out <dir>                 # blank forms
uv run python -m gosplan.transcribe validate <filled.csv>                # check one
uv run python -m gosplan.transcribe compare <a.csv> <b.csv>              # two readings

uv run pytest -q projects/gosplan/tests
```

`config/forensics.toml` still holds the placeholder contact string, and the fetcher refuses to
run until it is a real address. On Windows, `--list` prints Cyrillic source names and needs
`PYTHONIOENCODING=utf-8`.

## Current state

Scaffolded, with the acquisition and transcription pipelines implemented and tested.
**No analysis has been run and no findings exist in this tree.** Nothing has been downloaded:
`data/raw/` is empty and the acquisition code has never been run against the network from
here.

## Next actions

1. Fill in the contact string, run `make data`, and see which of the 23 acquirers actually
   work against the live hosts. Expect `publ.lib.ru` to need repeating and `istmat.org` to
   fail intermittently.
2. Confirm whether istmat.org's HTML chapter pages contain table text rather than just chapter
   indexes. If they do, that is the single largest change to the project's cost, because it
   would turn most of the transcription queue into scraping.
3. Transcribe target 1 twice, independently, and publish the disagreement rate. That number
   decides whether any digit-based method is usable here at all, and it is the cheapest
   informative thing this project can do.
4. Settle the anchor's internal inconsistency by reading Cucciolla (2017) rather than choosing
   a figure.
5. Find the republic annual, or write up its absence as a constraint on the design.

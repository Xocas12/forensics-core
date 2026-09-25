# DATA_STATUS: forensic-elections

Recomputed on 2026-09-07 directly from `projects/elections/data/SOURCES.yaml`. Every count in
this file was produced by reading that registry with a YAML parser and counting, not by
copying a number out of prose. Where the registry and a README disagree, the registry wins;
see [Registry against prose](#registry-against-prose).

## What this session did, and did not do

This session did scaffolding and acquisition wiring only. It read the source registry, the
access notes and the project README, ran `python -m elections.acquire --list` (which makes no
network request), recounted every figure below from the registry itself, and wrote this file.
**No analysis was run.** Every module under `src/elections/analysis/` is still a stub that
raises `NotImplementedError`, and nothing in this file is a result about an election: the only
numbers here are counts of registry rows. **No data was downloaded.** `data/raw/`,
`data/interim/` and `data/processed/` are untouched, no fetch was attempted, and the only
acquisition commands used were `--list` and `--dry-run`, which make no requests. **Nothing was
invented.** Every source id, URL claim, access tier and status below comes from
`SOURCES.yaml`, which was itself built from real fetch attempts with an independent
verification pass; where the registry records a gap, this file records the gap rather than
filling it from memory. Nothing under `packages/forensics_core` was edited, and no
`pyproject.toml`, lockfile or git state was touched.

## Summary

26 sources, one project.

| project   | verified | partial | blocked | unverified | total | with an acquirer | in a gated tier |
|-----------|----------|---------|---------|------------|-------|------------------|-----------------|
| elections | 14       | 6       | 4       | 2          | 26    | 12               | 0               |

| project   | free | total |
|-----------|------|-------|
| elections | 26   | 26    |

**Every source in this project is free.** Nothing here is paywalled, registration-gated, or
behind an archive visit. That is unusual in this programme and is why `elections` is the
calibration project that runs first.

Independent second-pass verification: **14 confirmed, 1 refuted, 11 not
checked**. The refuted entry is `notelections_online_mirror`, kept in the registry at status
`unverified` rather than deleted, so that the next person who finds the same search result
does not repeat the attempt.

Acquirer coverage: **12 of 26** entries have an acquirer (10 verified,
2 partial). The other 14 have none: 8 are free and
reachable and are deliberately left alone (an R scraping tool, repository landing pages, two
recorded negative searches, a HEAD probe recording a negative result, and lower-priority
duplicate snapshots), 4 are blocked, and 2 were never confirmed to exist. The reason
per source is in `data/ACCESS_NOTES.md`.

## The main table

Source by source, sorted by access tier, then status, then id. The `acquirer` column is the
asterisk column of `python -m elections.acquire --list`.

| id                                 | project   | access tier | status     | acquirer | 2nd-pass check |
|------------------------------------|-----------|-------------|------------|----------|----------------|
| `cecscraper_github`                | elections | free        | verified   | no       | confirmed      |
| `cikrf_eng_2018_wayback`           | elections | free        | verified   | yes      | confirmed      |
| `dkobak_elections_2011`            | elections | free        | verified   | yes      | not checked    |
| `dkobak_elections_2018`            | elections | free        | verified   | yes      | not checked    |
| `dkobak_elections_data_readme`     | elections | free        | verified   | yes      | not checked    |
| `dkobak_elections_github`          | elections | free        | verified   | no       | confirmed      |
| `dkobak_elections_repo_listing`    | elections | free        | verified   | yes      | not checked    |
| `figshare_kobak_aoas2016_supp`     | elections | free        | verified   | yes      | confirmed      |
| `gislab_cik_uik_20140404_head`     | elections | free        | verified   | no       | not checked    |
| `gislab_cik_uik_20180215`          | elections | free        | verified   | yes      | not checked    |
| `gislab_wiki_wayback`              | elections | free        | verified   | yes      | not checked    |
| `harvard_dataverse_search`         | elections | free        | verified   | no       | not checked    |
| `palladain_rus_pres_2018`          | elections | free        | verified   | yes      | confirmed      |
| `pmc_klimek_2012`                  | elections | free        | verified   | yes      | not checked    |
| `evgeny_boger_rus_elections_stats` | elections | free        | partial    | no       | confirmed      |
| `modos189_cikinfo`                 | elections | free        | partial    | no       | not checked    |
| `shpilkin_livejournal`             | elections | free        | partial    | no       | confirmed      |
| `slinko_2018_uik_scrape`           | elections | free        | partial    | no       | confirmed      |
| `wayback_vybory_2011_duma`         | elections | free        | partial    | yes      | confirmed      |
| `wayback_vybory_2018_pres`         | elections | free        | partial    | yes      | confirmed      |
| `cec_vybory_izbirkom_live`         | elections | free        | blocked    | no       | confirmed      |
| `cikrf_ru_live`                    | elections | free        | blocked    | no       | confirmed      |
| `gislab_wiki_live`                 | elections | free        | blocked    | no       | not checked    |
| `klimek_pnas_2012_si`              | elections | free        | blocked    | no       | confirmed      |
| `datahub_2011_duma`                | elections | free        | unverified | no       | confirmed      |
| `notelections_online_mirror`       | elections | free        | unverified | no       | refuted        |

## Access tiers that need a human

**There are none.** No entry in this registry is `registration`, `paywalled`,
`archive_visit` or `manual_transcription`. Nobody has to buy anything, register anywhere, or
travel anywhere to run this project.

That is a statement about the *access tier*, not about reachability, and the two are
different. Four free sources cannot be fetched from here, and one of them needs a person with
a browser.

### Free, but not fetchable by a machine

| Source | What is wrong | What a person would have to do |
|---|---|---|
| `klimek_pnas_2012_si` | The publisher returns HTTP 403 to non-browser clients, the PubMed Central copy serves a reCAPTCHA interstitial, and the authors' own data host no longer resolves | **Open the article's DOI page in a browser, save the supplementary PDF, and transcribe the estimator definition and any published figures into `docs/validation_anchors.md`.** This is not a purchase and not a registration: the material is free and only the automated route is blocked |
| `cec_vybory_izbirkom_live` | `vybory.izbirkom.ru` does not resolve at all, from the system resolver or from two public ones | Nothing that is clearly in scope. From a Russian network vantage point a person could check whether the hostname resolves and whether the 2020-era captcha gating is still in force. Whether that is acceptable here is the owner's call |
| `cikrf_ru_live` | Resolves, but TCP to ports 80 and 443 times out from this machine and is refused outright from a second, unrelated network | As above |
| `gislab_wiki_live` | HTTP 502 from the origin: a server-side outage of that wiki subdomain, not a block | Nothing. The archived copy is acquired instead (`gislab_wiki_wayback`), so nothing is lost while the origin is down. Worth re-testing occasionally |

Note the distinction the registry insists on. The commission's own portal was **not reached at
all**; `klimek_pnas_2012_si` **exists, is free, and is bot-blocked**; and
`notelections_online_mirror` was **refuted**, meaning that host now serves an unrelated
personal homepage. Three different failures, recorded three different ways.

## Actions requiring a human, most valuable first

1. **Put a real name and email in `config/forensics.toml` (`[http].contact`).** Unblocks:
   `elections`, entirely. It still holds the placeholder, and every fetcher refuses to touch
   the network until it does not, so all 12 acquirers are inert. A machine must not invent a
   contact address, which makes this a human action by construction. Cheapest and highest-value
   item on this list.
2. **Fetch the Klimek et al. (2012) supplementary material in a browser and transcribe its
   estimator definition and published values into `docs/validation_anchors.md`.** Unblocks:
   `elections` replication targets 2 (the comet tail) and 3 (turnout bimodality), both marked
   TO CONFIRM in the anchors file for exactly this reason. One person, a few minutes.
3. **Decide the 2018 national anchor.** Unblocks: `elections.clean.checks.check_winner_total`,
   which deliberately carries no 2018 value and raises `NoAnchorError` rather than guessing.
   The commission's portal aggregate and its own Resolution 152/1255-7 disagree, reportedly
   after polling stations were cancelled. Pick one, record the choice, and expect precinct sums
   to match it.
4. **Read the other replication paper and replace its TO CONFIRM entries in
   `docs/validation_anchors.md` with values read from it.** Unblocks: the published comparison
   values for replication target 1. The supplement carrying the Poland 2010 and Spain 2011
   false-positive controls is already free, verified and acquired
   (`figshare_kobak_aoas2016_supp`), so this is reading, not access.
5. **Decide whether a check of the commission portal from a Russian network vantage point is in
   scope.** Unblocks: nothing the project needs. It would only establish whether the block is
   geographic. Explicitly optional, and a scope decision rather than a data need.

Items 1 and 2 gate code. Items 3 and 4 gate the interpretation of results that do not exist
yet.

## What is bottlenecked on something a machine cannot fix

**`elections` is not bottlenecked on data.** This is the one project in the programme where no
human stands between the code and its inputs. The precinct-level data for both target
elections is free, published, verified and has acquirers, and the false-positive control data
for Poland 2010 and Spain 2011 ships in the same supplement, which is also acquired.

Two things are genuinely lost, and neither stops the project:

- **Independent re-derivation from the authority.** The commission's portal is unreachable, so
  the published re-scrape cannot be re-derived from source. Its national totals reproduce the
  commission's own archived totals exactly, which is strong corroboration but is not the same
  thing as independent verification. No amount of code fixes this: it is a network-level block
  and possibly a permanent one.
- **A national precinct-level reconstruction from the Wayback Machine as a fallback.** Archived
  coverage collapses outside Moscow, so a per-subdomain coverage census across roughly 85
  regional subdomains for two elections is the prerequisite, not the scrape. That census is a
  project, not a step.

The only real blocker on a human is item 2 above, and it costs a browser and a few minutes
rather than money, an institution, or a trip. Bluntly: with the contact string filled in this
project can proceed to a tidy frame today, and that one paper fetch is the difference between
replicating one published signature and replicating three.

## Registry against prose

Every count in `projects/elections/README.md` and `projects/elections/data/ACCESS_NOTES.md`
was checked against the registry and **all of them agree**: 26 sources, all free,
14 verified / 6 partial / 4 blocked / 2 unverified, 12 with an acquirer,
8 free and reachable with none by choice. No discrepancy was found, and
nothing in this file needed to override the project's own prose.

## Operational note

`uv run python -m elections.acquire --list` **crashes on a Windows console** with
`UnicodeEncodeError: 'charmap' codec can't encode characters`, raised inside
`forensics_core/provenance/runner.py` when it prints registry `name` fields containing
Cyrillic to a cp1252 stream. Run it with `PYTHONIOENCODING=utf-8`. This is a limitation of the
shared library, which this repository vendors as a submodule and must not edit, so it is
reported upstream rather than patched here. The same crash affects `china` and `gosplan` in
`forensic-economy`.

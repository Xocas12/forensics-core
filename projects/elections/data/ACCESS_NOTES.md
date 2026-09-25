# Access notes: elections

What failed, what is gated, and what needs a human. Written from actual fetch attempts made
during scaffolding; every claim here has a corresponding entry in `SOURCES.yaml` and a line
in `fetch_log.jsonl` once `make data` has run.

## Summary

All 26 sources in `SOURCES.yaml` are free; none is paywalled or registration-gated.

| Status | Count |
|---|---|
| Verified (fetched, HTTP 200 or 206, content confirmed) | 14 |
| Partial (reached, but the full dataset was not confirmed) | 6 |
| Blocked (exists, cannot be fetched from here) | 4 |
| Unverified (could not be confirmed at all) | 2 |
| **Total** | **26** |

`tests/test_access_notes_counts.py` recomputes these from the registry and fails if they drift.

**The data path is not bottlenecked.** The precinct data for both target elections is
available and complete. Two things are blocked: re-deriving that data from the original
authority, and one of the three replication targets, whose published estimator definition
sits behind a publisher block (see the comet tail, below).

## Blocked: the Central Election Commission's own portal

Registry ids `cec_vybory_izbirkom_live` and `cikrf_ru_live`. This is the significant access
failure, and it is a network-level block rather than a policy one.

- `vybory.izbirkom.ru` and `www.vybory.izbirkom.ru` **do not resolve at all**: no A record
  from the system resolver, from 8.8.8.8, or from 1.1.1.1. The domain's authoritative name
  servers are self-hosted on `izbirkom.ru`.
- `cikrf.ru`, `www.cikrf.ru` and `izbirkom.ru` resolve to a single address, and TCP
  connections to ports 80 and 443 **time out after roughly 21 seconds** from this machine and
  are **refused outright** from a second, unrelated network.
- It could not be determined from here whether the hostnames still work for clients inside
  Russia. Both outcomes are consistent with what was observed.

**Consequence.** Precinct data cannot be re-scraped from the authority, so the published
re-scrape cannot be independently re-derived. Its national totals do reproduce the
commission's own published totals exactly (see `docs/data_dictionary.md`), which is strong
corroboration but is not the same thing as independent verification.

**What a human could do.** From a Russian network vantage point, check whether the hostnames
resolve and whether the 2020-era captcha gating described in the `CECscraper` documentation is
still in force. Whether that is an acceptable step for this project is the user's call; the
project does not need it to proceed.

## Partial: the Wayback Machine as a fallback

Archived copies of the portal exist and are usable, but coverage is very uneven and cannot
substitute for the mirrors.

- The 2011 Duma results root page has a good snapshot (2021-12-29), from which the national
  totals in `docs/validation_anchors.md` were read. The 2018 presidential root likewise
  (2021-10-17).
- Leaf precinct tables are plain server-rendered HTML in Windows-1251, roughly 3 to 15 KB each,
  needing no JavaScript. One 2018 leaf was fetched and confirmed down to a named precinct.
- **But coverage collapses outside Moscow.** A sample of the archive's index showed dense
  2011 coverage for the Moscow city subdomain and essentially none for a small republic's
  subdomain, which had only a single unrelated 2011 URL and ten territorial-commission pages
  for 2018.

**Verdict.** A national precinct-level reconstruction from the archive is not realistic
without a per-subdomain coverage census across roughly 85 regional subdomains for two
elections. That census is the prerequisite, not the scrape.

## Blocked: the other two

Four registry entries are blocked, not two. Besides the two commission hosts above:

- **`gislab_wiki_live`** returns HTTP 502 from the origin, a 166-byte error body. This is a
  server-side outage of that wiki subdomain, not a geographic block or a TLS failure: the
  sibling host responds normally from here. The archived copy of the same page is acquired
  instead (`gislab_wiki_wayback`), so nothing is lost while the origin is down. Worth
  re-testing occasionally; an outage may end.
- **`klimek_pnas_2012_si`** is the supplementary material of Klimek et al. (2012), and it is
  the one that matters. The publisher returns HTTP 403 to non-browser clients, the PubMed
  Central copy serves a reCAPTCHA interstitial, and the authors' own data host no longer
  resolves. **This blocks a replication target, not just a convenience file**: the turnout
  bimodality anchor and the comet-tail estimator definition are both marked TO CONFIRM in
  `docs/validation_anchors.md` because of it.
  **Human step:** open the article's DOI page in a browser, save the supplementary PDF, and
  transcribe the estimator definition and any published figures into
  `docs/validation_anchors.md`. One person, a few minutes, and it unblocks two of the three
  replication targets.

## Refuted during verification

One source claimed by the first research pass was **refuted** by the independent second pass
and is recorded in `SOURCES.yaml` with status `unverified` rather than removed. The
captcha-free mirror that the `CECscraper` tool was written against no longer exists: every
path on that host now returns an unrelated personal homepage. Tools written against it will
appear to work and return nothing useful.

## Free and confirmed

- The published precinct-level re-scrape covering both target elections, with 95,225 rows for
  2011 and 97,699 for 2018.
  - **The 2011 file was downloaded and checked during scaffolding.** Its row count is 95,225,
    its registered-voter sum is 109,229,337, reproducing the commission's archived national
    total exactly, and the ballot-accounting identity holds for all 95,225 rows with zero
    violations.
  - **The 2018 file was not checked.** Its row count and digest are recorded in the registry
    from the fetch, and the mirror's own README states a registered-voter total of
    109,008,428, matching Resolution 152/1255-7. Neither the sum nor the ballot identity was
    recomputed from the file in this session. `elections.clean.checks` applies both checks to
    2018 as an untested extension of a 2011 measurement; a first failure there is a finding
    about the assumption, not necessarily about the data.
- The supplementary dataset of Kobak, Shpilkin & Pshenichnikov (2016), on Figshare under
  CC BY 4.0, covering Russia 2000-2012 **plus Poland 2010 and Spain 2011**. The two
  non-Russian elections are the control data for the false-positive check and are the reason
  this source is acquired even though its Russian coverage is redundant.

## Nothing here needs money or registration

No source required for this project is paywalled or gated behind a registration. That is
unusual within this programme and is why `elections` is the calibration project that runs
first.

## Actions requiring a human

1. **Decide the anchor for national totals.** The commission's portal aggregate for 2018
   (56,426,399 votes for the winner; 109,001,306 registered) differs from its own Resolution
   152/1255-7 (56,430,712; 109,008,428), reportedly after four polling stations were
   cancelled. Pick one, record the choice, and expect precinct sums to match it.
2. **Read the two papers whose estimators are replication targets** and record the exact
   estimator definitions and published values in `docs/validation_anchors.md`. The comet-tail
   anomalous-vote counts are currently marked TO CONFIRM.
3. **Optional:** decide whether a Russian-network check of the portal is in scope.

## Reachable, but deliberately left without an acquirer

Added when the acquisition modules were written. These eight sources are free and reachable;
`python -m elections.acquire --list` shows them unmarked and `--all` reports them as "no
acquirer implemented for this id". That is a decision, not an oversight, and the reason is
per source:

| Source | Why no acquirer |
|---|---|
| `cecscraper_github` | An R scraping tool, not data, and the portal it targets is unreachable and captcha-gated. Its registry URL is an HTML repository page. |
| `dkobak_elections_github` | The repository landing page. The three artefacts worth holding have their own registry entries (`dkobak_elections_2011`, `_2018`, `_data_readme`) and all three are acquired. |
| `gislab_cik_uik_20140404_head` | A HEAD probe recording a negative result: the earliest commission snapshot is April 2014, and the entry's own conclusion is that it cannot be back-joined to 2011 precinct numbers. Downloading it would contradict what the entry establishes. |
| `harvard_dataverse_search` | A recorded negative search result. Its own download plan says "do not build acquisition against Dataverse for this project". |
| `evgeny_boger_rus_elections_stats` | Covers 2012 only. Neither of this project's two elections. |
| `modos189_cikinfo` | A web application with no data assets; its releases endpoint is empty. Its download plan says "skip". |
| `shpilkin_livejournal` | A blog landing page with no confirmed direct table download; the tables it published are what the acquired mirror redistributes. |
| `slinko_2018_uik_scrape` | A third 2018 snapshot, 33.6 MB. Only its first 300 KB were ever read (the verification pass range-fetched them and identified tab-separated columns), so the file as a whole is an unvalidated third input rather than a check. Lower priority than the two 2018 files already acquired. |

## What the acquirers do fetch, and two places the dry run is misleading

Twelve sources have acquirers: both precinct files, the mirror's README and its directory
listing, the AOAS 2016 supplement that carries the Poland and Spain controls, the GIS-Lab
commission register and its archived documentation, the independent 2018 cross-check, the
three archived official summary pages, and the PubMed Central full text of Klimek et al.

`--dry-run` prints each source's registry URL, which for two of them is not the URL the
acquirer requests:

- `palladain_rus_pres_2018`: the registry URL is the repository landing page; the acquirer
  fetches the raw `uiks-utf8.csv` recorded in that entry's `evidence` field.
- `figshare_kobak_aoas2016_supp`: the registry URL is the JavaScript-rendered landing page,
  which answers a scripted client with an empty body. The acquirer follows the entry's own
  `download_plan`: read the Figshare metadata document, then fetch the payload URL it names.

Neither acquirer constructs a URL; both use one recorded in the registry entry.

## Digests: where they are pinned and where they cannot be

Pinned, so that a changed upstream file fails acquisition rather than the analysis: both
precinct zips, the GIS-Lab commission archive, the Palladain cross-check, the AOAS supplement.

Not pinned, with reason: the mirror's `README.md` and the GitHub directory listing, which are
expected to change and whose changes are the point of re-fetching them; and the four archived
pages, because the Wayback Machine injects a toolbar and timestamps into the body, so the
bytes are not reproducible. The independent verification pass saw exactly this on
`cikrf_eng_2018_wayback`: same content, different digest, six bytes of size difference. A
digest recorded for a Wayback page is a record of one fetch, not an integrity target.

One acquirer carries an extra guard. PubMed Central has already been observed serving a
reCAPTCHA interstitial under HTTP 200 (recorded under `klimek_pnas_2012_si`), and a challenge
page saved as `verified` would be a false integrity claim, so `pmc_klimek_2012` inspects what
came back and reports failure if it looks like an interstitial.

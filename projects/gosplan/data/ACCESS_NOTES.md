# Access notes - gosplan

What is free and digitised, what needs a person, and what is simply not reachable from here.
Every claim below has a corresponding entry in `SOURCES.yaml` with the fetch that produced it.
Where the registry's independent verification pass did not run, the entry's
`verification.verdict` reads `not_verified`, and that is true of **all 57 entries in this
project**: no second agent re-checked any of them. Treat everything here as one careful
session's findings, not as confirmed fact.

## Summary

| | Count |
|---|---|
| Verified (fetched, HTTP 200, content confirmed) | 31 |
| Partial (landing page or some files reached; full dataset not confirmed) | 10 |
| Blocked (exists, cannot be fetched from here) | 13 |
| Unverified (could not be confirmed at all) | 3 |
| **Sources with an acquirer** | **23** |
| **Sources needing a human** | **10** |

**This project is bottlenecked, and not on downloads.** The comparison data is free and
mostly one HTTP request away. The primary reported series is not: it exists as page images
whose optical character recognition is unusable for numbers, and the single volume that covers
the anchor at republic level has not been located in any openable form.

---

## Free, digitised, and already wired up

Twenty-three sources have acquirers. `python -m gosplan.acquire --list` marks them; nothing
below is gated, and none of it needed anything but an anonymous GET.

**The physical cotton series that bracket the anchor.** FAOSTAT bulk crop production carries
USSR seed cotton for all 31 years 1961-1991 with an official flag (the USSR is filed under the
*Europe* regional file, not Asia). USDA FAS PSD carries the same physical quantity as an
independent Western estimate, USSR 1960-1986 and Uzbekistan from 1987. Neither is pinned to a
checksum, because both publishers revise on a schedule and pinning would report a legitimate
republication as corruption.

**The Western reconstructions.** Maddison Project Database 2023 (country code `SUN`, "Former
USSR", 158 GDP-per-capita observations); the World Bank's Easterly and Fischer archive, which
already juxtaposes official net material product, Khanin's alternative and the CIA's GNP
estimate for 1928-1987; Mark Harrison's Warwick pages.

**The congressional compendia, and only half of each.** *Soviet Economy in the 1980's:
Problems and Prospects* (JEC, 1982) is acquired as **part 1 only**, from an archive.org copy;
part 2's committee URL appeared only in web-search results and no archive.org item for it was
located. *Gorbachev's Economic Plans* (JEC, 1987) is acquired as **volume 1 only**, from a
Wayback snapshot of the committee PDF; volume 2 has no confirmed URL and no fetched snapshot.
Both acquirers say so in their result line, and anything computed from either compendium
covers half of it.

**Harrison's plan-fraud dataset is the find of the registry.** The replication data for
"Forging Success: Soviet Managers and Accounting Fraud, 1943 to 1962" (*Journal of Comparative
Economics* 39:1, 2011) is a case-level index of prosecuted Soviet reporting fraud: three
sheets keyed by archival fond, with establishment, accused, branch, republic, what was
falsified and the sentence, including Uzbek and Kazakh agricultural cases. It is the nearest
thing this project has to a **second labelled source**. It is not a second anchor: it labels
what was *prosecuted*, in a different period, which makes it a positive-unlabelled problem
rather than a clean label set.

**The CIA estimates, from the mirror rather than from the CIA.** See below.

**The scans of the union annuals.** archive.org holds 28 volumes of *Narodnoe khoziaistvo
SSSR*. The acquirer takes the collection listing and one metadata document per volume, plus
the 1985 volume's hOCR and page-number sidecars. It deliberately does not pull every volume's
derivatives: that is roughly 1.8 GB, and 10 GB with page images, which is a scoped decision
rather than something `--all` should do.

**The 145 Hokkaido SRC series** are a transcription of official Narkhoz series, and the only
substantial machine-readable transcription of Soviet official statistics located anywhere.

---

## Blocked: the CIA Electronic Reading Room, and why that does not matter much

`cia.gov/readingroom` blocks scripted access outright. No path that is not the home page
returns what it was asked for, in one of two ways: search, document and PDF paths answer a 302
to the reading-room root with an Akamai-style "Access Denied" body, while the `uzbek cotton`
probes (one search URL and two document URLs, registry id `cia_foia_uzbek_cotton`) answered
200 with the reading-room home page in the body instead of the document. The registry records
that the denial was identical across the research user agent, a Chrome user agent with
matching Accept headers, replayed session cookies plus Referer, a single-word query, and a
separate fetch tool, and that the **first** request is denied. It is a block, not a rate limit: retrying cannot help and only adds denied
requests to the CIA's logs. Five registry entries record this and none of them has an
acquirer.

**The route of record is the archive.org collection `ciareadingroom`**, a per-document mirror
of 973,499 items that answers anonymous requests normally through the standard search and
metadata APIs. What `gosplan.acquire` takes from it is the search manifest for the project's
queries, not the corpus; per-document PDFs are pulled by a later scoped step.

**Two caveats that must travel with anything drawn from it.** It is a third-party upload from
October 2024 whose completeness relative to the CIA's own holdings has not been verified. And
archive.org's `advancedsearch` matches item metadata, not full document text, so a search that
returns nothing is evidence about the mirror's metadata rather than about what the CIA
released.

A browser from a US residential address would reach cia.gov directly. Whether that is worth
doing is the user's call; the mirror covers the same documents.

---

## Blocked: everything else, and what kind of block it is

The distinctions here matter. "Not found", "not free" and "not reachable from this network"
are three different things.

| Source | Kind of block | What it would take |
|---|---|---|
| `jec_senate_gov_reports` | 403 to scripts; the files are public | Nothing. The same PDFs are on archive.org and in Wayback snapshots, and the acquirers use those. Only the 1152 snapshot was confirmed by a HEAD (200, `application/pdf`); the 1185 and 1438 snapshots, the second of which is the one the Gorbachev acquirer fetches, are recorded by the availability API alone and were never fetched. |
| `rusneb_uzbek_annual` | **Geographic.** The 403 body is an interstitial telling the user to switch off their VPN | Russian-network egress to see the record at all, and then an assessment of whether the scan is openly viewable or restricted to a reading-room terminal. |
| `istmat_info_dead` | TCP connect fails on both ports; DNS resolves | Nothing to do. The project's content is at istmat**.org**, a different host and a different IP. |
| `hathitrust_full_view` | Cloudflare JavaScript challenge; whole-book download needs a logged-in session | A person with a HathiTrust account. The bibliographic API answers without the challenge and is used for metadata. |
| `icpsr_soviet_search`, `openicpsr_100666_soviet_macro` | Cloudflare challenge, plus a login requirement | A free ICPSR account for openICPSR deposits; a member institution for processed studies. |
| `faostat_api` | 401, "Missing Authorization Header" | Nothing needed: the bulk zips carry identical data with no auth. |
| `usda_psd_opendata_api` | 403, API key required | Nothing needed: the bulk CSV carries the same data. |

**`istmat.ru` is a trap and is in the registry only to name it as one.** It is a personal
history library that happens to hold the domain, unrelated to the Istmat project, and must
never be wired in as a fallback.

---

## Needs a human

Ten sources are listed by `python -m gosplan.acquire --all` at the end of a run:
`faostat_api`, `grdc_portal`, `hathitrust_full_view`, `hathitrust_ge_tempo_1966_io`,
`icpsr_soviet_search`, `openicpsr_100666_soviet_macro`, `rgae_reading_room`, `rsl_search`,
`rusneb_uzbek_annual`, `usda_psd_opendata_api`. Two more are discussed here that the runner
does not count among the ten, because they are free and reachable rather than gated:
`rgae_opisi_online`, whose crawl needs supervision, and `rand_soviet_national_income`, which
has nothing to fetch.

**`rgae_reading_room` and `rgae_opisi_online` - the Russian State Archive of the Economy.**
Both target collections are listed in a public, anonymous, no-login online finding aid:
fond 4372 (Gosplan) and fond 1562 (the Central Statistical Administration) both appear by name
in the electronic inventories at `opisi.rgae.ru`. The finding aid is more open than the brief
assumed. **But on the pages actually read there is no remote access to documents.** The
archive's own page states that
electronic images made to order in the reading rooms are handed to the user on the user's own
physical media, and that copying to tablets and smartphones is not performed. So: you can find
out what exists from here, and you cannot obtain any of it from here. Getting enterprise-level
records means going to Moscow, or to the Voronovskoe reading room.

**Two limits on that conclusion, both recorded in the registry and both unclosed.** Only the
fond-level list was reached in the online finding aid, so whether the opis-level listings and
the delo-level titles inside f.4372 and f.1562 are actually populated is unverified. And two
paths that could change the no-remote-access picture were never opened: the archive's GIS UIAD
system, which the registry names as the one lead that could change it, and the site's
"electronic pre-ordering of files into the reading room" menu item. Neither was fetched, so
nothing is claimed about what either offers.

The inventory crawl itself is possible but slow enough to need supervision: three requests
truncated at 4 to 8 KB under a 50-second timeout and only completed at 400 seconds, and
truncation returns a valid-looking 200. That is why there is no acquirer for it. HTTPS on both
`rgae.ru` and `opisi.rgae.ru` fails outright; plain HTTP works.

**`rsl_search` - the Russian State Library.** Correcting the brief's premise: `dlib.rsl.ru` is
no longer a browsable digital library, only a redirect stub pointing at `search.rsl.ru`, and
`search.rsl.ru` is a client-rendered application that returns zero record links to a
non-browser client. It is a catalogue lead for resolving shelf marks, not a bulk source. RSL
full-text viewing of 20th-century material generally needs an account and often an on-site
terminal; nobody read a page stating those terms, so no claim is made about them here.

**`hathitrust_ge_tempo_1966_io`** - the GE-TEMPO transformation of the 1966 Soviet
input-output table is digitised but search-only, so it needs a library copy or an interlibrary
loan. Same for the Treml volumes.

**`grdc_portal`** - the Global Runoff Data Centre states that its data are free of charge, but
the portal is a JavaScript application and delivery is by e-mailed link after a submitted
request. Whether it holds Amu Darya or Syr Darya stations covering the 1970s and 1980s **was
not confirmed**; check the period of record before requesting.

**`rand_soviet_national_income`** is a correction to an assumption worth recording: the
Bergson and Becker RAND Soviet national income studies are catalogued but marked "Web Only" or
"Out Of Print" with **no PDF link on the page at all**. The machine-readable equivalents
already exist in Harrison's compilation and the World Bank archive.

---

## The two things that actually block the project

### 1. The Uzbek republic annual, which covers the anchor

*Narodnoe khoziaistvo Uzbekskoi SSR* is the republic-level source for the padded series, and
**no digitised copy that anyone can open has been found**:

- archive.org's Narkhoz collection is union-level only; a separate search for Uzbek SSR
  material returned 29 items, none of them a statistical annual;
- HathiTrust returned no Narkhoz volume at all, union or republic (absence of proof rather
  than proof of absence: the catalogue renders client-side and could not be enumerated);
- publ.lib.ru holds nine union volumes and no republic ones;
- istmat.org lists six Uzbek editions, of which **only 1988 and 1990 fall near the padding
  decade**, and the site is intermittently unreachable from here;
- the 1957 edition is catalogued at the Russian national digital library, which refuses
  non-Russian egress outright.

The consequence for the design: republic-level work currently rests on whatever the union
volumes print by republic, which is less than the republic annual would give. This is the
project's weakest link and it is blocked on a person, not on code.

### 2. The hydrological correlate for the anchor window

The design assumed an irrigation-withdrawal series would give an independent physical check on
reported cotton output, since the falsifiers did not control the river. The CAWater-Info Aral
database table that was actually fetched runs **1992 to 2025** and therefore misses the
1978-1983 window entirely. Two pages of the same database, the Aral morphometry table
described as 1911-2018 and the river-resources page, were never opened and are the remaining
candidates; the acquirer fetches them in both English and Russian so a person can look. The
Global Runoff Data Centre is the other candidate and needs a request.

Until one of those yields a pre-1992 series, the independent physical check on the anchor is
FAOSTAT against USDA and nothing else. Both are estimates of the same reported quantity by
outside bodies, which is weaker than a driver the falsifiers could not touch.

---

## Reachable, but deliberately without an acquirer

Fourteen sources are free and reachable and have no code, because fetching them would produce
nothing usable. The registry keeps them because a negative result that is not written down
gets re-discovered.

| Source | Why no acquirer |
|---|---|
| `cia_readingroom_home` | The home page is all cia.gov serves to a script. Nothing to download. |
| `dtic_ada121312_rand` | A RAND paper with almost the same title as the JEC compendium. In the registry solely to prevent the confusion. |
| `duke_treml_webfiles` | Course lecture notes. Treml's input-output reconstructions are not hosted there in data form. |
| `harvard_dataverse_soviet_io_search` | A negative result: no Soviet I-O dataset on Dataverse. |
| `no_machine_readable_tables` | A negative result: no curated Narkhoz transcription on Zenodo or GitHub. |
| `pwt_110` | Checked rather than assumed: the Penn World Table contains no USSR entity. |
| `wb_wdi_country_api` | Same: no USSR series, and no pre-1988 Russia GDP. |
| `nasa_eo_aral_world_of_change`, `usgs_eros_earthshots_aral` | Imagery with narrative, no numeric series. |
| `wikipedia_uzbek_cotton_scandal` | Secondary, for pointers only. Its 981,000-tonne figure for 1983 is unverified against any primary or academic source and must not be used. |
| `istmat_ru_not_istmat` | The wrong site. Denylisted by being written down. |
| `hathitrust_narkhoz` | Client-rendered search; needs a headless browser, which is a different kind of tool. |
| `rand_soviet_national_income` | The PDFs do not exist to fetch. |
| `rgae_opisi_online` | A finding aid, not documents; the crawl needs 300-second timeouts and human supervision. |

### Three sources nobody confirmed exist

`github_search_soviet_data`, `khanin_lukavaya_tsifra` and
`osu_thesis_cotton_scandal_uzbek_national_consciousness` are status `unverified`, which is not
the same as reachable-but-useless: nobody established that they exist in the form the registry
claims, so they are not among the fourteen above. The runner skips them with
"existence was never confirmed; nothing to fetch".

**`khanin_lukavaya_tsifra` deserves a specific warning.** The registry's URL for it is a
LiveJournal post that is **not** the article: it is commemorative commentary that quotes one
headline finding. The article itself (Selyunin and Khanin, *Novyi mir* 1987 no. 2) and
Khanin's 1991 book were not located in any verified form, and the bibliographic details in the
registry come from search-result snippets. This is the biggest unclosed item in the source
hunt, and any citation of Khanin's numbers needs a copy read first. The next lead recorded is
`imwerden.de`, which hosts complete scanned issues of Soviet journals; nobody has tried it.

---

## Operational notes

**Fill in the contact string first.** `config/forensics.toml` still holds
`REPLACE_ME <you@example.org>`, and the fetcher refuses to touch the network until it is a
real address. `--list` and `--dry-run` work without it and make no requests.

**Two hosts need special handling and the acquirers already do it.** `publ.lib.ru` truncates
long responses (three attempts were needed for one 10 MB zip), so its downloads run with
ranged resume and a run that fails there should simply be repeated. `istmat.org` answers
roughly one request in three from this network, which looks like an overloaded origin rather
than a block, so a failure there is worth retrying later.

**One licence question needs a decision before the project publishes derived tables.**
istmat.org is CC BY-SA 4.0, which imposes a share-alike obligation on anything derived from
it. publ.lib.ru states non-commercial use only. The Soviet annuals themselves have no rights
statement on archive.org and their copyright status should be treated as unsettled.

**Console encoding on Windows.** `python -m gosplan.acquire --list` prints source names that
contain Cyrillic. On a console using the default code page this raises
`UnicodeEncodeError` from inside the shared runner, not from this project. Run with
`PYTHONIOENCODING=utf-8` until the shared library reconfigures its output stream.

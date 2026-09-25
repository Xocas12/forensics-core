"""Precinct-level (UIK) results for Russian federal elections, from verified public mirrors.

The Central Election Commission's own portal is unreachable from outside Russia (DNS failure
for ``vybory.izbirkom.ru``; TCP timeout or reset for ``cikrf.ru``), so re-scraping is not an
option here. See ``data/ACCESS_NOTES.md``. What this module downloads instead is the
published re-scrape whose national totals reproduce the commission's own, checked in
``docs/data_dictionary.md``, plus one independent second scrape of the 2018 election that
exists only as a cross-check.

Nothing is transformed here. Column mapping, the 2011/2018 schema reconciliation and the
turnout definitions belong to ``elections.clean``.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from elections.acquire._common import fetch_file
from elections.acquire.registry import AcquireResult, register

#: Raw file root of the dkobak/elections repository. Confirmed HTTP 200 during scaffolding;
#: it is the prefix of the ``url`` recorded for every ``dkobak_*`` entry in SOURCES.yaml.
DKOBAK_RAW = "https://raw.githubusercontent.com/dkobak/elections/master/data"

#: The 2018 cross-check table. SOURCES.yaml records this URL under ``palladain_rus_pres_2018``
#: in its ``evidence`` field (the entry's own ``url`` is the repository landing page, which is
#: HTML and not the data), together with the digest below.
PALLADAIN_UIKS_CSV = "https://raw.githubusercontent.com/Palladain/RussianPresidentialElection2018/master/uiks-utf8.csv"

#: sha256 of ``uiks-utf8.csv`` as recorded in the SOURCES.yaml notes for that entry and
#: re-confirmed by the independent verification pass (which re-downloaded the file).
PALLADAIN_UIKS_SHA256 = "fd164c60a9f8647679a9749d16c4bc58a4c523885fb04e2f194d5f045e554fe6"


@register("dkobak_elections_2011")
def duma_2011(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """2011 State Duma results: 95,225 polling stations, 29 columns, one zipped CSV.

    The primary input for the 2011 half of the project. The registry digest is pinned as
    ``expected_sha256`` so that a silently changed upstream file fails the acquisition rather
    than the analysis: ``docs/data_dictionary.md`` states row and total counts measured
    against exactly these bytes.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or f"{DKOBAK_RAW}/2011.csv.zip",
        dest_rel="dkobak/2011.csv.zip",
        expected_sha256=source.sha256,
        force=force,
    )


@register("dkobak_elections_2018")
def presidential_2018(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """2018 presidential results: 97,699 polling stations, 24 columns, one zipped CSV.

    The primary input for the 2018 half of the project, pinned to its recorded digest for the
    same reason as the 2011 file. Note the two policy decisions the source README forces and
    that ``elections.clean`` must record: the four polling stations whose results were later
    cancelled, and Crimea and Sevastopol, which have no 2011 counterpart.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or f"{DKOBAK_RAW}/2018.csv.zip",
        dest_rel="dkobak/2018.csv.zip",
        expected_sha256=source.sha256,
        force=force,
    )


@register("dkobak_elections_data_readme")
def dkobak_data_readme(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The mirror's own ``data/README.md``: provenance and per-election reconciliation.

    Six kilobytes, and the document the Tier 0 anchors in ``docs/validation_anchors.md`` are
    quoted from. Deliberately fetched **without** a pinned digest: its ``download_plan`` in
    the registry asks for it to be re-fetched each run so that an upstream revision shows up
    as a changed digest in the registry rather than as a silent contradiction of the anchors.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or f"{DKOBAK_RAW}/README.md",
        dest_rel="dkobak/README.md",
        force=force,
    )


@register("dkobak_elections_repo_listing")
def dkobak_repo_listing(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The GitHub contents listing for ``dkobak/elections/data`` as acquisition-time evidence.

    A 60-requests-per-hour unauthenticated API call that records the name and byte size of
    every file in the mirror on the day the data was taken. It is the cheapest available
    check that the two zips downloaded here are the two zips the registry describes, and it
    names the other ten elections (2000-2024) should an extra validation panel be wanted.
    No digest is pinned: the listing legitimately changes whenever the repository does.
    """
    return fetch_file(
        source,
        data_dir,
        url=source.url or "https://api.github.com/repos/dkobak/elections/contents/data",
        dest_rel="dkobak/contents_data.json",
        force=force,
    )


@register("palladain_rus_pres_2018")
def palladain_2018(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """An independent 2018 scrape, kept only as a cross-check of the primary file.

    Snapshot taken about six days after the election: 97,705 rows against the primary file's
    97,699 and 109,024,062 registered voters against 109,008,428, differences the registry
    attributes to later cancellations and corrections. It is therefore **not** an alternative
    input; it is the one available way to see how much a same-source scrape moves with its
    timing.

    The URL fetched is the raw CSV recorded in the entry's ``evidence`` field, not the entry's
    ``url``, which points at the repository landing page. ``--dry-run`` prints the registry
    URL, so the two differ there by design.
    """
    return fetch_file(
        source,
        data_dir,
        url=PALLADAIN_UIKS_CSV,
        dest_rel="palladain/uiks-utf8.csv",
        expected_sha256=PALLADAIN_UIKS_SHA256,
        force=force,
    )

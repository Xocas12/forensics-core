"""Western and international reconstructions of Soviet output: the comparison series.

None of this is ground truth (``docs/known_traps.md``, trap 8): the CIA, Bergson-school and
Khanin reconstructions were built from the same official inputs with different adjustments
and disagree with each other. They are alternative reconstructions to be reconciled against
the official figures and against each other, and the *spread between them* is itself
evidence about how much the official series can be trusted.

Four families are acquired here.

* **Mark Harrison's Warwick data pages.** The most valuable holding in the whole registry for
  this project is ``harrison_plan_fraud``: the replication dataset for "Forging Success:
  Soviet Managers and Accounting Fraud, 1943 to 1962" (*Journal of Comparative Economics*
  39:1, 2011), a case-level index of prosecuted Soviet reporting fraud -- establishment,
  accused, branch, republic, what was falsified, and the sentence -- including Uzbek and
  Kazakh agricultural cases. It is the nearest thing this project has to a **second labelled
  source**, and structurally it is the Soviet analogue of the SEC enforcement labels used in
  the ``aaer`` project. Alongside it: the 1928-1985 GNP, employment and capital compilation
  behind Harrison (1998), and six annual input-output matrices for 1940-1945 with their
  Leontief inverses, which are the only machine-readable Soviet I-O tables located anywhere.
* **The Maddison Project Database 2023**, which carries a "Former USSR" (``SUN``) GDP per
  capita series. The Penn World Table, checked rather than assumed, contains no USSR entity
  at all and therefore has no acquirer here.
* **The World Bank's "Soviet Economic Decline" dataset** (Easterly and Fischer 1995), which
  already juxtaposes official NMP, Khanin's alternative NMP and CIA GNP in one machine-
  readable archive, 1928-1987.
* **The Hokkaido SRC "Soviet and Russian Economic Statistical Series"**, 145 CSV files
  transcribed from the Narkhoz annuals. This is the *reported* side, not a reconstruction:
  it is the only substantial machine-readable transcription of official Soviet series that
  scaffolding located, and the transcription pipeline in :mod:`gosplan.transcribe` should
  treat it as an independent second transcription to compare against, not as a substitute
  for reading the printed page.

Two file-format traps to expect downstream: Harrison's ``.xls`` files are old BIFF workbooks
that ``openpyxl`` cannot read (use ``xlrd`` or LibreOffice), and the World Bank archive holds
MicroTSP ``.DB`` series files and a Lotus ``.WK1`` sheet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gosplan.acquire._common import fetch_file, hrefs, many, read_text, single
from gosplan.acquire.registry import AcquireResult, register

#: Root of Mark Harrison's data pages at Warwick.
HARRISON_DATA = "https://warwick.ac.uk/fac/soc/economics/staff/mharrison/data"

#: The six workbooks behind Harrison (1996), *Accounting for War*, confirmed present by the
#: scaffolding session (three downloaded, three checked by HEAD).
USSR_WW2_WORKBOOKS: tuple[str, ...] = (
    "gdp",
    "io_basic",
    "civprod",
    "defprod",
    "final",
    "labour",
)

#: Index page of the Hokkaido SRC series collection, and the pattern its data links follow.
SESS_INDEX = "https://src-h.slav.hokudai.ac.jp/database/SESS.html"
SESS_CSV_PATTERN = r"USSR/S\d+\.csv$"
SESS_DESCRIPTION_PATTERN = r"SESS-d\.html$"


@register("harrison_plan_fraud")
def harrison_plan_fraud(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Harrison's Soviet plan-fraud case index (JCE 2011) -- the second labelled source.

    Three sheets, one per archival fond (R-9492, R-8131, and fond 6), with columns including
    Establishment, Accused, #Accused, Where and Branch, and sample rows such as an overstated
    ploughing area in Uzbekistan and a reported 515 tons against an actual 315.

    This is the one file in the project pinned to its recorded digest. It is static
    replication material for a published paper, and if the bytes change, that is something a
    person must look at before any label built on it is reused -- so a mismatch is reported
    as a failure rather than silently accepted.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(
        source,
        data_dir,
        source.url,
        "harrison/plan_fraud_dataset.xlsx",
        force=force,
        expected_sha256=source.sha256 or None,
    )


@register("harrison_data_index")
def harrison_index(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Harrison's dataset index page, kept because the label-to-directory map is inconsistent.

    The index labels one collection "Plan Fraud" while its directory is ``/data/fraud/``
    (``/data/planfraud/`` returns 404), so the page itself is the only reliable enumeration
    of what exists. Downloading it makes the enumeration reproducible if the page changes.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(source, data_dir, source.url, "harrison/index.html", force=force)


@register("harrison_sovietgrowth")
def harrison_sovietgrowth(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Appendix A basic data for Harrison, "Trends in Soviet Labour Productivity, 1928-1985".

    A Western compilation, not Soviet official data: the sheet's own source notes cite
    Moorsteen and Powell (1966), Becker, Moorsteen and Powell (1968), Harrison (1996),
    Rapawy (1987) and CIA (1990). Series include GNP in billion rubles alongside employment
    and capital. The appendixes PDF is taken with it because the variable definitions are
    there and not in the workbook.
    """
    items = [
        (f"{HARRISON_DATA}/sovietgrowth/dataset.xls", "harrison/sovietgrowth_dataset.xls"),
        (f"{HARRISON_DATA}/sovietgrowth/appendixes.pdf", "harrison/sovietgrowth_appendixes.pdf"),
    ]
    return many(source, data_dir, items, force=force)


@register("harrison_ussr_ww2")
def harrison_ussr_ww2(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The six workbooks behind Harrison (1996), *Accounting for War*, 1940-1945.

    ``io_basic.xls`` is the reason this entry matters beyond the war years: it holds six
    annual input-output matrices with their ``(I-A)`` and ``(I-A)^-1`` forms and a conversion
    to 1937 factor costs. No machine-readable Soviet input-output table for any later year
    was located anywhere -- Harvard Dataverse, Zenodo and GitHub all came back negative, and
    the 1966 and 1972 Treml reconstructions are print-only. So this is the only I-O material
    on which :mod:`gosplan.analysis.io_reconciliation` can be exercised before a table is
    transcribed by hand.
    """
    items = [
        (f"{HARRISON_DATA}/ussr_ww2/{stem}.xls", f"harrison/ussr_ww2_{stem}.xls")
        for stem in USSR_WW2_WORKBOOKS
    ]
    return many(source, data_dir, items, force=force)


@register("harrison_greatwar_munitions_pdf")
def harrison_greatwar_munitions(
    source: Any, data_dir: Path, *, force: bool = False
) -> AcquireResult:
    """Two Harrison appendices that exist only as PDF, not as spreadsheets.

    Russia and USSR national income 1913-1928 (Markevich and Harrison, *Journal of Economic
    History* 2011) and Soviet munitions output. Both landing pages link exactly one PDF and
    no workbook, so these are table-extraction targets (camelot or tabula, page-level
    provenance kept) rather than downloads that yield data directly.
    """
    items = [
        (f"{HARRISON_DATA}/greatwar/appendix.pdf", "harrison/greatwar_appendix.pdf"),
        (f"{HARRISON_DATA}/sovietmunitions/data.pdf", "harrison/sovietmunitions_data.pdf"),
    ]
    return many(source, data_dir, items, force=force)


@register("maddison_mpd2023")
def maddison(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Maddison Project Database 2023, ``mpd2023_web.xlsx``.

    Country code ``SUN`` ("Former USSR") in the "Full data" sheet: 158 GDP-per-capita
    observations covering 1860 and 1900-2022, with the Sources sheet citing Moorsteen and
    Powell (1966) and Kuboniwa (2019) for the Soviet stretch. Note that ``RUS`` is present
    separately from 1860, so the two must not be concatenated.

    The DataverseNL link redirects to a presigned object-store URL. The fetcher follows
    redirects; the registry's warning not to send ``HEAD`` applies to that presigned URL,
    which returns 403 to anything but ``GET``.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(
        source,
        data_dir,
        source.url,
        "maddison/mpd2023_web.xlsx",
        force=force,
        expected_sha256=source.sha256 or None,
    )


@register("wb_soviet_economic_decline")
def wb_soviet_decline(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Easterly and Fischer (1995) "The Soviet Economic Decline" archive.

    Annual series 1928-1987 from Gomulka and Schaffer (1991), plus republican data 1970-1990.
    The nested ``USSR.ZIP`` holds fourteen MicroTSP ``.DB`` files whose names are the point of
    the acquisition: ``YOFF`` (official NMP), ``YKHAN`` (Khanin's NMP), ``GNPWEST`` (CIA GNP)
    and the matching capital-stock triple ``KOFF`` / ``KWEST`` / ``KKHAN``. Three
    reconstructions of the same economy in one archive is exactly the input the
    hidden-inflation and reconciliation work needs.

    Only the dataset zip is fetched. The catalog page lists three further resources under the
    same DDH id (a data description PDF, a second dataset zip and a report PDF), but the
    registry recorded their filenames only in elided form, and guessing a URL is not
    permitted -- open the catalog page once and add them to the registry properly.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return single(
        source,
        data_dir,
        source.url,
        "worldbank/soviet_economic_decline_dataset.zip",
        force=force,
        expected_sha256=source.sha256 or None,
    )


@register("hokudai_sess")
def hokudai_sess(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Hokkaido SRC "Soviet and Russian Economic Statistical Series": index, then every CSV.

    The index is fetched first and the data links are read off it rather than constructed,
    because the section structure and the set of series codes are the publisher's to change.
    Each series file carries ``CODE NUMBER, FULL NAME, UNIT, SOURCE`` and annual columns from
    1940 to 1989, with ``Narkhoz.`` in the source column.

    Two traps recorded in the registry, both of which belong in any loader written for these
    files and neither of which is applied here: **missing values are coded 0.0**, so a naive
    read turns "not published" into "zero", and at least one unit label disagrees with the
    magnitudes it labels (a series marked "Mil. rubles" carrying billions).
    """
    index_rel = "hokudai_sess/SESS.html"
    idx = fetch_file(source.id, data_dir, source.url or SESS_INDEX, index_rel, force=force)
    if not idx.ok or idx.path is None or not idx.path.exists():
        return AcquireResult(source.id, False, f"index: {idx.detail}")

    html = read_text(idx.path)
    csv_urls = hrefs(html, base=SESS_INDEX, pattern=SESS_CSV_PATTERN)
    doc_urls = hrefs(html, base=SESS_INDEX, pattern=SESS_DESCRIPTION_PATTERN)
    if not csv_urls:
        return AcquireResult(
            source.id,
            False,
            f"index fetched ({idx.detail}) but no links matching {SESS_CSV_PATTERN} were found",
            (idx.path,),
        )

    items = [(u, f"hokudai_sess/{u.rsplit('/', 1)[-1]}") for u in doc_urls]
    items += [(u, f"hokudai_sess/series/{u.rsplit('/', 1)[-1]}") for u in csv_urls]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"index + {len(csv_urls)} series links; {result.detail}",
        (idx.path, *result.paths),
        result.skipped_cached,
    )

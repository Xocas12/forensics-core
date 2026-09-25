"""Method and benchmark papers that are free to fetch, plus their bibliographic metadata.

These are not data. They are acquired because the coefficients, thresholds and target numbers
this project must reproduce were read out of them, and ``docs/validation_anchors.md`` cites
them line by line; keeping checksummed local copies is what makes those citations checkable
later.

What is free here and what is not
---------------------------------
* **Beneish (1999)** is acquired as the June 1999 **working-paper** version from a third-party
  mirror. The typeset *Financial Analysts Journal* 55(5): 24-36 article is paywalled: doi.org
  resolves to tandfonline.com, which returned HTTP 403 with a bot-block page (registry
  ``beneish_1999_faj_publisher``). The working paper's Table 3 Panel A, unweighted probit row,
  is where the eight coefficients in :mod:`aaer.features.beneish` come from.
* **Bao et al. (2020)** full text is paywalled at Wiley. Only the Crossref record is free.
* **The 2022 erratum** is paywalled and Wiley returns 403 to scripted clients (registry
  ``jar_erratum_2022``). Its Crossref record is free and confirms it exists and what it
  corrects; its *substance* is available free only second-hand, through Walker (2022) in
  *Econ Journal Watch*, which quotes it verbatim with page numbers. That is why both Walker
  papers are acquired: they are currently the only free route to the corrected performance
  figures that ``docs/validation_anchors.md`` uses as the Tier 1 target. Walker is a critic
  writing in a critique journal; treat his framing as contested and his quoted numbers as
  checkable.

Not acquired, deliberately
--------------------------
* ``wikipedia_beneish_mscore``. Its own registry entry says "Not needed for acquisition;
  reference only". It corroborated the eight-variable formula during scaffolding and its bytes
  already drifted by one between two probes.
* ``jar_online_supplements_page``. A search of the served HTML for "Bao" or "Detecting
  Accounting Fraud" returned zero matches, so the supplement is not reachable from it; the
  registry directs the reader to the GitHub repository instead
  (:mod:`aaer.acquire.bao_replication`).

Crossref is called with the contact string in the ``User-Agent``, which is what puts a client
in Crossref's polite pool; the same mechanism as everywhere else in this package.
"""

from __future__ import annotations

from pathlib import Path

from aaer.acquire._common import fetch_file
from aaer.acquire.registry import AcquireResult, register

#: One file, two registry entries. ``econjwatch.org`` serves Walker (2022) at both
#: ``/File+download/1245/...`` and ``/file_download/1245/...``; the registry verified each
#: separately and both record sha256 6a1396dd...  Pointing both acquirers at one destination
#: means the second one is answered from cache instead of downloading the same bytes twice.
WALKER_2022_DEST = "literature/Walker2022_EJW_erroneous_erratum.pdf"


@register("beneish_1999_working_paper_pdf")
def beneish_working_paper(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Beneish (1999), "The Detection of Earnings Manipulation", June 1999 working paper.

    Table 3 Panel A, unweighted probit: constant -4.840, DSRI .920, GMI .528, AQI .404,
    SGI .892, DEPI .115, SGAI -.172, TATA 4.679, LVGI -.327. The -1.78 cut-off in the same
    text is stated at 20:1 or 30:1 relative error costs, not as a constant of nature.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "literature/Beneish1999_working_paper.pdf",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("bao2020_jar_metadata")
def bao_crossref(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Crossref record for Bao et al. (2020), DOI 10.1111/1475-679X.12292.

    Metadata and abstract only; the abstract states no numeric AUC or NDCG values and the full
    text is paywalled at Wiley.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "literature/crossref_bao2020.json",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("crossref_jar_erratum")
def erratum_crossref(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Crossref record for the 2022 erratum, DOI 10.1111/1475-679X.12454.

    Its ``update-to`` field points at 10.1111/1475-679x.12292 with type ``erratum``, updated
    2022-08-04. That field is worth a standing check across the whole bibliography: it is how a
    correction to any cited DOI can be detected automatically.
    """
    return fetch_file(
        source, data_dir, source.url, "literature/crossref_jar_erratum.json", force=force
    )


@register("ejw_walker_2021_critique")
def walker_2021(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Walker (2021), *Econ Journal Watch* 18(1): 61-70, the critique that led to the erratum."""
    return fetch_file(
        source,
        data_dir,
        source.url,
        "literature/Walker2021_EJW_critique.pdf",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("ejw_walker_2022")
def walker_2022(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Walker (2022), *Econ Journal Watch* 19(2): 190-203.

    The only free route this project has to the erratum's own numbers, which it quotes with
    page references. Shares a destination with ``ejw_walker_2022_erroneous_erratum``; see
    :data:`WALKER_2022_DEST`.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        WALKER_2022_DEST,
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("ejw_walker_2022_erroneous_erratum")
def walker_2022_alternate_url(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The same PDF under the site's lower-case ``/file_download/`` path.

    Both registry entries record sha256 6a1396dd..., so whichever runs second is answered from
    cache. Keeping both registered means neither entry is reported as an unimplemented gap.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        WALKER_2022_DEST,
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("ejw_bao_response_page")
def bao_response_landing(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Landing page of the authors' March 2021 reply to Walker.

    They state there that they "find no evidence that these two issues alter our paper's
    inferences", 17 months before the erratum conceded the coding error. The reply PDF itself
    is linked from this page and was not fetched during scaffolding, so its URL is not asserted
    here; take it from the saved HTML.
    """
    return fetch_file(source, data_dir, source.url, "literature/ejw_bao_response.html", force=force)

"""The Bao, Ke, Li, Yu & Zhang (2020) replication repository (GitHub: JarFraud/FraudDetection).

Bao, Y., B. Ke, B. Li, Y. J. Yu and J. Zhang (2020). "Detecting Accounting Fraud in Publicly
Traded U.S. Firms Using a Machine Learning Approach." *Journal of Accounting Research*
58(1): 199-235, DOI 10.1111/1475-679X.12292.

Why this repository matters more than the paper
-----------------------------------------------
``data_FraudDetection_JAR2020.csv`` ships 28 raw Compustat annual items and 14 derived ratios
for 146,045 firm-years, fiscal years 1990-2014, with the AAER fraud label attached. It is the
**free substitute for Compustat** for this specific task, and it is the only source in the
registry that covers the 1990s and 2000s at the firm-year level with structured financials.
Registry entry ``bao_analysis_csv`` records the counts: ``misstate=1`` on 964 rows spanning 412
distinct ``p_aaer`` values, ``misstate=0`` on 145,081; positives peak in 2000 (86) and 2001
(81); 2009 onward has 112 positives across 33,064 firm-years.

Two limits, both recorded in the registry and both load-bearing:

* Three of the twelve inputs :mod:`aaer.features.beneish` needs are **absent**, so this file
  supports four of the eight Beneish components as shipped, five with a balance-sheet TATA:
  ``xsga`` is missing (SGAI impossible); ``ppent`` is missing and only gross ``ppegt`` is
  shipped, which :mod:`aaer.clean.xbrl_map` refuses to substitute (AQI and DEPI impossible);
  and ``oancf`` is missing, so TATA needs the balance-sheet definition, which is the one
  Beneish (1999) actually uses and therefore a choice rather than a gap.
* The labels file ``AAER_firm_year.csv`` is keyed on **CIK** while the analysis file is keyed on
  **gvkey**. ``identifiers.csv`` is the bridge, which is why :func:`jarfraud_repo_files` fetches
  it even though the registry entry it belongs to is nominally "the repository".

Version, and why ``master`` is used rather than a pinned commit
---------------------------------------------------------------
A 2022 erratum (*JAR* 60(4): 1635-1646) states that an error in this repository's code "led to
an overstatement of model performance metrics". The head commit is 2022-08-10 "update code and
data", six days after the erratum's update date, so the current ``master`` is the **corrected**
dataset (registry ``bao_commits``). The download plan in the registry asks for a commit-SHA
pin; what is done here is stronger for the purpose: every file whose digest the registry
records is fetched with ``expected_sha256``, so if ``master`` moves the download fails loudly
with a digest mismatch instead of silently returning different numbers. ``bao_commits`` is
acquired alongside so the head SHA at acquisition time is on disk.

No LICENSE file exists in the repository (registry ``bao_repo_api``). Treat redistribution as
all-rights-reserved and cite Bao et al. (2020) as the README asks. Nothing acquired here may be
committed to a public repository.
"""

from __future__ import annotations

from pathlib import Path

from aaer.acquire._common import fetch_file, fetch_many
from aaer.acquire.registry import AcquireResult, register

#: Raw-content base for the repository's default branch (``master``).
JARFRAUD_RAW = "https://raw.githubusercontent.com/JarFraud/FraudDetection/master"

#: Digests recorded in the registry for files that have no registry entry of their own
#: (they are documented inside the ``jarfraud_github_repo`` entry's notes, which the
#: independent verification pass confirmed against the GitHub contents API).
IDENTIFIERS_SHA256 = "4af80a02f4ae520943ab2774cb9a707d7b797f29a662e3bba78d8cf2dc478291"
DATASHEET_SHA256 = "9b4e4c807c39f54b852a71156f7988fff0c68f87116c2e53ae531a5dd76356d4"


@register("bao_analysis_csv")
def analysis_csv(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """``data_FraudDetection_JAR2020.csv`` -- 47,782,071 bytes, 146,045 rows, 46 columns.

    The digest pins the post-erratum version. A mismatch means the repository was updated
    again and that any comparison with the erratum's numbers is void until it is investigated.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "bao2020/data_FraudDetection_JAR2020.csv",
        expected_sha256=source.sha256 or None,
        force=force,
        resume=True,
    )


@register("bao_labels_csv")
def labels_csv(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """``AAER_firm_year.csv`` -- the raw fraud firm-year labels, keyed on CIK.

    1,746 rows, 716 distinct CIKs, 716 distinct ``P_AAER``, ``YEARA`` 1971-2015.
    ``UNDERSTATEMENT`` is 0 on 1,694 rows (overstatement, the class the paper models), 1 on 51
    and 3 on one row. Joining to the analysis file needs ``identifiers.csv``.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "bao2020/AAER_firm_year.csv",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("bao_readme")
def readme(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The repository README, which is also the JAR data description sheet.

    It documents that the AAER labels come from the UC-Berkeley CFRM database covering
    announcements from 17 May 1982 to 30 September 2016, hand-extended to 31 December 2018, and
    that the accounting data is Compustat fundamental annual FY1991-2014 downloaded in April
    2017. It does **not** mention the 2022 erratum; do not read it as current.
    """
    return fetch_file(
        source,
        data_dir,
        source.url,
        "bao2020/README.md",
        expected_sha256=source.sha256 or None,
        force=force,
    )


@register("bao_repo_api")
def repo_contents(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """GitHub contents listing: the ten root files with their sizes and download URLs.

    Kept as the acquisition-time inventory of the repository. Unauthenticated GitHub API calls
    are limited to 60 per hour per address; this is one call.
    """
    return fetch_file(source, data_dir, source.url, "bao2020/repo_contents.json", force=force)


@register("bao_commits")
def repo_commits(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Commit history, so the head SHA at acquisition time is recorded on disk.

    24 commits, 2019-10-07 to 2022-08-10. The head commit post-dates the erratum by six days.
    """
    return fetch_file(source, data_dir, source.url, "bao2020/repo_commits.json", force=force)


@register("jarfraud_github_repo")
def jarfraud_repo_files(source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The repository files that have no registry entry of their own.

    ``identifiers.csv`` (1,608,699 bytes) is the CIK-to-gvkey bridge without which the labels
    file and the analysis file cannot be joined. ``BKLYZ Datasheet.pdf`` and ``SAS coding.pdf``
    are the JAR datasheet and the variable-construction code; the registry records that the
    datasheet's text contains no AUC, NDCG or erratum strings, so it documents variables, not
    results.

    The Matlab files (``run_RUSBoost.m``, ``tune_RUSBoost.m``, ``data_reader.m``,
    ``evaluate.m``) are deliberately left: this project reimplements the benchmark against
    :mod:`forensics_core.eval.harness` rather than running the authors' Matlab.

    Because one registry entry carries one digest, the entry's ``sha256`` / ``bytes`` /
    ``local_path`` fields end up describing the last file written; ``data/fetch_log.jsonl``
    holds one line per file.
    """
    items = [
        (f"{JARFRAUD_RAW}/identifiers.csv", "bao2020/identifiers.csv"),
        (f"{JARFRAUD_RAW}/BKLYZ%20Datasheet.pdf", "bao2020/BKLYZ_Datasheet.pdf"),
        (f"{JARFRAUD_RAW}/SAS%20coding.pdf", "bao2020/SAS_coding.pdf"),
    ]
    expected = {
        "bao2020/identifiers.csv": IDENTIFIERS_SHA256,
        "bao2020/BKLYZ_Datasheet.pdf": DATASHEET_SHA256,
    }
    return fetch_many(source, data_dir, items, expected=expected, force=force, unit="repo files")

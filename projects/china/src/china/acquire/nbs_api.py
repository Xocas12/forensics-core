"""The bureau's catalogue API: a discovery layer that works, above a values layer that does not.

**Read this before running it.** ``data.stats.gov.cn`` is the source of the project's central
access problem, and its story has two halves that must not be run together:

* The **legacy** ``easyquery.htm`` API is blocked. Every request returned HTTP 403 from the
  site's web application firewall with ``reason:UrlACL``, for every combination of user
  agent, cookie jar and header set, from two different egress addresses and via two
  different tools. Sibling legacy paths return 404 with a Spring Boot body, so the legacy
  application is retired rather than merely firewalled. Those registry entries are marked
  ``blocked`` and have **no acquirer**, deliberately.
* The **new** catalogue endpoints under ``/dg/website/publicrelease/web/external`` were
  reported returning HTTP 200 by a later scaffolding pass, with the drill-down chain
  executed to two named leaves. That pass was **never independently verified**: those
  registry entries carry ``verification.verdict: not_verified``. The acquirers below exist
  because the registry says the endpoints are free and reachable; if they turn out not to
  be, the run records a failure and the entries get downgraded, which is the correct
  outcome and is why this is worth attempting rather than assuming.

Either way the portal cannot deliver a provincial series today: the **values** endpoint is
unknown. Thirteen candidate paths were probed and all thirteen returned the application's own
404 page while a control path returned 200. So what these acquirers collect is a catalogue:
indicator identifiers, their date ranges and their scope notes. That is the map a future
operator with a working values endpoint would need, and it is worth having on disk now.

The requests here send the ``Referer`` the verified probes sent. They do **not** send the
browser ``User-Agent`` those probes used; see :mod:`china.acquire._common`.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_file
from china.acquire.registry import AcquireResult, register
from china.clean.nbs_api import parse_index_tree

__all__ = [
    "API_BASE",
    "API_REFERER",
    "PROVINCIAL_ANNUAL_CODE",
    "crawl_tree",
    "indicators_url",
    "tree_url",
]

#: Base of the new portal's public-release API.
API_BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"

#: Header the verified probes sent with every call.
API_REFERER = {"Referer": "https://data.stats.gov.cn/dg/website/page.html"}

#: Category code for the provincial annual database: the one this project needs.
PROVINCIAL_ANNUAL_CODE = 6

#: Category code for the national annual database, the denominator of the gap.
NATIONAL_ANNUAL_CODE = 3

#: Ceiling on catalogue requests per category, so a cyclic or unexpectedly wide tree cannot
#: turn into an unbounded crawl.
MAX_TREE_REQUESTS = 400


def tree_url(pid: str, code: int) -> str:
    """URL of one catalogue level.

    Parameters
    ----------
    pid : str
        Parent node id. The empty string requests the root of the category.
    code : int
        Category code; see :data:`china.clean.nbs_api.CATEGORY_CODES`.

    Returns
    -------
    str
        Absolute URL.
    """
    return f"{API_BASE}/new/queryIndexTreeAsync?pid={pid}&code={code}"


def indicators_url(cid: str) -> str:
    """URL of the indicator list for one leaf of the catalogue.

    Parameters
    ----------
    cid : str
        Leaf id.

    Returns
    -------
    str
        Absolute URL.
    """
    return f"{API_BASE}/new/queryIndicatorsByCid?cid={cid}&dt=&name="


def crawl_tree(
    source: Source,
    data_dir: Path,
    code: int,
    *,
    force: bool = False,
    max_requests: int = MAX_TREE_REQUESTS,
) -> tuple[int, int, list[str]]:
    """Walk one category of the catalogue breadth-first, caching every response.

    Each level is fetched, written to ``data/raw/nbs_api/tree/code<code>/<pid>.json`` and
    then re-read from that file, so a resumed crawl makes no request for a level it already
    holds. Leaves additionally get their indicator list.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        Registry entry to attribute the fetches to.
    data_dir : Path
        The project's ``data/`` directory.
    code : int
        Category code to walk.
    force : bool, default False
        Re-fetch levels already on disk.
    max_requests : int, default :data:`MAX_TREE_REQUESTS`
        Hard ceiling on levels fetched, counting cached ones.

    Returns
    -------
    n_levels : int
        Catalogue levels available on disk after the crawl.
    n_leaves : int
        Leaves whose indicator list is available on disk.
    problems : list of str
        One line per level or leaf that could not be fetched or parsed. The first failure
        does not stop the walk; an unreachable branch costs that branch.
    """
    raw = data_dir / "raw"
    queue: list[str] = [""]
    seen: set[str] = set()
    n_levels = 0
    n_leaves = 0
    problems: list[str] = []

    while queue and (n_levels + n_leaves) < max_requests:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        rel = f"nbs_api/tree/code{code}/{pid or 'root'}.json"
        path = raw / rel
        if force or not path.exists():
            result = fetch_file(
                source,
                data_dir,
                url=tree_url(pid, code),
                dest_rel=rel,
                headers=API_REFERER,
                force=force,
            )
            if not result.ok:
                problems.append(f"code {code} pid {pid or 'root'!r}: {result.detail}")
                continue
        try:
            nodes = parse_index_tree(path.read_bytes())
        except (OSError, ValueError) as exc:
            problems.append(f"code {code} pid {pid or 'root'!r}: unparseable ({exc})")
            continue
        n_levels += 1

        for node_id, is_leaf in zip(nodes["node_id"], nodes["is_leaf"], strict=True):
            node_id = str(node_id)
            if not node_id:
                continue
            if bool(is_leaf):
                leaf_rel = f"nbs_api/indicators/{node_id}.json"
                if force or not (raw / leaf_rel).exists():
                    leaf_result = fetch_file(
                        source,
                        data_dir,
                        url=indicators_url(node_id),
                        dest_rel=leaf_rel,
                        headers=API_REFERER,
                        force=force,
                    )
                    if not leaf_result.ok:
                        problems.append(f"leaf {node_id}: {leaf_result.detail}")
                        continue
                n_leaves += 1
            elif node_id not in seen:
                queue.append(node_id)

    if queue:
        problems.append(
            f"stopped at the {max_requests}-request ceiling with {len(queue)} nodes unvisited"
        )
    return n_levels, n_leaves, problems


@register("nbs_dg_api_tree")
def catalogue(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The provincial-annual and national-annual catalogues, walked to their leaves.

    What lands on disk is the identifier map: which series exist, what their date ranges are,
    and what scope notes the bureau attaches to each indicator. The registry records the two
    leaves this project needs most, gross regional product from 1992 and its index, plus
    freight volume from 1979 and energy-product consumption.

    A single 403 here means the whole portal story is the blocked one and nothing else. The
    result line says which category failed, and every attempt is in ``data/fetch_log.jsonl``.
    """
    details: list[str] = []
    problems: list[str] = []
    for code in (PROVINCIAL_ANNUAL_CODE, NATIONAL_ANNUAL_CODE):
        levels, leaves, issues = crawl_tree(source, data_dir, code, force=force)
        details.append(f"code {code}: {levels} levels, {leaves} leaves")
        problems.extend(issues)
    detail = "; ".join(details)
    if problems:
        detail += f"; {len(problems)} problems: {problems[0]}"
    return AcquireResult(source.id, not problems, detail)


@register("nbs_dg_api_query_search")
def keyword_search(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The keyword-search endpoint: the cheapest liveness check on the portal.

    One request. It returns the latest observation for each matching indicator, which makes
    it useless for building a series and ideal for answering the only question that matters
    here: does this portal serve values to an anonymous client from this network at all. Keep
    the response; the ``cid`` and region codes it carries are what would seed a values call
    if the values endpoint is ever found.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_file(
        source,
        data_dir,
        url=source.url,
        dest_rel="nbs_api/query_search_grp.json",
        headers=API_REFERER,
        expected_sha256=None,
        force=force,
    )


@register("nbs_provincial_finance_branch")
def finance_branch(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Archive the negative result: the provincial finance branch has no loans leaf.

    Six hundred and twenty-one bytes of evidence that the entire finance branch of the
    provincial annual database contains one leaf, insurance premiums, and no deposits or
    loans. Worth keeping on disk because "we looked and it is not there" is a claim this
    project makes in ``docs/data_dictionary.md`` and in ``data/ACCESS_NOTES.md``, and a claim
    of absence should be reproducible.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")
    return fetch_file(
        source,
        data_dir,
        url=source.url,
        dest_rel="nbs_api/provincial_finance_branch.json",
        headers=API_REFERER,
        force=force,
    )

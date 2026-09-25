"""The Wayback Machine as cold storage for yearbook vintages.

The project's whole method depends on old yearbook editions staying available, and the bureau
has already retired one thing this project needed: the legacy ``easyquery.htm`` API is gone,
not merely firewalled. If the editions go the same way, the vintages go with them, and there
is no reconstructing a pre-revision series afterwards.

The archive holds two useful things, both confirmed during scaffolding:

* per-table captures of edition pages under the **old** site path ``stats.gov.cn/tjsj/ndsj/``
  (the 2015 edition's table images were found archived in July 2017, an independent frozen
  copy of a vintage that does not live on the bureau's servers);
* complete-volume archives for editions the live site no longer hosts at all: ``1997.rar``
  through ``2001.rar``, one of which was confirmed by a HEAD request returning 200 and
  2,643,245 bytes.

What this acquirer does is fetch the **index** of captures, not the captures. The index is
small, it is the thing that tells you what is recoverable and how big the job is, and it
carries a digest per capture so integrity checking is free. Pulling the captures themselves is
:func:`capture_items`, which is deliberately not wired to a registry id: it is a decision
about disk and about politeness, and it should be taken on purpose.

Rate limits. The registry's download plan asks for one request every two to three seconds
against ``web.archive.org`` and warns of intermittent 429 and 503 responses. The shared
configuration has no entry for that host, so it falls back to the default of two requests a
second. Whoever runs this at scale should add a ``"web.archive.org"`` line to
``config/forensics.toml`` first; the crawl here is deliberately kept to about twenty requests
so that the default limit is not abusive in the meantime. This is noted in
``data/ACCESS_NOTES.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_files
from china.acquire.registry import AcquireResult, register
from china.acquire.yearbook import EDITION_YEARS

__all__ = [
    "CDX_COLUMNS",
    "capture_items",
    "capture_url",
    "cdx_url",
    "parse_cdx_json",
]

#: Columns the archive's JSON output carries, in its own order.
CDX_COLUMNS: tuple[str, ...] = (
    "urlkey",
    "timestamp",
    "original",
    "mimetype",
    "statuscode",
    "digest",
    "length",
)

_CDX_BASE = "https://web.archive.org/cdx/search/cdx"

#: Editions to enumerate. The archive holds the pre-2023 site structure, so the path prefix
#: here is ``tjsj/ndsj`` and not the ``sj/ndsj`` of the live server.
ARCHIVED_PATH_PREFIX = "stats.gov.cn/tjsj/ndsj"


def cdx_url(path_glob: str, *, limit: int = 2000) -> str:
    """URL of a capture-index query, on the query string the registry's plan states.

    Parameters
    ----------
    path_glob : str
        Path pattern, e.g. ``"stats.gov.cn/tjsj/ndsj/2015/html/*"``.
    limit : int, default 2000
        Maximum rows returned.

    Returns
    -------
    str
        Absolute URL.
    """
    return (
        f"{_CDX_BASE}?url={path_glob}&output=json"
        f"&collapse=urlkey&filter=statuscode:200&limit={limit}"
    )


def capture_url(timestamp: str, original: str) -> str:
    """URL that returns a capture's **original** bytes.

    The ``id_`` suffix is what suppresses the archive's injected banner and rewriting. Without
    it, an archived JPEG or RAR comes back altered and its digest will not match.

    Parameters
    ----------
    timestamp : str
        Capture timestamp as the index reports it, e.g. ``"20160420183800"``.
    original : str
        The originally archived URL.

    Returns
    -------
    str
        Absolute URL.

    Examples
    --------
    >>> capture_url("20160420183800", "http://www.stats.gov.cn/tjsj/ndsj/1997.rar")
    'https://web.archive.org/web/20160420183800id_/http://www.stats.gov.cn/tjsj/ndsj/1997.rar'
    """
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def parse_cdx_json(payload: bytes | str) -> pd.DataFrame:
    """Parse a capture-index response into a frame.

    The archive returns a list of lists whose **first** row is the column header. That header
    is used rather than assumed, so a change of column order upstream cannot silently shift
    every field by one.

    Parameters
    ----------
    payload : bytes or str
        Response body.

    Returns
    -------
    pandas.DataFrame
        One row per capture, with ``length`` numeric so the size of a download can be totalled
        before any of it is fetched. An index with only a header, or an empty body, gives an
        empty frame with the expected columns: "nothing archived" is a real answer.

    Raises
    ------
    ValueError
        If the body is not JSON, or is JSON but not a list of rows.
    """
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    stripped = text.strip()
    if not stripped:
        return pd.DataFrame(columns=list(CDX_COLUMNS))
    try:
        rows = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"capture index is not JSON: {exc}") from exc
    if not isinstance(rows, list) or (rows and not isinstance(rows[0], list)):
        raise ValueError("capture index is JSON but not the expected list-of-rows shape")
    if len(rows) < 2:
        return pd.DataFrame(columns=list(CDX_COLUMNS))
    header = [str(column) for column in rows[0]]
    frame = pd.DataFrame(rows[1:], columns=header)
    if "length" in frame.columns:
        frame["length"] = pd.to_numeric(frame["length"], errors="coerce").astype("Int64")
    return frame


def capture_items(frame: pd.DataFrame, dest_prefix: str = "wayback") -> list[tuple[str, str]]:
    """Turn a parsed capture index into work items for a download.

    Not called by the acquirer. Downloading captures is an explicit decision, because the
    complete-volume archives are megabytes each and the archive asks to be treated gently.

    Parameters
    ----------
    frame : pandas.DataFrame
        Output of :func:`parse_cdx_json`.
    dest_prefix : str, default "wayback"
        Directory under ``data/raw`` to write into.

    Returns
    -------
    list of (str, str)
        ``(url, dest_rel)`` pairs. The destination keeps the capture timestamp in the path,
        because two captures of one URL are two different vintages and must not overwrite
        each other.

    Raises
    ------
    KeyError
        If ``frame`` lacks ``timestamp`` or ``original``.
    """
    for column in ("timestamp", "original"):
        if column not in frame.columns:
            raise KeyError(f"capture index has no {column!r} column")
    items: list[tuple[str, str]] = []
    for timestamp, original in zip(frame["timestamp"], frame["original"], strict=True):
        leaf = str(original).rsplit("/", 1)[-1] or "index.html"
        items.append(
            (capture_url(str(timestamp), str(original)), f"{dest_prefix}/{timestamp}/{leaf}")
        )
    return items


@register("wayback_nbs_yearbooks")
def capture_indexes(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """The capture indexes: what the archive holds of the yearbook, and how big it is.

    One request for the whole ``tjsj/ndsj`` prefix, which is where the complete-volume
    archives for 1997 to 2001 show up, plus one per edition year for that edition's table
    files. About twenty small JSON responses.

    Nothing is downloaded from the archive beyond these indexes. Use :func:`parse_cdx_json`
    and :func:`capture_items` to decide what, if anything, to pull, and read the rate-limit
    note in this module's docstring first.
    """
    work: list[tuple[str, ...]] = [
        (source.url or cdx_url(f"{ARCHIVED_PATH_PREFIX}/*", limit=40), "wayback/cdx_root.json")
    ]
    work.extend(
        (cdx_url(f"{ARCHIVED_PATH_PREFIX}/{year}/html/*"), f"wayback/cdx_{year}.json")
        for year in EDITION_YEARS
    )
    return fetch_files(source, data_dir, work, force=force, label="capture indexes")

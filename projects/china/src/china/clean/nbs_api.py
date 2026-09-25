"""Loaders for the National Bureau of Statistics catalogue API responses.

This is metadata, not data. The catalogue endpoints under
``data.stats.gov.cn/dg/website/publicrelease/web/external`` return the indicator tree and,
per leaf, the indicators it holds. The endpoint that returns the actual **values** could not
be found: thirteen candidate paths were probed and every one returned the application's own
404 page, while a control path returned 200. So this module can turn a catalogue response
into a frame, and there is nothing yet for it to turn a series into.

Read ``data/ACCESS_NOTES.md`` before relying on any of it. The legacy ``easyquery.htm`` API
is blocked outright from this network by the site's web application firewall, reproduced by
two agents from two egress addresses; the catalogue endpoints parsed here were reported
working by one scaffolding pass that no second pass re-checked.

Response shape, quoted from the registry evidence::

    {"data": [...], "success": true, "state": 20000, "message": "..."}

with each tree node carrying ``_id``, ``name``, ``isLeaf``, ``treeinfo_pid``,
``treeinfo_level``, ``treeinfo_globalid``, ``sdate``, ``edate`` and ``type``.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

__all__ = [
    "CATEGORY_CODES",
    "INDICATOR_COLUMNS",
    "TREE_COLUMNS",
    "parse_envelope",
    "parse_index_tree",
    "parse_indicators",
]

#: Category codes accepted by ``queryIndexTreeAsync``. Verified during scaffolding.
CATEGORY_CODES: dict[int, str] = {
    1: "monthly",
    2: "quarterly",
    3: "national annual",
    5: "provincial quarterly",
    6: "provincial annual",
    7: "census and other",
}

#: Columns of the frame :func:`parse_index_tree` returns.
TREE_COLUMNS: tuple[str, ...] = (
    "node_id",
    "name",
    "is_leaf",
    "parent_id",
    "level",
    "start_year",
    "end_year",
    "node_type",
)

#: Columns of the frame :func:`parse_indicators` returns.
INDICATOR_COLUMNS: tuple[str, ...] = (
    "indicator_id",
    "name",
    "scope_note",
    "unit",
    "decimals",
)


def parse_envelope(payload: bytes | str) -> list[dict[str, Any]]:
    """Unwrap the API's ``{"data": [...], "success": ...}`` envelope.

    Parameters
    ----------
    payload : bytes or str
        Response body. The endpoints send ``text/html`` for some responses even though the
        body is JSON, so the content type is deliberately not consulted.

    Returns
    -------
    list of dict
        The ``data`` list.

    Raises
    ------
    ValueError
        If the body is not JSON, if it is not an envelope, or if the envelope reports
        failure. A failure envelope is an answer from the server and must not be mistaken
        for an empty catalogue.
    """
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not JSON: {exc}") from exc
    if not isinstance(obj, dict) or "data" not in obj:
        raise ValueError(f"response is not an API envelope; top-level keys {list(obj)[:6]}")
    if obj.get("success") is False:
        raise ValueError(
            f"API reported failure: state={obj.get('state')!r} message={obj.get('message')!r}"
        )
    data = obj["data"]
    if isinstance(data, dict):  # the /query endpoint nests one more level
        data = data.get("data", [])
    if not isinstance(data, list):
        raise ValueError(f"envelope 'data' is {type(data).__name__}, expected a list")
    return [row for row in data if isinstance(row, dict)]


def _year(value: Any) -> Any:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return pd.NA


def parse_index_tree(payload: bytes | str) -> pd.DataFrame:
    """Parse one ``queryIndexTreeAsync`` response into a frame of catalogue nodes.

    Parameters
    ----------
    payload : bytes or str
        Response body.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`TREE_COLUMNS`. ``node_id`` is the value to pass back as ``pid`` to
        walk one level deeper, and, for a leaf, the ``cid`` that identifies a series family.
        The response uses ``_id`` for both roles; a ``cid`` key is preferred when present,
        because the registry evidence quotes leaves by ``cid``.

    Raises
    ------
    ValueError
        Via :func:`parse_envelope`, for a non-JSON body or a failure envelope.
    """
    rows = parse_envelope(payload)
    frame = pd.DataFrame(
        [
            {
                "node_id": str(row.get("cid") or row.get("_id") or ""),
                "name": str(row.get("name", "")),
                "is_leaf": bool(row.get("isLeaf", False)),
                "parent_id": str(row.get("treeinfo_pid") or ""),
                "level": row.get("treeinfo_level"),
                "start_year": _year(row.get("sdate")),
                "end_year": _year(row.get("edate")),
                "node_type": str(row.get("type") or ""),
            }
            for row in rows
        ],
        columns=list(TREE_COLUMNS),
    )
    frame["is_leaf"] = frame["is_leaf"].astype("boolean")
    frame["level"] = pd.to_numeric(frame["level"], errors="coerce").astype("Int64")
    frame["start_year"] = frame["start_year"].astype("Int64")
    frame["end_year"] = frame["end_year"].astype("Int64")
    return frame


def parse_indicators(payload: bytes | str) -> pd.DataFrame:
    """Parse one ``queryIndicatorsByCid`` response into a frame of indicators.

    The ``i_mark`` field is carried through as ``scope_note`` and is the one field worth
    reading closely: it is where the bureau documents changes of statistical scope, which is
    exactly where an accounting-method break would be announced.

    Parameters
    ----------
    payload : bytes or str
        Response body.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`INDICATOR_COLUMNS`. Fields absent from a response become empty
        strings or ``<NA>`` rather than being dropped, so that a shape change upstream shows
        up as blank columns and not as a silently shorter frame.

    Raises
    ------
    ValueError
        Via :func:`parse_envelope`.
    """
    rows = parse_envelope(payload)
    frame = pd.DataFrame(
        [
            {
                "indicator_id": str(row.get("_id") or row.get("indic_id") or ""),
                "name": str(row.get("i_showname") or row.get("i_name") or ""),
                "scope_note": str(row.get("i_mark") or ""),
                "unit": str(row.get("du") or ""),
                "decimals": row.get("dp"),
            }
            for row in rows
        ],
        columns=list(INDICATOR_COLUMNS),
    )
    frame["decimals"] = pd.to_numeric(frame["decimals"], errors="coerce").astype("Int64")
    return frame

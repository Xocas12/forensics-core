"""Loader for the World Bank indicator responses: the national denominator, with a vintage warning.

This is the only national gross domestic product series in the project that arrives as data
rather than as a photograph of a table, so it is tempting to make it the denominator of the
provincial-sum gap. Resist that. The World Bank republishes the bureau's **current** vintage,
already revised through the fourth economic census, and the provincial numerator comes from a
yearbook edition that was frozen years earlier. Subtracting one from the other measures the
revision, not the gap, and it will look like a large and interesting finding.

The correct denominator for a gap is the national total printed in the **same edition** as
the provincial rows, which is another JPEG scan. This series is the cross-check on that: if
the extracted national total and the World Bank's current figure for the same year differ by
much more than the known revisions, the extraction is wrong.

Response shape, quoted from the registry evidence: a two-element array whose first element is
the paging and metadata object, including ``lastupdated``, and whose second is the list of
observations.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from china.clean.schema import NATIONAL, PANEL_COLUMNS, SERIES

__all__ = [
    "INDICATOR_TO_SERIES",
    "OBSERVATION_COLUMNS",
    "YUAN_PER_HUNDRED_MILLION",
    "parse_indicator_response",
    "to_panel",
    "vintage_from_last_updated",
]

#: The yearbook prints money in 100 million yuan; the World Bank prints it in yuan.
YUAN_PER_HUNDRED_MILLION = 1e8

#: Which World Bank indicators map onto a panel series, and how. Only the current-price
#: series has a counterpart in :data:`china.clean.schema.SERIES`; the constant-price and
#: growth indicators are acquired as context and have no panel home yet, so converting them
#: would mean inventing a series name.
INDICATOR_TO_SERIES: dict[str, str] = {"NY.GDP.MKTP.CN": "gdp_national_nominal"}

#: Columns of the frame :func:`parse_indicator_response` returns.
OBSERVATION_COLUMNS: tuple[str, ...] = (
    "indicator",
    "country",
    "year",
    "value",
    "last_updated",
)


def _extract(payload: bytes | str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"World Bank response is not JSON: {exc}") from exc
    if not isinstance(obj, list) or len(obj) != 2:
        raise ValueError(
            "World Bank response is not the two-element [metadata, observations] array; "
            "an error response has this shape too, so check the first element"
        )
    meta, rows = obj
    if not isinstance(meta, dict) or not isinstance(rows, list):
        raise ValueError("World Bank response elements are not [object, list]")
    return meta, [row for row in rows if isinstance(row, dict)]


def vintage_from_last_updated(last_updated: str) -> str:
    """Vintage label for a World Bank response.

    Parameters
    ----------
    last_updated : str
        The ``lastupdated`` field, e.g. ``"2026-07-13"``.

    Returns
    -------
    str
        For example ``"wb2026-07-13"``. When the field is missing or empty the label is
        ``"wb-unknown"``, which is deliberately ugly: an unlabelled vintage should be visible
        in every table it appears in.
    """
    cleaned = str(last_updated or "").strip()
    return f"wb{cleaned}" if cleaned else "wb-unknown"


def parse_indicator_response(payload: bytes | str) -> pd.DataFrame:
    """Parse one indicator response into a frame of observations.

    Parameters
    ----------
    payload : bytes or str
        Response body.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`OBSERVATION_COLUMNS`, sorted by year, **with null observations
        dropped**. The World Bank returns a row per year whether or not it has a value;
        keeping the nulls as NaN rows would violate the panel rule that a missing observation
        is an absent row.

    Raises
    ------
    ValueError
        If the body is not JSON or is not the expected two-element array.
    """
    meta, rows = _extract(payload)
    last_updated = str(meta.get("lastupdated", ""))
    records = []
    for row in rows:
        if row.get("value") is None:
            continue
        indicator = row.get("indicator") or {}
        country = row.get("country") or {}
        records.append(
            {
                "indicator": str(indicator.get("id", "")) if isinstance(indicator, dict) else "",
                "country": str(country.get("id", "")) if isinstance(country, dict) else "",
                "year": row.get("date"),
                "value": row.get("value"),
                "last_updated": last_updated,
            }
        )
    frame = pd.DataFrame(records, columns=list(OBSERVATION_COLUMNS))
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna(subset=["year", "value"]).sort_values("year").reset_index(drop=True)


def to_panel(observations: pd.DataFrame, *, source_id: str = "worldbank_chn_gdp") -> pd.DataFrame:
    """Convert parsed observations into tidy panel rows.

    The only unit conversion in this module: yuan to 100 million yuan, dividing by
    :data:`YUAN_PER_HUNDRED_MILLION`, so that the national denominator is in the same unit as
    the yearbook's provincial levels. The province column is
    :data:`china.clean.schema.NATIONAL`.

    Parameters
    ----------
    observations : pandas.DataFrame
        Output of :func:`parse_indicator_response`.
    source_id : str, default "worldbank_chn_gdp"
        Registry id to stamp on every row.

    Returns
    -------
    pandas.DataFrame
        Rows in :data:`china.clean.schema.PANEL_COLUMNS`, one per year, vintage taken from
        the response's ``lastupdated``.

    Raises
    ------
    ValueError
        If the frame holds an indicator that has no panel series in
        :data:`INDICATOR_TO_SERIES`. Guessing a series name for a series nobody defined is
        how an undocumented number gets into a panel.
    """
    if observations.empty:
        return pd.DataFrame(columns=list(PANEL_COLUMNS))
    unknown = sorted(
        {str(i) for i in observations["indicator"] if str(i) not in INDICATOR_TO_SERIES}
    )
    if unknown:
        raise ValueError(
            f"no panel series defined for World Bank indicator(s) {unknown}; "
            "add one to china.clean.schema.SERIES, with its unit, before loading it"
        )
    series_names = observations["indicator"].map(INDICATOR_TO_SERIES)
    return pd.DataFrame(
        {
            "province": NATIONAL,
            "year": observations["year"].astype("int64"),
            "series": series_names,
            "value": observations["value"] / YUAN_PER_HUNDRED_MILLION,
            "unit": series_names.map(lambda name: SERIES[name].unit),
            "vintage": observations["last_updated"].map(vintage_from_last_updated),
            "source_id": source_id,
        },
        columns=list(PANEL_COLUMNS),
    )

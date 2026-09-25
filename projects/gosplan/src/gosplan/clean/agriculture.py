"""The USDA production, supply and distribution cotton file, loaded as published.

This is the only one of the agricultural sources whose layout the registry records in full.
``usda_psd_cotton_bulk`` records the twelve column names of the CSV inside
``psd_cotton_csv.zip``, the member's name (``psd_cotton.csv``), the commodity code to keep
(``2631000``), and the unit the ``Production`` attribute is published in (``1000 480 lb.
Bales``). The loader keeps every published column under its published name and adds the
basis columns of :data:`gosplan.clean._common.BASIS_COLUMNS`.

The two FAOSTAT bulk files are **not** loaded; see :data:`gosplan.clean.UNLOADED` and
``docs/data_dictionary.md``.

What the loader does not do, on purpose:

* **No unit conversion.** The registry records a bales-to-tonnes factor, but lint bales and
  tonnes of seed cotton are different physical quantities, and the conversion belongs with
  whoever states it beside a result.
* **No union totals for 1987-1991.** The file has no "Former Soviet Union" row, so a union
  total is a sum over successor republics whose composition is a choice that must be
  recorded where it is made.
* **No choice between the two year columns.** ``Market_Year`` and ``Calendar_Year`` are
  both kept; the seal withholds a row if either falls in the held-out window.

The file carries Uzbekistan cotton rows. Every row passes through the seal before the frame
is returned, and the only thing reported about withheld rows is how many there were.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gosplan.clean._common import (
    CURRENCY_BASIS_COLUMN,
    SOURCE_ID_COLUMN,
    TERRITORIAL_BASIS_COLUMN,
    UNIT_COLUMN,
    SchemaError,
    finish,
    read_published_csv,
    require_exact_header,
    to_number,
    withhold_sealed,
)
from gosplan.transcribe.schema import CurrencyBasis, TerritorialBasis
from gosplan.transcribe.validate import MONETARY_UNIT_PATTERN

__all__ = [
    "USDA_PSD_COLUMNS",
    "USDA_PSD_COTTON_COMMODITY_CODE",
    "USDA_PSD_MEMBER",
    "USDA_PSD_RAW_PATH",
    "USDA_PSD_SOURCE_ID",
    "load_usda_psd_cotton",
]

#: Registry id.
USDA_PSD_SOURCE_ID = "usda_psd_cotton_bulk"

#: Where :func:`gosplan.acquire.agriculture.usda_psd_cotton` puts the download, relative to
#: ``data/raw``.
USDA_PSD_RAW_PATH = "usda_psd/psd_cotton_csv.zip"

#: The CSV inside the zip, as named in the registry's download plan.
USDA_PSD_MEMBER = "psd_cotton.csv"

#: The header, exactly as the registry's notes record it.
USDA_PSD_COLUMNS: tuple[str, ...] = (
    "Commodity_Code",
    "Commodity_Description",
    "Country_Code",
    "Country_Name",
    "Market_Year",
    "Calendar_Year",
    "Month",
    "Attribute_ID",
    "Attribute_Description",
    "Unit_ID",
    "Unit_Description",
    "Value",
)

#: The commodity the registry's download plan filters on.
USDA_PSD_COTTON_COMMODITY_CODE = "2631000"

#: What the seal is told the series is. The registry identifies this file, and commodity
#: :data:`USDA_PSD_COTTON_COMMODITY_CODE` within it, as cotton; the published
#: ``Commodity_Description`` text is not recorded, so it is not relied on to say so.
_SEAL_SERIES_LABEL = "cotton"


def load_usda_psd_cotton(path: Path) -> pd.DataFrame:
    """Load the USDA FAS PSD cotton file, with the held-out rows withheld.

    Parameters
    ----------
    path : Path
        ``psd_cotton_csv.zip`` as downloaded, or the ``psd_cotton.csv`` extracted from it.

    Returns
    -------
    pandas.DataFrame
        One row per published row of commodity ``2631000``, with every published column
        under its published name (``Market_Year``, ``Calendar_Year`` and ``Month`` as
        integers, ``Value`` as a float, the rest as strings), plus ``source_id``, ``unit``
        (a copy of ``Unit_Description``), ``territorial_basis`` (``unstated``: the publisher
        does not say) and ``currency_basis`` (``not_monetary``). ``attrs["n_withheld"]``
        is the number of rows the seal withheld.

    Raises
    ------
    SchemaError
        If the header differs from the recorded one, a numeric column holds a non-number,
        or a unit looks monetary: the registry records no monetary attribute in this file,
        so one appearing is a layout the loader has not been told about.
    """
    raw = read_published_csv(Path(path), member=USDA_PSD_MEMBER)
    require_exact_header(raw, USDA_PSD_COLUMNS, USDA_PSD_SOURCE_ID)

    frame = raw.loc[raw["Commodity_Code"].str.strip() == USDA_PSD_COTTON_COMMODITY_CODE].copy()
    for col in ("Market_Year", "Calendar_Year", "Month"):
        frame[col] = to_number(frame[col], what=col, integer=True)
    frame["Value"] = to_number(frame["Value"], what="Value")

    monetary = frame["Unit_Description"].str.contains(MONETARY_UNIT_PATTERN, na=False)
    if monetary.any():
        units = sorted(frame.loc[monetary, "Unit_Description"].unique())
        raise SchemaError(
            f"{USDA_PSD_SOURCE_ID}: unit(s) {units} look monetary, but the registry records "
            "no monetary attribute in this file and no currency basis for one"
        )

    frame[SOURCE_ID_COLUMN] = USDA_PSD_SOURCE_ID
    frame[UNIT_COLUMN] = frame["Unit_Description"]
    frame[TERRITORIAL_BASIS_COLUMN] = TerritorialBasis.UNSTATED.value
    frame[CURRENCY_BASIS_COLUMN] = CurrencyBasis.NOT_MONETARY.value

    frame = frame.reset_index(drop=True)
    frame, n_withheld = withhold_sealed(
        frame,
        region=frame["Country_Name"],
        series=pd.Series(_SEAL_SERIES_LABEL, index=frame.index),
        years=[frame["Market_Year"], frame["Calendar_Year"]],
    )
    return finish(frame, source_id=USDA_PSD_SOURCE_ID, n_withheld=n_withheld)

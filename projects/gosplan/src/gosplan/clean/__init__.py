"""Loaders for the sources that are already machine-readable, and a register of the ones that
are not yet loadable.

A loader reads a file :mod:`gosplan.acquire` has put under ``data/raw`` and returns a
``pandas.DataFrame`` that keeps every published column under its published name and adds
four columns, :data:`BASIS_COLUMNS`:

``source_id``
    The ``SOURCES.yaml`` id the rows came from.
``unit``
    The unit the publisher states, copied verbatim. Never normalised, never converted.
``territorial_basis``
    In the vocabulary of :class:`gosplan.transcribe.schema.TerritorialBasis`. The 1939-40
    annexations changed what "USSR" means (``docs/known_traps.md``, trap 2).
``currency_basis``
    In the vocabulary of :class:`gosplan.transcribe.schema.CurrencyBasis`, or **blank** where
    the registry does not record which rouble a monetary series is in. The 1961
    redenomination rescaled every monetary series tenfold (trap 1), and a blank here is a
    statement that the series cannot yet be compared with anything, not an oversight.

Every loaded frame has passed through :func:`gosplan.seal.filter_sealed`, and
``frame.attrs["n_withheld"]`` says how many rows the seal withheld. That count is the only
thing reported about them.

The rule these loaders follow is the card's: **no column name, sheet name, unit or base year
is used unless the registry records it.** Where the registry does not record what a loader
needs, there is no loader, and :data:`UNLOADED` says why. A source that is missing from both
:data:`LOADERS` and :data:`UNLOADED` is a silent gap, which the tests refuse.
"""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from gosplan.clean._common import BASIS_COLUMNS, N_WITHHELD_ATTR, SchemaError
from gosplan.clean.agriculture import load_usda_psd_cotton
from gosplan.clean.western_estimates import load_hokudai_sess

#: Registry id -> loader.
LOADERS: MappingProxyType[str, Callable[..., Any]] = MappingProxyType(
    {
        "usda_psd_cotton_bulk": load_usda_psd_cotton,
        "hokudai_sess": load_hokudai_sess,
    }
)

#: Registry id -> why no loader exists. Each reason names what the registry would have to
#: record, or what the stack would have to be able to read, for one to be written. The
#: ambiguity reports named here are in ``workorders/``.
UNLOADED: MappingProxyType[str, str] = MappingProxyType(
    {
        "faostat_qcl_bulk_europe_ussr": (
            "column names only partly recorded: the registry names Area Code, Item Code and "
            "Element Code and writes years as Y1961, but not the name of the unit column or "
            "of the flag column the registry itself says must be kept, and records the "
            "encoding only as 'latin-1/UTF-8' (AMBIGUITY-WO-504-1)"
        ),
        "faostat_qcl_bulk_asia_uzbekistan": (
            "same file layout as faostat_qcl_bulk_europe_ussr, with the same unrecorded "
            "columns (AMBIGUITY-WO-504-1)"
        ),
        "maddison_mpd2023": (
            "the 'Full data' sheet's columns are recorded (countrycode, country, region, year, "
            "gdppc, pop) but the unit and price base year of gdppc are not, and pop's unit is "
            "only implied by the notes (AMBIGUITY-WO-504-3)"
        ),
        "harrison_sovietgrowth": (
            "legacy Excel 97-2003 BIFF8 .xls: needs xlrd or LibreOffice, neither of which is a "
            "project dependency; no column headers recorded (AMBIGUITY-WO-504-2)"
        ),
        "harrison_ussr_ww2": (
            "six legacy BIFF .xls workbooks (old BIFF header, codepage -535): need xlrd or "
            "LibreOffice; no sheet names or column headers recorded (AMBIGUITY-WO-504-2)"
        ),
        "wb_soviet_economic_decline": (
            "nested zip of MicroTSP .DB series files and a Lotus 1-2-3 USSR.WK1 sheet: no "
            "reader for either in the stack (AMBIGUITY-WO-504-2)"
        ),
        "harrison_plan_fraud": (
            "a case index, not a series: column headers recorded only as 'include "
            "Establishment, Accused, #Accused, Where, Branch', no year or series column "
            "recorded for the seal to check, and no numeric column for a unit to describe "
            "(AMBIGUITY-WO-504-4)"
        ),
        "harrison_greatwar_munitions_pdf": (
            "PDF appendices only; a table-extraction or transcription job, not a loader"
        ),
        "pwt_110": (
            "the registry records that PWT contains no USSR entity, and records no column "
            "names for the Data sheet"
        ),
    }
)

__all__ = [
    "BASIS_COLUMNS",
    "LOADERS",
    "N_WITHHELD_ATTR",
    "UNLOADED",
    "SchemaError",
    "load_hokudai_sess",
    "load_usda_psd_cotton",
]

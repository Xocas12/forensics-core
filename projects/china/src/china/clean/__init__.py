"""Cleaning: raw acquisitions to one tidy provincial-year-series-vintage panel.

Modules
-------
schema
    The panel: ``province, year, series, value, unit, vintage, source_id``, the series
    catalogue with units, and validation. Start here; the ``vintage`` column is what the
    whole project turns on.
provinces
    Canonical province names, edition-to-edition aliases, the rows in a regional table that
    are not provinces, and the sub-provincial units the admitted revisions actually happened
    in.
yearbook
    The edition contents frames, parsed for real. The table images themselves are stubs:
    they are JPEG scans and there is no honest parser to write until an extraction back end
    is chosen.
worldbank
    The national gross domestic product series, machine-readable, with the vintage warning
    that stops it being used as the gap's denominator.
nbs_api
    The bureau's catalogue responses. Metadata only: the values endpoint is unknown.
pbc_reports
    The central bank's regional reports. Loan balances arrive as rounded prose, and the
    Chinese-to-canonical province mapping is an open question this module refuses to guess.

What is machine-readable today, and what is not
-----------------------------------------------
Machine-readable and implemented: yearbook contents frames, World Bank indicator responses,
catalogue tree and indicator responses, central-bank report index and year pages, loan-balance
sentences once a PDF's text is extracted, Figshare article metadata.

Not machine-readable: **every actual provincial number**, because every one of them is inside
a JPEG. That is the project's bottleneck and it is stated as such in ``README.md``,
``data/ACCESS_NOTES.md`` and in the docstring of
:func:`china.clean.yearbook.extract_table_image`, which raises rather than returning
something plausible.
"""

from china.clean.schema import (
    NATIONAL,
    PANEL_COLUMNS,
    PANEL_KEY,
    SERIES,
    coerce_panel,
    empty_panel,
    validate_panel,
)

__all__ = [
    "NATIONAL",
    "PANEL_COLUMNS",
    "PANEL_KEY",
    "SERIES",
    "coerce_panel",
    "empty_panel",
    "validate_panel",
]

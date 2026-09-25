"""Map XBRL tags in the SEC Financial Statement Data Sets to the twelve Beneish items.

This is the weakest link in the whole pipeline, and it is written to look weak rather than to
look finished.

What is being mapped
--------------------
:data:`aaer.features.beneish.REQUIRED_COLUMNS` names twelve financial items for fiscal year
``t``, and :data:`aaer.features.beneish.LAGGED_COLUMNS` the ten of them that are also needed for
``t-1``. The Financial Statement Data Sets deliver facts keyed by *us-gaap taxonomy element
name*, one row per ``(adsh, tag, version, ddate, qtrs, uom, segments, coreg)``. Turning the
second into the first is a dictionary, and the dictionary is a modelling decision, not a
lookup table that exists somewhere to be copied.

Confirmation status: read this before using any number that comes out of here
-----------------------------------------------------------------------------
**The mapping in :data:`BENEISH_TAG_MAP` is provisional.** Exactly one element name in it was
observed in a response actually fetched from the SEC during scaffolding:
``AccountsReceivableNetCurrent``, in the ``companyfacts`` sample for CIK 0000320193 (registry
entry ``sec_companyfacts_api_sample``; ``AccountsPayableCurrent`` was also observed, in the API
documentation's endpoint example, but it is not one of the twelve items). Every other element
name here comes from the implementer's knowledge of the us-gaap taxonomy and **has not been
checked against a real filing in this project**. Each entry carries
:attr:`ItemMapping.confirmed` and a note saying what specifically is doubtful.

Confirming them is cheap and is the first thing to do with the acquired data: load a quarter
with :func:`aaer.clean.fsds.read_fsds_zip`, count ``num.tag`` by frequency among 10-K filings,
and compare against the candidate lists below. :func:`tag_frequency` does exactly that.

Three selection rules that are also unconfirmed
-----------------------------------------------
1. ``qtrs``: this module assumes ``qtrs == 0`` marks a point-in-time (balance sheet) fact and
   ``qtrs == 4`` a four-quarter (annual) duration. That convention is defined in section 5.3 of
   the documentation PDF, which was **not read** during scaffolding -- only its section
   headings and the NUM key were. Confirm it against ``data/raw/fsds/financial-statement-data-sets.pdf``
   (``python -m aaer.acquire sec_fsds_readme``) before trusting any flow item.
2. ``ddate == sub.period``: the current fiscal year's figure is taken to be the fact whose date
   equals the filing's own period end, which discards the prior-year comparatives that the same
   filing also carries. That is a deliberate choice -- comparatives are *restated* values and
   using them for ``t-1`` would silently mix vintages -- but it means the lag has to come from
   the previous year's own filing (:func:`add_lags`), and firms that were not filing in XBRL a
   year earlier have no lag at all.
3. ``version`` beginning with ``us-gaap``: filer extension tags are excluded. TAG.custom is the
   authoritative flag for that and is the better test once the tag table is loaded.

What this module does not do
----------------------------
It does not fill gaps, interpolate, or fall back to a related item when a mapping misses. A
firm-year missing one of the twelve items comes out with ``NaN`` in that column and is counted
in :attr:`MappingResult.steps`. Nothing is imputed anywhere in this project.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from aaer.features.beneish import LAGGED_COLUMNS, REQUIRED_COLUMNS

#: Filing forms treated as annual reports. Only the plain ``10-K`` is included: ``10-K/A``
#: amendments restate a year already counted, and mixing them in would double-count firm-years
#: unless amendment supersession is handled explicitly, which it is not.
ANNUAL_FORMS: tuple[str, ...] = ("10-K",)

#: Fiscal-period code of an annual filing in SUB.fp.
ANNUAL_FISCAL_PERIOD: str = "FY"

#: ``qtrs`` value assumed to mark a point-in-time fact (balance sheet). UNCONFIRMED; see the
#: module docstring, rule 1.
QTRS_INSTANT: str = "0"

#: ``qtrs`` value assumed to mark a four-quarter duration fact (income / cash-flow statement).
#: UNCONFIRMED; see the module docstring, rule 1.
QTRS_ANNUAL: str = "4"


@dataclass(frozen=True)
class ItemMapping:
    """Candidate us-gaap tags for one of the twelve Beneish items.

    Attributes
    ----------
    item : str
        Column name in :data:`aaer.features.beneish.REQUIRED_COLUMNS`.
    tags : tuple of str
        us-gaap element names in **priority order**: the first one present for a filing wins.
    kind : {"instant", "duration"}
        Whether the item is a stock (balance sheet) or a flow (income / cash-flow statement).
        Decides which ``qtrs`` value is selected.
    confirmed : bool
        True only if the element name was seen in a response actually fetched from the SEC and
        recorded in ``data/SOURCES.yaml``. Currently true for exactly one item.
    note : str
        What is doubtful about this entry, in plain words.
    """

    item: str
    tags: tuple[str, ...]
    kind: Literal["instant", "duration"]
    confirmed: bool
    note: str

    @property
    def qtrs(self) -> str:
        """The ``NUM.qtrs`` value this item is selected on."""
        return QTRS_INSTANT if self.kind == "instant" else QTRS_ANNUAL


def _m(item: str, tags: Sequence[str], kind: str, confirmed: bool, note: str) -> ItemMapping:
    return ItemMapping(item, tuple(tags), kind, confirmed, note)  # type: ignore[arg-type]


#: The mapping. One entry per item in :data:`aaer.features.beneish.REQUIRED_COLUMNS`.
#: PROVISIONAL -- see the module docstring. Tags are listed most-preferred first.
BENEISH_TAG_MAP: Mapping[str, ItemMapping] = {
    "receivables": _m(
        "receivables",
        [
            "AccountsReceivableNetCurrent",
            "ReceivablesNetCurrent",
            "AccountsReceivableGrossCurrent",
        ],
        "instant",
        True,
        "AccountsReceivableNetCurrent was observed in the fetched companyfacts sample for CIK "
        "0000320193 (registry sec_companyfacts_api_sample), so the element name is real. Which "
        "of the three most filers use, and whether Beneish's 'receivables' should be net or "
        "gross of allowance, are both unconfirmed; Beneish (1999) uses net.",
    ),
    "sales": _m(
        "sales",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
        ],
        "duration",
        False,
        "UNCONFIRMED, and the riskiest entry in the table: the dominant revenue element changed "
        "with the ASC 606 revenue standard, so quarters before and after roughly 2018 are "
        "expected to use different tags for the same economic quantity. Priority order here "
        "puts the post-606 elements first, which biases the choice on filings that report both. "
        "Check the split by year with tag_frequency() before using any time series of SGI.",
    ),
    "cogs": _m(
        "cogs",
        ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfServices"],
        "duration",
        False,
        "UNCONFIRMED. CostOfRevenue and CostOfGoodsAndServicesSold are not the same quantity for "
        "firms with a service segment, and GMI is a ratio of ratios, so a tag switch between t-1 "
        "and t produces a spurious index far from 1.",
    ),
    "current_assets": _m(
        "current_assets",
        ["AssetsCurrent"],
        "instant",
        False,
        "UNCONFIRMED. Firms with an unclassified balance sheet -- banks, insurers, some "
        "REITs -- do not report a current/noncurrent split at all, so this item is missing for "
        "an entire, industry-correlated block of filers rather than at random. That is trap 6 "
        "in docs/known_traps.md arriving as missingness instead of as bias.",
    ),
    "ppe_net": _m(
        "ppe_net",
        ["PropertyPlantAndEquipmentNet"],
        "instant",
        False,
        "UNCONFIRMED. Beneish's AQI and DEPI both use net PP&E. No gross-PP&E fallback is "
        "listed on purpose: substituting gross for net changes the quantity, and a silent "
        "substitution would be worse than a missing value.",
    ),
    "total_assets": _m(
        "total_assets",
        ["Assets"],
        "instant",
        False,
        "UNCONFIRMED, though 'Assets' is the least likely element in this table to be wrong. It "
        "is the denominator of AQI, LVGI and TATA, so a firm-year missing it loses three of the "
        "eight components.",
    ),
    "depreciation": _m(
        "depreciation",
        [
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ],
        "duration",
        False,
        "UNCONFIRMED and definitionally impure: Beneish's DEPI wants depreciation excluding "
        "amortisation, while the first two candidates include it. The Compustat item the "
        "literature uses (dp) also combines them, so this may be the right kind of wrong for "
        "comparability -- but say which is used in any table.",
    ),
    "sga": _m(
        "sga",
        ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense"],
        "duration",
        False,
        "UNCONFIRMED, and the item most likely to be simply absent: many filers report only "
        "OperatingExpenses or split selling and administrative costs across custom tags. Note "
        "the parallel gap on the other data path: the Bao et al. CSV has no xsga column either "
        "(registry bao_analysis_csv), so SGAI is the one Beneish component that neither free "
        "source supports cleanly.",
    ),
    "long_term_debt": _m(
        "long_term_debt",
        ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
        "instant",
        False,
        "UNCONFIRMED. LongTermDebt includes the current portion while LongTermDebtNoncurrent "
        "excludes it; Beneish's LVGI pairs long-term debt with current liabilities, so taking "
        "the wrong one double-counts the current portion. Compustat's dltt is the noncurrent "
        "figure. Whether the operating-lease liabilities that ASC 842 moved onto the balance "
        "sheet in 2019 belong here is a further, unresolved question.",
    ),
    "current_liabilities": _m(
        "current_liabilities",
        ["LiabilitiesCurrent"],
        "instant",
        False,
        "UNCONFIRMED. Same unclassified-balance-sheet problem as current_assets, and missing "
        "for the same filers, so the two gaps are perfectly correlated.",
    ),
    "income_continuing_ops": _m(
        "income_continuing_ops",
        [
            "IncomeLossFromContinuingOperations",
            "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
            "ProfitLoss",
            "NetIncomeLoss",
        ],
        "duration",
        False,
        "UNCONFIRMED. The last two candidates are NOT income from continuing operations: they "
        "include discontinued operations, and ProfitLoss includes noncontrolling interests. "
        "They are listed because most filers with no discontinued operations tag only "
        "NetIncomeLoss, in which case the two coincide -- but the fallback silently changes the "
        "definition for firms that do have discontinued operations, which is exactly the "
        "population where restructuring and manipulation cluster. Consider dropping the "
        "fallbacks and accepting the missingness instead; trap 7 in docs/known_traps.md.",
    ),
    "cash_from_operations": _m(
        "cash_from_operations",
        [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        "duration",
        False,
        "UNCONFIRMED. Needed only because aaer.features.beneish.tata implements the "
        "cash-flow-statement definition of total accruals. Beneish (1999) itself computes "
        "accruals from balance-sheet changes, which needs no cash-flow item at all; if this "
        "mapping proves unreliable, switching TATA to the balance-sheet definition is the "
        "cheaper fix, and the registry notes the Bao et al. CSV omits oancf for the same reason.",
    ),
}

#: Items whose element name was observed in a fetched SEC response.
CONFIRMED_ITEMS: tuple[str, ...] = tuple(k for k, v in BENEISH_TAG_MAP.items() if v.confirmed)

#: Items whose mapping is the implementer's assumption and needs checking against a real filing.
UNCONFIRMED_ITEMS: tuple[str, ...] = tuple(k for k, v in BENEISH_TAG_MAP.items() if not v.confirmed)


def mapping_table() -> pd.DataFrame:
    """The mapping as a frame: one row per item, for ``docs/data_dictionary.md`` and audits."""
    return pd.DataFrame(
        [
            {
                "item": m.item,
                "kind": m.kind,
                "qtrs": m.qtrs,
                "n_candidate_tags": len(m.tags),
                "tags": ";".join(m.tags),
                "confirmed": m.confirmed,
                "note": m.note,
            }
            for m in BENEISH_TAG_MAP.values()
        ]
    )


def check_mapping_covers_beneish() -> tuple[str, ...]:
    """Items :mod:`aaer.features.beneish` requires that this mapping does not define.

    Returns
    -------
    tuple of str
        Empty when the mapping is complete. Called by the test suite so that adding an item to
        ``REQUIRED_COLUMNS`` fails loudly here instead of producing an all-``NaN`` column.
    """
    return tuple(c for c in REQUIRED_COLUMNS if c not in BENEISH_TAG_MAP)


@dataclass(frozen=True)
class MappingResult:
    """The firm-year panel plus a full account of what was lost getting to it.

    Attributes
    ----------
    frame : pandas.DataFrame
        One row per ``(cik, fy)``, the six key columns ``adsh, cik, fy, period, form, filed``
        returned by :func:`annual_submissions` and merged through unchanged, followed by the
        twelve items. Missing items are ``NaN``; nothing is imputed. ``filed`` is the filing
        date the deduplication ranked on, kept so that a downstream caller can see which
        vintage of a restated firm-year it is holding.
    steps : pandas.DataFrame
        Columns ``step, n_rows, n_lost, note``, in pipeline order. This is the "how many
        firm-years are lost at each mapping step" record.
    item_coverage : pandas.DataFrame
        Columns ``item, confirmed, n_present, n_missing, share_present, tags_used``.
    unmapped_items : tuple of str
        Items for which **no** candidate tag matched a single fact. These are reported, never
        dropped: an item that maps to nothing means the mapping is wrong, not that the item
        does not exist.
    """

    frame: pd.DataFrame
    steps: pd.DataFrame
    item_coverage: pd.DataFrame
    unmapped_items: tuple[str, ...]

    def summary(self) -> str:
        """One paragraph fit for a log or a notebook cell."""
        complete = int(self.frame[list(REQUIRED_COLUMNS)].notna().all(axis=1).sum())
        parts = [
            f"{len(self.frame)} firm-years mapped, {complete} complete on all "
            f"{len(REQUIRED_COLUMNS)} items",
        ]
        if self.unmapped_items:
            parts.append(
                f"UNMAPPED ITEMS (no fact matched any candidate tag): "
                f"{', '.join(self.unmapped_items)}"
            )
        parts.append(
            f"{len(UNCONFIRMED_ITEMS)} of {len(BENEISH_TAG_MAP)} mappings are "
            f"unconfirmed against a real filing"
        )
        return "; ".join(parts)


def annual_submissions(
    sub: pd.DataFrame,
    *,
    forms: Iterable[str] = ANNUAL_FORMS,
    fiscal_period: str = ANNUAL_FISCAL_PERIOD,
) -> pd.DataFrame:
    """Annual submissions, one per ``(cik, fy)``.

    Parameters
    ----------
    sub : pandas.DataFrame
        The SUB table of one or more quarters (:mod:`aaer.clean.fsds`).
    forms : iterable of str, default :data:`ANNUAL_FORMS`
        Accepted ``form`` values.
    fiscal_period : str, default "FY"
        Accepted ``fp`` value.

    Returns
    -------
    pandas.DataFrame
        Columns ``adsh, cik, fy, period, form, filed``, with ``fy`` as nullable integer. When a
        firm has more than one qualifying filing for the same fiscal year, the one with the
        latest ``filed`` date is kept; ties keep the last row in file order.
    """
    wanted = set(forms)
    keep = sub[sub["form"].isin(wanted) & (sub["fp"] == fiscal_period)].copy()
    keep["fy"] = pd.to_numeric(keep["fy"], errors="coerce").astype("Int64")
    keep = keep[keep["fy"].notna()]
    keep = keep.sort_values("filed", kind="stable")
    keep = keep.drop_duplicates(subset=["cik", "fy"], keep="last")
    return keep[["adsh", "cik", "fy", "period", "form", "filed"]].reset_index(drop=True)


def _tag_catalog() -> pd.DataFrame:
    rows = []
    for m in BENEISH_TAG_MAP.values():
        for rank, tag in enumerate(m.tags):
            rows.append({"item": m.item, "tag": tag, "tag_rank": rank, "qtrs_required": m.qtrs})
    return pd.DataFrame(rows)


def tag_frequency(
    num: pd.DataFrame, *, adsh: Iterable[str] | None = None, top: int = 50
) -> pd.DataFrame:
    """Most frequent us-gaap tags, to check :data:`BENEISH_TAG_MAP` against reality.

    This is the confirmation tool the module docstring points at: run it on an acquired quarter,
    look for the candidate element names, and correct the mapping where the real filings
    disagree. It counts facts, not firms, so a filer reporting a tag many times counts many
    times; that is fine for spotting names and not fine for anything else.

    Parameters
    ----------
    num : pandas.DataFrame
        The NUM table.
    adsh : iterable of str, optional
        Restrict to these submissions, e.g. the annual ones.
    top : int, default 50
        Rows returned.

    Returns
    -------
    pandas.DataFrame
        Columns ``tag, n_facts, in_mapping, mapped_item``.
    """
    facts = num if adsh is None else num[num["adsh"].isin(set(adsh))]
    counts = facts["tag"].value_counts().head(top).rename_axis("tag").reset_index(name="n_facts")
    catalog = _tag_catalog()[["tag", "item"]].drop_duplicates("tag")
    out = counts.merge(catalog, on="tag", how="left")
    out["in_mapping"] = out["item"].notna()
    return out.rename(columns={"item": "mapped_item"})


def map_beneish_items(
    sub: pd.DataFrame,
    num: pd.DataFrame,
    *,
    taxonomy_prefix: str = "us-gaap",
    unit: str = "USD",
    forms: Iterable[str] = ANNUAL_FORMS,
) -> MappingResult:
    """Build the firm-year panel of the twelve Beneish items, counting every loss.

    Parameters
    ----------
    sub, num : pandas.DataFrame
        SUB and NUM tables from :mod:`aaer.clean.fsds`, for one quarter or many.
    taxonomy_prefix : str, default "us-gaap"
        Only facts whose ``version`` starts with this are used, which excludes filer extension
        tags. See the module docstring, rule 3.
    unit : str, default "USD"
        Only facts in this unit of measure are used.
    forms : iterable of str, default :data:`ANNUAL_FORMS`
        Forms treated as annual reports.

    Returns
    -------
    MappingResult

    Notes
    -----
    Consolidated totals only: rows with a non-empty ``segments`` or ``coreg`` are excluded,
    since those carry dimensional breakdowns and co-registrant figures rather than the
    consolidated line item.
    """
    steps: list[dict[str, object]] = []

    def _step(name: str, n: int, note: str) -> None:
        previous = steps[-1]["n_rows"] if steps else n
        steps.append(
            {"step": name, "n_rows": n, "n_lost": int(previous) - n, "note": note}  # type: ignore[operator]
        )

    _step("submissions in input", int(sub["adsh"].nunique()), "SUB rows, any form")
    annual = annual_submissions(sub, forms=forms)
    _step(
        "annual filings, deduplicated to one per (cik, fy)",
        len(annual),
        f"form in {sorted(set(forms))} and fp == {ANNUAL_FISCAL_PERIOD!r}; latest filed wins",
    )

    catalog = _tag_catalog()
    facts = num.merge(annual[["adsh", "cik", "fy", "period"]], on="adsh", how="inner")
    facts = facts[
        (facts["uom"] == unit)
        & (facts["segments"] == "")
        & (facts["coreg"] == "")
        & facts["version"].str.startswith(taxonomy_prefix)
        & (facts["ddate"] == facts["period"])
    ]
    facts = facts.merge(catalog, on="tag", how="inner")
    facts = facts[(facts["qtrs"] == facts["qtrs_required"]) & facts["value"].notna()]

    chosen = (
        facts.sort_values(["adsh", "item", "tag_rank"], kind="stable")
        .drop_duplicates(subset=["adsh", "item"], keep="first")
        .loc[:, ["adsh", "item", "tag", "value"]]
    )

    # `chosen` already holds at most one row per (adsh, item), so the aggregation below is a
    # no-op; pivot_table is used only because it tolerates an empty input frame.
    wide = chosen.pivot_table(index="adsh", columns="item", values="value", aggfunc="first")
    wide = wide.reindex(columns=list(REQUIRED_COLUMNS))
    frame = annual.merge(wide, left_on="adsh", right_index=True, how="left")
    _step(
        "firm-years with at least one mapped fact",
        int(frame[list(REQUIRED_COLUMNS)].notna().any(axis=1).sum()),
        "a firm-year with no fact at all usually means the filing was not detail-tagged",
    )
    _step(
        f"firm-years complete on all {len(REQUIRED_COLUMNS)} items",
        int(frame[list(REQUIRED_COLUMNS)].notna().all(axis=1).sum()),
        "no imputation is performed; incomplete rows are kept in `frame` with NaN",
    )

    tags_used = (
        chosen.groupby("item")["tag"]
        .agg(lambda s: ";".join(f"{t}={n}" for t, n in s.value_counts().items()))
        .to_dict()
    )
    coverage = pd.DataFrame(
        [
            {
                "item": item,
                "confirmed": BENEISH_TAG_MAP[item].confirmed,
                "n_present": int(frame[item].notna().sum()),
                "n_missing": int(frame[item].isna().sum()),
                "share_present": (
                    float(frame[item].notna().mean()) if len(frame) else float("nan")
                ),
                "tags_used": tags_used.get(item, ""),
            }
            for item in REQUIRED_COLUMNS
        ]
    )
    unmapped = tuple(coverage.loc[coverage["n_present"] == 0, "item"])

    return MappingResult(
        frame=frame.reset_index(drop=True),
        steps=pd.DataFrame(steps),
        item_coverage=coverage,
        unmapped_items=unmapped,
    )


@dataclass(frozen=True)
class LagResult:
    """A firm-year panel with ``_lag`` columns attached, and the cost of attaching them."""

    frame: pd.DataFrame
    n_input_rows: int
    n_with_any_lag: int
    n_with_all_lags: int

    def summary(self) -> str:
        """One line: how many firm-years survived the lag join."""
        return (
            f"{self.n_input_rows} firm-years in, {self.n_with_any_lag} matched a prior year, "
            f"{self.n_with_all_lags} complete on all {len(LAGGED_COLUMNS)} lagged items"
        )


def add_lags(frame: pd.DataFrame, *, id_col: str = "cik", year_col: str = "fy") -> LagResult:
    """Attach year ``t-1`` values as ``<item>_lag`` columns by joining the panel to itself.

    The lag comes from the **prior year's own filing**, not from the comparative column of the
    current filing; see the module docstring, rule 2. The practical consequence is that the
    first year a firm appears in the data has no lag, so the whole of 2009 is unusable for
    Beneish indices even where the items themselves are present.

    Parameters
    ----------
    frame : pandas.DataFrame
        Output of :func:`map_beneish_items`, or anything with ``id_col``, ``year_col`` and the
        item columns.
    id_col : str, default "cik"
        Firm identifier. CIK is stable across years; ``adsh`` is not, it is per filing.
    year_col : str, default "fy"
        Fiscal year, integer-valued.

    Returns
    -------
    LagResult

    Raises
    ------
    ValueError
        If ``id_col``, ``year_col`` or any lagged item column is absent.
    """
    base_items = [c[: -len("_lag")] for c in LAGGED_COLUMNS]
    missing = [c for c in (id_col, year_col, *base_items) if c not in frame.columns]
    if missing:
        raise ValueError(f"add_lags: missing columns {missing}")

    years = pd.to_numeric(frame[year_col], errors="coerce").astype("Int64")
    prior = frame.loc[:, [id_col, *base_items]].copy()
    prior[year_col] = years + 1
    prior = prior.rename(columns={c: f"{c}_lag" for c in base_items})
    prior = prior[prior[year_col].notna()].drop_duplicates(subset=[id_col, year_col], keep="last")

    left = frame.copy()
    left[year_col] = years
    out = left.merge(prior, on=[id_col, year_col], how="left")

    lag_cols = list(LAGGED_COLUMNS)
    return LagResult(
        frame=out,
        n_input_rows=len(frame),
        n_with_any_lag=int(out[lag_cols].notna().any(axis=1).sum()),
        n_with_all_lags=int(out[lag_cols].notna().all(axis=1).sum()),
    )

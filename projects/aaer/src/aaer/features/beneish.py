"""Beneish M-score: the standard baseline for earnings-manipulation screening.

Reference: Beneish, M. D. (1999). "The Detection of Earnings Manipulation." *Financial
Analysts Journal* 55(5): 24-36.

Verification status
-------------------
The eight coefficients and the intercept below were **confirmed** against Table 3 Panel A,
"unweighted probit" row, of the June 1999 working-paper version of Beneish (1999), read at
https://www.calctopia.com/papers/beneish1999.pdf . The typeset *Financial Analysts Journal*
version is paywalled and was not read. Coefficients and t-statistics as printed:

    Constant -4.840 (-11.01), DSRI 0.920 (6.02), GMI 0.528 (2.20), AQI 0.404 (3.20),
    SGI 0.892 (5.39), DEPI 0.115 (0.70), SGAI -0.172 (-0.71), TATA 4.679 (3.73),
    LVGI -0.327 (-1.22)

giving M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI
           - 0.172*SGAI + 4.679*TATA - 0.327*LVGI.

DEPI, SGAI and LVGI are not statistically significant in the paper's own estimation.

.. warning::
   **The -1.78 threshold is not a universal constant: it encodes an assumed cost ratio.**
   The paper states that at relative error costs of 20:1 or 30:1 the model classifies a firm
   as a manipulator when the estimated probability exceeds .0376, "a score greater than
   -1.78"; at 10:1 the cut-off is -1.49 (probability .0685). Any table that flags on -1.78
   must say which cost assumption it is making.

.. warning::
   Table 3 also reports a **WESML** (weighted exogenous sampling maximum likelihood) variant
   with a different intercept (-4.954) and different coefficients. This module implements the
   unweighted probit. The widely circulated **five-variable "Beneish model" is unverified**:
   its coefficients do not appear in the 1999 working paper and were found only on commercial
   websites, one of which mislabels a term. Do not implement it from those sources.

See ``projects/aaer/docs/validation_anchors.md`` for the full provenance record.

Every component index is implemented as a separate, separately tested function operating on
aligned ``pandas.Series`` (or scalars) for year *t* and year *t-1*. Each function returns
``NaN`` where a denominator is zero or an input is missing rather than raising, because
firm-year panels are ragged; ``m_score`` propagates ``NaN`` and a flag is never raised on a
``NaN`` score.

Sign conventions follow the paper: every index is constructed so that a value above 1
(or TATA above 0) points toward manipulation, and every coefficient except SGAI and LVGI is
positive.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

ArrayLike = pd.Series | np.ndarray | float | int

#: Eight-variable model coefficients: Beneish (1999) Table 3 Panel A, unweighted probit.
BENEISH_8_COEFFICIENTS: Mapping[str, float] = {
    "DSRI": 0.920,
    "GMI": 0.528,
    "AQI": 0.404,
    "SGI": 0.892,
    "DEPI": 0.115,
    "SGAI": -0.172,
    "TATA": 4.679,
    "LVGI": -0.327,
}
#: Intercept of the eight-variable model (Beneish 1999, Table 3 Panel A).
BENEISH_8_INTERCEPT: float = -4.84
#: Flag threshold at 20:1 or 30:1 relative error costs: M > -1.78 means likely manipulator.
#: At 10:1 the paper gives -1.49. See the module docstring.
BENEISH_FLAG_THRESHOLD: float = -1.78

COMPONENT_NAMES: tuple[str, ...] = ("DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "TATA", "LVGI")


def _ratio(num: ArrayLike, den: ArrayLike) -> ArrayLike:
    """num / den with NaN (not inf, not an exception) where den == 0."""
    num_a = np.asarray(num, dtype=float)
    den_a = np.asarray(den, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(den_a == 0, np.nan, num_a / den_a)
    if isinstance(num, pd.Series):
        return pd.Series(out, index=num.index, name=num.name)
    if isinstance(den, pd.Series):
        return pd.Series(out, index=den.index)
    if out.ndim == 0:
        return float(out)
    return out


def dsri(receivables_t, sales_t, receivables_tm1, sales_tm1) -> ArrayLike:
    """Days' Sales in Receivables Index.

    DSRI = (Receivables_t / Sales_t) / (Receivables_{t-1} / Sales_{t-1}).
    A large increase in receivables relative to sales may indicate revenue inflation.
    """
    return _ratio(_ratio(receivables_t, sales_t), _ratio(receivables_tm1, sales_tm1))


def gmi(sales_t, cogs_t, sales_tm1, cogs_tm1) -> ArrayLike:
    """Gross Margin Index.

    GMI = [(Sales_{t-1} - COGS_{t-1}) / Sales_{t-1}] / [(Sales_t - COGS_t) / Sales_t].
    Greater than 1 when margins deteriorated: a firm with worsening prospects is more likely
    to manipulate.
    """
    margin_tm1 = _ratio(np.asarray(sales_tm1, float) - np.asarray(cogs_tm1, float), sales_tm1)
    margin_t = _ratio(np.asarray(sales_t, float) - np.asarray(cogs_t, float), sales_t)
    out = _ratio(margin_tm1, margin_t)
    return _as_like(out, sales_t)


def aqi(
    current_assets_t, ppe_net_t, total_assets_t, current_assets_tm1, ppe_net_tm1, total_assets_tm1
) -> ArrayLike:
    """Asset Quality Index.

    AQI = [1 - (CurrentAssets_t + PPE_t) / TotalAssets_t]
          / [1 - (CurrentAssets_{t-1} + PPE_{t-1}) / TotalAssets_{t-1}].
    Beneish (1999) uses current assets plus net PP&E; later variants (e.g. Beneish, Lee &
    Nichols 2013) also add securities -- that variant is deliberately not used here.
    """
    nc_t = 1.0 - np.asarray(
        _ratio(np.asarray(current_assets_t, float) + np.asarray(ppe_net_t, float), total_assets_t),
        float,
    )
    nc_tm1 = 1.0 - np.asarray(
        _ratio(
            np.asarray(current_assets_tm1, float) + np.asarray(ppe_net_tm1, float), total_assets_tm1
        ),
        float,
    )
    return _as_like(_ratio(nc_t, nc_tm1), total_assets_t)


def sgi(sales_t, sales_tm1) -> ArrayLike:
    """Sales Growth Index. SGI = Sales_t / Sales_{t-1}."""
    return _ratio(sales_t, sales_tm1)


def depi(depreciation_t, ppe_net_t, depreciation_tm1, ppe_net_tm1) -> ArrayLike:
    """Depreciation Index.

    DEPI = [Dep_{t-1} / (Dep_{t-1} + PPE_{t-1})] / [Dep_t / (Dep_t + PPE_t)].
    Greater than 1 when the depreciation rate slowed (assets being written down more slowly).
    """
    rate_tm1 = _ratio(
        depreciation_tm1, np.asarray(depreciation_tm1, float) + np.asarray(ppe_net_tm1, float)
    )
    rate_t = _ratio(
        depreciation_t, np.asarray(depreciation_t, float) + np.asarray(ppe_net_t, float)
    )
    return _as_like(_ratio(rate_tm1, rate_t), ppe_net_t)


def sgai(sga_t, sales_t, sga_tm1, sales_tm1) -> ArrayLike:
    """Sales, General & Administrative Expenses Index.

    SGAI = (SGA_t / Sales_t) / (SGA_{t-1} / Sales_{t-1}).
    """
    return _ratio(_ratio(sga_t, sales_t), _ratio(sga_tm1, sales_tm1))


def lvgi(
    long_term_debt_t,
    current_liabilities_t,
    total_assets_t,
    long_term_debt_tm1,
    current_liabilities_tm1,
    total_assets_tm1,
) -> ArrayLike:
    """Leverage Index.

    LVGI = [(LTD_t + CurrentLiabilities_t) / TotalAssets_t]
           / [(LTD_{t-1} + CurrentLiabilities_{t-1}) / TotalAssets_{t-1}].
    """
    lev_t = _ratio(
        np.asarray(long_term_debt_t, float) + np.asarray(current_liabilities_t, float),
        total_assets_t,
    )
    lev_tm1 = _ratio(
        np.asarray(long_term_debt_tm1, float) + np.asarray(current_liabilities_tm1, float),
        total_assets_tm1,
    )
    return _as_like(_ratio(lev_t, lev_tm1), total_assets_t)


def tata(income_continuing_ops_t, cash_from_operations_t, total_assets_t) -> ArrayLike:
    """Total Accruals to Total Assets.

    TATA = (Income from continuing operations_t - Cash flow from operations_t) / TotalAssets_t.
    Beneish (1999) computes accruals from balance-sheet changes; the cash-flow-statement
    definition used here is the common post-SFAS-95 substitute and is what the SEC Financial
    Statement Data Sets can support. State which definition is used in any comparison.
    """
    accruals = np.asarray(income_continuing_ops_t, float) - np.asarray(
        cash_from_operations_t, float
    )
    return _as_like(_ratio(accruals, total_assets_t), total_assets_t)


def _as_like(values, template) -> ArrayLike:
    if isinstance(template, pd.Series):
        return pd.Series(np.asarray(values, float), index=template.index)
    arr = np.asarray(values, float)
    return float(arr) if arr.ndim == 0 else arr


#: Column names expected by :func:`beneish_components` for year t; the same names with a
#: ``_lag`` suffix hold year t-1 values.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "receivables",
    "sales",
    "cogs",
    "current_assets",
    "ppe_net",
    "total_assets",
    "depreciation",
    "sga",
    "long_term_debt",
    "current_liabilities",
    "income_continuing_ops",
    "cash_from_operations",
)
LAGGED_COLUMNS: tuple[str, ...] = tuple(
    f"{c}_lag"
    for c in REQUIRED_COLUMNS
    if c not in ("income_continuing_ops", "cash_from_operations")
)


def beneish_components(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the eight component indices for a tidy firm-year frame.

    ``df`` must contain :data:`REQUIRED_COLUMNS` for year t and :data:`LAGGED_COLUMNS` for
    year t-1 (produced by ``aaer.clean`` from the SEC Financial Statement Data Sets or any
    other source mapped to this dictionary; see ``docs/data_dictionary.md``).

    Returns a frame indexed like ``df`` with columns DSRI, GMI, AQI, SGI, DEPI, SGAI, TATA, LVGI.
    """
    missing = [c for c in (*REQUIRED_COLUMNS, *LAGGED_COLUMNS) if c not in df.columns]
    if missing:
        raise ValueError(f"beneish_components: missing columns {missing}")
    d = df
    out = pd.DataFrame(index=df.index)
    out["DSRI"] = dsri(d["receivables"], d["sales"], d["receivables_lag"], d["sales_lag"])
    out["GMI"] = gmi(d["sales"], d["cogs"], d["sales_lag"], d["cogs_lag"])
    out["AQI"] = aqi(
        d["current_assets"],
        d["ppe_net"],
        d["total_assets"],
        d["current_assets_lag"],
        d["ppe_net_lag"],
        d["total_assets_lag"],
    )
    out["SGI"] = sgi(d["sales"], d["sales_lag"])
    out["DEPI"] = depi(d["depreciation"], d["ppe_net"], d["depreciation_lag"], d["ppe_net_lag"])
    out["SGAI"] = sgai(d["sga"], d["sales"], d["sga_lag"], d["sales_lag"])
    out["TATA"] = tata(d["income_continuing_ops"], d["cash_from_operations"], d["total_assets"])
    out["LVGI"] = lvgi(
        d["long_term_debt"],
        d["current_liabilities"],
        d["total_assets"],
        d["long_term_debt_lag"],
        d["current_liabilities_lag"],
        d["total_assets_lag"],
    )
    return out


def m_score(
    components: pd.DataFrame | Mapping[str, float],
    *,
    coefficients: Mapping[str, float] = BENEISH_8_COEFFICIENTS,
    intercept: float = BENEISH_8_INTERCEPT,
) -> pd.Series | float:
    """Linear combination of the component indices (see module docstring for the caveat on
    the coefficients). Accepts the frame returned by :func:`beneish_components` or a mapping
    for a single observation. ``NaN`` in any used component gives ``NaN``."""
    if isinstance(components, pd.DataFrame):
        missing = [c for c in coefficients if c not in components.columns]
        if missing:
            raise ValueError(f"m_score: missing component columns {missing}")
        score = pd.Series(float(intercept), index=components.index)
        for name, coef in coefficients.items():
            score = score + coef * components[name].astype(float)
        return score.rename("m_score")
    missing = [c for c in coefficients if c not in components]
    if missing:
        raise ValueError(f"m_score: missing components {missing}")
    return float(intercept) + float(
        sum(coef * float(components[name]) for name, coef in coefficients.items())
    )


def flag(score: pd.Series | float, threshold: float = BENEISH_FLAG_THRESHOLD) -> pd.Series | bool:
    """``score > threshold`` with ``NaN`` never flagged (returns False for NaN)."""
    if isinstance(score, pd.Series):
        return (score > threshold).fillna(False).astype(bool).rename("beneish_flag")
    return bool(score > threshold) if not np.isnan(score) else False

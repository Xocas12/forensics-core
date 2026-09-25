"""Each Beneish component is tested separately against hand-computed values on obviously
synthetic inputs. No real firm data is used anywhere here."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from aaer.features import beneish as b


def test_dsri_hand_computed():
    # (20/100) / (10/100) = 2.0
    assert b.dsri(20, 100, 10, 100) == pytest.approx(2.0)


def test_gmi_hand_computed():
    # margin_{t-1} = (100-60)/100 = 0.4 ; margin_t = (100-70)/100 = 0.3 ; GMI = 0.4/0.3
    assert b.gmi(100, 70, 100, 60) == pytest.approx(0.4 / 0.3)


def test_aqi_hand_computed():
    # t:   1 - (30+50)/100 = 0.2 ; t-1: 1 - (40+50)/100 = 0.1 ; AQI = 2.0
    assert b.aqi(30, 50, 100, 40, 50, 100) == pytest.approx(2.0)


def test_sgi_hand_computed():
    assert b.sgi(150, 100) == pytest.approx(1.5)


def test_depi_hand_computed():
    # rate_{t-1} = 10/(10+90) = 0.10 ; rate_t = 5/(5+95) = 0.05 ; DEPI = 2.0
    assert b.depi(5, 95, 10, 90) == pytest.approx(2.0)


def test_sgai_hand_computed():
    # (30/100) / (20/100) = 1.5
    assert b.sgai(30, 100, 20, 100) == pytest.approx(1.5)


def test_lvgi_hand_computed():
    # t: (40+20)/100 = 0.6 ; t-1: (20+10)/100 = 0.3 ; LVGI = 2.0
    assert b.lvgi(40, 20, 100, 20, 10, 100) == pytest.approx(2.0)


def test_tata_hand_computed():
    # (50 - 30) / 200 = 0.1
    assert b.tata(50, 30, 200) == pytest.approx(0.1)


def test_zero_denominators_give_nan_not_error():
    assert math.isnan(b.dsri(1, 0, 1, 1))
    assert math.isnan(b.sgi(1, 0))
    assert math.isnan(b.tata(1, 1, 0))


def test_m_score_neutral_firm_is_minus_2_48():
    """All indices exactly 1 and zero accruals: M = -4.84 + (0.920+0.528+0.404+0.892+0.115
    -0.172-0.327) = -4.84 + 2.36 = -2.48, below the -1.78 threshold -> not flagged.
    (Coefficients themselves are still TO CONFIRM against Beneish 1999.)"""
    comps = {k: 1.0 for k in b.COMPONENT_NAMES}
    comps["TATA"] = 0.0
    score = b.m_score(comps)
    assert score == pytest.approx(-2.48)
    assert b.flag(score) is False


def test_m_score_tata_dominates():
    comps = {k: 1.0 for k in b.COMPONENT_NAMES}
    comps["TATA"] = 0.2  # 4.679 * 0.2 = 0.9358 -> -2.48 + 0.9358 = -1.5442 > -1.78
    score = b.m_score(comps)
    assert score == pytest.approx(-2.48 + 4.679 * 0.2)
    assert b.flag(score) is True


def test_beneish_components_dataframe_roundtrip():
    df = pd.DataFrame(
        {
            "receivables": [20.0],
            "sales": [100.0],
            "cogs": [70.0],
            "current_assets": [30.0],
            "ppe_net": [50.0],
            "total_assets": [100.0],
            "depreciation": [5.0],
            "sga": [30.0],
            "long_term_debt": [40.0],
            "current_liabilities": [20.0],
            "income_continuing_ops": [50.0],
            "cash_from_operations": [30.0],
            "receivables_lag": [10.0],
            "sales_lag": [100.0],
            "cogs_lag": [60.0],
            "current_assets_lag": [40.0],
            "ppe_net_lag": [50.0],
            "total_assets_lag": [100.0],
            "depreciation_lag": [10.0],
            "sga_lag": [20.0],
            "long_term_debt_lag": [20.0],
            "current_liabilities_lag": [10.0],
        },
        index=["SYNTHETIC-FIRM-0001:2000"],
    )
    comps = b.beneish_components(df)
    assert list(comps.columns) == list(b.COMPONENT_NAMES)
    row = comps.iloc[0]
    assert row["DSRI"] == pytest.approx(2.0)
    assert row["GMI"] == pytest.approx(0.4 / 0.3)
    assert row["AQI"] == pytest.approx(2.0)
    assert row["SGI"] == pytest.approx(1.0)
    # depreciation: rate_{t-1} = 10/60 ; rate_t = 5/55 -> DEPI = (10/60)/(5/55)
    assert row["DEPI"] == pytest.approx((10 / 60) / (5 / 55))
    assert row["SGAI"] == pytest.approx(1.5)
    assert row["TATA"] == pytest.approx(0.2)
    assert row["LVGI"] == pytest.approx(2.0)
    score = b.m_score(comps)
    expected = (
        -4.84
        + 0.920 * 2.0
        + 0.528 * (0.4 / 0.3)
        + 0.404 * 2.0
        + 0.892 * 1.0
        + 0.115 * ((10 / 60) / (5 / 55))
        - 0.172 * 1.5
        + 4.679 * 0.2
        - 0.327 * 2.0
    )
    assert score.iloc[0] == pytest.approx(expected)
    assert bool(b.flag(score).iloc[0]) is (expected > -1.78)


def test_beneish_components_missing_column_raises():
    with pytest.raises(ValueError, match="missing columns"):
        b.beneish_components(pd.DataFrame({"sales": [1.0]}))


def test_flag_nan_is_false():
    s = pd.Series([np.nan, -1.0, -3.0])
    f = b.flag(s)
    assert f.tolist() == [False, True, False]

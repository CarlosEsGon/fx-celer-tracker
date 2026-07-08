"""End-to-end analytics: Trade + mid + rates + USD DFs -> TradeAnalysis."""

from datetime import date

import pytest

from core.analyzer import analyze_trade

DF_NEAR = 0.9995
DF_FAR = 0.9884


def test_swap_analysis_complete(swap_trade, eurusd_mid, fx_rates):
    a = analyze_trade(swap_trade, eurusd_mid, fx_rates, DF_NEAR, DF_FAR)

    assert a.trade_id == swap_trade.trade_id
    assert a.tenor_label == "3M"
    assert a.tenor_days == 92
    assert a.spot_exposure_base == 1_000_000
    assert a.spot_exposure_usd == pytest.approx(1_165_000)
    assert a.pv_near_leg_usd == pytest.approx(1_165_000 * DF_NEAR)
    assert a.pv_far_leg_usd == pytest.approx(1_168_000 * DF_FAR)
    assert a.combined_risk_usd == pytest.approx(a.pv_near_leg_usd + a.pv_far_leg_usd)
    assert a.inception_pnl_usd != 0
    assert a.notional_mismatch_base == 0
    assert a.mid_fallback is False
    assert a.near_value_date == date(2026, 7, 7)
    assert a.far_value_date == date(2026, 10, 7)
    assert a.bbg_forward_mid == eurusd_mid.forward_mid


def test_outright_analysis_complete(outright_trade, gbpusd_mid, fx_rates):
    a = analyze_trade(outright_trade, gbpusd_mid, fx_rates, DF_FAR, DF_FAR)

    assert a.product_type == "FX_OUTRIGHT"
    assert a.spot_exposure_base == -500_000          # single leg IS spot exposure
    assert a.spot_exposure_usd == pytest.approx(-635_000)
    assert a.tenor_days == 94
    assert a.tenor_label == "3M"
    assert a.near_value_date == date(2026, 10, 7)
    assert a.far_value_date == date(2026, 10, 7)
    # sold at 1.2700 vs mid 1.2713 -> negative inception PnL
    assert a.inception_pnl_usd < 0


def test_discount_factors_scale_leg_pvs(swap_trade, eurusd_mid, fx_rates):
    full = analyze_trade(swap_trade, eurusd_mid, fx_rates, 1.0, 1.0)
    half = analyze_trade(swap_trade, eurusd_mid, fx_rates, 0.5, 0.5)
    assert half.pv_near_leg_usd == pytest.approx(full.pv_near_leg_usd * 0.5)
    assert half.pv_far_leg_usd == pytest.approx(full.pv_far_leg_usd * 0.5)
    # spot exposure is a notional metric — never discounted
    assert half.spot_exposure_usd == pytest.approx(full.spot_exposure_usd)


def test_valuation_date_only_affects_tenor(outright_trade, gbpusd_mid, fx_rates):
    # Outright tenor runs valuation date -> leg value date (swaps: near -> far)
    a_trade_date = analyze_trade(outright_trade, gbpusd_mid, fx_rates, DF_FAR, DF_FAR)
    a_spot = analyze_trade(
        outright_trade, gbpusd_mid, fx_rates, DF_FAR, DF_FAR,
        valuation_date=date(2026, 7, 7),
    )
    assert a_spot.tenor_days == a_trade_date.tenor_days - 2
    # DFs come from the curve source, so PVs are unchanged for the same DFs
    assert a_spot.pv_far_leg_usd == pytest.approx(a_trade_date.pv_far_leg_usd)


def test_mid_fallback_propagates(swap_trade, eurusd_mid, fx_rates):
    fb = eurusd_mid.model_copy(update={"fallback": True})
    a = analyze_trade(swap_trade, fb, fx_rates, DF_NEAR, DF_FAR)
    assert a.mid_fallback is True

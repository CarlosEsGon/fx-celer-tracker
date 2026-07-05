"""End-to-end analytics: Trade + mid + rates -> TradeAnalysis."""

from datetime import date

import pytest

from core.analyzer import analyze_trade


def test_swap_analysis_complete(swap_trade, eurusd_mid, fx_rates):
    a = analyze_trade(swap_trade, eurusd_mid, fx_rates, quote_ccy_rate=0.045)

    assert a.trade_id == swap_trade.trade_id
    assert a.tenor_label == "3M"
    assert a.tenor_days == 92
    assert a.spot_exposure_base == 1_000_000
    assert a.spot_exposure_usd == pytest.approx(1_165_000)
    assert a.npv_far_leg_quote == pytest.approx(1_168_000 / (1 + 0.045 * 94 / 360))
    assert a.combined_risk_usd == pytest.approx(a.spot_exposure_usd + a.npv_far_leg_usd)
    assert a.inception_pnl_usd != 0
    assert a.notional_mismatch_base == 0
    assert a.mid_fallback is False
    assert a.near_value_date == date(2026, 7, 7)
    assert a.far_value_date == date(2026, 10, 7)
    assert a.bbg_forward_mid == eurusd_mid.forward_mid


def test_outright_analysis_complete(outright_trade, gbpusd_mid, fx_rates):
    a = analyze_trade(outright_trade, gbpusd_mid, fx_rates, quote_ccy_rate=0.045)

    assert a.product_type == "FX_OUTRIGHT"
    assert a.spot_exposure_base == -500_000          # single leg IS spot exposure
    assert a.spot_exposure_usd == pytest.approx(-635_000)
    assert a.tenor_days == 94
    assert a.tenor_label == "3M"
    assert a.near_value_date == date(2026, 10, 7)
    assert a.far_value_date == date(2026, 10, 7)
    # sold at 1.2700 vs mid 1.2713 -> negative inception PnL
    assert a.inception_pnl_usd < 0


def test_valuation_date_override(swap_trade, eurusd_mid, fx_rates):
    a_trade_date = analyze_trade(swap_trade, eurusd_mid, fx_rates, 0.045)
    a_spot = analyze_trade(
        swap_trade, eurusd_mid, fx_rates, 0.045, valuation_date=date(2026, 7, 7)
    )
    # Two fewer discounting days -> smaller DF effect -> larger NPV magnitude
    assert abs(a_spot.npv_far_leg_quote) > abs(a_trade_date.npv_far_leg_quote)


def test_mid_fallback_propagates(swap_trade, eurusd_mid, fx_rates):
    fb = eurusd_mid.model_copy(update={"fallback": True})
    a = analyze_trade(swap_trade, fb, fx_rates, 0.045)
    assert a.mid_fallback is True

"""histTrades parser tests. FORWARD_REC/SWAP_REC carry the same trade economics
as the conftest fixtures (GBP/USD outright, EUR/USD swap), reframed as raw
/histTrades payloads: a GBP/USD forward dealt in USD (terms) and a EUR/USD T/N
swap dealt in EUR (base).
"""

from datetime import date, datetime, timezone

import pytest

from core.hist_trades import (
    parse_date_opt,
    parse_m0_age_ms,
    parse_record,
    parse_reference_rate,
    parse_scaled,
)
from core.models import ProductType

FORWARD_REC = {
    "id": "sid_1000000000000000001",
    "orderId": "1000000000000000002",
    "sourceExecutionId": "1000000000000000001",
    "quoteId": "1000000000000000003",
    "external_qid": "123456789",
    "trader": "SYSTEM_USER",
    "account": "ACCOUNT_A",
    "portfolio": "BOOK_A",
    "time": "2026-07-06T09:26:46.307Z",
    "productType": "FORWARD",
    "securityId": "GBP/USD",
    "base": "GBP",
    "currency": "USD",
    "orderType": "PREVIOUSLY_QUOTED",
    "executionMethod": "RFQ",
    "merchantOrderType": "",
    "clob_type": "",
    "ignore": "N",
    "trade_side": "SELL",
    "near_leg_side": "SELL",
    "far_leg_side": "",
    "expectedSide": "SELL",
    "near_leg_spot": 1269000,
    "near_leg_points": 1000,
    "near_leg_price": 1270000,
    "far_leg_spot": "NaN",
    "far_leg_points": "NaN",
    "far_leg_price": "NaN",
    "trade_price": 1269000,
    "mid_0": 1268995,
    "est_trader_price": 1269195,
    "trader_price": "NaN",
    "u1_mid": "NaN",
    "u2_mid": "NaN",
    "reference_rates": "GBP/USD:1.268995",
    "priceSource": "",
    "commission": 0,
    "near_leg_qty": 635000000000,
    "far_leg_qty": "NaN",
    "parent_order_qty": 635000000000,
    "swap_qty": "NaN",
    "spot_base_qty": -500394011000,
    "spot_terms_qty": 635000000000,
    "new_terms_qty": 635000000000,
    "near_leg_settlementDate": "2026-10-07",
    "far_leg_settlementDate": "-999999999-01-01",
    "near_leg_tenor": "B",
    "far_leg_tenor": "",
    "m0_time": "2026-07-06T09:26:45.795Z",
    "m0_age": {"j": 512000000},
    "destinationKey": "DEST_KEY_1",
    "stream_code": "STREAM_A",
    "orderText": "",
    "u1": "",
    "u2": "",
}

SWAP_REC = {
    "id": "sid_2000000000000000001",
    "orderId": "2000000000000000002",
    "sourceExecutionId": "2000000000000000001",
    "quoteId": "2000000000000000003",
    "external_qid": "00000000-0000-0000-0000-000000000000",
    "trader": "firstname.lastname",
    "account": "ACCOUNT_B",
    "portfolio": "BOOK_A",
    "time": "2026-07-06T10:15:02.100Z",
    "productType": "SWAP",
    "securityId": "EUR/USD",
    "base": "EUR",
    "currency": "EUR",
    "orderType": "LIMIT",
    "executionMethod": "RFQ",
    "merchantOrderType": "",
    "clob_type": "",
    "ignore": "IS_SWAP",
    "trade_side": "SELL",
    "near_leg_side": "BUY",
    "far_leg_side": "SELL",
    "expectedSide": "SELL",
    "near_leg_spot": 1164991,
    "near_leg_points": 9,
    "near_leg_price": 1165000,
    "far_leg_spot": 1164991,
    "far_leg_points": 3009,
    "far_leg_price": 1168000,
    "trade_price": 1164991,
    "mid_0": 1164971,
    "est_trader_price": 1165171,
    "trader_price": "NaN",
    "u1_mid": "NaN",
    "u2_mid": "NaN",
    "reference_rates": "EUR/USD:1.164991",
    "priceSource": "",
    "commission": 0,
    "near_leg_qty": 1000000000000,
    "far_leg_qty": 1000000000000,
    "parent_order_qty": 1000000000000,
    "swap_qty": 0,
    "spot_base_qty": 0,
    "spot_terms_qty": 0,
    "new_terms_qty": 0,
    "near_leg_settlementDate": "2026-07-07",
    "far_leg_settlementDate": "2026-07-08",
    "near_leg_tenor": "B",
    "far_leg_tenor": "B",
    "m0_time": "2026-07-06T10:20:01.000Z",
    "m0_age": {"j": 467000000},
    "destinationKey": "MOCK_BANK",
    "stream_code": "STREAM_B",
    "orderText": "",
    "u1": "",
    "u2": "",
}


# ---- primitives -------------------------------------------------------------


def test_parse_scaled():
    assert parse_scaled(1333810) == pytest.approx(1.333810)
    assert parse_scaled(825) == pytest.approx(0.000825)
    assert parse_scaled(761000000000) == pytest.approx(761_000)
    assert parse_scaled("NaN") is None
    assert parse_scaled(None) is None
    assert parse_scaled(0) == 0.0


def test_parse_date_sentinel():
    assert parse_date_opt("-999999999-01-01") is None
    assert parse_date_opt("") is None
    assert parse_date_opt("2027-07-21") == date(2027, 7, 21)


def test_parse_reference_rate():
    pair, rate = parse_reference_rate("GBP/USD:1.3337949999999998")
    assert pair == "GBP/USD"
    assert rate == pytest.approx(1.333795)


def test_parse_m0_age():
    assert parse_m0_age_ms({"j": 512000000}) == pytest.approx(512.0)
    assert parse_m0_age_ms({}) is None
    assert parse_m0_age_ms(None) is None


# ---- FORWARD (dealt in terms currency) ----------------------------------------


def test_forward_maps_to_outright():
    parsed = parse_record(FORWARD_REC)
    assert parsed is not None
    t = parsed.trade
    assert t.product_type == ProductType.FX_OUTRIGHT
    assert t.trade_id == "sid_1000000000000000001"
    assert t.currency_pair == "GBP/USD"
    assert t.booked_at == datetime(2026, 7, 6, 9, 26, 46, 307000, tzinfo=timezone.utc)
    assert t.leg.value_date == date(2026, 10, 7)
    assert t.leg.rate == pytest.approx(1.270000)


def test_forward_base_notional_derived_via_all_in_rate():
    """Dealt 635,000 USD (terms) SELL: base = -635000/1.270 = -500,000 GBP.
    NOT spot_base_qty (-500,394), which is the spot-rate decomposition."""
    t = parse_record(FORWARD_REC).trade
    assert t.leg.base_amount == pytest.approx(-500_000, abs=0.5)
    assert t.leg.base_amount != pytest.approx(-500_394.0, abs=1.0)
    # sold GBP -> receive USD
    assert t.leg.quote_amount == pytest.approx(635_000, abs=0.01)


def test_forward_no_validation_warnings():
    parsed = parse_record(FORWARD_REC)
    assert parsed.warnings == []


def test_forward_extras_preserved():
    t = parse_record(FORWARD_REC).trade
    assert t.extras["ignore"] == "N"
    assert t.extras["orderId"] == "1000000000000000002"  # string, not float
    assert t.extras["spot_base_qty"] == -500394011000


# ---- SWAP (dealt in base currency) ----------------------------------------------


def test_swap_maps_with_both_legs():
    parsed = parse_record(SWAP_REC)
    assert parsed is not None
    t = parsed.trade
    assert t.product_type == ProductType.FX_SWAP
    assert t.near_leg.value_date == date(2026, 7, 7)
    assert t.far_leg.value_date == date(2026, 7, 8)
    assert t.near_leg.rate == pytest.approx(1.165000)
    assert t.far_leg.rate == pytest.approx(1.168000)


def test_swap_dealt_in_base_signed_amounts():
    """Dealt 1,000,000 EUR (base). Near BUY -> +1m; far SELL -> -1m."""
    t = parse_record(SWAP_REC).trade
    assert t.near_leg.base_amount == pytest.approx(1_000_000)
    assert t.far_leg.base_amount == pytest.approx(-1_000_000)
    assert t.near_leg.quote_amount == pytest.approx(-1_000_000 * 1.165000)
    assert t.far_leg.quote_amount == pytest.approx(1_000_000 * 1.168000)


def test_swap_ignores_swap_qty_zero():
    """swap_qty is 0 on a genuine 1m swap — must not be used for sizing."""
    t = parse_record(SWAP_REC).trade
    assert abs(t.near_leg.base_amount) == pytest.approx(1_000_000)


def test_swap_no_validation_warnings():
    assert parse_record(SWAP_REC).warnings == []


# ---- validation + robustness ---------------------------------------------------


def test_unknown_product_type_skipped():
    bad = dict(FORWARD_REC, productType="NDF")
    assert parse_record(bad) is None


def test_swap_same_sides_warns():
    bad = dict(SWAP_REC, far_leg_side="BUY")
    parsed = parse_record(bad)
    assert any("same side" in w for w in parsed.warnings)


def test_price_reconciliation_warning():
    bad = dict(FORWARD_REC, near_leg_price=1999999)
    parsed = parse_record(bad)
    assert any("spot+points" in w for w in parsed.warnings)


def test_missing_near_essentials_skipped():
    bad = dict(FORWARD_REC, near_leg_qty="NaN")
    assert parse_record(bad) is None


def test_spot_skipped_as_not_relevant():
    spot = dict(FORWARD_REC, productType="SPOT")
    assert parse_record(spot) is None


def test_cad_base_pair_skipped():
    cad = dict(FORWARD_REC, securityId="CAD/USD", base="CAD")
    assert parse_record(cad) is None


def test_cad_terms_pair_skipped():
    cad = dict(FORWARD_REC, securityId="USD/CAD", base="USD", currency="CAD")
    assert parse_record(cad) is None


def test_non_cad_pair_not_skipped():
    assert parse_record(FORWARD_REC) is not None


def test_counterparty_from_destination_key():
    assert parse_record(FORWARD_REC).trade.counterparty == "DEST_KEY_1"


# ---- end-to-end with analytics ---------------------------------------------------


def test_parsed_swap_flows_through_analyzer(fx_rates):
    from core.analyzer import analyze_trade
    from core.models import MidSnapshot

    t = parse_record(SWAP_REC).trade
    mid = MidSnapshot(
        pair="EUR/USD",
        value_date=t.far_leg.value_date,
        spot_mid=1.164800,
        swap_points_mid=0.05,
        forward_mid=1.164900,
        as_of=t.booked_at,
    )
    a = analyze_trade(t, mid, fx_rates, 1.0, 0.9999)
    assert a.tenor_days == 1          # T/N: one day between legs
    assert a.spot_exposure_base == pytest.approx(1_000_000)
    assert a.spot_exposure_usd == pytest.approx(1_000_000 * 1.1650)
    assert a.inception_pnl_usd != 0


# ---- EUR/CHF non-USD cross, 1,000,000 EUR notional -----------------------------
#
# Adapted from the documented /histTrades SWAP example for a cross (neither leg
# USD): securityId EUR/CHF, base EUR, currency CHF, triangulated via
# u1=EUR/USD / u2=USD/CHF. Notional scaled down from the doc's 280m to 1m EUR
# to make the economics easy to check by hand.

EURCHF_SWAP_REC = {
    "id": "sid_3000000000000000001",
    "orderId": "3000000000000000002",
    "sourceExecutionId": "3000000000000000001",
    "quoteId": "3000000000000000003",
    "external_qid": "6d5428ad-5ae4-4ee7-9644-8ba6f34cb28d",
    "trader": "SYSTEM_USER",
    "account": "GEFL",
    "portfolio": "EBOOK",
    "time": "2026-07-07T09:50:18.024Z",
    "productType": "SWAP",
    "securityId": "EUR/CHF",
    "base": "EUR",
    "currency": "CHF",
    "orderType": "PREVIOUSLY_QUOTED",
    "executionMethod": "RFQ",
    "merchantOrderType": "",
    "clob_type": "",
    "ignore": "IS_SWAP",
    "trade_side": "SELL",
    "near_leg_side": "SELL",
    "far_leg_side": "BUY",
    "expectedSide": "SELL",
    "near_leg_spot": 922060,
    "near_leg_points": 148,
    "near_leg_price": 922208,
    "far_leg_spot": 922060,
    "far_leg_points": -241,
    "far_leg_price": 921818,
    "trade_price": 922060,
    "mid_0": 921975,
    "est_trader_price": 922175,
    "trader_price": "NaN",
    "u1": "EUR/USD",
    "u2": "USD/CHF",
    "u1_mid": 1142555,
    "u2_mid": 806940,
    "reference_rates": "USD/CHF:0.806945",
    "priceSource": "",
    "commission": 0,
    "near_leg_qty": 1_000_000_000_000,
    "far_leg_qty": 1_000_000_000_000,
    "parent_order_qty": 1_000_000_000_000,
    "swap_qty": 0,
    "spot_base_qty": 0,
    "spot_terms_qty": 0,
    "new_terms_qty": 0,
    "near_leg_settlementDate": "2026-07-07",
    "far_leg_settlementDate": "2026-07-13",
    "near_leg_tenor": "TOD",
    "far_leg_tenor": "B",
    "m0_time": "2026-07-07T09:50:17.715Z",
    "m0_age": {"j": 309000000},
    "destinationKey": "PE_BNS",
    "stream_code": "BNS_NSP_AI",
    "orderText": "",
}


def test_eurchf_cross_not_skipped():
    """EUR/CHF has no CAD leg and isn't SPOT, so it must survive the new filters."""
    assert parse_record(EURCHF_SWAP_REC) is not None


def test_eurchf_cross_maps_with_both_legs():
    t = parse_record(EURCHF_SWAP_REC).trade
    assert t.product_type == ProductType.FX_SWAP
    assert t.currency_pair == "EUR/CHF"
    assert t.base_currency == "EUR"
    assert t.quote_currency == "CHF"
    assert t.near_leg.rate == pytest.approx(0.922208)
    assert t.far_leg.rate == pytest.approx(0.921818)


def test_eurchf_cross_dealt_currency_is_terms_not_base():
    """`currency` is CHF (terms) here, not EUR (base) — confirms the parser's
    "never assume base" rule (module docstring) actually engages for a cross:
    base_amount is derived by dividing the CHF qty by the all-in rate, NOT by
    treating the raw 1,000,000 qty as already being the EUR notional."""
    t = parse_record(EURCHF_SWAP_REC).trade
    # dealt_ccy (CHF) != base_ccy (EUR) -> base = qty / rate, then signed for SELL
    expected_near_base = -1_000_000 / 0.922208
    assert t.near_leg.base_amount == pytest.approx(expected_near_base, rel=1e-6)
    assert t.near_leg.base_amount != pytest.approx(-1_000_000, abs=1.0)


def test_eurchf_cross_flows_through_analyzer(fx_rates):
    """USD exposure triangulates EUR->USD and CHF->USD independently, per
    core/fx.py's design — no direct EUR/CHF rate is looked up."""
    from core.analyzer import analyze_trade
    from core.models import MidSnapshot

    t = parse_record(EURCHF_SWAP_REC).trade
    mid = MidSnapshot(
        pair="EUR/CHF",
        value_date=t.far_leg.value_date,
        spot_mid=0.922060,
        swap_points_mid=-0.000389,
        forward_mid=0.921671,
        as_of=t.booked_at,
    )
    a = analyze_trade(t, mid, fx_rates, 1.0, 0.9992)
    assert a.tenor_days == 6  # 2026-07-07 -> 2026-07-13
    assert a.inception_pnl_usd != 0

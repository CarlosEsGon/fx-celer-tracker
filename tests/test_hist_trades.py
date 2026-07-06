"""histTrades parser tests, built from the two verified real payloads:
a GBP/USD forward dealt in USD (terms) and an AUD/USD T/N swap dealt in AUD (base).
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
    "near_leg_spot": 1333810,
    "near_leg_points": 825,
    "near_leg_price": 1334635,
    "far_leg_spot": "NaN",
    "far_leg_points": "NaN",
    "far_leg_price": "NaN",
    "trade_price": 1333810,
    "mid_0": 1333805,
    "est_trader_price": 1334005,
    "trader_price": "NaN",
    "u1_mid": "NaN",
    "u2_mid": "NaN",
    "reference_rates": "GBP/USD:1.3337949999999998",
    "priceSource": "",
    "commission": 0,
    "near_leg_qty": 761000000000,
    "far_leg_qty": "NaN",
    "parent_order_qty": 761000000000,
    "swap_qty": "NaN",
    "spot_base_qty": -570546029794,
    "spot_terms_qty": 761000000000,
    "new_terms_qty": 761000000000,
    "near_leg_settlementDate": "2027-07-21",
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
    "securityId": "AUD/USD",
    "base": "AUD",
    "currency": "AUD",
    "orderType": "LIMIT",
    "executionMethod": "RFQ",
    "merchantOrderType": "",
    "clob_type": "",
    "ignore": "IS_SWAP",
    "trade_side": "SELL",
    "near_leg_side": "BUY",
    "far_leg_side": "SELL",
    "expectedSide": "SELL",
    "near_leg_spot": 693150,
    "near_leg_points": 9,
    "near_leg_price": 693159,
    "far_leg_spot": 693150,
    "far_leg_points": 0,
    "far_leg_price": 693150,
    "trade_price": 693150,
    "mid_0": 693130,
    "est_trader_price": 693330,
    "trader_price": "NaN",
    "u1_mid": "NaN",
    "u2_mid": "NaN",
    "reference_rates": "AUD/USD:0.6931350000000001",
    "priceSource": "",
    "commission": 0,
    "near_leg_qty": 8000000000000,
    "far_leg_qty": 8000000000000,
    "parent_order_qty": 8000000000000,
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
    "destinationKey": "DEST_KEY_2",
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
    assert t.leg.value_date == date(2027, 7, 21)
    assert t.leg.rate == pytest.approx(1.334635)


def test_forward_base_notional_derived_via_all_in_rate():
    """Dealt 761,000 USD (terms) SELL: base = -761000/1.334635 = -570,193 GBP.
    NOT spot_base_qty (-570,546), which is the spot-rate decomposition."""
    t = parse_record(FORWARD_REC).trade
    assert t.leg.base_amount == pytest.approx(-570_193.3, abs=0.5)
    assert t.leg.base_amount != pytest.approx(-570_546.0, abs=1.0)
    # sold GBP -> receive USD
    assert t.leg.quote_amount == pytest.approx(761_000, abs=0.01)


def test_forward_no_validation_warnings():
    parsed = parse_record(FORWARD_REC)
    assert parsed.warnings == []


def test_forward_extras_preserved():
    t = parse_record(FORWARD_REC).trade
    assert t.extras["ignore"] == "N"
    assert t.extras["orderId"] == "1000000000000000002"  # string, not float
    assert t.extras["spot_base_qty"] == -570546029794


# ---- SWAP (dealt in base currency) ----------------------------------------------


def test_swap_maps_with_both_legs():
    parsed = parse_record(SWAP_REC)
    assert parsed is not None
    t = parsed.trade
    assert t.product_type == ProductType.FX_SWAP
    assert t.near_leg.value_date == date(2026, 7, 7)
    assert t.far_leg.value_date == date(2026, 7, 8)
    assert t.near_leg.rate == pytest.approx(0.693159)
    assert t.far_leg.rate == pytest.approx(0.693150)


def test_swap_dealt_in_base_signed_amounts():
    """Dealt 8,000,000 AUD (base). Near BUY -> +8m; far SELL -> -8m."""
    t = parse_record(SWAP_REC).trade
    assert t.near_leg.base_amount == pytest.approx(8_000_000)
    assert t.far_leg.base_amount == pytest.approx(-8_000_000)
    assert t.near_leg.quote_amount == pytest.approx(-8_000_000 * 0.693159)
    assert t.far_leg.quote_amount == pytest.approx(8_000_000 * 0.693150)


def test_swap_ignores_swap_qty_zero():
    """swap_qty is 0 on a genuine 8m swap — must not be used for sizing."""
    t = parse_record(SWAP_REC).trade
    assert abs(t.near_leg.base_amount) == pytest.approx(8_000_000)


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


def test_spot_treated_as_outright():
    spot = dict(
        FORWARD_REC,
        productType="SPOT",
        near_leg_points=0,
        near_leg_price=1333810,
        near_leg_settlementDate="2026-07-08",
        spot_base_qty=-570546029794,
        new_terms_qty=761000000000,
    )
    parsed = parse_record(spot)
    assert parsed.trade.product_type == ProductType.FX_OUTRIGHT
    assert parsed.trade.leg.rate == pytest.approx(1.333810)


def test_counterparty_from_destination_key():
    assert parse_record(FORWARD_REC).trade.counterparty == "DEST_KEY_1"


# ---- end-to-end with analytics ---------------------------------------------------


def test_parsed_swap_flows_through_analyzer(fx_rates):
    from core.analyzer import analyze_trade
    from core.models import MidSnapshot

    t = parse_record(SWAP_REC).trade
    mid = MidSnapshot(
        pair="AUD/USD",
        value_date=t.far_leg.value_date,
        spot_mid=0.693135,
        swap_points_mid=0.05,
        forward_mid=0.693140,
        as_of=t.booked_at,
    )
    a = analyze_trade(t, mid, fx_rates, quote_ccy_rate=0.045)
    assert a.tenor_days == 1          # T/N: one day between legs
    assert a.spot_exposure_base == pytest.approx(8_000_000)
    assert a.spot_exposure_usd == pytest.approx(8_000_000 * 0.66)
    assert a.inception_pnl_usd != 0

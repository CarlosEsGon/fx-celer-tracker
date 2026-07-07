from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from core.models import Leg, MidSnapshot, ProductType, Trade


@pytest.fixture
def fx_rates() -> dict[str, float]:
    return {
        "EURUSD": 1.1650,
        "GBPUSD": 1.2700,
        "USDJPY": 145.00,
        "AUDUSD": 0.6600,
        "USDCHF": 0.8070,
    }


@pytest.fixture
def swap_trade() -> Trade:
    """Matched EUR/USD buy-sell swap, 2026-07-07 -> 2026-10-07 (92 days, 3M)."""
    return Trade(
        trade_id="FXS-TEST-001",
        product_type=ProductType.FX_SWAP,
        currency_pair="EUR/USD",
        base_currency="EUR",
        quote_currency="USD",
        trade_date=date(2026, 7, 5),
        near_leg=Leg(
            value_date=date(2026, 7, 7),
            base_amount=1_000_000,
            quote_amount=-1_165_000,
            rate=1.1650,
        ),
        far_leg=Leg(
            value_date=date(2026, 10, 7),
            base_amount=-1_000_000,
            quote_amount=1_168_000,
            rate=1.1680,
        ),
        counterparty="MOCK_BANK",
        booked_at=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
    )


@pytest.fixture
def outright_trade() -> Trade:
    """GBP/USD sell 500k forward to 2026-10-07."""
    return Trade(
        trade_id="FXO-TEST-001",
        product_type=ProductType.FX_OUTRIGHT,
        currency_pair="GBP/USD",
        base_currency="GBP",
        quote_currency="USD",
        trade_date=date(2026, 7, 5),
        leg=Leg(
            value_date=date(2026, 10, 7),
            base_amount=-500_000,
            quote_amount=635_000,
            rate=1.2700,
        ),
        counterparty="MOCK_BANK",
        booked_at=datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def eurusd_mid() -> MidSnapshot:
    return MidSnapshot(
        pair="EUR/USD",
        value_date=date(2026, 10, 7),
        spot_mid=1.1648,
        swap_points_mid=28.5,
        forward_mid=1.16765,
        as_of=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
    )


@pytest.fixture
def gbpusd_mid() -> MidSnapshot:
    return MidSnapshot(
        pair="GBP/USD",
        value_date=date(2026, 10, 7),
        spot_mid=1.2698,
        swap_points_mid=15.0,
        forward_mid=1.2713,
        as_of=datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc),
    )

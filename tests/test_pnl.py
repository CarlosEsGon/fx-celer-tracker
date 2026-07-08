from datetime import date

import pytest

from core.models import Leg
from core.pnl import inception_pnl, inception_pnl_quote


def test_swap_pnl_on_points(swap_trade, eurusd_mid):
    # traded points 1.1680-1.1650=0.0030 ; mid points 1.16765-1.1648=0.00285
    # far leg sells base -> direction +1
    expected = (0.0030 - 0.00285) * 1_000_000
    assert inception_pnl_quote(swap_trade, eurusd_mid) == pytest.approx(expected)


def test_swap_pnl_direction_flips(swap_trade, eurusd_mid):
    flipped = swap_trade.model_copy(deep=True)
    flipped.near_leg.base_amount *= -1
    flipped.near_leg.quote_amount *= -1
    flipped.far_leg.base_amount *= -1
    flipped.far_leg.quote_amount *= -1
    expected = -(0.0030 - 0.00285) * 1_000_000
    assert inception_pnl_quote(flipped, eurusd_mid) == pytest.approx(expected)


def test_outright_pnl_vs_forward_mid(outright_trade, gbpusd_mid):
    # sold 500k GBP at 1.2700, mid forward 1.2713:
    # (mid - traded) * base = (1.2713-1.2700) * -500000 = -650 USD
    assert inception_pnl_quote(outright_trade, gbpusd_mid) == pytest.approx(-650.0)


def test_outright_pnl_positive_when_sold_above_mid(outright_trade, gbpusd_mid):
    better = outright_trade.model_copy(deep=True)
    better.leg = Leg(
        value_date=date(2026, 10, 7),
        base_amount=-500_000,
        quote_amount=636_500,
        rate=1.2730,
    )
    # sold above mid -> profit: (1.2713-1.2730)*-500000 = +850
    assert inception_pnl_quote(better, gbpusd_mid) == pytest.approx(850.0)


def test_uneven_swap_priced_leg_by_leg(swap_trade, eurusd_mid):
    uneven = swap_trade.model_copy(deep=True)
    uneven.far_leg = Leg(
        value_date=date(2026, 10, 7),
        base_amount=-800_000,
        quote_amount=934_400,
        rate=1.1680,
    )
    near_pnl = (1.1648 - 1.1650) * 1_000_000
    far_pnl = (1.16765 - 1.1680) * -800_000
    assert inception_pnl_quote(uneven, eurusd_mid) == pytest.approx(near_pnl + far_pnl)


def test_uneven_reduces_to_points_when_matched(swap_trade, eurusd_mid):
    near_pnl = (1.1648 - 1.1650) * 1_000_000
    far_pnl = (1.16765 - 1.1680) * -1_000_000
    points = inception_pnl_quote(swap_trade, eurusd_mid)
    assert points == pytest.approx(near_pnl + far_pnl)


def test_full_pnl_converts_then_discounts(swap_trade, eurusd_mid, fx_rates):
    raw = inception_pnl_quote(swap_trade, eurusd_mid)
    df_far = 0.9884
    pnl_quote, pnl_usd = inception_pnl(swap_trade, eurusd_mid, df_far, fx_rates)
    assert pnl_quote == pytest.approx(raw)          # quote figure undiscounted
    assert pnl_usd == pytest.approx(raw * df_far)   # quote ccy is USD

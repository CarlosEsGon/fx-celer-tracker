"""Inception PnL vs the Bloomberg mid at execution time.

FX_OUTRIGHT:
    pnl_quote = (leg.rate - forward_mid) * leg.base_amount
    (signed base amount carries direction)

FX_SWAP, matched notionals — valued on swap points:
    traded_points = far.rate - near.rate         (rate terms)
    mid_points    = forward_mid - spot_mid
    pnl_quote     = (traded_points - mid_points) * |far.base_amount| * direction
    direction: +1 if the far leg sells base (buy-sell benefits from wider points)

FX_SWAP, uneven notionals — priced leg by leg:
    near leg vs spot mid, far leg vs forward mid, sum of the two.
    Reduces to the points formula when notionals match.

All results are discounted to the valuation date with the ACT/360 DF and
converted to USD.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

from core.discount import discount_factor
from core.fx import convert_to_usd
from core.models import MidSnapshot, ProductType, Trade

_EPS = 1e-9


def _swap_pnl_quote(trade: Trade, mid: MidSnapshot) -> float:
    near, far = trade.near_leg, trade.far_leg
    if abs(abs(near.base_amount) - abs(far.base_amount)) > _EPS:
        # Uneven swap: value each leg against its own mid.
        # A leg buying base at `rate` when mid is `m` is worth (m - rate) * base
        # in quote terms; signs fall out of the signed base amounts.
        near_pnl = (mid.spot_mid - near.rate) * near.base_amount
        far_pnl = (mid.forward_mid - far.rate) * far.base_amount
        return near_pnl + far_pnl

    traded_points = far.rate - near.rate
    mid_points = mid.forward_mid - mid.spot_mid
    direction = 1.0 if far.base_amount < 0 else -1.0
    return (traded_points - mid_points) * abs(far.base_amount) * direction


def _outright_pnl_quote(trade: Trade, mid: MidSnapshot) -> float:
    leg = trade.leg
    # Bought base at leg.rate when mid forward is mid.forward_mid:
    # worth (mid - traded) per unit of base bought.
    return (mid.forward_mid - leg.rate) * leg.base_amount


def inception_pnl_quote(trade: Trade, mid: MidSnapshot) -> float:
    if trade.product_type == ProductType.FX_SWAP:
        return _swap_pnl_quote(trade, mid)
    return _outright_pnl_quote(trade, mid)


def inception_pnl(
    trade: Trade,
    mid: MidSnapshot,
    valuation_date: date,
    quote_ccy_rate: float,
    fx_rates: Mapping[str, float],
) -> tuple[float, float]:
    """Returns (pnl_quote_pv, pnl_usd), discounted to valuation_date."""
    raw = inception_pnl_quote(trade, mid)
    df = discount_factor(valuation_date, trade.discounted_leg.value_date, quote_ccy_rate)
    pnl_quote_pv = raw * df
    pnl_usd = convert_to_usd(pnl_quote_pv, trade.quote_currency, fx_rates)
    return pnl_quote_pv, pnl_usd

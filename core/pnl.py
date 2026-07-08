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

The USD result is converted from quote currency first, then discounted with
the USD discount factor for the discounted leg's value date (USD approach —
same convention as the leg PVs in core/exposure.py).
"""

from __future__ import annotations

from typing import Mapping

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
    df_far: float,
    fx_rates: Mapping[str, float],
) -> tuple[float, float]:
    """Returns (pnl_quote, pnl_usd). The quote figure is undiscounted; the USD
    figure is the quote PnL converted to USD then multiplied by the USD DF for
    the discounted leg's value date."""
    raw = inception_pnl_quote(trade, mid)
    pnl_usd = convert_to_usd(raw, trade.quote_currency, fx_rates) * df_far
    return raw, pnl_usd

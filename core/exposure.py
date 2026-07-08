"""Spot exposure and USD-perspective leg PVs.

Leg PVs follow a USD approach: each leg's base notional is converted to USD,
then multiplied by a ready-to-multiply USD discount factor for that leg's value
date (from the DAS curve, or the mock curve locally). Both legs are discounted,
so forward-starting trades are valued correctly.

    pv_near_leg_usd = USD(near-leg base amount) x DF(near value date)
    pv_far_leg_usd  = USD(far-leg  base amount) x DF(far value date)

Spot exposure is the SUM of the two leg PVs. The legs trade in opposite
directions, so the PVs are opposite-signed and the notionals cancel: what
survives is the discounting spread between the two settlement dates (plus the
mismatch for uneven swaps) — the only spot risk.

Outrights are valued as if they were a matched swap: a synthetic near leg with
the same amount as the single (far-settling) leg, opposite direction — the
spot hedge — settling at spot.
"""

from __future__ import annotations

from typing import Mapping

from core.fx import convert_to_usd
from core.models import ProductType, Trade


def spot_exposure_base(trade: Trade) -> float:
    return trade.exposure_leg.base_amount


def notional_mismatch_base(trade: Trade) -> float:
    """Net base-notional mismatch for uneven swaps (0 for matched/outrights)."""
    if trade.product_type != ProductType.FX_SWAP:
        return 0.0
    return trade.near_leg.base_amount + trade.far_leg.base_amount


def pv_near_leg_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_near: float
) -> float:
    if trade.product_type == ProductType.FX_SWAP:
        amount = trade.near_leg.base_amount
    else:
        # Outright as a matched swap: synthetic near leg with the same amount
        # as the single leg, opposite direction (the spot hedge).
        amount = -trade.leg.base_amount
    return convert_to_usd(amount, trade.base_currency, fx_rates) * df_near


def pv_far_leg_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_far: float
) -> float:
    leg = trade.discounted_leg          # far leg (swap) or single leg (outright)
    return convert_to_usd(leg.base_amount, trade.base_currency, fx_rates) * df_far


def spot_exposure_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_near: float, df_far: float
) -> float:
    """Net spot exposure in USD: the sum of the two leg PVs (opposite-signed
    for a swap, single leg for an outright)."""
    return pv_near_leg_usd(trade, fx_rates, df_near) + pv_far_leg_usd(
        trade, fx_rates, df_far
    )

"""Spot exposure and USD-perspective leg PVs.

Leg PVs follow a USD approach: each leg's base notional is converted to USD,
then multiplied by a ready-to-multiply USD discount factor for that leg's value
date (from the DAS curve, or the mock curve locally). Both legs are discounted,
so forward-starting trades are valued correctly.

    pv_near_leg_usd = USD(near-leg base amount) x DF(near value date)
    pv_far_leg_usd  = USD(far-leg  base amount) x DF(far value date)   [swaps]
                    = 0                                                [outrights]

Spot exposure is the SUM of the two leg PVs. For a swap the legs trade in
opposite directions, so the PVs are opposite-signed and net to the residual
spot delta: ~0 for a matched swap (spot-neutral), the mismatch for an uneven
swap. For an outright there is no far leg, so spot exposure is just the single
leg's discounted USD value — the full exposure.
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
    leg = trade.exposure_leg
    return convert_to_usd(leg.base_amount, trade.base_currency, fx_rates) * df_near


def pv_far_leg_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_far: float
) -> float:
    if trade.far_leg is None:          # outright: no offsetting far leg
        return 0.0
    return convert_to_usd(trade.far_leg.base_amount, trade.base_currency, fx_rates) * df_far


def spot_exposure_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_near: float, df_far: float
) -> float:
    """Net spot exposure in USD: the sum of the two leg PVs (opposite-signed
    for a swap, single leg for an outright)."""
    return pv_near_leg_usd(trade, fx_rates, df_near) + pv_far_leg_usd(
        trade, fx_rates, df_far
    )

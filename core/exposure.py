"""Spot exposure and USD-perspective leg PVs.

Spot exposure (both product types carry it):
    FX_SWAP:     signed base notional of the near leg
    FX_OUTRIGHT: signed base notional of the single leg

Leg PVs follow a USD approach: the leg's cash flow is converted to USD first,
then multiplied by a ready-to-multiply USD discount factor for the leg's value
date (from the DAS curve, or the mock curve locally). The near leg is
discounted too, so forward-starting trades are valued correctly.

    pv_near_leg_usd = USD(near-leg base amount)  x DF(near value date)
    pv_far_leg_usd  = USD(far-leg quote amount)  x DF(far value date)
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


def spot_exposure_usd(trade: Trade, fx_rates: Mapping[str, float]) -> float:
    return convert_to_usd(spot_exposure_base(trade), trade.base_currency, fx_rates)


def pv_near_leg_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_near: float
) -> float:
    leg = trade.exposure_leg
    return convert_to_usd(leg.base_amount, trade.base_currency, fx_rates) * df_near


def pv_far_leg_usd(
    trade: Trade, fx_rates: Mapping[str, float], df_far: float
) -> float:
    leg = trade.discounted_leg
    return convert_to_usd(leg.quote_amount, trade.quote_currency, fx_rates) * df_far


def combined_risk_usd(pv_near_usd: float, pv_far_usd: float) -> float:
    return pv_near_usd + pv_far_usd

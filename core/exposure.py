"""Spot exposure and far-leg NPV.

Spot exposure (both product types carry it):
    FX_SWAP:     signed base notional of the near leg
    FX_OUTRIGHT: signed base notional of the single leg

Far-leg NPV: quote-currency cash flow of the discounted leg (far leg for swaps,
single leg for outrights), discounted with the ACT/360 money-market DF.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

from core.discount import present_value
from core.fx import convert_to_usd
from core.models import ProductType, Trade


def spot_exposure_base(trade: Trade) -> float:
    return trade.exposure_leg.base_amount


def notional_mismatch_base(trade: Trade) -> float:
    """Net base-notional mismatch for uneven swaps (0 for matched/outrights)."""
    if trade.product_type != ProductType.FX_SWAP:
        return 0.0
    return trade.near_leg.base_amount + trade.far_leg.base_amount


def npv_far_leg_quote(trade: Trade, valuation_date: date, quote_ccy_rate: float) -> float:
    leg = trade.discounted_leg
    return present_value(leg.quote_amount, valuation_date, leg.value_date, quote_ccy_rate)


def spot_exposure_usd(trade: Trade, fx_rates: Mapping[str, float]) -> float:
    return convert_to_usd(spot_exposure_base(trade), trade.base_currency, fx_rates)


def npv_far_leg_usd(
    trade: Trade,
    valuation_date: date,
    quote_ccy_rate: float,
    fx_rates: Mapping[str, float],
) -> float:
    pv = npv_far_leg_quote(trade, valuation_date, quote_ccy_rate)
    return convert_to_usd(pv, trade.quote_currency, fx_rates)


def combined_risk_usd(spot_usd: float, npv_usd: float) -> float:
    return spot_usd + npv_usd

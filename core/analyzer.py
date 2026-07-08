"""Analytics engine: turn a Trade + market data into a TradeAnalysis."""

from __future__ import annotations

from datetime import date
from typing import Mapping

from core import exposure, pnl
from core.models import MidSnapshot, Trade, TradeAnalysis
from core.tenor import identify_tenor


def analyze_trade(
    trade: Trade,
    mid: MidSnapshot,
    fx_rates: Mapping[str, float],
    df_near: float,
    df_far: float,
    valuation_date: date | None = None,
) -> TradeAnalysis:
    val_date = valuation_date or trade.trade_date

    days, label = identify_tenor(trade, val_date)

    spot_base = exposure.spot_exposure_base(trade)
    pv_near_usd = exposure.pv_near_leg_usd(trade, fx_rates, df_near)
    pv_far_usd = exposure.pv_far_leg_usd(trade, fx_rates, df_far)
    spot_usd = pv_near_usd + pv_far_usd
    mismatch = exposure.notional_mismatch_base(trade)

    pnl_quote, pnl_usd = pnl.inception_pnl(trade, mid, df_far, fx_rates)

    return TradeAnalysis(
        trade_id=trade.trade_id,
        product_type=trade.product_type.value,
        currency_pair=trade.currency_pair,
        tenor_label=label,
        tenor_days=days,
        spot_exposure_base=spot_base,
        spot_exposure_usd=spot_usd,
        pv_near_leg_usd=pv_near_usd,
        pv_far_leg_usd=pv_far_usd,
        bbg_spot_mid=mid.spot_mid,
        bbg_swap_points_mid=mid.swap_points_mid,
        bbg_forward_mid=mid.forward_mid,
        bbg_as_of=mid.as_of,
        inception_pnl_quote=pnl_quote,
        inception_pnl_usd=pnl_usd,
        notional_mismatch_base=mismatch,
        mid_fallback=mid.fallback,
        near_value_date=trade.exposure_leg.value_date,
        far_value_date=trade.discounted_leg.value_date,
        counterparty=trade.counterparty,
        status=trade.status.value,
        version=trade.version,
    )

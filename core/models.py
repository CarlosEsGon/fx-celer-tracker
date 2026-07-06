"""Internal trade and analysis models.

This schema is the single source of truth for the app. Real Celer messages are
mapped into these models by the feed adapter (core/trade_feed.py); only the
adapter changes when the real message format is known.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator


class ProductType(str, Enum):
    FX_SWAP = "FX_SWAP"
    FX_OUTRIGHT = "FX_OUTRIGHT"


class TradeStatus(str, Enum):
    NEW = "NEW"
    AMENDED = "AMENDED"
    CANCELLED = "CANCELLED"


class Leg(BaseModel):
    value_date: date
    base_amount: float   # signed: + = buy base, - = sell base
    quote_amount: float  # signed, opposite sign to base_amount
    rate: float


class Trade(BaseModel):
    trade_id: str
    product_type: ProductType
    currency_pair: str          # "EUR/USD"
    base_currency: str
    quote_currency: str
    trade_date: date
    near_leg: Optional[Leg] = None   # swaps only
    far_leg: Optional[Leg] = None    # swaps only
    leg: Optional[Leg] = None        # outrights only
    counterparty: str = ""
    booked_at: datetime
    status: TradeStatus = TradeStatus.NEW
    version: int = 1
    # Full raw source record (e.g. the /histTrades payload) for audit; fields
    # we don't derive logic from are preserved here verbatim.
    extras: dict = {}

    @model_validator(mode="after")
    def _check_legs(self) -> "Trade":
        if self.product_type == ProductType.FX_SWAP:
            if self.near_leg is None or self.far_leg is None:
                raise ValueError("FX_SWAP requires near_leg and far_leg")
        elif self.leg is None:
            raise ValueError("FX_OUTRIGHT requires leg")
        return self

    @property
    def exposure_leg(self) -> Leg:
        """Leg carrying the spot exposure: near leg (swap) or single leg (outright)."""
        return self.near_leg if self.product_type == ProductType.FX_SWAP else self.leg

    @property
    def discounted_leg(self) -> Leg:
        """Leg whose quote cash flow is discounted: far leg (swap) or single leg."""
        return self.far_leg if self.product_type == ProductType.FX_SWAP else self.leg


class MidSnapshot(BaseModel):
    """Bloomberg (or mock) mid captured for a specific pair/value date/time."""

    pair: str
    value_date: date
    spot_mid: float
    swap_points_mid: float   # in pips
    forward_mid: float       # outright forward rate
    as_of: datetime
    fallback: bool = False   # true if point-in-time quote at booked_at unavailable


class TradeAnalysis(BaseModel):
    trade_id: str
    product_type: str
    currency_pair: str
    tenor_label: str
    tenor_days: int
    spot_exposure_base: float
    spot_exposure_usd: float
    npv_far_leg_quote: float
    npv_far_leg_usd: float
    combined_risk_usd: float
    bbg_spot_mid: float
    bbg_swap_points_mid: float
    bbg_forward_mid: float
    bbg_as_of: datetime
    inception_pnl_quote: float
    inception_pnl_usd: float
    notional_mismatch_base: float = 0.0
    mid_fallback: bool = False
    near_value_date: date
    far_value_date: Optional[date] = None
    counterparty: str = ""
    status: str = "NEW"
    version: int = 1

"""Wire schemas for the mock Celer server (mirror of core.models.Trade)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class LegIn(BaseModel):
    value_date: date
    base_amount: float
    quote_amount: float
    rate: float


class TradeIn(BaseModel):
    trade_id: str
    product_type: str
    currency_pair: str
    base_currency: str
    quote_currency: str
    trade_date: date
    near_leg: Optional[LegIn] = None
    far_leg: Optional[LegIn] = None
    leg: Optional[LegIn] = None
    counterparty: str = "MOCK_BANK"
    booked_at: datetime
    status: str = "NEW"
    version: int = 1


class BbgMidOut(BaseModel):
    pair: str
    value_date: date
    spot_mid: float
    swap_points_mid: float
    forward_mid: float
    as_of: datetime

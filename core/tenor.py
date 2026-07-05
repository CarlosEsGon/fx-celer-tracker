"""Tenor identification.

FX_SWAP:     calendar days between near and far value dates.
FX_OUTRIGHT: calendar days between valuation date and the single leg's value date.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence, Tuple

from core.models import ProductType, Trade

# (upper bound in calendar days, label) — checked in order
DEFAULT_BUCKETS: Sequence[Tuple[int, str]] = (
    (1, "ON"),
    (2, "TN"),
    (9, "1W"),
    (16, "2W"),
    (45, "1M"),
    (75, "2M"),
    (135, "3M"),
    (225, "6M"),
    (320, "9M"),
    (400, "1Y"),
)


def tenor_days(trade: Trade, valuation_date: date) -> int:
    if trade.product_type == ProductType.FX_SWAP:
        return (trade.far_leg.value_date - trade.near_leg.value_date).days
    return (trade.leg.value_date - valuation_date).days


def tenor_label(days: int, buckets: Sequence[Tuple[int, str]] = DEFAULT_BUCKETS) -> str:
    for upper, label in buckets:
        if days <= upper:
            return label
    return ">1Y"


def identify_tenor(trade: Trade, valuation_date: date) -> Tuple[int, str]:
    days = tenor_days(trade, valuation_date)
    return days, tenor_label(days)

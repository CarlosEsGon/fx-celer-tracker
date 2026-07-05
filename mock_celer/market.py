"""Deterministic mock market data.

The /bbg/mid endpoint must answer for ANY pair, ANY value date, at ANY time —
simulating Bloomberg answering a direct broken-date, point-in-time request.
Numbers are deterministic (same inputs -> same mid) so inception PnL is
reproducible, and are seeded close to the sample traded rates so PnL looks
realistic locally.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timezone

SPOT_MIDS: dict[str, float] = {
    "EURUSD": 1.1648,
    "GBPUSD": 1.2698,
    "USDJPY": 145.02,
    "AUDUSD": 0.6598,
    "USDCAD": 1.3702,
    "USDCHF": 0.8801,
    "EURGBP": 0.9172,
    "NZDUSD": 0.6102,
}

FX_RATES: dict[str, float] = {
    "EURUSD": 1.1650,
    "GBPUSD": 1.2700,
    "USDJPY": 145.00,
    "AUDUSD": 0.6600,
    "USDCAD": 1.3700,
    "USDCHF": 0.8800,
    "NZDUSD": 0.6100,
}

DISCOUNT_RATES: dict[str, float] = {
    "USD": 0.045,
    "EUR": 0.030,
    "GBP": 0.041,
    "JPY": 0.005,
    "CHF": 0.012,
    "AUD": 0.038,
    "CAD": 0.035,
}
DEFAULT_DISCOUNT_RATE = 0.030

# Annualised forward-points drift per pair (rate units per year of tenor),
# roughly reflecting rate differentials embedded in the spot/discount setup.
_POINTS_DRIFT: dict[str, float] = {
    "EURUSD": 0.0125,
    "GBPUSD": 0.0055,
    "USDJPY": -4.80,
    "AUDUSD": 0.0060,
    "USDCAD": -0.0090,
    "USDCHF": -0.0280,
    "EURGBP": 0.0095,
    "NZDUSD": 0.0065,
}


def _key(pair: str) -> str:
    return pair.replace("/", "").replace(" ", "").upper()


def pip_factor(pair: str) -> float:
    return 0.01 if _key(pair)[3:] == "JPY" else 0.0001


def _wiggle(*parts: str, scale: float) -> float:
    """Deterministic pseudo-noise in [-scale, +scale] derived from inputs."""
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / 2**64  # [0, 1)
    return (unit * 2 - 1) * scale


def get_mid(pair: str, value_date: date, as_of: datetime) -> dict:
    key = _key(pair)
    base_spot = SPOT_MIDS.get(key, 1.0)
    pip = pip_factor(pair)

    # Spot drifts deterministically with the as_of minute (same time -> same mid)
    minute_bucket = as_of.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
    spot_mid = base_spot + _wiggle(key, minute_bucket, "spot", scale=8 * pip)

    # Forward points grow ~linearly with tenor plus small curve noise
    tenor_days = max((value_date - as_of.date()).days, 0)
    drift = _POINTS_DRIFT.get(key, 0.0100)
    fwd_offset = drift * tenor_days / 360
    fwd_offset += _wiggle(key, minute_bucket, str(value_date), "fwd", scale=2 * pip) * math.sqrt(
        max(tenor_days, 1) / 90
    )

    forward_mid = spot_mid + fwd_offset
    swap_points_mid = fwd_offset / pip  # in pips

    return {
        "pair": pair,
        "value_date": value_date,
        "spot_mid": round(spot_mid, 6),
        "swap_points_mid": round(swap_points_mid, 3),
        "forward_mid": round(forward_mid, 6),
        "as_of": as_of,
    }

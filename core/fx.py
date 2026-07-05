"""USD conversion from a table of USD-legged spot rates.

Rates are keyed like "EURUSD" (base first). Handles:
  - direct:      EUR -> USD via EURUSD
  - inverse:     JPY -> USD via USDJPY (divide)
  - identity:    USD -> USD
Cross-pair trade amounts are always in one of the pair's currencies, and each
currency is triangulated to USD through its own USD leg, so no cross rate is
needed here.
"""

from __future__ import annotations

from typing import Mapping


class MissingRateError(KeyError):
    pass


def usd_rate(currency: str, rates: Mapping[str, float]) -> float:
    """Units of USD per 1 unit of `currency`."""
    ccy = currency.upper()
    if ccy == "USD":
        return 1.0
    direct = rates.get(f"{ccy}USD")
    if direct:
        return direct
    inverse = rates.get(f"USD{ccy}")
    if inverse:
        return 1.0 / inverse
    raise MissingRateError(f"No USD rate available for {currency}")


def convert_to_usd(amount: float, currency: str, rates: Mapping[str, float]) -> float:
    return amount * usd_rate(currency, rates)


def pip_factor(pair: str) -> float:
    """Pip size for a pair, e.g. 0.0001 for EUR/USD, 0.01 for USD/JPY."""
    quote = pair.replace(" ", "").split("/")[1].upper()
    return 0.01 if quote == "JPY" else 0.0001

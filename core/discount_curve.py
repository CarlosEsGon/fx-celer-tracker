"""USD discount-factor sources.

Valuation follows a USD perspective: each leg's cash flow is converted to USD
first, then multiplied by a USD discount factor for that leg's value date.
Discount factors arrive ready to multiply — no rate/day-count math here.

- DasDiscountCurve: production source; wraps the internal das_client module
  (lazy import, available at work only — same pattern as blpapi).
- MockDiscountCurve: local dev/tests; derives DFs from the flat USD rate in
  settings.yaml via the ACT/360 formula in core/discount.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from core.discount import discount_factor


class DiscountCurve(ABC):
    @abstractmethod
    def get_df(self, valuation_date: date, cash_flow_date: date) -> float:
        """USD discount factor (ready to multiply) for a cash flow date."""


class MockDiscountCurve(DiscountCurve):
    def __init__(self, usd_rate: float) -> None:
        self._rate = usd_rate

    def get_df(self, valuation_date: date, cash_flow_date: date) -> float:
        return discount_factor(valuation_date, cash_flow_date, self._rate)


class DasDiscountCurve(DiscountCurve):
    """USD curve discount factors from the internal DAS system.

    das_client is imported lazily so the module is only required when this
    source is selected (DISCOUNT_SOURCE=das).
    """

    def __init__(self) -> None:
        import das_client  # noqa: F401 — fail fast if unavailable

        self._das = das_client

    def get_df(self, valuation_date: date, cash_flow_date: date) -> float:
        # Single integration point with das_client; adjust this call if its
        # signature differs (e.g. takes the valuation date or a currency).
        return float(self._das.get_discount_factor(cash_flow_date))

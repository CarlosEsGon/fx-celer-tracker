"""ACT/360 money-market discounting.

    d  = days(valuation_date, cash_flow_date)
    tau = d / 360
    DF = 1 / (1 + r * tau)
    PV = cash_flow * DF
"""

from __future__ import annotations

from datetime import date

ACT_360 = 360


def year_fraction(valuation_date: date, cash_flow_date: date, basis: int = ACT_360) -> float:
    return (cash_flow_date - valuation_date).days / basis


def discount_factor(
    valuation_date: date,
    cash_flow_date: date,
    rate: float,
    basis: int = ACT_360,
) -> float:
    tau = year_fraction(valuation_date, cash_flow_date, basis)
    if tau <= 0:
        return 1.0
    return 1.0 / (1.0 + rate * tau)


def present_value(
    cash_flow: float,
    valuation_date: date,
    cash_flow_date: date,
    rate: float,
    basis: int = ACT_360,
) -> float:
    return cash_flow * discount_factor(valuation_date, cash_flow_date, rate, basis)

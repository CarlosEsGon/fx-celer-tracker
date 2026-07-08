from datetime import date

import pytest

from core.config import Settings, build_discount_curve
from core.discount_curve import MockDiscountCurve

VAL = date(2026, 7, 5)


def test_mock_curve_act360():
    curve = MockDiscountCurve(usd_rate=0.045)
    df = curve.get_df(VAL, date(2026, 10, 7))  # 94 days
    assert df == pytest.approx(1 / (1 + 0.045 * 94 / 360))


def test_mock_curve_past_or_same_date_is_par():
    curve = MockDiscountCurve(usd_rate=0.045)
    assert curve.get_df(VAL, VAL) == 1.0
    assert curve.get_df(VAL, date(2026, 7, 1)) == 1.0


def test_build_discount_curve_mock_uses_usd_rate():
    s = Settings(discount_rates={"USD": 0.05, "DEFAULT": 0.03})
    curve = build_discount_curve(s)
    df = curve.get_df(VAL, date(2026, 10, 7))
    assert df == pytest.approx(1 / (1 + 0.05 * 94 / 360))


def test_build_discount_curve_falls_back_to_default_rate():
    s = Settings(discount_rates={"DEFAULT": 0.03})
    curve = build_discount_curve(s)
    df = curve.get_df(VAL, date(2026, 10, 7))
    assert df == pytest.approx(1 / (1 + 0.03 * 94 / 360))

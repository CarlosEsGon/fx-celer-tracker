from datetime import date

import pytest

from core.discount import discount_factor, present_value, year_fraction

VAL = date(2026, 7, 5)
CF = date(2026, 10, 7)  # 94 days later


def test_year_fraction_act360():
    assert year_fraction(VAL, CF) == pytest.approx(94 / 360)


def test_discount_factor_formula():
    r = 0.045
    expected = 1 / (1 + r * 94 / 360)
    assert discount_factor(VAL, CF, r) == pytest.approx(expected)


def test_discount_factor_zero_rate_is_one():
    assert discount_factor(VAL, CF, 0.0) == pytest.approx(1.0)


def test_discount_factor_same_day_is_one():
    assert discount_factor(VAL, VAL, 0.10) == 1.0


def test_present_value():
    r = 0.045
    df = 1 / (1 + r * 94 / 360)
    assert present_value(1_168_000, VAL, CF, r) == pytest.approx(1_168_000 * df)


def test_pv_preserves_sign():
    assert present_value(-1_000_000, VAL, CF, 0.045) < 0

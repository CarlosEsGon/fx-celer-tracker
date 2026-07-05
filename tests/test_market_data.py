"""Tests for the mock market data source (deterministic point-in-time quotes)."""

from datetime import date, datetime, timezone

import pytest

from mock_celer import market

AS_OF = datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc)
VD = date(2026, 10, 7)


def test_same_inputs_same_mid():
    a = market.get_mid("EUR/USD", VD, AS_OF)
    b = market.get_mid("EUR/USD", VD, AS_OF)
    assert a == b


def test_different_time_different_mid():
    a = market.get_mid("EUR/USD", VD, AS_OF)
    b = market.get_mid("EUR/USD", VD, datetime(2026, 7, 5, 14, 31, tzinfo=timezone.utc))
    assert a["spot_mid"] != b["spot_mid"]


def test_forward_consistent_with_points():
    m = market.get_mid("EUR/USD", VD, AS_OF)
    reconstructed = m["spot_mid"] + m["swap_points_mid"] * 0.0001
    assert reconstructed == pytest.approx(m["forward_mid"], abs=1e-6)


def test_jpy_pip_factor():
    m = market.get_mid("USD/JPY", VD, AS_OF)
    reconstructed = m["spot_mid"] + m["swap_points_mid"] * 0.01
    assert reconstructed == pytest.approx(m["forward_mid"], abs=1e-4)


def test_any_pair_any_date_answers():
    m = market.get_mid("NZD/USD", date(2027, 3, 19), AS_OF)  # broken date
    assert m["forward_mid"] > 0
    assert m["spot_mid"] > 0


def test_longer_tenor_more_points_eurusd():
    near = market.get_mid("EUR/USD", date(2026, 8, 7), AS_OF)
    far = market.get_mid("EUR/USD", date(2027, 7, 5), AS_OF)
    assert abs(far["swap_points_mid"]) > abs(near["swap_points_mid"])


def test_spot_mid_near_seeded_value():
    m = market.get_mid("EUR/USD", VD, AS_OF)
    assert m["spot_mid"] == pytest.approx(1.1648, abs=0.002)

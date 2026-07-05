import pytest

from core.fx import MissingRateError, convert_to_usd, pip_factor, usd_rate


def test_direct_pair(fx_rates):
    assert convert_to_usd(1_000_000, "EUR", fx_rates) == pytest.approx(1_165_000)


def test_identity_usd(fx_rates):
    assert convert_to_usd(500, "USD", fx_rates) == 500


def test_inverse_pair(fx_rates):
    assert convert_to_usd(145_000_000, "JPY", fx_rates) == pytest.approx(1_000_000)


def test_cross_pair_currencies_each_triangulate(fx_rates):
    # EUR/GBP trade: base converts via EURUSD, quote via GBPUSD
    assert convert_to_usd(1_000_000, "EUR", fx_rates) == pytest.approx(1_165_000)
    assert convert_to_usd(-880_000, "GBP", fx_rates) == pytest.approx(-1_117_600)


def test_missing_rate_raises(fx_rates):
    with pytest.raises(MissingRateError):
        usd_rate("SEK", fx_rates)


def test_pip_factor():
    assert pip_factor("EUR/USD") == 0.0001
    assert pip_factor("USD/JPY") == 0.01

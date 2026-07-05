from datetime import date

import pytest

from core import exposure
from core.models import Leg, ProductType

VAL = date(2026, 7, 5)
R_USD = 0.045


def test_swap_spot_exposure_is_near_leg_base(swap_trade):
    assert exposure.spot_exposure_base(swap_trade) == 1_000_000


def test_outright_spot_exposure_is_single_leg_base(outright_trade):
    assert exposure.spot_exposure_base(outright_trade) == -500_000


def test_swap_npv_discounts_far_quote_flow(swap_trade):
    df = 1 / (1 + R_USD * 94 / 360)
    assert exposure.npv_far_leg_quote(swap_trade, VAL, R_USD) == pytest.approx(
        1_168_000 * df
    )


def test_outright_npv_discounts_single_leg(outright_trade):
    df = 1 / (1 + R_USD * 94 / 360)
    assert exposure.npv_far_leg_quote(outright_trade, VAL, R_USD) == pytest.approx(
        635_000 * df
    )


def test_usd_conversion_and_combined(swap_trade, fx_rates):
    spot_usd = exposure.spot_exposure_usd(swap_trade, fx_rates)
    assert spot_usd == pytest.approx(1_165_000)
    npv_usd = exposure.npv_far_leg_usd(swap_trade, VAL, R_USD, fx_rates)
    assert exposure.combined_risk_usd(spot_usd, npv_usd) == pytest.approx(
        spot_usd + npv_usd
    )


def test_matched_swap_has_no_mismatch(swap_trade):
    assert exposure.notional_mismatch_base(swap_trade) == 0.0


def test_uneven_swap_mismatch(swap_trade):
    uneven = swap_trade.model_copy(deep=True)
    uneven.far_leg = Leg(
        value_date=date(2026, 10, 7),
        base_amount=-800_000,
        quote_amount=934_400,
        rate=1.1680,
    )
    assert exposure.notional_mismatch_base(uneven) == pytest.approx(200_000)


def test_outright_has_no_mismatch(outright_trade):
    assert outright_trade.product_type == ProductType.FX_OUTRIGHT
    assert exposure.notional_mismatch_base(outright_trade) == 0.0

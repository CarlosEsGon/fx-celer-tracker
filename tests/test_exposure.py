from datetime import date

import pytest

from core import exposure
from core.models import Leg, ProductType

DF_NEAR = 0.9995
DF_FAR = 0.9884


def test_swap_spot_exposure_is_near_leg_base(swap_trade):
    assert exposure.spot_exposure_base(swap_trade) == 1_000_000


def test_outright_spot_exposure_is_single_leg_base(outright_trade):
    assert exposure.spot_exposure_base(outright_trade) == -500_000


def test_swap_pv_near_leg_usd(swap_trade, fx_rates):
    # near leg: +1,000,000 EUR -> USD at 1.1650, then x DF(near date)
    assert exposure.pv_near_leg_usd(swap_trade, fx_rates, DF_NEAR) == pytest.approx(
        1_165_000 * DF_NEAR
    )


def test_swap_pv_far_leg_usd(swap_trade, fx_rates):
    # far leg: +1,168,000 USD quote flow x DF(far date)
    assert exposure.pv_far_leg_usd(swap_trade, fx_rates, DF_FAR) == pytest.approx(
        1_168_000 * DF_FAR
    )


def test_outright_leg_pvs_use_single_leg(outright_trade, fx_rates):
    # single leg is both the exposure leg and the discounted leg
    assert exposure.pv_near_leg_usd(outright_trade, fx_rates, DF_FAR) == pytest.approx(
        -500_000 * 1.27 * DF_FAR
    )
    assert exposure.pv_far_leg_usd(outright_trade, fx_rates, DF_FAR) == pytest.approx(
        635_000 * DF_FAR
    )


def test_usd_conversion_and_combined(swap_trade, fx_rates):
    spot_usd = exposure.spot_exposure_usd(swap_trade, fx_rates)
    assert spot_usd == pytest.approx(1_165_000)
    pv_near = exposure.pv_near_leg_usd(swap_trade, fx_rates, DF_NEAR)
    pv_far = exposure.pv_far_leg_usd(swap_trade, fx_rates, DF_FAR)
    assert exposure.combined_risk_usd(pv_near, pv_far) == pytest.approx(
        pv_near + pv_far
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

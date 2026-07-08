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


def test_swap_leg_pvs_are_opposite_signed(swap_trade, fx_rates):
    # near +1,000,000 EUR -> +1,165,000 USD x DF_near
    pv_near = exposure.pv_near_leg_usd(swap_trade, fx_rates, DF_NEAR)
    assert pv_near == pytest.approx(1_165_000 * DF_NEAR)
    # far -1,000,000 EUR -> -1,165,000 USD x DF_far  (opposite direction)
    pv_far = exposure.pv_far_leg_usd(swap_trade, fx_rates, DF_FAR)
    assert pv_far == pytest.approx(-1_165_000 * DF_FAR)
    assert pv_near > 0 > pv_far


def test_swap_spot_exposure_is_sum_of_leg_pvs(swap_trade, fx_rates):
    # Matched swap: the legs nearly cancel, leaving only the discounting spread.
    spot = exposure.spot_exposure_usd(swap_trade, fx_rates, DF_NEAR, DF_FAR)
    assert spot == pytest.approx(1_165_000 * DF_NEAR - 1_165_000 * DF_FAR)


def test_outright_far_leg_is_zero_full_directional(outright_trade, fx_rates):
    # No far leg to offset: spot exposure = the single leg's discounted value.
    assert exposure.pv_far_leg_usd(outright_trade, fx_rates, DF_FAR) == 0.0
    spot = exposure.spot_exposure_usd(outright_trade, fx_rates, DF_FAR, DF_FAR)
    assert spot == pytest.approx(-500_000 * 1.27 * DF_FAR)


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


def test_uneven_swap_spot_exposure_reflects_mismatch(swap_trade, fx_rates):
    uneven = swap_trade.model_copy(deep=True)
    uneven.far_leg = Leg(
        value_date=date(2026, 10, 7),
        base_amount=-800_000,
        quote_amount=934_400,
        rate=1.1680,
    )
    # near +1,000,000 EUR, far -800,000 EUR -> net long base exposure
    spot = exposure.spot_exposure_usd(uneven, fx_rates, DF_NEAR, DF_FAR)
    assert spot == pytest.approx(1_165_000 * DF_NEAR - 800_000 * 1.165 * DF_FAR)
    assert spot > 0


def test_outright_has_no_mismatch(outright_trade):
    assert outright_trade.product_type == ProductType.FX_OUTRIGHT
    assert exposure.notional_mismatch_base(outright_trade) == 0.0

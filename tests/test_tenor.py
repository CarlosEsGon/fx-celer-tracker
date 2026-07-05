from datetime import date

from core.tenor import identify_tenor, tenor_label


def test_swap_tenor_is_near_to_far(swap_trade):
    days, label = identify_tenor(swap_trade, valuation_date=date(2026, 7, 5))
    assert days == 92
    assert label == "3M"


def test_outright_tenor_is_valuation_to_leg(outright_trade):
    days, label = identify_tenor(outright_trade, valuation_date=date(2026, 7, 5))
    assert days == 94
    assert label == "3M"


def test_bucket_labels():
    assert tenor_label(1) == "ON"
    assert tenor_label(2) == "TN"
    assert tenor_label(7) == "1W"
    assert tenor_label(14) == "2W"
    assert tenor_label(30) == "1M"
    assert tenor_label(60) == "2M"
    assert tenor_label(91) == "3M"
    assert tenor_label(182) == "6M"
    assert tenor_label(270) == "9M"
    assert tenor_label(365) == "1Y"
    assert tenor_label(500) == ">1Y"

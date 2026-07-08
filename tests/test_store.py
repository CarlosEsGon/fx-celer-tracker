from datetime import date, datetime, timezone

from core.analyzer import analyze_trade
from core.store import TradeStore


def _store(tmp_path):
    return TradeStore(tmp_path / "trades.db")


def test_trade_round_trip(tmp_path, swap_trade):
    store = _store(tmp_path)
    store.save_trade(swap_trade)
    loaded = store.load_trade(swap_trade.trade_id, swap_trade.version)
    assert loaded == swap_trade


def test_dedupe_by_id_and_version(tmp_path, swap_trade):
    store = _store(tmp_path)
    assert not store.has_seen(swap_trade.trade_id, 1)
    store.save_trade(swap_trade)
    assert store.has_seen(swap_trade.trade_id, 1)
    assert not store.has_seen(swap_trade.trade_id, 2)


def test_last_booked_at_for_catchup(tmp_path, swap_trade, outright_trade):
    store = _store(tmp_path)
    assert store.last_booked_at() is None
    store.save_trade(swap_trade)     # 14:30Z
    store.save_trade(outright_trade)  # 15:00Z
    assert store.last_booked_at() == datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc)


def test_analysis_persist_and_query(tmp_path, swap_trade, eurusd_mid, fx_rates):
    store = _store(tmp_path)
    analysis = analyze_trade(swap_trade, eurusd_mid, fx_rates, 0.9995, 0.9884)
    store.save_trade(swap_trade)
    store.save_analysis(analysis)

    rows = store.get_trade_history()
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_id"] == swap_trade.trade_id
    assert row["tenor_label"] == "3M"
    assert row["inception_pnl_usd"] is not None
    assert row["bbg_forward_mid"] == eurusd_mid.forward_mid


def test_cancelled_drops_out_of_default_queries(tmp_path, swap_trade):
    store = _store(tmp_path)
    store.save_trade(swap_trade)
    assert store.mark_cancelled(swap_trade.trade_id, "CANCELLED")
    assert store.get_trade_history() == []
    assert len(store.get_trade_history(include_cancelled=True)) == 1


def test_amended_treated_like_cancelled(tmp_path, swap_trade):
    store = _store(tmp_path)
    store.save_trade(swap_trade)
    store.mark_cancelled(swap_trade.trade_id, "AMENDED")
    assert store.get_trade_history() == []
    audit = store.get_trade_history(include_cancelled=True)
    assert audit[0]["status"] == "AMENDED"


def test_filter_by_pair_and_since(tmp_path, swap_trade, outright_trade):
    store = _store(tmp_path)
    store.save_trade(swap_trade)
    store.save_trade(outright_trade)
    assert len(store.get_trade_history(pair="EUR/USD")) == 1
    since = datetime(2026, 7, 5, 14, 45, tzinfo=timezone.utc)
    assert len(store.get_trade_history(since=since)) == 1


def test_csv_export(tmp_path, swap_trade):
    store = _store(tmp_path)
    store.save_trade(swap_trade)
    out = tmp_path / "export.csv"
    n = store.export_csv(out)
    assert n == 1
    assert "FXS-TEST-001" in out.read_text()

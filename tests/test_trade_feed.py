"""Feed tests: frame parsing, dedupe overlap, catch-up cursor advancement."""

from datetime import datetime, timezone

import pytest

from core.models import TradeStatus
from core.trade_feed import MockCelerFeed, RealCelerFeed

SWAP_FRAME = """{
  "trade_id": "FXS-20260705-001",
  "product_type": "FX_SWAP",
  "currency_pair": "EUR/USD",
  "base_currency": "EUR",
  "quote_currency": "USD",
  "trade_date": "2026-07-05",
  "near_leg": {"value_date": "2026-07-07", "base_amount": 1000000,
               "quote_amount": -1165000, "rate": 1.1650},
  "far_leg": {"value_date": "2026-10-07", "base_amount": -1000000,
              "quote_amount": 1168000, "rate": 1.1680},
  "counterparty": "MOCK_BANK",
  "booked_at": "2026-07-05T14:30:00Z",
  "status": "NEW",
  "version": 1
}"""


def test_mock_feed_parses_trade_frame():
    feed = MockCelerFeed()
    trade = feed._parse_frame(SWAP_FRAME)
    assert trade is not None
    assert trade.trade_id == "FXS-20260705-001"
    assert trade.status == TradeStatus.NEW


def test_mock_feed_skips_ping():
    feed = MockCelerFeed()
    assert feed._parse_frame('{"type": "ping"}') is None


def test_malformed_frame_raises_for_caller_to_skip():
    feed = MockCelerFeed()
    with pytest.raises(Exception):
        feed._parse_frame('{"garbage": true}')


def test_real_feed_skips_transport_frames():
    feed = RealCelerFeed(ws_url="ws://example", capture_raw=False)
    assert feed._parse_frame('{"type": "heartbeat"}') is None
    assert feed._parse_frame('{"messageType": "ACK"}') is None
    assert feed._parse_frame('{"msgType": "subscribed"}') is None


def test_real_feed_unwraps_trade_envelope():
    feed = RealCelerFeed(ws_url="ws://example", capture_raw=False)
    framed = '{"type": "execution", "trade": %s}' % SWAP_FRAME
    trade = feed._parse_frame(framed)
    assert trade is not None
    assert trade.trade_id == "FXS-20260705-001"


def test_real_feed_passthrough_when_frame_is_trade():
    feed = RealCelerFeed(ws_url="ws://example", capture_raw=False)
    trade = feed._parse_frame(SWAP_FRAME)
    assert trade is not None


def test_catchup_cursor_advances():
    feed = MockCelerFeed()
    assert feed._since is None
    trade = feed._parse_frame(SWAP_FRAME)
    feed._advance_since(trade)
    assert feed._since == datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc)
    # An older trade must not move the cursor backwards
    older = trade.model_copy(
        update={"booked_at": datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc)}
    )
    feed._advance_since(older)
    assert feed._since == datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc)


def test_capture_writes_raw_frames(tmp_path):
    path = tmp_path / "frames.jsonl"
    feed = RealCelerFeed(ws_url="ws://example", capture_raw=True, capture_path=path)
    feed._capture('{"a": 1}')
    feed._capture('{"b": 2}')
    lines = path.read_text().strip().splitlines()
    assert lines == ['{"a": 1}', '{"b": 2}']

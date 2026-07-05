"""Trade feeds: async streams of Trade events.

TradeFeed contract:
    async for event in feed.events():
        # event is FeedEvent: either a parsed Trade or a status change

Both implementations share the same websocket machinery:
  - reconnect with exponential backoff (never raises out of the loop)
  - server ping tolerance / liveness timeout
  - REST snapshot catch-up on connect (missed-while-down recovery)
  - raw-frame capture for day-1 schema discovery (RealCelerFeed)

RealCelerFeed._parse_frame is the ONLY code expected to change on day 1 once
real frames have been captured with scripts/celer_probe.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
import websockets

from core.models import Trade

log = logging.getLogger(__name__)


@dataclass
class FeedEvent:
    """Either a trade or a connection-status notification."""

    kind: str                      # "trade" | "status"
    trade: Optional[Trade] = None
    status: str = ""               # connected | reconnecting | catching_up
    catchup: bool = False          # trade delivered via snapshot, not live push
    detail: str = ""


@dataclass
class _WsConfig:
    ws_url: str
    rest_url: str = ""
    headers: dict = field(default_factory=dict)
    liveness_timeout_sec: float = 45.0
    backoff_initial_sec: float = 1.0
    backoff_max_sec: float = 30.0
    capture_path: Optional[Path] = None


class TradeFeed(ABC):
    @abstractmethod
    def events(self) -> AsyncIterator[FeedEvent]: ...

    @abstractmethod
    def set_catchup_since(self, since: Optional[datetime]) -> None:
        """Booked-at timestamp to resume from (persisted by the store)."""


class _WebsocketFeed(TradeFeed):
    """Shared websocket consumption loop."""

    def __init__(self, config: _WsConfig) -> None:
        self._cfg = config
        self._since: Optional[datetime] = None

    def set_catchup_since(self, since: Optional[datetime]) -> None:
        self._since = since

    # -- subclass hooks ---------------------------------------------------------

    def _parse_frame(self, raw: str) -> Optional[Trade]:
        """Map one wire frame to a Trade; None to skip (heartbeats etc.)."""
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("type") == "ping":
            return None
        return Trade(**data)

    async def _snapshot(self) -> list[Trade]:
        """REST catch-up for trades missed while disconnected."""
        if not self._cfg.rest_url:
            return []
        params = {}
        if self._since is not None:
            params["since"] = self._since.isoformat()
        async with httpx.AsyncClient(
            timeout=10.0, headers=self._cfg.headers
        ) as client:
            resp = await client.get(f"{self._cfg.rest_url}/trades", params=params)
            resp.raise_for_status()
            trades = []
            for item in resp.json():
                try:
                    trades.append(Trade(**item))
                except Exception:
                    log.exception("skipping malformed snapshot trade: %.200s", item)
            return trades

    # -- capture -------------------------------------------------------------------

    def _capture(self, raw: str) -> None:
        if self._cfg.capture_path is None:
            return
        try:
            self._cfg.capture_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cfg.capture_path, "a", encoding="utf-8") as fh:
                fh.write(raw.strip() + "\n")
        except OSError:
            log.exception("raw frame capture failed")

    # -- main loop -----------------------------------------------------------------

    async def events(self) -> AsyncIterator[FeedEvent]:
        backoff = self._cfg.backoff_initial_sec
        while True:
            try:
                async with websockets.connect(
                    self._cfg.ws_url,
                    additional_headers=self._cfg.headers or None,
                    ping_interval=20,
                    ping_timeout=15,
                ) as ws:
                    log.info("websocket connected: %s", self._cfg.ws_url)
                    backoff = self._cfg.backoff_initial_sec

                    # Catch-up first, so nothing booked while down is lost
                    yield FeedEvent(kind="status", status="catching_up")
                    try:
                        for trade in await self._snapshot():
                            self._advance_since(trade)
                            yield FeedEvent(kind="trade", trade=trade, catchup=True)
                    except Exception:
                        log.exception("snapshot catch-up failed; continuing live")

                    yield FeedEvent(kind="status", status="connected")

                    while True:
                        raw = await asyncio.wait_for(
                            ws.recv(), timeout=self._cfg.liveness_timeout_sec
                        )
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        self._capture(raw)
                        try:
                            trade = self._parse_frame(raw)
                        except Exception:
                            log.exception("skipping malformed frame: %.300s", raw)
                            continue
                        if trade is None:
                            continue
                        self._advance_since(trade)
                        yield FeedEvent(kind="trade", trade=trade)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("feed disconnected (%s); retrying in %.1fs", exc, backoff)
                yield FeedEvent(kind="status", status="reconnecting", detail=str(exc))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._cfg.backoff_max_sec)

    def _advance_since(self, trade: Trade) -> None:
        if self._since is None or trade.booked_at > self._since:
            self._since = trade.booked_at


class MockCelerFeed(_WebsocketFeed):
    """Feed from the local mock Celer server."""

    def __init__(
        self,
        ws_url: str = "ws://localhost:8000/ws/trades",
        rest_url: str = "http://localhost:8000",
    ) -> None:
        super().__init__(_WsConfig(ws_url=ws_url, rest_url=rest_url))


class RealCelerFeed(_WebsocketFeed):
    """Feed from the real Celer websocket.

    Transport (URL + auth header) is config-driven. The frame mapping below is
    a best-effort guess pending real captured frames — adjust _parse_frame
    after running scripts/celer_probe.py on day 1.
    """

    def __init__(
        self,
        ws_url: str,
        rest_url: str = "",
        auth_header_name: str = "Authorization",
        auth_header_value: str = "",
        capture_raw: bool = True,
        capture_path: str | Path = "data/celer_frames.jsonl",
    ) -> None:
        headers = (
            {auth_header_name: auth_header_value} if auth_header_value else {}
        )
        super().__init__(
            _WsConfig(
                ws_url=ws_url,
                rest_url=rest_url,
                headers=headers,
                capture_path=Path(capture_path) if capture_raw else None,
            )
        )

    def _parse_frame(self, raw: str) -> Optional[Trade]:
        data = json.loads(raw)

        # Ignore non-trade frames (heartbeats, acks, subscription confirms).
        if not isinstance(data, dict):
            return None
        msg_type = str(
            data.get("type") or data.get("messageType") or data.get("msgType") or ""
        ).lower()
        if msg_type in {"ping", "pong", "heartbeat", "ack", "subscribed"}:
            return None

        # DAY-1 TODO: map real Celer execution-report fields to core.models.Trade.
        # Compare captured frames in data/celer_frames.jsonl with this mapping and
        # correct field names/nesting as needed. If frames already match the
        # internal schema (the mock format), this passthrough just works.
        payload = data.get("trade", data)
        return Trade(**payload)

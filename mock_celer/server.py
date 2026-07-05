"""Mock Celer server: websocket trade feed + supporting REST endpoints.

Run:  uvicorn mock_celer.server:app --reload --port 8000

- WS  /ws/trades?since=...   push feed; optional replay of missed trades
- GET /health
- GET /trades?since=...      snapshot for catch-up
- GET /trades/{trade_id}
- POST /trades               inject a trade -> broadcast to ws clients
- GET /fx-rates
- GET /curves/{currency}
- GET /bbg/mid?pair=&value_date=&as_of=   point-in-time broken-date mock mid
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from mock_celer import market
from mock_celer.schemas import BbgMidOut, TradeIn

log = logging.getLogger("mock_celer")
app = FastAPI(title="Mock Celer Server")

_trades: dict[str, dict] = {}          # trade_id -> raw trade dict (latest version)
_clients: set[WebSocket] = set()
_lock = asyncio.Lock()


def _serialize(trade: TradeIn) -> dict:
    return json.loads(trade.model_dump_json())


async def _broadcast(payload: dict) -> None:
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "clients": len(_clients), "trades": len(_trades)}


@app.get("/trades")
async def list_trades(since: Optional[datetime] = None) -> list[dict]:
    items = sorted(_trades.values(), key=lambda t: t["booked_at"])
    if since is None:
        return items
    since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)

    def booked(t: dict) -> datetime:
        dt = datetime.fromisoformat(t["booked_at"])
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    return [t for t in items if booked(t) > since_utc]


@app.get("/trades/{trade_id}")
async def get_trade(trade_id: str) -> dict:
    if trade_id not in _trades:
        raise HTTPException(status_code=404, detail="unknown trade_id")
    return _trades[trade_id]


@app.post("/trades")
async def inject_trade(trade: TradeIn) -> dict:
    payload = _serialize(trade)
    async with _lock:
        _trades[trade.trade_id] = payload
    await _broadcast(payload)
    log.info("injected + broadcast %s to %d client(s)", trade.trade_id, len(_clients))
    return {"accepted": trade.trade_id, "clients_notified": len(_clients)}


@app.get("/fx-rates")
async def fx_rates() -> dict[str, float]:
    return market.FX_RATES


@app.get("/curves/{currency}")
async def curve(currency: str) -> dict:
    rate = market.DISCOUNT_RATES.get(currency.upper(), market.DEFAULT_DISCOUNT_RATE)
    return {"currency": currency.upper(), "rate": rate}


@app.get("/bbg/mid", response_model=BbgMidOut)
async def bbg_mid(
    pair: str = Query(..., description="e.g. EURUSD or EUR/USD"),
    value_date: date = Query(...),
    as_of: Optional[datetime] = Query(None, description="defaults to now (UTC)"),
) -> BbgMidOut:
    ts = as_of or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return BbgMidOut(**market.get_mid(pair, value_date, ts))


@app.websocket("/ws/trades")
async def ws_trades(websocket: WebSocket, since: Optional[str] = None) -> None:
    await websocket.accept()
    _clients.add(websocket)
    log.info("ws client connected (%d total)", len(_clients))
    try:
        # Optional replay of trades booked after `since`
        if since:
            since_dt = datetime.fromisoformat(since)
            for trade in await list_trades(since=since_dt):
                await websocket.send_json(trade)
        # Keep the connection open; server->client pings keep it alive and
        # let the client detect a dead socket. Client messages are ignored
        # except as implicit liveness.
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        _clients.discard(websocket)
        log.info("ws client disconnected (%d left)", len(_clients))

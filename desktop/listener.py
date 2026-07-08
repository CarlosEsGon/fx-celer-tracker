"""Feed listener: consumes the websocket feed on a worker thread, analyses
trades, persists them, and hands UI events to the Tkinter thread via a queue.

Tkinter is not thread-safe — nothing in this module touches the UI directly.
UI events are plain dicts drained by the main thread with root.after().
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from core.analyzer import analyze_trade
from core.config import Settings, build_discount_curve, build_feed, build_market_data
from core.models import Trade, TradeAnalysis, TradeStatus
from core.store import TradeStore
from core.trade_feed import FeedEvent

log = logging.getLogger(__name__)

RETRY_INTERVAL_SEC = 30.0


@dataclass
class UiEvent:
    kind: str                                   # trade | digest | removal | status | pnl_pending
    analysis: Optional[TradeAnalysis] = None
    analyses: Optional[list[TradeAnalysis]] = None
    trade: Optional[Trade] = None
    status: str = ""
    detail: str = ""


class FeedListener:
    def __init__(self, settings: Settings, store: TradeStore, ui_queue: "queue.Queue[UiEvent]") -> None:
        self._settings = settings
        self._store = store
        self._ui = ui_queue
        self._feed = build_feed(settings)
        self._market = build_market_data(settings)
        self._curve = build_discount_curve(settings)
        self._pending: list[Trade] = []          # trades awaiting a mid retry
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()

    # ---- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="feed-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: None)  # wake the loop

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception:
            log.exception("listener crashed")
            self._ui.put(UiEvent(kind="status", status="down", detail="listener crashed; see logs"))
        finally:
            self._loop.close()

    # ---- main consumption loop -------------------------------------------------

    async def _main(self) -> None:
        self._feed.set_catchup_since(self._store.last_booked_at())
        retry_task = asyncio.create_task(self._retry_pending_loop())
        catchup_batch: list[TradeAnalysis] = []
        in_catchup = False
        try:
            async for event in self._feed.events():
                if self._stop.is_set():
                    break
                if event.kind == "status":
                    if event.status == "catching_up":
                        in_catchup = True
                        catchup_batch = []
                    elif event.status == "connected":
                        in_catchup = False
                        self._flush_catchup(catchup_batch)
                        catchup_batch = []
                    self._ui.put(UiEvent(kind="status", status=event.status, detail=event.detail))
                    continue

                analysis = self._process_trade(event.trade)
                if analysis is None:
                    continue
                if not self._should_notify(analysis):
                    continue
                if in_catchup or event.catchup:
                    catchup_batch.append(analysis)
                else:
                    self._ui.put(UiEvent(kind="trade", analysis=analysis))
        finally:
            retry_task.cancel()

    def _flush_catchup(self, batch: list[TradeAnalysis]) -> None:
        if not batch:
            return
        if len(batch) == 1:
            self._ui.put(UiEvent(kind="trade", analysis=batch[0]))
        else:
            self._ui.put(UiEvent(kind="digest", analyses=batch,
                                 detail="while you were away"))

    # ---- per-trade processing -----------------------------------------------------

    def _process_trade(self, trade: Trade) -> Optional[TradeAnalysis]:
        try:
            if self._store.has_seen(trade.trade_id, trade.version):
                log.debug("duplicate %s v%d ignored", trade.trade_id, trade.version)
                return None

            # Lifecycle: amendments are treated as cancellations
            if trade.status in (TradeStatus.AMENDED, TradeStatus.CANCELLED):
                self._store.save_trade(trade)
                self._store.mark_cancelled(trade.trade_id, trade.status.value)
                verb = "amended — removed from tracking" \
                    if trade.status == TradeStatus.AMENDED else "cancelled"
                log.info("%s: %s", trade.trade_id, verb)
                self._ui.put(UiEvent(kind="removal", trade=trade, detail=verb))
                return None

            self._store.save_trade(trade)
            return self._analyse_and_store(trade)
        except Exception:
            log.exception("failed processing %s", getattr(trade, "trade_id", "?"))
            return None

    def _analyse_and_store(self, trade: Trade) -> Optional[TradeAnalysis]:
        val_date = self._valuation_date(trade)
        try:
            mid = self._market.get_mid(
                trade.currency_pair,
                trade.discounted_leg.value_date,
                trade.booked_at,
            )
            fx_rates = self._market.get_fx_rates()
            df_near = self._curve.get_df(val_date, trade.exposure_leg.value_date)
            df_far = self._curve.get_df(val_date, trade.discounted_leg.value_date)
        except Exception:
            log.exception("market data failed for %s; queued for retry", trade.trade_id)
            self._pending.append(trade)
            self._ui.put(UiEvent(kind="pnl_pending", trade=trade,
                                 detail="market data unavailable — PnL pending"))
            return None

        analysis = analyze_trade(
            trade, mid, fx_rates, df_near, df_far,
            valuation_date=val_date,
        )
        self._store.save_analysis(analysis)
        log.info(
            "%s %s %s tenor=%s spotUSD=%.0f pnlUSD=%.0f%s",
            trade.trade_id, trade.product_type.value, trade.currency_pair,
            analysis.tenor_label, analysis.spot_exposure_usd,
            analysis.inception_pnl_usd, " [mid fallback]" if analysis.mid_fallback else "",
        )
        return analysis

    def _should_notify(self, analysis: TradeAnalysis) -> bool:
        """Popup filter: currency must be watched AND exposure must clear the
        threshold (both settings are user-configurable, live, via the Settings
        window). Persistence/analytics are unaffected either way."""
        watched = self._settings.watched_currencies
        if watched:
            base_ccy, _, quote_ccy = analysis.currency_pair.partition("/")
            if base_ccy.upper() not in watched and quote_ccy.upper() not in watched:
                return False
        threshold = self._settings.exposure_threshold_usd
        if threshold > 0 and abs(analysis.spot_exposure_usd) < threshold:
            return False
        return True

    def _valuation_date(self, trade: Trade) -> date:
        if self._settings.valuation_date_mode == "spot":
            return trade.trade_date + timedelta(days=2)
        return trade.trade_date

    # ---- mid retry loop ------------------------------------------------------------

    async def _retry_pending_loop(self) -> None:
        while True:
            await asyncio.sleep(RETRY_INTERVAL_SEC)
            if not self._pending:
                continue
            retrying, self._pending = self._pending, []
            log.info("retrying market data for %d pending trade(s)", len(retrying))
            for trade in retrying:
                analysis = self._analyse_and_store(trade)
                if analysis is not None and self._should_notify(analysis):
                    self._ui.put(UiEvent(kind="trade", analysis=analysis))

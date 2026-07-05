"""FX Celer Trade Tracker — desktop entry point.

Run:  python -m desktop.app

Main window shows connection status and a running trade count; each new trade
raises a popup (digest for bursts) and an optional voice summary. The websocket
listener runs on a worker thread; this module owns the Tkinter main loop and
drains the UI queue with root.after().
"""

from __future__ import annotations

import logging
import queue

import customtkinter as ctk

from core.config import load_settings
from core.store import TradeStore
from desktop.listener import FeedListener, UiEvent
from desktop.logging_setup import setup_logging
from desktop.popup import DigestPopup, NoticePopup, TradePopup, notice_for_removal
from desktop.voice import VoiceAnnouncer, digest_summary, trade_summary

log = logging.getLogger(__name__)

UI_PUMP_MS = 200
BURST_WINDOW_MS = 1500

STATUS_COLOURS = {
    "connected": "#1fa860",
    "catching_up": "#d78a1f",
    "reconnecting": "#d78a1f",
    "down": "#d5453c",
}


class TrackerApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.store = TradeStore(self.settings.db_path)
        self.ui_queue: "queue.Queue[UiEvent]" = queue.Queue()
        self.voice = VoiceAnnouncer(enabled=self.settings.voice_enabled)
        self.listener = FeedListener(self.settings, self.store, self.ui_queue)

        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("FX Celer Trade Tracker")
        self.root.geometry("420x190")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._burst: list = []          # analyses buffered inside the burst window
        self._burst_job: str | None = None
        self._trade_count = 0

        self._build_main_window()

    # ---- main window --------------------------------------------------------

    def _build_main_window(self) -> None:
        feed_name = "Celer (real)" if self.settings.trade_feed == "celer" else "Mock Celer"
        md_name = "Bloomberg (blpapi)" if self.settings.market_data == "blpapi" else "Mock BBG"

        ctk.CTkLabel(self.root, text="FX Celer Trade Tracker",
                     font=ctk.CTkFont(size=17, weight="bold")).pack(
            anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(self.root, text=f"Feed: {feed_name}    Market data: {md_name}",
                     font=ctk.CTkFont(size=12), text_color="gray65").pack(
            anchor="w", padx=18)

        self.status_label = ctk.CTkLabel(self.root, text="● starting…",
                                         font=ctk.CTkFont(size=13),
                                         text_color="gray65")
        self.status_label.pack(anchor="w", padx=18, pady=(10, 0))

        self.count_label = ctk.CTkLabel(self.root, text="Trades this session: 0",
                                        font=ctk.CTkFont(size=12),
                                        text_color="gray65")
        self.count_label.pack(anchor="w", padx=18, pady=(4, 0))

        self.voice_switch = ctk.CTkSwitch(
            self.root, text="Voice announcements", command=self._toggle_voice)
        if self.settings.voice_enabled:
            self.voice_switch.select()
        self.voice_switch.pack(anchor="w", padx=18, pady=(12, 0))

    def _toggle_voice(self) -> None:
        self.voice.enabled = bool(self.voice_switch.get())

    def _set_status(self, status: str, detail: str = "") -> None:
        colour = STATUS_COLOURS.get(status, "gray65")
        text = f"● {status}" + (f" — {detail}" if detail else "")
        self.status_label.configure(text=text, text_color=colour)

    # ---- UI queue pump ---------------------------------------------------------

    def _pump(self) -> None:
        try:
            while True:
                event = self.ui_queue.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self.root.after(UI_PUMP_MS, self._pump)

    def _handle(self, event: UiEvent) -> None:
        if event.kind == "status":
            self._set_status(event.status, event.detail)
        elif event.kind == "trade":
            self._trade_count += 1
            self.count_label.configure(text=f"Trades this session: {self._trade_count}")
            self._burst.append(event.analysis)
            if self._burst_job is None:
                self._burst_job = self.root.after(BURST_WINDOW_MS, self._flush_burst)
        elif event.kind == "digest":
            self._trade_count += len(event.analyses)
            self.count_label.configure(text=f"Trades this session: {self._trade_count}")
            DigestPopup(self.root, event.analyses, event.detail or "catch-up")
            self.voice.say(digest_summary(event.analyses, event.detail or "caught up"))
        elif event.kind == "removal":
            notice_for_removal(self.root, event.trade, event.detail)
        elif event.kind == "pnl_pending":
            NoticePopup(
                self.root,
                title=f"Trade {event.trade.trade_id}",
                message=f"{event.trade.currency_pair} received, but {event.detail}. "
                        "It will be analysed automatically when market data returns.",
            )

    def _flush_burst(self) -> None:
        batch, self._burst = self._burst, []
        self._burst_job = None
        if not batch:
            return
        if len(batch) > self.settings.digest_threshold:
            DigestPopup(self.root, batch, "burst")
            self.voice.say(digest_summary(batch, "just now"))
        else:
            for analysis in batch:
                TradePopup(self.root, analysis)
                self.voice.say(trade_summary(analysis))

    # ---- lifecycle ------------------------------------------------------------------

    def run(self) -> None:
        self.listener.start()
        self.root.after(UI_PUMP_MS, self._pump)
        log.info("tracker started (feed=%s, market_data=%s)",
                 self.settings.trade_feed, self.settings.market_data)
        self.root.mainloop()

    def _on_close(self) -> None:
        log.info("shutting down")
        self.listener.stop()
        self.voice.stop()
        self.store.close()
        self.root.destroy()


def main() -> None:
    setup_logging()
    TrackerApp().run()


if __name__ == "__main__":
    main()

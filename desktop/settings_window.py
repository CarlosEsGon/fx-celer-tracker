"""Popup settings window: choose which currencies trigger a popup and the
minimum spot exposure required before one is shown. Called only from the UI
thread; mutates the shared Settings object in place so the listener thread
picks up changes immediately, and persists them to settings.yaml."""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from core.config import MAIN_CURRENCIES, Settings, save_popup_settings
from core.store import TradeStore

MUTED = "gray65"
RED = "#d5453c"


class SettingsWindow(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        settings: Settings,
        store: TradeStore,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.title("Popup settings")
        self.attributes("-topmost", True)
        self.geometry("+140+140")
        self.resizable(False, False)

        self._settings = settings
        self._on_saved = on_saved

        self._other_currencies = sorted(
            (set(store.distinct_currencies()) | set(settings.watched_currencies))
            - set(MAIN_CURRENCIES)
        )
        # Empty watched_currencies means "no filter" (everything is watched,
        # including currencies not seen yet) - reflect that by pre-checking
        # every box shown.
        preselect_all = not settings.watched_currencies

        ctk.CTkLabel(self, text="Currencies to watch",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(14, 2), sticky="w")
        ctk.CTkLabel(self, text="A popup only fires for trades in a checked currency.",
                     font=ctk.CTkFont(size=11), text_color=MUTED).grid(
            row=1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="w")

        ctk.CTkLabel(self, text="Main", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).grid(row=2, column=0, padx=16, sticky="w")
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=3, column=0, columnspan=2, padx=12, sticky="w")
        self._main_vars: dict[str, ctk.BooleanVar] = {}
        for i, ccy in enumerate(MAIN_CURRENCIES):
            var = ctk.BooleanVar(value=preselect_all or ccy in settings.watched_currencies)
            self._main_vars[ccy] = var
            ctk.CTkCheckBox(main_frame, text=ccy, variable=var, width=70).grid(
                row=0, column=i, padx=4, pady=4)

        self._other_vars: dict[str, ctk.BooleanVar] = {}
        if self._other_currencies:
            ctk.CTkLabel(self, text="Other", text_color=MUTED,
                         font=ctk.CTkFont(size=11)).grid(
                row=4, column=0, padx=16, pady=(8, 0), sticky="w")
            rows = (len(self._other_currencies) - 1) // 5 + 1
            other_frame = ctk.CTkScrollableFrame(
                self, fg_color="transparent", width=340, height=min(36 * rows, 108))
            other_frame.grid(row=5, column=0, columnspan=2, padx=12, sticky="w")
            for i, ccy in enumerate(self._other_currencies):
                var = ctk.BooleanVar(value=preselect_all or ccy in settings.watched_currencies)
                self._other_vars[ccy] = var
                ctk.CTkCheckBox(other_frame, text=ccy, variable=var, width=70).grid(
                    row=i // 5, column=i % 5, padx=4, pady=4)

        ctk.CTkLabel(self, text="Minimum spot exposure (USD equivalent)",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=6, column=0, columnspan=2, padx=16, pady=(16, 2), sticky="w")
        ctk.CTkLabel(self, text="A popup only fires when |spot exposure| is at or above this. 0 = always.",
                     font=ctk.CTkFont(size=11), text_color=MUTED).grid(
            row=7, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")

        self._threshold_entry = ctk.CTkEntry(self, width=160)
        self._threshold_entry.insert(0, f"{settings.exposure_threshold_usd:,.0f}")
        self._threshold_entry.grid(row=8, column=0, padx=16, pady=(0, 8), sticky="w")

        self._error_label = ctk.CTkLabel(self, text="", text_color=RED,
                                         font=ctk.CTkFont(size=11))
        self._error_label.grid(row=9, column=0, columnspan=2, padx=16, sticky="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=10, column=0, columnspan=2, padx=16, pady=(4, 14), sticky="e")
        ctk.CTkButton(btns, text="Cancel", width=90, fg_color="transparent",
                     border_width=1, command=self.destroy).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btns, text="Save", width=90, command=self._save).pack(side="right")

    def _save(self) -> None:
        raw = self._threshold_entry.get().strip().replace(",", "")
        try:
            threshold = float(raw) if raw else 0.0
            if threshold < 0:
                raise ValueError
        except ValueError:
            self._error_label.configure(text="Enter a non-negative number.")
            return

        selected = {ccy for ccy, var in {**self._main_vars, **self._other_vars}.items()
                    if var.get()}
        all_known = set(MAIN_CURRENCIES) | set(self._other_currencies)
        if selected == all_known:
            # Every currently-known currency is checked - treat as "no
            # filter" so currencies traded for the first time later are
            # watched too, instead of freezing today's list.
            selected = set()

        self._settings.watched_currencies = selected
        self._settings.exposure_threshold_usd = threshold
        save_popup_settings(self._settings)

        if self._on_saved:
            self._on_saved()
        self.destroy()

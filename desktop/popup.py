"""Trade popups (CustomTkinter). Called only from the UI thread."""

from __future__ import annotations

import customtkinter as ctk

from core.models import Trade, TradeAnalysis

GREEN = "#1fa860"
RED = "#d5453c"
AMBER = "#d78a1f"
MUTED = "gray65"


def _fmt_amount(value: float, ccy: str = "") -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000:
        text = f"{v / 1_000_000:,.2f}M"
    elif v >= 1_000:
        text = f"{v / 1_000:,.0f}k"
    else:
        text = f"{v:,.0f}"
    return f"{sign}{text} {ccy}".strip()


class TradePopup(ctk.CTkToplevel):
    def __init__(self, master, analysis: TradeAnalysis) -> None:
        super().__init__(master)
        a = analysis
        self.title(f"New trade — {a.trade_id}")
        self.attributes("-topmost", True)
        self.geometry("+80+80")
        self.resizable(False, False)

        base_ccy, quote_ccy = a.currency_pair.split("/")

        header = ctk.CTkLabel(
            self,
            text=f"{a.product_type.replace('FX_', '')}  {a.currency_pair}  {a.tenor_label} ({a.tenor_days}d)",
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        header.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 2), sticky="w")

        sub = ctk.CTkLabel(
            self,
            text=f"{a.trade_id}   ·   {a.counterparty}",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        sub.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="w")

        rows: list[tuple[str, str, str | None]] = [
            ("Near / far value date",
             f"{a.near_value_date}  →  {a.far_value_date or '—'}", None),
            ("Spot exposure",
             f"{_fmt_amount(a.spot_exposure_base, base_ccy)}   ({_fmt_amount(a.spot_exposure_usd, 'USD')})",
             None),
            ("Far-leg NPV",
             f"{_fmt_amount(a.npv_far_leg_quote, quote_ccy)}   ({_fmt_amount(a.npv_far_leg_usd, 'USD')})",
             None),
            ("BBG mid (spot / pts / fwd)",
             f"{a.bbg_spot_mid:.5f} / {a.bbg_swap_points_mid:.2f} / {a.bbg_forward_mid:.5f}"
             + ("   [FALLBACK]" if a.mid_fallback else ""),
             AMBER if a.mid_fallback else None),
        ]
        if a.notional_mismatch_base:
            rows.append(
                ("Uneven swap mismatch",
                 _fmt_amount(a.notional_mismatch_base, base_ccy), AMBER)
            )

        r = 2
        for label, value, colour in rows:
            ctk.CTkLabel(self, text=label, text_color=MUTED,
                         font=ctk.CTkFont(size=12)).grid(
                row=r, column=0, padx=(16, 10), pady=2, sticky="w")
            ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=12),
                         text_color=colour or ("gray10", "gray90")).grid(
                row=r, column=1, padx=(0, 16), pady=2, sticky="w")
            r += 1

        pnl_colour = GREEN if a.inception_pnl_usd >= 0 else RED
        ctk.CTkLabel(self, text="Inception PnL",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=r, column=0, padx=(16, 10), pady=(10, 2), sticky="w")
        ctk.CTkLabel(self, text=_fmt_amount(a.inception_pnl_usd, "USD"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=pnl_colour).grid(
            row=r, column=1, padx=(0, 16), pady=(10, 2), sticky="w")
        r += 1

        ctk.CTkLabel(self, text="Combined risk",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=r, column=0, padx=(16, 10), pady=(0, 2), sticky="w")
        ctk.CTkLabel(self, text=_fmt_amount(a.combined_risk_usd, "USD"),
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=r, column=1, padx=(0, 16), pady=(0, 2), sticky="w")
        r += 1

        ctk.CTkButton(self, text="Dismiss", width=90, command=self.destroy).grid(
            row=r, column=1, padx=16, pady=(10, 14), sticky="e")


class DigestPopup(ctk.CTkToplevel):
    """One window listing many trades (bursts / catch-up)."""

    def __init__(self, master, analyses: list[TradeAnalysis], reason: str) -> None:
        super().__init__(master)
        self.title(f"{len(analyses)} trades — {reason}")
        self.attributes("-topmost", True)
        self.geometry("+100+100")

        ctk.CTkLabel(
            self,
            text=f"{len(analyses)} trades ({reason})",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        frame = ctk.CTkScrollableFrame(self, width=560, height=min(60 + 30 * len(analyses), 380))
        frame.pack(padx=12, pady=4, fill="both", expand=True)

        for a in sorted(analyses, key=lambda x: abs(x.spot_exposure_usd), reverse=True):
            colour = GREEN if a.inception_pnl_usd >= 0 else RED
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=f"{a.currency_pair}  {a.tenor_label:>4}  "
                     f"spot {_fmt_amount(a.spot_exposure_usd, 'USD'):>12}",
                font=ctk.CTkFont(size=12, family="Consolas"),
            ).pack(side="left", padx=(6, 10))
            ctk.CTkLabel(
                row,
                text=f"PnL {_fmt_amount(a.inception_pnl_usd, 'USD')}",
                font=ctk.CTkFont(size=12, family="Consolas"),
                text_color=colour,
            ).pack(side="left")
            ctk.CTkLabel(row, text=a.trade_id, text_color=MUTED,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=6)

        ctk.CTkButton(self, text="Dismiss", width=90, command=self.destroy).pack(
            anchor="e", padx=16, pady=(6, 14))


class NoticePopup(ctk.CTkToplevel):
    """Small notification: cancellations/amendments, PnL pending."""

    def __init__(self, master, title: str, message: str) -> None:
        super().__init__(master)
        self.title(title)
        self.attributes("-topmost", True)
        self.geometry("+120+120")
        self.resizable(False, False)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=12),
                     text_color=MUTED, wraplength=380, justify="left").pack(
            anchor="w", padx=16, pady=2)
        ctk.CTkButton(self, text="OK", width=70, command=self.destroy).pack(
            anchor="e", padx=16, pady=(10, 14))
        self.after(15_000, self.destroy)


def notice_for_removal(master, trade: Trade, detail: str) -> NoticePopup:
    return NoticePopup(
        master,
        title="Trade removed",
        message=f"{trade.trade_id} ({trade.currency_pair}) {detail}.",
    )

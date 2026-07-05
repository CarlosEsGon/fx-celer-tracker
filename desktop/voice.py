"""Voice announcer: pyttsx3 (Windows SAPI) on its own worker thread.

Speech is queued so the UI never blocks; new-trade announcements only —
never for heartbeats, reconnects, or removals.
"""

from __future__ import annotations

import logging
import queue
import threading

from core.models import TradeAnalysis

log = logging.getLogger(__name__)

_TENOR_WORDS = {
    "ON": "overnight", "TN": "tom next",
    "1W": "one week", "2W": "two week",
    "1M": "one month", "2M": "two month", "3M": "three month",
    "6M": "six month", "9M": "nine month", "1Y": "one year",
    ">1Y": "beyond one year",
}


def _spoken_amount(value: float, unit: str) -> str:
    sign = "negative " if value < 0 else ""
    v = abs(value)
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:.1f} billion {unit}"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.1f} million {unit}"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.0f} thousand {unit}"
    return f"{sign}{v:.0f} {unit}"


def trade_summary(a: TradeAnalysis) -> str:
    pair_spoken = a.currency_pair.replace("/", " ")
    tenor = _TENOR_WORDS.get(a.tenor_label, a.tenor_label)
    product = "swap" if a.product_type == "FX_SWAP" else "outright"
    base_ccy = a.currency_pair.split("/")[0]
    parts = [
        f"New {pair_spoken} {tenor} {product}.",
        f"Spot exposure {_spoken_amount(a.spot_exposure_base, base_ccy)}.",
        f"Inception P and L {_spoken_amount(a.inception_pnl_usd, 'dollars')}.",
        f"Combined risk {_spoken_amount(a.combined_risk_usd, 'dollars')}.",
    ]
    if a.mid_fallback:
        parts.append("Mid is a fallback quote.")
    return " ".join(parts)


def digest_summary(analyses: list[TradeAnalysis], reason: str) -> str:
    biggest = max(analyses, key=lambda x: abs(x.spot_exposure_usd))
    return (
        f"{len(analyses)} trades {reason}. Largest: "
        f"{biggest.currency_pair.replace('/', ' ')} {_TENOR_WORDS.get(biggest.tenor_label, biggest.tenor_label)}, "
        f"spot exposure {_spoken_amount(biggest.spot_exposure_usd, 'dollars')}."
    )


class VoiceAnnouncer:
    def __init__(self, enabled: bool = True, rate_wpm: int = 175) -> None:
        self.enabled = enabled
        self._rate = rate_wpm
        self._queue: "queue.Queue[str | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="voice", daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        if self.enabled:
            self._queue.put(text)

    def stop(self) -> None:
        self._queue.put(None)

    def _run(self) -> None:
        try:
            import pyttsx3
        except Exception:
            log.warning("pyttsx3 unavailable — voice disabled")
            self.enabled = False
            return
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
        except Exception:
            log.exception("TTS engine init failed — voice disabled")
            self.enabled = False
            return

        while True:
            text = self._queue.get()
            if text is None:
                return
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                log.exception("TTS failed for: %.80s", text)

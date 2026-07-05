"""Market data providers.

Contract: get_mid(pair, value_date, as_of) returns the mid spot / swap points /
forward for the trade's exact (broken) value date AS OF the trade's execution
time. The quote comes directly from the source — never interpolated locally.

- MockBloombergProvider: calls the mock server's /bbg/mid endpoint.
- BlpapiProvider: real Bloomberg Desktop API. Retrieval chain (each step falls
  through to the next; steps 2-3 set fallback=True):
    1. IntradayTickRequest on the broken-date ticker "CCY1/CCY2 MM/DD/YY Curncy"
       around booked_at -> mid from nearest BID/ASK ticks
    2. IntradayTickRequest on the spot ticker at booked_at + CURRENT broken-date
       forward points via ReferenceDataRequest
    3. Current ReferenceDataRequest mid on the broken-date ticker
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone

import httpx

from core.fx import pip_factor
from core.models import MidSnapshot

log = logging.getLogger(__name__)


class MarketDataError(Exception):
    pass


class MarketDataProvider(ABC):
    @abstractmethod
    def get_mid(self, pair: str, value_date: date, as_of: datetime) -> MidSnapshot: ...

    @abstractmethod
    def get_fx_rates(self) -> dict[str, float]: ...

    @abstractmethod
    def get_discount_rate(self, currency: str) -> float: ...


# --------------------------------------------------------------------------- #
# Mock provider (local dev)
# --------------------------------------------------------------------------- #


class MockBloombergProvider(MarketDataProvider):
    def __init__(self, rest_url: str, timeout: float = 5.0) -> None:
        self._base = rest_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def get_mid(self, pair: str, value_date: date, as_of: datetime) -> MidSnapshot:
        resp = self._client.get(
            f"{self._base}/bbg/mid",
            params={
                "pair": pair,
                "value_date": value_date.isoformat(),
                "as_of": as_of.isoformat(),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return MidSnapshot(**data, fallback=False)

    def get_fx_rates(self) -> dict[str, float]:
        resp = self._client.get(f"{self._base}/fx-rates")
        resp.raise_for_status()
        return resp.json()

    def get_discount_rate(self, currency: str) -> float:
        resp = self._client.get(f"{self._base}/curves/{currency}")
        resp.raise_for_status()
        return resp.json()["rate"]


# --------------------------------------------------------------------------- #
# Real Bloomberg Desktop API provider
# --------------------------------------------------------------------------- #


class BlpapiProvider(MarketDataProvider):
    """Point-in-time broken-date mids from a local Bloomberg terminal.

    blpapi is imported lazily so the package is only needed when this provider
    is selected (MARKET_DATA=blpapi). First run: scripts/bbg_probe.py.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8194,
        tick_window_sec: int = 120,
        discount_rates: dict[str, float] | None = None,
    ) -> None:
        import blpapi  # noqa: F401 — fail fast if unavailable

        self._blpapi = blpapi
        self._tick_window = timedelta(seconds=tick_window_sec)
        self._discount_rates = discount_rates or {}

        opts = blpapi.SessionOptions()
        opts.setServerHost(host)
        opts.setServerPort(port)
        opts.setAutoRestartOnDisconnection(True)
        self._session = blpapi.Session(opts)
        if not self._session.start():
            raise MarketDataError(f"Cannot start blpapi session ({host}:{port})")
        if not self._session.openService("//blp/refdata"):
            raise MarketDataError("Cannot open //blp/refdata")
        self._refdata = self._session.getService("//blp/refdata")
        log.info("blpapi session started (%s:%s)", host, port)

    # ---- ticker construction ------------------------------------------------

    @staticmethod
    def _spot_ticker(pair: str) -> str:
        return f"{pair.replace('/', '').upper()} Curncy"

    @staticmethod
    def _broken_date_ticker(pair: str, value_date: date) -> str:
        # DAPI "FX Broken Dates Forwards Syntax": CCY1/CCY2 MM/DD/YY Curncy
        p = pair.replace(" ", "").upper()
        if "/" not in p:
            p = f"{p[:3]}/{p[3:]}"
        return f"{p} {value_date.strftime('%m/%d/%y')} Curncy"

    # ---- low-level requests --------------------------------------------------

    def _collect_response(self):
        """Yield messages until the final RESPONSE event."""
        while True:
            event = self._session.nextEvent(10_000)
            for msg in event:
                yield msg
            if event.eventType() == self._blpapi.Event.RESPONSE:
                return
            if event.eventType() == self._blpapi.Event.TIMEOUT:
                raise MarketDataError("blpapi request timed out")

    def _tick_mid_at(self, security: str, as_of: datetime) -> float | None:
        """Mid from BID/ASK ticks nearest to as_of, or None if no ticks."""
        as_of_utc = as_of.astimezone(timezone.utc)
        request = self._refdata.createRequest("IntradayTickRequest")
        request.set("security", security)
        for etype in ("BID", "ASK"):
            request.getElement("eventTypes").appendValue(etype)
        # All IntradayTickRequest times are GMT
        request.set("startDateTime", (as_of_utc - self._tick_window).strftime("%Y-%m-%dT%H:%M:%S"))
        request.set("endDateTime", (as_of_utc + self._tick_window).strftime("%Y-%m-%dT%H:%M:%S"))
        self._session.sendRequest(request)

        best: dict[str, tuple[float, float]] = {}  # type -> (abs_dt_seconds, value)
        for msg in self._collect_response():
            if not msg.hasElement("tickData"):
                continue
            tick_data = msg.getElement("tickData").getElement("tickData")
            for tick in tick_data.values():
                t_type = tick.getElementAsString("type")
                t_time = tick.getElementAsDatetime("time")
                t_val = tick.getElementAsFloat("value")
                t_dt = datetime(
                    t_time.year, t_time.month, t_time.day,
                    t_time.hour, t_time.minute, t_time.second,
                    tzinfo=timezone.utc,
                )
                dist = abs((t_dt - as_of_utc).total_seconds())
                if t_type not in best or dist < best[t_type][0]:
                    best[t_type] = (dist, t_val)

        if "BID" in best and "ASK" in best:
            return (best["BID"][1] + best["ASK"][1]) / 2
        if best:
            return next(iter(best.values()))[1]
        return None

    def _reference_mid(self, security: str, quote_format: str | None = None) -> float | None:
        """Current PX_BID/PX_ASK mid via ReferenceDataRequest."""
        request = self._refdata.createRequest("ReferenceDataRequest")
        request.getElement("securities").appendValue(security)
        for field in ("PX_BID", "PX_ASK", "PX_MID"):
            request.getElement("fields").appendValue(field)
        if quote_format:
            override = request.getElement("overrides").appendElement()
            override.setElement("fieldId", "FWD_CURVE_QUOTE_FORMAT")
            override.setElement("value", quote_format)
        self._session.sendRequest(request)

        bid = ask = mid = None
        for msg in self._collect_response():
            if not msg.hasElement("securityData"):
                continue
            for sec in msg.getElement("securityData").values():
                if sec.hasElement("securityError"):
                    log.warning("securityError for %s: %s", security, sec)
                    return None
                fields = sec.getElement("fieldData")
                if fields.hasElement("PX_MID"):
                    mid = fields.getElementAsFloat("PX_MID")
                if fields.hasElement("PX_BID"):
                    bid = fields.getElementAsFloat("PX_BID")
                if fields.hasElement("PX_ASK"):
                    ask = fields.getElementAsFloat("PX_ASK")
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return mid

    # ---- public API -----------------------------------------------------------

    def get_mid(self, pair: str, value_date: date, as_of: datetime) -> MidSnapshot:
        pip = pip_factor(pair if "/" in pair else f"{pair[:3]}/{pair[3:]}")
        broken_ticker = self._broken_date_ticker(pair, value_date)
        spot_ticker = self._spot_ticker(pair)

        # Step 1: point-in-time ticks on the broken-date ticker
        forward = self._tick_mid_at(broken_ticker, as_of)
        spot = self._tick_mid_at(spot_ticker, as_of)
        fallback = False

        if forward is None:
            # Step 2: point-in-time spot + CURRENT broken-date forward points
            log.info("no tick history for %s; falling back to spot ticks + current points", broken_ticker)
            fallback = True
            points = self._reference_mid(broken_ticker, quote_format="POINTS")
            if spot is not None and points is not None:
                forward = spot + points * pip
            else:
                # Step 3: current outright mid on the broken-date ticker
                log.info("falling back to current reference mid for %s", broken_ticker)
                forward = self._reference_mid(broken_ticker, quote_format="OUTRIGHT")
                if spot is None:
                    spot = self._reference_mid(spot_ticker)

        if forward is None or spot is None:
            raise MarketDataError(
                f"Bloomberg returned no usable mid for {broken_ticker} as of {as_of}"
            )

        return MidSnapshot(
            pair=pair,
            value_date=value_date,
            spot_mid=spot,
            swap_points_mid=(forward - spot) / pip,
            forward_mid=forward,
            as_of=as_of,
            fallback=fallback,
        )

    def get_fx_rates(self) -> dict[str, float]:
        """Current spot mids for USD conversion of the pairs we care about."""
        rates: dict[str, float] = {}
        for key in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"):
            mid = self._reference_mid(f"{key} Curncy")
            if mid is not None:
                rates[key] = mid
        return rates

    def get_discount_rate(self, currency: str) -> float:
        # Flat per-currency rates from config in v1 (see settings.yaml);
        # swap for curve retrieval in v2.
        return self._discount_rates.get(
            currency.upper(), self._discount_rates.get("default", 0.03)
        )

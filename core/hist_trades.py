"""/histTrades adapter: parse the real trade endpoint into internal Trades.

Implements the verified field specification for GET <host>/histTrades:

  - all prices/points/quantities are ints scaled by 1e6
  - "NaN" strings are nulls; "-999999999-01-01" is a null date;
    0 in spot_base_qty/swap_qty on SWAPs means "not populated"
  - near_leg_qty/far_leg_qty are denominated in the `currency` field, which
    may be the pair's base OR terms currency — never assume
  - base notional: qty (if dealt in base) or qty / all-in rate (if in terms)
  - productType is the only product classifier (SPOT | FORWARD | SWAP);
    SPOT records and any CAD-cross record are skipped as not relevant
  - leg-level sides come from near_leg_side/far_leg_side; trade_side is NOT
    interchangeable with them (observed matching the FAR leg on swaps)
  - do not derive logic from: swap_qty, new_terms_qty, trader_price, u1*/u2*,
    merchantOrderType, clob_type, priceSource (parsed + persisted only, via
    Trade.extras)

Validation checks are emitted as warnings, never hard failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Optional

from core.models import Leg, ProductType, Trade

log = logging.getLogger(__name__)

SCALE = 1_000_000
DATE_SENTINEL = "-999999999-01-01"

# ignore-field audit (§4.6): log any value never seen before
_KNOWN_IGNORE_VALUES: set[str] = {"N", "IS_SWAP"}
_seen_ignore_values: set[str] = set()


# --------------------------------------------------------------------------- #
# Primitive parsers
# --------------------------------------------------------------------------- #


def parse_scaled(value: Any) -> Optional[float]:
    """Scaled numeric field: int -> value/1e6; "NaN"/None/"" -> None."""
    if value is None or value == "NaN" or value == "":
        return None
    return float(value) / SCALE


def parse_date_opt(value: Any) -> Optional[date]:
    if not value or value == DATE_SENTINEL:
        return None
    return date.fromisoformat(value)


def parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_reference_rate(value: Any) -> Optional[tuple[str, float]]:
    """"GBP/USD:1.3337949999999998" -> ("GBP/USD", 1.333795). Unscaled."""
    if not value or ":" not in str(value):
        return None
    pair, _, rate = str(value).partition(":")
    try:
        return pair, round(float(rate), 8)
    except ValueError:
        return None


def parse_m0_age_ms(value: Any) -> Optional[float]:
    """{"j": 512000000} (nanoseconds) -> 512.0 ms."""
    if isinstance(value, dict) and "j" in value and value["j"] is not None:
        try:
            return float(value["j"]) / 1e6
        except (TypeError, ValueError):
            return None
    return None


def _track_ignore_value(value: Any) -> None:
    text = str(value)
    if text in _seen_ignore_values:
        return
    _seen_ignore_values.add(text)
    if text not in _KNOWN_IGNORE_VALUES:
        log.warning("histTrades: new `ignore` value observed: %r", text)


# --------------------------------------------------------------------------- #
# Record -> Trade
# --------------------------------------------------------------------------- #


@dataclass
class ParsedRecord:
    trade: Trade
    warnings: list[str] = field(default_factory=list)


def _signed_base_amount(
    dealt_qty: float,
    side: str,
    dealt_ccy: str,
    base_ccy: str,
    all_in_rate: float,
) -> float:
    """Base-currency notional per §1.4, signed by the leg side (SELL base < 0)."""
    base = dealt_qty if dealt_ccy == base_ccy else dealt_qty / all_in_rate
    return base if side == "BUY" else -base


def _build_leg(
    value_date: date,
    dealt_qty: float,
    side: str,
    dealt_ccy: str,
    base_ccy: str,
    all_in_rate: float,
) -> Leg:
    base_amount = _signed_base_amount(dealt_qty, side, dealt_ccy, base_ccy, all_in_rate)
    return Leg(
        value_date=value_date,
        base_amount=base_amount,
        quote_amount=-base_amount * all_in_rate,
        rate=all_in_rate,
    )


def _validate(rec: dict, warnings: list[str]) -> None:
    """§5 consistency checks — warnings only."""
    def close(a: Optional[float], b: Optional[float], tol: float = 1e-9) -> bool:
        return a is not None and b is not None and abs(a - b) <= tol

    product = rec.get("productType", "")
    pair = rec.get("securityId", "")
    base_ccy = pair.split("/")[0] if "/" in pair else ""
    terms_ccy = pair.split("/")[1] if "/" in pair else ""

    near_spot = parse_scaled(rec.get("near_leg_spot"))
    near_points = parse_scaled(rec.get("near_leg_points"))
    near_price = parse_scaled(rec.get("near_leg_price"))
    if near_spot is not None and near_points is not None and near_price is not None:
        if not close(near_price, near_spot + near_points, tol=1e-6):
            warnings.append(
                f"near_leg_price {near_price} != spot+points {near_spot + near_points}"
            )

    far_spot = parse_scaled(rec.get("far_leg_spot"))
    far_points = parse_scaled(rec.get("far_leg_points"))
    far_price = parse_scaled(rec.get("far_leg_price"))
    if far_spot is not None and far_points is not None and far_price is not None:
        if not close(far_price, far_spot + far_points, tol=1e-6):
            warnings.append(
                f"far_leg_price {far_price} != spot+points {far_spot + far_points}"
            )

    if rec.get("base") and base_ccy and rec["base"] != base_ccy:
        warnings.append(f"base {rec['base']} != securityId base {base_ccy}")

    dealt = rec.get("currency", "")
    if dealt and dealt not in (base_ccy, terms_ccy):
        warnings.append(f"currency {dealt} not in pair {pair}")

    if product in ("SPOT", "FORWARD"):
        if parse_date_opt(rec.get("far_leg_settlementDate")) is not None:
            warnings.append(f"{product} has a far_leg_settlementDate")
        near_qty = parse_scaled(rec.get("near_leg_qty"))
        spot_base = parse_scaled(rec.get("spot_base_qty"))
        if (
            dealt == terms_ccy
            and near_qty is not None
            and near_spot
            and spot_base is not None
            and spot_base != 0
        ):
            expected = near_qty / near_spot
            if abs(abs(spot_base) - expected) > max(1.0, expected * 1e-4):
                warnings.append(
                    f"|spot_base_qty| {abs(spot_base):.0f} != near_qty/spot {expected:.0f}"
                )
        if spot_base is not None and spot_base != 0:
            side = rec.get("near_leg_side", "")
            if (spot_base < 0) != (side == "SELL"):
                warnings.append(
                    f"spot_base_qty sign {spot_base:.0f} inconsistent with near_leg_side {side}"
                )
    elif product == "SWAP":
        if parse_date_opt(rec.get("far_leg_settlementDate")) is None:
            warnings.append("SWAP without far_leg_settlementDate")
        if rec.get("near_leg_side") == rec.get("far_leg_side"):
            warnings.append("SWAP legs have the same side")


def parse_record(rec: dict) -> Optional[ParsedRecord]:
    """Parse one /histTrades record. Returns None for unusable records."""
    warnings: list[str] = []
    product = rec.get("productType", "")

    if product not in ("SPOT", "FORWARD", "SWAP"):
        log.warning("histTrades: unknown productType %r (id=%s) — skipped",
                    product, rec.get("id"))
        return None

    if product == "SPOT":
        log.debug("histTrades: SPOT record %s not relevant — skipped", rec.get("id"))
        return None

    pair_ccys = str(rec.get("securityId", "")).split("/")
    if "CAD" in pair_ccys:
        log.debug("histTrades: CAD pair %s (id=%s) not relevant — skipped",
                   rec.get("securityId"), rec.get("id"))
        return None

    _track_ignore_value(rec.get("ignore", ""))
    _validate(rec, warnings)

    try:
        pair = rec["securityId"]
        base_ccy, terms_ccy = pair.split("/")
        dealt_ccy = rec["currency"]
        booked_at = parse_datetime(rec["time"])
        near_date = parse_date_opt(rec.get("near_leg_settlementDate"))
        near_qty = parse_scaled(rec.get("near_leg_qty"))
        near_price = parse_scaled(rec.get("near_leg_price"))
        near_side = rec.get("near_leg_side", "")

        if near_date is None or near_qty is None or near_price is None or not near_side:
            log.warning("histTrades: record %s missing near-leg essentials — skipped",
                        rec.get("id"))
            return None

        counterparty = (
            rec.get("destinationKey") or rec.get("stream_code") or rec.get("account") or ""
        )

        common = dict(
            trade_id=rec["id"],
            currency_pair=pair,
            base_currency=base_ccy,
            quote_currency=terms_ccy,
            trade_date=booked_at.date(),
            counterparty=counterparty,
            booked_at=booked_at,
            extras=rec,
        )

        if product == "SWAP":
            far_date = parse_date_opt(rec.get("far_leg_settlementDate"))
            far_qty = parse_scaled(rec.get("far_leg_qty"))
            far_price = parse_scaled(rec.get("far_leg_price"))
            far_side = rec.get("far_leg_side", "")
            if far_date is None or far_qty is None or far_price is None or not far_side:
                log.warning("histTrades: SWAP %s missing far-leg essentials — skipped",
                            rec.get("id"))
                return None
            trade = Trade(
                product_type=ProductType.FX_SWAP,
                near_leg=_build_leg(near_date, near_qty, near_side,
                                    dealt_ccy, base_ccy, near_price),
                far_leg=_build_leg(far_date, far_qty, far_side,
                                   dealt_ccy, base_ccy, far_price),
                **common,
            )
        else:  # SPOT and FORWARD are both single-leg outrights internally
            trade = Trade(
                product_type=ProductType.FX_OUTRIGHT,
                leg=_build_leg(near_date, near_qty, near_side,
                               dealt_ccy, base_ccy, near_price),
                **common,
            )
    except (KeyError, ValueError, TypeError) as exc:
        log.exception("histTrades: unparseable record (id=%s): %s", rec.get("id"), exc)
        return None

    for w in warnings:
        log.warning("histTrades validation (%s): %s", rec.get("id"), w)
    return ParsedRecord(trade=trade, warnings=warnings)


# --------------------------------------------------------------------------- #
# Polling feed
# --------------------------------------------------------------------------- #


class HistTradesFeed:
    """TradeFeed over GET /histTrades (poll + dedupe downstream).

    The endpoint returns the full history each call; the listener's persistent
    (trade_id, version) dedupe makes re-yields harmless. The first successful
    poll (and the first after any outage) is delivered as catch-up so the UI
    shows a digest instead of one popup per historical trade.
    """

    def __init__(self, url: str, poll_interval_sec: float = 2.0) -> None:
        self._url = url
        self._interval = poll_interval_sec
        self._since: Optional[datetime] = None  # kept for interface parity

    def set_catchup_since(self, since: Optional[datetime]) -> None:
        self._since = since

    async def events(self) -> AsyncIterator["FeedEvent"]:
        import asyncio

        import httpx

        from core.trade_feed import FeedEvent

        backoff = 1.0
        catchup_mode = True
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                try:
                    resp = await client.get(self._url)
                    resp.raise_for_status()
                    records = resp.json()
                except Exception as exc:
                    log.warning("histTrades poll failed (%s); retry in %.1fs", exc, backoff)
                    yield FeedEvent(kind="status", status="reconnecting", detail=str(exc))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    catchup_mode = True  # digest whatever accrued during the outage
                    continue

                backoff = 1.0
                if catchup_mode:
                    yield FeedEvent(kind="status", status="catching_up")

                if not isinstance(records, list):
                    log.warning("histTrades: expected a JSON array, got %s", type(records))
                    records = []

                for rec in records:
                    parsed = parse_record(rec) if isinstance(rec, dict) else None
                    if parsed is None:
                        continue
                    yield FeedEvent(kind="trade", trade=parsed.trade, catchup=catchup_mode)

                if catchup_mode:
                    yield FeedEvent(kind="status", status="connected")
                    catchup_mode = False

                await asyncio.sleep(self._interval)

"""Day-1 Bloomberg smoke test — run this FIRST at the terminal.

    python scripts/bbg_probe.py EUR/USD 2026-10-07 --as-of "2026-07-05T14:30:00Z"

Walks the exact retrieval chain the app uses and prints raw results per step:
  1. IntradayTickRequest on the broken-date ticker around as_of
  2. IntradayTickRequest on the spot ticker + current forward points
  3. Current ReferenceDataRequest mid on the broken-date ticker

Requires: Bloomberg terminal logged in, Desktop API on localhost:8194, and
  pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bloomberg broken-date mid probe")
    parser.add_argument("pair", help="e.g. EUR/USD")
    parser.add_argument("value_date", help="YYYY-MM-DD (broken dates fine)")
    parser.add_argument("--as-of", default=None,
                        help="ISO timestamp (default: now UTC)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8194)
    parser.add_argument("--window", type=int, default=120,
                        help="tick search window seconds (default 120)")
    args = parser.parse_args()

    value_date = date.fromisoformat(args.value_date)
    as_of = (
        datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if args.as_of else datetime.now(timezone.utc)
    )

    print(f"pair={args.pair}  value_date={value_date}  as_of={as_of.isoformat()}")
    print(f"connecting to {args.host}:{args.port} ...")

    try:
        from core.market_data import BlpapiProvider, MarketDataError
    except ImportError as exc:
        print(f"FATAL: cannot import provider: {exc}")
        return 2

    try:
        provider = BlpapiProvider(
            host=args.host, port=args.port, tick_window_sec=args.window
        )
    except Exception as exc:
        print(f"FATAL: blpapi session failed: {exc}")
        print("Checks: terminal logged in? Desktop API enabled? blpapi installed?")
        return 2

    broken = provider._broken_date_ticker(args.pair, value_date)
    spot = provider._spot_ticker(args.pair)
    print(f"\nbroken-date ticker: {broken!r}\nspot ticker:        {spot!r}\n")

    print("--- step 1: point-in-time ticks on broken-date ticker ---")
    fwd_tick = provider._tick_mid_at(broken, as_of)
    print(f"    -> {fwd_tick}")

    print("--- step 1b: point-in-time ticks on spot ticker ---")
    spot_tick = provider._tick_mid_at(spot, as_of)
    print(f"    -> {spot_tick}")

    print("--- step 2: current forward POINTS on broken-date ticker ---")
    points = provider._reference_mid(broken, quote_format="POINTS")
    print(f"    -> {points}")

    print("--- step 3: current OUTRIGHT mid on broken-date ticker ---")
    outright = provider._reference_mid(broken, quote_format="OUTRIGHT")
    print(f"    -> {outright}")

    print("\n--- full get_mid() as the app calls it ---")
    try:
        mid = provider.get_mid(args.pair, value_date, as_of)
        print(f"    spot_mid        = {mid.spot_mid}")
        print(f"    swap_points_mid = {mid.swap_points_mid}")
        print(f"    forward_mid     = {mid.forward_mid}")
        print(f"    fallback        = {mid.fallback}")
        print("\nOK — provider is usable. Set MARKET_DATA=blpapi in .env.")
        return 0
    except MarketDataError as exc:
        print(f"    FAILED: {exc}")
        print("Inspect the step outputs above to see which leg returned nothing.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

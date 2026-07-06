"""Day-1 probe for the real /histTrades endpoint.

    python scripts/hist_probe.py
    python scripts/hist_probe.py --url http://localhost:8051/histTrades --raw

Fetches the array, parses every record through the production adapter, and
prints a per-trade summary plus any validation warnings. Also saves the raw
payload to data/hist_trades_raw.json for offline inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from core.hist_trades import parse_record  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="histTrades endpoint probe")
    parser.add_argument("--url", default="http://localhost:8051/histTrades")
    parser.add_argument("--raw", action="store_true", help="print raw records too")
    parser.add_argument("--out", default="data/hist_trades_raw.json")
    args = parser.parse_args()

    print(f"GET {args.url} ...")
    try:
        resp = httpx.get(args.url, timeout=10.0)
        resp.raise_for_status()
        records = resp.json()
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 2

    if not isinstance(records, list):
        print(f"Unexpected payload type: {type(records)} — expected JSON array")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"{len(records)} record(s); raw payload saved to {out}\n")

    ok = skipped = warned = 0
    product_types: dict[str, int] = {}
    for rec in records:
        pt = rec.get("productType", "?") if isinstance(rec, dict) else "?"
        product_types[pt] = product_types.get(pt, 0) + 1
        parsed = parse_record(rec) if isinstance(rec, dict) else None
        if parsed is None:
            skipped += 1
            print(f"  SKIPPED  {rec.get('id', '?') if isinstance(rec, dict) else rec}")
            continue
        t = parsed.trade
        ok += 1
        legs = (
            f"near {t.near_leg.base_amount:,.0f} @ {t.near_leg.rate} / "
            f"far {t.far_leg.base_amount:,.0f} @ {t.far_leg.rate}"
            if t.product_type.value == "FX_SWAP"
            else f"leg {t.leg.base_amount:,.0f} @ {t.leg.rate}"
        )
        print(f"  {t.trade_id}  {t.product_type.value:11s} {t.currency_pair}  {legs}")
        if args.raw:
            print(f"    raw: {json.dumps(rec)[:300]}")
        for w in parsed.warnings:
            warned += 1
            print(f"    WARNING: {w}")

    print(f"\nproduct types: {product_types}")
    print(f"parsed OK: {ok}   skipped: {skipped}   warnings: {warned}")
    print("\nIf this looks right, set TRADE_FEED=histtrades in .env and launch the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

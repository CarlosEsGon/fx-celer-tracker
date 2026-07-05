"""Day-1 Celer websocket probe — capture real frames before wiring the feed.

    python scripts/celer_probe.py --frames 20

Reads CELER_WS_URL (+ auth header) from .env, connects, and dumps the first N
raw frames to data/celer_frames.jsonl. Compare the captured frames against
RealCelerFeed._parse_frame in core/trade_feed.py and adjust the mapping —
that method is the only code expected to change on day 1.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_settings  # noqa: E402


async def probe(ws_url: str, headers: dict, n_frames: int, out_path: Path, timeout: float) -> int:
    import websockets

    print(f"connecting to {ws_url} ...")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    captured = 0
    try:
        async with websockets.connect(
            ws_url, additional_headers=headers or None, ping_interval=20
        ) as ws:
            print(f"connected. waiting for {n_frames} frame(s), timeout {timeout:.0f}s each ...")
            with open(out_path, "a", encoding="utf-8") as fh:
                while captured < n_frames:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        print(f"no frame within {timeout:.0f}s — is anything trading? "
                              f"({captured} captured so far)")
                        continue
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    fh.write(raw.strip() + "\n")
                    fh.flush()
                    captured += 1
                    preview = raw[:160].replace("\n", " ")
                    print(f"[{captured}/{n_frames}] {preview}{'…' if len(raw) > 160 else ''}")
    except KeyboardInterrupt:
        print("\ninterrupted.")
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print("Checks: URL correct? auth header set in .env? VPN/network reachable?")
        return 2

    print(f"\n{captured} frame(s) written to {out_path}")
    print("Next: compare frames with RealCelerFeed._parse_frame (core/trade_feed.py).")
    return 0 if captured else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Celer websocket frame capture")
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="seconds to wait per frame (default 60)")
    parser.add_argument("--url", default=None, help="override CELER_WS_URL")
    parser.add_argument("--out", default="data/celer_frames.jsonl")
    args = parser.parse_args()

    settings = load_settings()
    ws_url = args.url or settings.celer_ws_url
    if not ws_url:
        print("FATAL: no websocket URL. Set CELER_WS_URL in .env or pass --url.")
        return 2
    headers = (
        {settings.celer_auth_header_name: settings.celer_auth_header_value}
        if settings.celer_auth_header_value else {}
    )
    return asyncio.run(probe(ws_url, headers, args.frames, Path(args.out), args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())

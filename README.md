# FX Trade Tracker

Desktop tracker for FX swaps, forwards, and spot trades. Consumes a trade feed
(the verified real source is a REST endpoint, `GET /histTrades`), computes
tenor, spot exposure, far-leg NPV, and inception PnL versus the Bloomberg mid
at execution time, stores every trade + analysis in SQLite, and alerts via a
desktop popup and optional voice summary.

Runs fully locally against a **mock server** and **mock Bloomberg mids**.
Switching to the real trade endpoint and a real Bloomberg terminal is an
`.env` change, not a code change.

## Trade feeds (selected via `TRADE_FEED` in `.env`)

| Feed | Value | Transport | Status |
|------|-------|-----------|--------|
| histTrades | `histtrades` | REST poll of `GET http://localhost:8051/histTrades` (full array, persistent dedupe) | **Verified against real payloads** — the production feed |
| Mock | `mock` | Local FastAPI websocket + REST (`mock_celer/`) | For local dev/demo |
| Celer websocket | `celer` | Websocket with config-driven URL/auth | Speculative fallback if a push feed becomes available |

### histTrades wire format (implemented in `core/hist_trades.py`)

The parser implements the documented, payload-verified specification:

- **Scaling:** every price/points/quantity is an integer ×1e6 (`1334635` → 1.334635)
- **Null sentinels:** string `"NaN"` on numerics, `"-999999999-01-01"` on far-leg
  dates, `0` meaning "unpopulated" for `spot_base_qty`/`swap_qty` on SWAPs,
  empty strings on text fields
- **Quantity denomination:** `near_leg_qty`/`far_leg_qty` follow the `currency`
  field, which can be the pair's **base or terms** currency — never assumed
- **Base notional:** dealt in base → the quantity itself; dealt in terms →
  quantity ÷ **all-in rate** (`near_leg_price`). `spot_base_qty` is never used
  for notionals (it is the spot-rate decomposition, not the settling amount)
- **Classification:** `productType` only (`SPOT`/`FORWARD` → single-leg
  outright, `SWAP` → two legs). Leg direction from `near_leg_side`/
  `far_leg_side`; `trade_side` is never used for leg logic
- **Never derived from:** `swap_qty` (0 even on real swaps), `new_terms_qty`,
  `trader_price`, `u1*`/`u2*`, tenor codes (`"B"` appears on everything —
  dating uses settlement dates only)
- **Audit:** the full raw record is preserved on each trade (`Trade.extras`)
  and lands in SQLite; §5 validation checks (price = spot + points,
  spot_base_qty magnitude/sign, side consistency, sentinel presence per
  product) are logged as warnings, never hard failures; new `ignore` values
  are logged on first sight

## Quick start (local, mock everything)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env

# Terminal 1 - mock server (websocket feed + REST + mock BBG mids)
uvicorn mock_celer.server:app --reload --port 8000

# Terminal 2 - desktop tracker
python -m desktop.app

# Inject a test trade (broadcast over the websocket feed)
curl -X POST http://localhost:8000/trades -H "Content-Type: application/json" -d @mock_celer/sample_trade_swap.json
```

Expected: a popup appears immediately with the trade's tenor, spot exposure,
far-leg NPV, Bloomberg mid comparison, and inception PnL; voice reads a summary.

## Run the tests

```bash
pytest
```

Covers tenor bucketing, ACT/360 discounting, FX conversion (direct, inverse,
cross triangulation), exposure (incl. uneven swaps), inception PnL (swap
points, outright forward, uneven leg-by-leg, direction flips), deterministic
mock mids, SQLite round-trips and lifecycle, feed parsing, and the histTrades
parser tested against the two documented real payloads (GBP/USD forward dealt
in terms, AUD/USD T/N swap dealt in base).

## Analytics conventions

| Area | Convention |
|------|------------|
| Products | `FX_SWAP` (near + far legs), `FX_OUTRIGHT` (single leg — SPOT and FORWARD both map here) |
| Tenor | Calendar days near→far value date (swap) or valuation→value date (outright), bucketed ON…1Y, >1Y |
| Spot exposure | Signed base notional of the near leg (swap) or the single leg (outright); uneven-swap mismatch surfaced separately |
| Far-leg NPV | Quote-ccy cash flow discounted with ACT/360 money-market DF: `DF = 1/(1 + r*d/360)` |
| Valuation date | `trade_date` (configurable to spot in `config/settings.yaml`) |
| Bloomberg mid | Per trade: pair + exact (broken) value date + `booked_at` timestamp. Point-in-time, quoted directly by the source — never interpolated locally |
| Inception PnL | Traded rate vs mid at execution, discounted; swaps on swap points, outrights on forward rate; uneven swaps priced leg-by-leg |
| Lifecycle | Only `NEW` analysed. `AMENDED` is treated as `CANCELLED`: trade removed from tracking, audit row kept (websocket feeds; histTrades has no lifecycle fields) |
| Persistence | SQLite `data/trades.db`: raw trade (incl. full source record), analysis, BBG mid snapshot, inception PnL; CSV export helper |

## Day 1 at work — real connection runbook

1. **Install deps** (corporate proxy permitting):

   ```bash
   pip install -r requirements.txt
   pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/
   ```

2. **Probe Bloomberg first** (terminal must be logged in; Desktop API listens on
   `localhost:8194`):

   ```bash
   python scripts/bbg_probe.py EUR/USD 2026-10-07 --as-of "2026-07-05T14:30:00Z"
   ```

   Prints each step of the retrieval chain (broken-date ticks → spot ticks +
   current points → current reference mid) with raw responses. Fix
   connectivity/permission issues here before touching the app.

3. **Probe the trade endpoint**:

   ```bash
   python scripts/hist_probe.py
   ```

   Fetches `GET http://localhost:8051/histTrades`, runs every record through
   the production parser, prints per-trade summaries + validation warnings +
   a productType census, and saves the raw payload to
   `data/hist_trades_raw.json` for offline inspection.

   (If a Celer websocket becomes available instead, `scripts/celer_probe.py`
   captures raw frames for the `RealCelerFeed` adapter.)

4. **Flip the switches** in `.env`:

   ```
   TRADE_FEED=histtrades
   HIST_TRADES_URL=http://localhost:8051/histTrades
   MARKET_DATA=blpapi
   ```

5. **Launch**: `python -m desktop.app`. Connection status is shown in the main
   window; every poll, trade, and error is logged to `data/logs/tracker.log`.
   The first poll (and the first after any outage) arrives as a single
   "catch-up" digest popup instead of one popup per historical trade.

## Architecture

- `core/hist_trades.py` — **verified /histTrades parser** (scaling, sentinels,
  dealt-currency notionals, validation warnings) + polling feed
- `core/` — pure, tested logic: models, tenor, ACT/360 discounting, USD
  conversion (incl. cross triangulation), exposure, inception PnL, market-data
  providers (mock + working blpapi), websocket feeds, SQLite store
- `mock_celer/` — local mock server: `WS /ws/trades` push feed, REST
  snapshot/inject, mock FX rates, discount curves, deterministic point-in-time
  `/bbg/mid` quotes
- `desktop/` — CustomTkinter app: feed listener on a worker thread, UI-thread
  popup queue, digest popups for bursts/catch-up, removal notices, voice
  announcer, rotating logs
- `scripts/` — standalone day-1 probes: `hist_probe.py` (trade endpoint),
  `bbg_probe.py` (Bloomberg retrieval chain), `celer_probe.py` (websocket
  frame capture)

### Known limits (v1)

- Flat discount rate per currency (indicative NPV, not full curve/CSA)
- Calendar-day tenors (no holiday calendars yet)
- No NDFs
- histTrades open questions from the spec are parsed-and-stored only, never
  derived from: `trade_side` semantics on swaps, `new_terms_qty`, `ignore`
  value set, `commission` scaling, pagination/sort order of the array
- Broken-date BBG tickers may lack tick history; provider then falls back to
  spot ticks + current points (or current mid) and flags `mid_fallback`
- Bloomberg intraday tick history is limited (~140 days) — fine live, matters
  only for catch-up after very long downtime

## GitHub / work transfer

Repo contains **no secrets and no real trade data** — mock data and the two
documented (anonymised) sample payloads only. Credentials and real URLs live
in `.env` (gitignored). Push to a **private** repo; confirm your employer's
policy on pulling personal GitHub code into the work environment.

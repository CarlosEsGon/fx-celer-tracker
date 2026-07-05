# FX Celer Trade Tracker

Desktop tracker for FX swaps and outrights executed on Celer. Subscribes to a
websocket trade feed, computes tenor, spot exposure, far-leg NPV, and inception
PnL versus the Bloomberg mid at execution time, stores every trade + analysis in
SQLite, and alerts via a desktop popup and optional voice summary.

Runs fully locally against a **mock Celer server** and **mock Bloomberg mids**.
Switching to the real Celer websocket and a real Bloomberg terminal is an
`.env` change, not a code change.

## Quick start (local, mock everything)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env

# Terminal 1 - mock Celer server (websocket feed + REST + mock BBG mids)
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

## Assumptions (v1 — adjust when real Celer/BBG docs are available)

| Area | Assumption |
|------|------------|
| Transport | Celer pushes executed trades as JSON over a websocket; snapshot REST endpoint for catch-up |
| Products | `FX_SWAP` (near + far legs), `FX_OUTRIGHT` (single leg) |
| Tenor | Calendar days near→far value date (swap) or valuation→value date (outright), bucketed ON…1Y, >1Y |
| Spot exposure | Signed base notional of the near leg (swap) or the single leg (outright) |
| Far-leg NPV | Quote-ccy cash flow discounted with ACT/360 money-market DF: `DF = 1/(1 + r*d/360)` |
| Valuation date | `trade_date` (configurable to spot in `config/settings.yaml`) |
| Bloomberg mid | Per trade: pair + exact (broken) value date + `booked_at` timestamp. Point-in-time, quoted directly by the source — never interpolated locally |
| Inception PnL | Traded rate vs mid at execution, discounted; swaps on swap points, outrights on forward rate; uneven swaps priced leg-by-leg |
| Lifecycle | Only `NEW` analysed. `AMENDED` is treated as `CANCELLED`: trade removed from tracking, audit row kept |
| Persistence | SQLite `data/trades.db`: raw trade, analysis, BBG mid snapshot, inception PnL |

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

3. **Probe Celer**: set `CELER_WS_URL` (+ auth header) in `.env`, then:

   ```bash
   python scripts/celer_probe.py --frames 20
   ```

   Dumps raw frames to `data/celer_frames.jsonl`. Compare against the mapping in
   `core/trade_feed.py` (`RealCelerFeed._parse_frame`) and adjust field names —
   that method is the only code expected to change on day 1.

4. **Flip the switches** in `.env`:

   ```
   TRADE_FEED=celer
   MARKET_DATA=blpapi
   ```

5. **Launch**: `python -m desktop.app`. Connection status is shown in the main
   window; every frame and error is logged to `data/logs/tracker.log`.

## Architecture

- `mock_celer/` — FastAPI app: `WS /ws/trades` push feed, REST snapshot/inject,
  mock FX rates, discount curves, and point-in-time `/bbg/mid` quotes
- `core/` — pure, tested logic: models, tenor, ACT/360 discounting, USD
  conversion (incl. cross triangulation), exposure, inception PnL, market-data
  providers (mock + blpapi), trade feeds (mock + real Celer), SQLite store
- `desktop/` — CustomTkinter app: websocket listener on a worker thread,
  UI-thread popup queue, digest popups for bursts, voice announcer
- `scripts/` — standalone day-1 probes for Bloomberg and Celer

### Known limits (v1)

- Flat discount rate per currency (indicative NPV, not full curve/CSA)
- Calendar-day tenors (no holiday calendars yet)
- No NDFs
- Broken-date BBG tickers may lack tick history; provider then falls back to
  spot ticks + current points (or current mid) and flags `mid_fallback`
- Bloomberg intraday tick history is limited (~140 days) — fine live, matters
  only for catch-up after very long downtime

## GitHub / work transfer

Repo contains **no secrets and no real schemas** — mock data only. Credentials
and real URLs live in `.env` (gitignored). Push to a **private** repo; confirm
your employer's policy on pulling personal GitHub code into the work
environment.

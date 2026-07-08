# FX Trade Tracker

Desktop tracker for FX swaps, forwards, and spot trades. Consumes a trade feed
(the verified real source is a REST endpoint, `GET /histTrades`), computes
tenor and a USD-perspective spot risk and inception PnL versus the Bloomberg
mid at execution time, stores every trade + analysis in SQLite, and alerts via
a desktop popup and optional voice summary — filtered to the currencies and
exposure size you actually care about.

Runs fully locally against a **mock server**, **mock Bloomberg mids**, and a
**mock discount curve**. Switching to the real trade endpoint, a real
Bloomberg terminal, and the real DAS discount curve is an `.env` change, not a
code change.

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

Expected: a popup appears immediately with the trade's tenor, value dates,
and net spot risk in USD; voice reads a summary. Use the **Popup settings…**
button in the main window to restrict which currencies raise a popup and set
a minimum spot-risk threshold (see below).

## Run the tests

```bash
pytest
```

Covers tenor bucketing, ACT/360 discounting (mock curve), USD leg-PV
valuation and the net spot-risk formula (matched/uneven swaps, outrights
valued as a matched swap), FX conversion (direct, inverse, cross
triangulation), inception PnL (swap points, outright forward, uneven
leg-by-leg, direction flips), the discount-curve seam (mock + DAS wiring),
deterministic mock mids, SQLite round-trips/migration and lifecycle, feed
parsing, and the histTrades parser tested against the two documented real
payloads (GBP/USD forward dealt in terms, AUD/USD T/N swap dealt in base).

## Popup settings (currency watch-list + spot-risk threshold)

Opened via the **Popup settings…** button in the main window
(`desktop/settings_window.py`), applies live (no restart), and persists to
`config/settings.yaml` under `popup:`.

- **Currencies to watch**: checkboxes for the main currencies
  (`core.config.MAIN_CURRENCIES` — CHF, AUD, JPY, EUR, GBP) plus a dynamic
  "Other" section listing every currency seen in trade history
  (`TradeStore.distinct_currencies()`). Only checked currencies raise a
  popup. Leaving everything unchecked (or empty in the YAML) means **no
  filter** — every currency is watched, including ones not seen yet.
- **Minimum spot exposure (USD)**: a popup only fires once `|spot risk USD|`
  clears this value. `0` (default) means always notify.
- **Both conditions must hold** — a popup needs a watched currency **and** a
  spot risk over the threshold (`FeedListener._should_notify`).

These filters only gate whether a popup is shown; every trade is still
persisted and analysed regardless.

## Analytics conventions

| Area | Convention |
|------|------------|
| Products | `FX_SWAP` (near + far legs), `FX_OUTRIGHT` (single leg — SPOT and FORWARD both map here) |
| Tenor | Calendar days near→far value date (swap) or valuation→value date (outright), bucketed ON…1Y, >1Y |
| Leg PVs | USD approach: each leg's **base notional** is converted to USD, then multiplied by a ready-to-multiply **USD discount factor** for that leg's settlement date (`core/exposure.py`) |
| Spot risk | The **sum** of the two leg PVs. Legs trade in opposite directions, so notionals cancel — what survives is the discounting spread between the two settlement dates (plus the mismatch on an uneven swap). Outrights are valued as a matched swap: a synthetic near leg with the same amount as the single leg, opposite direction (the spot hedge), settling at spot (T+2) |
| Discount source | `DISCOUNT_SOURCE` in `.env`: `das` (work) takes ready-made USD discount factors from the internal `das_client` module; `mock` (default, local dev) derives DFs from the flat USD rate in `config/settings.yaml` via ACT/360 (`core/discount_curve.py`) |
| Valuation date | `trade_date` (configurable to spot in `config/settings.yaml`) |
| Bloomberg mid | Per trade: pair + exact (broken) value date + `booked_at` timestamp. Point-in-time, quoted directly by the source — never interpolated locally |
| Inception PnL | Traded rate vs mid at execution (swaps on swap points, outrights on forward rate, uneven swaps priced leg-by-leg); converted to USD then discounted at the far leg's USD DF. Computed and stored, but not shown in the popup/voice (see below) |
| Lifecycle | Only `NEW` analysed. `AMENDED` is treated as `CANCELLED`: trade removed from tracking, audit row kept (websocket feeds; histTrades has no lifecycle fields) |
| Persistence | SQLite `data/trades.db`: raw trade (incl. full source record), analysis (leg PVs, spot risk, inception PnL), BBG mid snapshot; CSV export helper. Older DBs (pre USD-leg-PV columns) are migrated in place automatically |

### What the popup and voice actually show

Trimmed to the essentials: product/pair/tenor header, trade ID/counterparty,
near/far value dates, a single **Spot risk (USD)** line, and — only when
relevant — an amber uneven-swap mismatch or `[FALLBACK]` mid indicator. Leg
PVs, the BBG mid detail, and inception PnL are computed and persisted but no
longer displayed or spoken; the digest popup (bursts/catch-up) still lists
spot risk and PnL per trade in its compact table.

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
   DISCOUNT_SOURCE=das
   ```

   `DISCOUNT_SOURCE=das` requires `das_client` to be importable (internal
   module, not part of this repo) and exposing
   `get_discount_factor(cash_flow_date) -> float`
   (`core/discount_curve.py:DasDiscountCurve`) — adjust that one call if the
   real signature differs.

5. **Launch**: `python -m desktop.app`. Connection status is shown in the main
   window; every poll, trade, and error is logged to `data/logs/tracker.log`.
   The first poll (and the first after any outage) arrives as a single
   "catch-up" digest popup instead of one popup per historical trade.

## Architecture

- `core/hist_trades.py` — **verified /histTrades parser** (scaling, sentinels,
  dealt-currency notionals, validation warnings) + polling feed
- `core/` — pure, tested logic: models, tenor, ACT/360 discounting (mock
  curve), USD conversion (incl. cross triangulation), USD leg-PV exposure,
  inception PnL, the discount-curve seam (mock + DAS), market-data providers
  (mock + working blpapi), websocket feeds, SQLite store
- `mock_celer/` — local mock server: `WS /ws/trades` push feed, REST
  snapshot/inject, mock FX rates, deterministic point-in-time `/bbg/mid`
  quotes
- `desktop/` — CustomTkinter app: feed listener on a worker thread (filters
  popups by watched currency + spot-risk threshold), UI-thread popup queue,
  digest popups for bursts/catch-up, removal notices, popup settings window,
  voice announcer, rotating logs
- `scripts/` — standalone day-1 probes: `hist_probe.py` (trade endpoint),
  `bbg_probe.py` (Bloomberg retrieval chain), `celer_probe.py` (websocket
  frame capture)

## File reference

Every tracked file, what it's for.

### `core/` — pure logic, unit tested, no UI/IO framework dependencies

| File | Purpose |
|------|---------|
| `models.py` | Pydantic schema: `Leg`, `Trade` (with `exposure_leg`/`discounted_leg` properties that pick near-vs-single and far-vs-single leg by product type), `MidSnapshot`, `TradeAnalysis` — the single source of truth for the app's data shapes |
| `config.py` | `Settings` dataclass; `load_settings()` merges `.env` (secrets/URLs/selection) with `config/settings.yaml` (behaviour); `save_popup_settings()` persists the popup currency/threshold filters back to YAML; `MAIN_CURRENCIES` constant; `build_feed()` / `build_market_data()` / `build_discount_curve()` factories that pick the mock vs. real implementation per `Settings` |
| `tenor.py` | Calendar-day tenor calculation and ON…1Y/`>1Y` bucketing (`identify_tenor`) |
| `discount.py` | ACT/360 money-market discount factor/PV math (`discount_factor`, `present_value`) — used only by the mock discount curve now |
| `discount_curve.py` | The DAS integration seam: `DiscountCurve` protocol, `MockDiscountCurve` (flat USD rate, local dev), `DasDiscountCurve` (lazy-imports `das_client`, work-only) |
| `fx.py` | USD conversion (`convert_to_usd`, direct/inverse/identity `usd_rate`) and pip-size lookup (`pip_factor`) |
| `exposure.py` | USD leg-PV valuation: `pv_near_leg_usd`/`pv_far_leg_usd`, `spot_exposure_usd` (their sum — the net spot risk), `notional_mismatch_base` (uneven swaps) |
| `pnl.py` | Inception PnL vs the Bloomberg mid at execution: swap points, outright forward, uneven leg-by-leg; converts to USD then discounts at the far leg's USD DF |
| `analyzer.py` | `analyze_trade()` — wires tenor + exposure + PnL together into one `TradeAnalysis` per trade |
| `market_data.py` | `MarketDataProvider` interface; `MockBloombergProvider` (mock server's `/bbg/mid` + `/fx-rates`); `BlpapiProvider` (real Bloomberg Desktop API, broken-date tick retrieval chain with fallbacks) |
| `trade_feed.py` | `TradeFeed` interface; shared websocket machinery (reconnect/backoff, liveness timeout, REST snapshot catch-up, raw-frame capture) in `_WebsocketFeed`; `MockCelerFeed` (local mock) and `RealCelerFeed` (real Celer, frame mapping is the one thing to adjust on day 1) |
| `hist_trades.py` | The **verified** `/histTrades` REST adapter: scaling (×1e6), null sentinels, dealt-currency notionals (base vs. terms), SPOT/CAD-cross filtering, §5 validation warnings, plus the polling `HistTradesFeed` |
| `store.py` | SQLite persistence (`TradeStore`): trade + analysis tables, dedupe by `(trade_id, version)`, catch-up bookmark (`last_booked_at`), auto-migration of older schemas, `distinct_currencies()` for the popup settings UI, CSV export |

### `desktop/` — CustomTkinter app

| File | Purpose |
|------|---------|
| `app.py` | Entry point (`python -m desktop.app`); `TrackerApp` owns the Tkinter main loop, main window, UI event queue pump, burst-window batching into single/digest popups, and the Popup settings / voice controls |
| `listener.py` | `FeedListener` — runs the feed + market-data + discount-curve calls on a worker thread; `_should_notify()` gates popups by watched currency + spot-risk threshold; `_near_settlement()` picks the synthetic near-leg date for outrights; retry loop for trades whose market data failed |
| `popup.py` | `TradePopup` (single trade: dates, spot risk, conditional mismatch/fallback), `DigestPopup` (scrollable list for bursts/catch-up), `NoticePopup` (cancellations, PnL-pending, auto-dismiss) |
| `settings_window.py` | `SettingsWindow` — the Popup settings UI: main + dynamic "other" currency checkboxes, the spot-risk threshold field, live-apply + YAML persistence |
| `voice.py` | `VoiceAnnouncer` (pyttsx3 on its own thread, queued so the UI never blocks); `trade_summary()`/`digest_summary()` build the spoken text (spot risk only, no PnL) |
| `logging_setup.py` | Rotating file handler (`data/logs/tracker.log`) + console logging setup |

### `mock_celer/` — local mock server (`uvicorn mock_celer.server:app`)

| File | Purpose |
|------|---------|
| `server.py` | FastAPI app: `WS /ws/trades` push feed (with replay), `POST /trades` to inject + broadcast, `GET /trades`/`/trades/{id}` snapshot, `GET /fx-rates`, `GET /curves/{ccy}`, `GET /bbg/mid` |
| `market.py` | Deterministic mock market data: seeded spot mids/FX rates/discount rates per pair, hash-based reproducible "noise" so the same `(pair, value_date, as_of)` always answers the same mid |
| `schemas.py` | Pydantic wire schemas for the mock server (`TradeIn`, `LegIn`, `BbgMidOut`) — a mirror of `core.models` for the HTTP/WS boundary |
| `sample_trade_swap.json`, `sample_trade_outright.json` | Fixture payloads for `POST /trades` (used in the Quick Start `curl` example) |

### `scripts/` — day-1 standalone probes (not imported by the app)

| File | Purpose |
|------|---------|
| `bbg_probe.py` | Walks the real Bloomberg retrieval chain for one pair/date and prints raw responses per step — run first to debug terminal connectivity |
| `hist_probe.py` | Fetches the real `/histTrades` array, runs every record through the production parser, prints per-trade summaries + validation warnings + a productType census |
| `celer_probe.py` | Connects to the real Celer websocket and dumps raw frames to `data/celer_frames.jsonl` for comparing against `RealCelerFeed._parse_frame` |

### `tests/` — pytest, run via `pytest` (config in `pyproject.toml`)

One file per `core/` module (`test_models` logic is covered inline via fixtures in `conftest.py`, which defines the shared `swap_trade`/`outright_trade`/`fx_rates`/mid fixtures used throughout): `test_tenor.py`, `test_discount.py`, `test_discount_curve.py`, `test_fx.py`, `test_exposure.py`, `test_pnl.py`, `test_analyzer.py`, `test_market_data.py` (mock provider determinism), `test_trade_feed.py` (websocket reconnect/backoff/catch-up), `test_hist_trades.py` (the two documented real payloads + edge cases), `test_store.py` (round-trips, migration, lifecycle, CSV export).

### Root / config files

| File | Purpose |
|------|---------|
| `.env.example` | Template for `.env` — feed/market-data/discount-source selection, URLs, credentials placeholders (copy to `.env`, which is gitignored) |
| `config/settings.yaml` | Non-secret behaviour: voice settings, popup digest/currency-filter/threshold, valuation-date mode, mock discount rates, tenor bucket table |
| `pyproject.toml` | Pytest config only (`testpaths`, `pythonpath`, default args) |
| `requirements.txt` | Python dependencies (`blpapi` deliberately excluded — installed separately at work, see Day 1 runbook) |
| `.github/workflows/ci.yml` | GitHub Actions: installs core/test deps (skips `customtkinter`/`pyttsx3`, desktop-only) and runs `pytest` on push/PR |

### Known limits (v1)

- Mock discount curve is a flat rate per currency (indicative, not a full
  curve/CSA) — `DISCOUNT_SOURCE=das` at work replaces this with real DFs
- Calendar-day tenors (no holiday calendars yet)
- No NDFs
- histTrades open questions from the spec are parsed-and-stored only, never
  derived from: `trade_side` semantics on swaps, `new_terms_qty`, `ignore`
  value set, `commission` scaling, pagination/sort order of the array
- Broken-date BBG tickers may lack tick history; provider then falls back to
  spot ticks + current points (or current mid) and flags `mid_fallback`
- Bloomberg intraday tick history is limited (~140 days) — fine live, matters
  only for catch-up after very long downtime
- `save_popup_settings()` rewrites `config/settings.yaml` via
  `yaml.safe_dump`, so hand-written comments in that file are lost the first
  time popup settings are saved from the UI

## GitHub / work transfer

Repo contains **no secrets and no real trade data** — mock data and the two
documented (anonymised) sample payloads only. Credentials and real URLs live
in `.env` (gitignored). Push to a **private** repo; confirm your employer's
policy on pulling personal GitHub code into the work environment.

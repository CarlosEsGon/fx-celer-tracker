"""SQLite persistence: trades, analyses, mid snapshots, dedupe state.

Also the durable memory that makes restarts safe:
  - seen (trade_id, version) pairs -> no duplicate popups after restart
  - last processed booked_at       -> snapshot catch-up starting point
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.models import Trade, TradeAnalysis

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id      TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    product_type  TEXT NOT NULL,
    currency_pair TEXT NOT NULL,
    counterparty  TEXT,
    trade_date    TEXT NOT NULL,
    booked_at     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'NEW',
    raw_json      TEXT NOT NULL,
    inserted_at   TEXT NOT NULL,
    PRIMARY KEY (trade_id, version)
);

CREATE TABLE IF NOT EXISTS analysis (
    trade_id             TEXT NOT NULL,
    version              INTEGER NOT NULL DEFAULT 1,
    tenor_label          TEXT,
    tenor_days           INTEGER,
    spot_exposure_base   REAL,
    spot_exposure_usd    REAL,
    pv_near_leg_usd      REAL,
    pv_far_leg_usd       REAL,
    combined_risk_usd    REAL,
    bbg_spot_mid         REAL,
    bbg_swap_points_mid  REAL,
    bbg_forward_mid      REAL,
    bbg_as_of            TEXT,
    inception_pnl_quote  REAL,
    inception_pnl_usd    REAL,
    notional_mismatch    REAL,
    mid_fallback         INTEGER,
    near_value_date      TEXT,
    far_value_date       TEXT,
    status               TEXT NOT NULL DEFAULT 'NEW',
    superseded           INTEGER NOT NULL DEFAULT 0,
    computed_at          TEXT NOT NULL,
    PRIMARY KEY (trade_id, version)
);
"""


class TradeStore:
    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # Databases created before the USD leg-PV columns existed (they
            # had npv_far_leg_quote/npv_far_leg_usd instead) get the new
            # columns added; old columns are left in place for the audit trail.
            for col in ("pv_near_leg_usd", "pv_far_leg_usd"):
                try:
                    self._conn.execute(f"ALTER TABLE analysis ADD COLUMN {col} REAL")
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()

    # ---- dedupe / catch-up state -------------------------------------------

    def has_seen(self, trade_id: str, version: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM trades WHERE trade_id = ? AND version = ?",
            (trade_id, version),
        )
        return cur.fetchone() is not None

    def last_booked_at(self) -> Optional[datetime]:
        cur = self._conn.execute("SELECT MAX(booked_at) AS m FROM trades")
        row = cur.fetchone()
        if row is None or row["m"] is None:
            return None
        dt = datetime.fromisoformat(row["m"])
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # ---- writes ----------------------------------------------------------------

    def save_trade(self, trade: Trade) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO trades
                   (trade_id, version, product_type, currency_pair, counterparty,
                    trade_date, booked_at, status, raw_json, inserted_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade.trade_id,
                    trade.version,
                    trade.product_type.value,
                    trade.currency_pair,
                    trade.counterparty,
                    trade.trade_date.isoformat(),
                    trade.booked_at.isoformat(),
                    trade.status.value,
                    trade.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._conn.commit()

    def save_analysis(self, a: TradeAnalysis) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO analysis
                   (trade_id, version, tenor_label, tenor_days,
                    spot_exposure_base, spot_exposure_usd,
                    pv_near_leg_usd, pv_far_leg_usd, combined_risk_usd,
                    bbg_spot_mid, bbg_swap_points_mid, bbg_forward_mid, bbg_as_of,
                    inception_pnl_quote, inception_pnl_usd,
                    notional_mismatch, mid_fallback,
                    near_value_date, far_value_date, status, superseded, computed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)""",
                (
                    a.trade_id,
                    a.version,
                    a.tenor_label,
                    a.tenor_days,
                    a.spot_exposure_base,
                    a.spot_exposure_usd,
                    a.pv_near_leg_usd,
                    a.pv_far_leg_usd,
                    a.combined_risk_usd,
                    a.bbg_spot_mid,
                    a.bbg_swap_points_mid,
                    a.bbg_forward_mid,
                    a.bbg_as_of.isoformat(),
                    a.inception_pnl_quote,
                    a.inception_pnl_usd,
                    a.notional_mismatch_base,
                    1 if a.mid_fallback else 0,
                    a.near_value_date.isoformat(),
                    a.far_value_date.isoformat() if a.far_value_date else None,
                    a.status,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._conn.commit()

    def mark_cancelled(self, trade_id: str, new_status: str) -> bool:
        """Mark a trade removed from tracking (CANCELLED, or AMENDED which we
        treat as a cancellation). Analysis rows are kept for the audit trail.
        Returns True if the trade existed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE trades SET status = ? WHERE trade_id = ?",
                (new_status, trade_id),
            )
            self._conn.execute(
                "UPDATE analysis SET status = ?, superseded = 1 WHERE trade_id = ?",
                (new_status, trade_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ---- queries ----------------------------------------------------------------

    def get_trade_history(
        self,
        pair: Optional[str] = None,
        since: Optional[datetime] = None,
        include_cancelled: bool = False,
    ) -> list[dict]:
        sql = """SELECT t.*, a.tenor_label, a.tenor_days, a.spot_exposure_base,
                        a.spot_exposure_usd, a.pv_near_leg_usd, a.pv_far_leg_usd,
                        a.combined_risk_usd, a.bbg_spot_mid, a.bbg_swap_points_mid,
                        a.bbg_forward_mid, a.bbg_as_of, a.inception_pnl_quote,
                        a.inception_pnl_usd, a.notional_mismatch, a.mid_fallback,
                        a.near_value_date, a.far_value_date, a.computed_at
                 FROM trades t
                 LEFT JOIN analysis a
                   ON a.trade_id = t.trade_id AND a.version = t.version
                 WHERE 1=1"""
        params: list = []
        if not include_cancelled:
            sql += " AND t.status = 'NEW'"
        if pair:
            sql += " AND t.currency_pair = ?"
            params.append(pair)
        if since:
            sql += " AND t.booked_at > ?"
            params.append(since.isoformat())
        sql += " ORDER BY t.booked_at"
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def export_csv(self, path: str | Path) -> int:
        rows = self.get_trade_history(include_cancelled=True)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("")
            return 0
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def distinct_currencies(self) -> list[str]:
        """All base/quote currencies seen across booked trades, for populating
        the popup settings 'other currencies' list."""
        cur = self._conn.execute("SELECT DISTINCT currency_pair FROM trades")
        ccys: set[str] = set()
        for row in cur.fetchall():
            pair = row["currency_pair"]
            if "/" in pair:
                base, quote = pair.split("/", 1)
                ccys.add(base.strip().upper())
                ccys.add(quote.strip().upper())
        return sorted(ccys)

    def load_trade(self, trade_id: str, version: int) -> Optional[Trade]:
        cur = self._conn.execute(
            "SELECT raw_json FROM trades WHERE trade_id = ? AND version = ?",
            (trade_id, version),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Trade(**json.loads(row["raw_json"]))

    def close(self) -> None:
        self._conn.close()

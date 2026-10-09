"""Single-process transactional persistence; owning services use this boundary."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


class Store:
    backend_name = "SQLITE_OFFLINE"

    def __init__(self, path=":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.depth = 0
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS subscriptions(
                id TEXT PRIMARY KEY, account TEXT NOT NULL, kind TEXT NOT NULL,
                symbol TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders(
                id TEXT PRIMARY KEY, strategy TEXT NOT NULL, account TEXT NOT NULL,
                symbol TEXT NOT NULL, side TEXT NOT NULL, quantity INTEGER NOT NULL,
                created REAL NOT NULL, status TEXT NOT NULL, filled INTEGER NOT NULL DEFAULT 0,
                emergency INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS fills(
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL, strategy TEXT NOT NULL,
                account TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
                quantity INTEGER NOT NULL, price TEXT NOT NULL, timestamp REAL NOT NULL,
                charges TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
                payload TEXT NOT NULL);
        """)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        self.audit_clock = time.time
        if version > 14:
            raise ValueError("SQLite schema is newer than this application")
        if version < 1:
            self.db.execute("PRAGMA user_version=1")
            version = 1
        # Member 4's earlier local schema used version 2 for subscription
        # enablement. If risk policies are absent, replay migration 002 and
        # continue through the shared hardening sequence before migration 006.
        if version >= 2 and not self._table_exists("risk_policies"):
            version = 1
            self.db.execute("PRAGMA user_version=1")
        self.db.commit()
        for number, filename in (
            (2, "002_risk_policies.sql"),
            (3, "003_safety_state.sql"),
            (4, "004_dispatch_evidence.sql"),
            (5, "005_history_indexes.sql"),
            (6, "006_subscription_state.sql"),
            (7, "007_user_authentication.sql"),
            (8, "008_account_risk.sql"),
            (9, "009_audit_correlation.sql"),
            (10, "010_risk_price_guard.sql"),
            (11, "011_benchmark_runs.sql"),
            (12, "012_operator_grants.sql"),
            (13, "013_021_order_mappings.sql"),
            (14, "014_closed_candles.sql"),
        ):
            if version < number:
                sql = (
                    Path(__file__).parent / "sqlite_migrations" / filename
                ).read_text(encoding="utf-8")
                self.db.executescript(
                    f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version={number};\nCOMMIT;"
                )
                version = number
        subscription_columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(subscriptions)")
        }
        if "enabled" not in subscription_columns:
            raise ValueError("subscription state migration did not add enabled")

    def _table_exists(self, name):
        return (
            self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            is not None
        )

    @contextmanager
    def transaction(self):
        with self.lock:
            outer = self.depth == 0
            self.depth += 1
            try:
                yield self.db
                if outer:
                    self.db.commit()
            except Exception:
                if outer:
                    self.db.rollback()
                raise
            finally:
                self.depth -= 1

    def rows(self, query, args=()):
        with self.lock:
            return self.db.execute(query, args).fetchall()

    def save_candle(self, candle, *, provider="replay"):
        with self.transaction():
            self.db.execute(
                """INSERT INTO closed_candles
                (provider,symbol,interval,start_time,end_time,open,high,low,close,volume,is_closed,volume_available,data_source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(provider,symbol,interval,start_time) DO NOTHING""",
                (
                    provider,
                    candle.symbol,
                    candle.interval,
                    candle.start_time,
                    candle.end_time,
                    str(candle.open),
                    str(candle.high),
                    str(candle.low),
                    str(candle.close),
                    candle.volume,
                    int(candle.is_closed),
                    int(candle.volume_available),
                    candle.data_source,
                ),
            )

    def candle_rows(self, symbol=None, interval=None, limit=200):
        clauses, args = [], []
        if symbol:
            clauses.append("symbol=?")
            args.append(symbol.upper())
        if interval:
            clauses.append("interval=?")
            args.append(interval)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(min(max(int(limit), 1), 1000))
        return self.rows(
            f"SELECT * FROM closed_candles{where} ORDER BY start_time DESC LIMIT ?",
            tuple(args),
        )

    def audit(self, event_type, payload, correlation_id=None):
        # Caller holds the transaction; event commits atomically with its transition.
        if correlation_id is None and isinstance(payload, dict):
            correlation_id = payload.get("intent_id") or payload.get("order_id")
            if correlation_id is None and payload.get("fill_id"):
                row = self.db.execute(
                    "SELECT order_id FROM fills WHERE id=?", (payload["fill_id"],)
                ).fetchone()
                correlation_id = row["order_id"] if row else None
        self.db.execute(
            "INSERT INTO audit(type,payload,recorded_at,correlation_id) VALUES (?,?,?,?)",
            (
                event_type,
                json.dumps(payload, default=str),
                self.audit_clock(),
                correlation_id,
            ),
        )

    def close(self):
        self.db.close()

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
        if version > 5:
            raise ValueError("SQLite schema is newer than this application")
        if version < 1:
            self.db.execute("PRAGMA user_version=1")
        self.db.commit()
        for number, filename in (
            (2, "002_risk_policies.sql"),
            (3, "003_safety_state.sql"),
            (4, "004_dispatch_evidence.sql"),
            (5, "005_history_indexes.sql"),
        ):
            if version < number:
                sql = (
                    Path(__file__).parent / "sqlite_migrations" / filename
                ).read_text(encoding="utf-8")
                self.db.executescript(
                    f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version={number};\nCOMMIT;"
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

    def audit(self, event_type, payload):
        # Caller holds the transaction; event commits atomically with its transition.
        self.db.execute(
            "INSERT INTO audit(type,payload,recorded_at) VALUES (?,?,?)",
            (event_type, json.dumps(payload, default=str), self.audit_clock()),
        )

    def close(self):
        self.db.close()

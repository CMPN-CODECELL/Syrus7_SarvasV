"""Single-process transactional persistence; owning services use this boundary."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


class Store:
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
        if version > 2:
            raise ValueError("SQLite schema is newer than this application")
        if version < 1:
            self.db.execute("PRAGMA user_version=1")
        self.db.commit()
        if version < 2:
            sql = (
                Path(__file__).parent / "sqlite_migrations/002_risk_policies.sql"
            ).read_text(encoding="utf-8")
            self.db.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=2;\nCOMMIT;"
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
            "INSERT INTO audit(type,payload) VALUES (?,?)",
            (event_type, json.dumps(payload, default=str)),
        )

    def close(self):
        self.db.close()

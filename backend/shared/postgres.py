"""PostgreSQL implementation of the existing Store service boundary."""

from threading import RLock
import time

import psycopg
from psycopg.rows import dict_row

from backend.shared.store import Store


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        # Domain queries use SQLite-style ``?`` placeholders. Psycopg treats
        # percent signs in LIKE patterns as formatting tokens, so escape
        # literal percent signs before translating the placeholders.
        translated = sql.replace("%", "%%").replace("?", "%s")
        return self.connection.execute(translated, args)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


class PostgresStore(Store):
    backend_name = "POSTGRESQL"

    def __init__(self, database_url):
        self.lock = RLock()
        self.depth = 0
        self.audit_clock = time.time
        try:
            connection = psycopg.connect(
                database_url, row_factory=dict_row, connect_timeout=10
            )
        except Exception:
            raise RuntimeError(
                "PostgreSQL connection failed; check local configuration privately"
            ) from None
        self.db = Connection(connection)
        try:
            # Database-wide ownership lock: a second control plane must not trade.
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(724091837) AS acquired"
            ).fetchone()["acquired"]
            if not acquired:
                raise RuntimeError("another AlgoShield process owns this database")
            connection.execute("SET search_path TO algoshield, public")
            connection.execute("SET statement_timeout = '10s'")
            row = connection.execute(
                "SELECT to_regclass('algoshield.schema_migrations') AS migration_table"
            ).fetchone()
            if not row["migration_table"]:
                raise RuntimeError("database migrations required before startup")
            from backend.shared.migrate import migrations

            recorded = {
                r["name"]: r["checksum"]
                for r in connection.execute(
                    "SELECT name,checksum FROM schema_migrations"
                ).fetchall()
            }
            expected = {name: checksum for name, checksum, _ in migrations()}
            if recorded != expected:
                raise RuntimeError("migration version/checksum mismatch")
            connection.commit()
        except Exception:
            connection.close()
            # Never leak connection details or server error text to logs/UI.
            raise RuntimeError(
                "PostgreSQL initialization failed; inspect migrations/connectivity privately"
            ) from None

    def save_candle(self, candle, *, provider="replay"):
        with self.transaction():
            self.db.execute(
                """INSERT INTO algoshield.closed_candles
                (provider,symbol,interval_seconds,start_time,end_time,open,high,low,close,volume,is_closed,volume_available,data_source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider,symbol,interval_seconds,start_time) DO NOTHING""",
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
                    candle.is_closed,
                    candle.volume_available,
                    candle.data_source,
                ),
            )
            self.db.execute(
                "DELETE FROM algoshield.closed_candles "
                "WHERE provider=? AND symbol=? AND start_time<?",
                (
                    provider,
                    candle.symbol,
                    candle.start_time - self.CANDLE_RETENTION_SECONDS,
                ),
            )

    def candle_rows(self, symbol=None, interval=None, limit=200, provider=None):
        clauses, args = [], []
        if symbol:
            clauses.append("symbol=?")
            args.append(symbol.upper())
        if interval:
            clauses.append("interval_seconds=?")
            args.append(interval)
        if provider:
            clauses.append("provider=?")
            args.append(provider)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        bounded_limit = min(max(int(limit), 1), 1000)
        args.extend((bounded_limit, bounded_limit))
        return self.rows(
            "SELECT * FROM (SELECT provider,symbol,interval_seconds AS interval,"
            "start_time,end_time,open,high,low,close,volume,is_closed,"
            "volume_available,data_source FROM algoshield.closed_candles"
            f"{where} ORDER BY start_time DESC LIMIT ?) recent "
            "ORDER BY start_time ASC LIMIT ?",
            tuple(args),
        )

    def candle_count(self, provider=None):
        if provider:
            return self.rows(
                "SELECT COUNT(*) AS n FROM algoshield.closed_candles WHERE provider=?",
                (provider,),
            )[0]["n"]
        return self.rows(
            "SELECT COUNT(*) AS n FROM algoshield.closed_candles"
        )[0]["n"]

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
        return self.connection.execute(sql.replace("?", "%s"), args)

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

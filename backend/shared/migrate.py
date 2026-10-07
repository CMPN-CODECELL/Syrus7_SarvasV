"""Inspect first; explicit --apply performs only reviewed additive migrations."""

import argparse
import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from backend.shared.config import settings


def migrations():
    for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
        data = path.read_bytes()
        yield path.name, hashlib.sha256(data).hexdigest(), data.decode()


def inspect(connection):
    return connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2"
    ).fetchall()


def apply(connection):
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(724091838)")
        tables = inspect(connection)
        existing = {
            r["table_name"] for r in tables if r["table_schema"] == "algoshield"
        }
        if existing and "schema_migrations" not in existing:
            raise ValueError(
                "existing unmanaged AlgoShield schema; inspect before adopting"
            )
        connection.execute("CREATE SCHEMA IF NOT EXISTS algoshield")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS algoshield.schema_migrations "
            "(name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        recorded = {
            r["name"]: r["checksum"]
            for r in connection.execute(
                "SELECT name,checksum FROM algoshield.schema_migrations"
            ).fetchall()
        }
        expected = {name: checksum for name, checksum, _ in migrations()}
        if set(recorded) - set(expected):
            raise ValueError("unknown migration versions; cannot downgrade")
        for name, checksum, sql in migrations():
            if name in recorded:
                if recorded[name] != checksum:
                    raise ValueError("migration checksum mismatch")
                continue
            connection.execute(sql)
            connection.execute(
                "INSERT INTO algoshield.schema_migrations(name,checksum) VALUES (%s,%s)",
                (name, checksum),
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = settings()["database_url"]
    if not url:
        raise SystemExit("DATABASE_URL is not configured; no remote changes made")
    try:
        with psycopg.connect(
            url, row_factory=dict_row, connect_timeout=10
        ) as connection:
            connection.execute("SET statement_timeout = '10s'")
            tables = inspect(connection)
            print(
                "Existing application tables:",
                [(r["table_schema"], r["table_name"]) for r in tables],
            )
            if args.apply:
                apply(connection)
                print("Reviewed additive migrations applied")
    except Exception:
        raise SystemExit(
            "PostgreSQL inspection/migration failed; inspect connection or schema privately; no credentials printed"
        ) from None


if __name__ == "__main__":
    main()

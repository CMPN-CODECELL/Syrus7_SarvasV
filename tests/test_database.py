import hashlib
import sqlite3

import pytest

from backend.shared.config import settings
from backend.shared.migrate import migrations
from backend.shared.postgres import Connection
from backend.shared.store import Store


def test_environment_precedence_and_local_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ALGOSHIELD_DB", raising=False)
    (tmp_path / ".env").write_text("ALGOSHIELD_DB=fallback.db\n")
    (tmp_path / ".env.local").write_text("DATABASE_URL=local-test-value\n")
    assert settings() == {
        "database_url": "local-test-value",
        "sqlite_path": "fallback.db",
    }
    monkeypatch.setenv("DATABASE_URL", "process-test-value")
    assert settings()["database_url"] == "process-test-value"


def test_additive_migration_constraints_and_checksum():
    items = list(migrations())
    assert len(items) == 2
    name, checksum, sql = items[0]
    assert name == "001_bootstrap.sql"
    assert checksum == hashlib.sha256(sql.encode()).hexdigest()
    assert "DROP " not in sql.upper()
    assert "DELETE " not in sql.upper()
    assert "id TEXT PRIMARY KEY, order_id" in sql
    assert "filled <= quantity" in sql
    assert "REFERENCES algoshield.orders(id)" in sql
    name, checksum, sql = items[1]
    assert name == "002_subscription_state.sql"
    assert checksum == hashlib.sha256(sql.encode()).hexdigest()
    assert "ALTER TABLE algoshield.subscriptions" in sql
    assert "enabled INTEGER NOT NULL DEFAULT 1" in sql


def test_postgres_placeholder_binding():
    class Driver:
        def execute(self, sql, args):
            self.sql, self.args = sql, args
            return "cursor"

    raw = Driver()
    assert (
        Connection(raw).execute("SELECT * FROM orders WHERE id=?", ("literal?",))
        == "cursor"
    )
    assert raw.sql == "SELECT * FROM orders WHERE id=%s"
    assert raw.args == ("literal?",)


def test_postgres_error_does_not_echo_credentials(monkeypatch):
    from backend.shared.postgres import PostgresStore
    import backend.shared.postgres as module

    class Driver:
        def execute(self, *args):
            raise RuntimeError("secret-in-driver-error")

        def close(self):
            pass

    monkeypatch.setattr(module.psycopg, "connect", lambda *a, **kw: Driver())
    with pytest.raises(RuntimeError) as error:
        PostgresStore("secret-connection-string")
    assert "secret" not in str(error.value)


def test_sqlite_v1_subscription_state_migrates_additively(tmp_path):
    path = tmp_path / "v1.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE accounts(id TEXT PRIMARY KEY)")
    connection.execute(
        "CREATE TABLE subscriptions("
        "id TEXT PRIMARY KEY, account TEXT NOT NULL, kind TEXT NOT NULL, "
        "symbol TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO accounts VALUES ('a')")
    connection.execute("INSERT INTO subscriptions VALUES ('s','a','momentum','X')")
    connection.execute("PRAGMA user_version=1")
    connection.commit()
    connection.close()

    store = Store(path)
    try:
        row = store.rows("SELECT enabled FROM subscriptions WHERE id='s'")[0]
        assert row["enabled"] == 1
        assert store.rows("PRAGMA user_version")[0][0] == 2
    finally:
        store.close()

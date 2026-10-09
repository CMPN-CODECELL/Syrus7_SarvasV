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
        "021_enabled": False,
        "021_product": "INTRADAY",
        "market_data_provider": "replay",
        "021_max_timestamp_skew_seconds": 10.0,
        "broker_read_timeout_seconds": 8.0,
        "broker_write_timeout_seconds": 8.0,
        "reconciliation_timeout_seconds": 10.0,
        "auto_scan_limit": 200,
        "auto_max_positions": 3,
        "auto_lookback_updates": 5,
        "auto_entry_momentum": 0.003,
        "auto_take_profit": 0.01,
        "auto_stop_loss": 0.005,
        "auto_cooldown_seconds": 60,
    }
    monkeypatch.setenv("DATABASE_URL", "process-test-value")
    assert settings()["database_url"] == "process-test-value"


def test_021_live_mode_requires_021_market_data(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALGOSHIELD_021_ENABLED", "true")
    monkeypatch.setenv("ALGOSHIELD_MARKET_DATA_PROVIDER", "yahoo")

    with pytest.raises(ValueError, match="disable ALGOSHIELD_021_ENABLED"):
        settings()


def test_021_live_mode_uses_dedicated_sqlite_timeline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ALGOSHIELD_DB", "mock.db")
    monkeypatch.setenv("ALGOSHIELD_021_ENABLED", "true")
    monkeypatch.delenv("ALGOSHIELD_021_DB", raising=False)

    assert settings()["sqlite_path"] == "data/platform-021.db"
    monkeypatch.setenv("ALGOSHIELD_021_DB", "provider.db")
    assert settings()["sqlite_path"] == "provider.db"


def test_021_market_data_requires_live_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALGOSHIELD_021_ENABLED", "false")
    monkeypatch.setenv("ALGOSHIELD_MARKET_DATA_PROVIDER", "021")

    with pytest.raises(ValueError, match="ALGOSHIELD_021_ENABLED=true"):
        settings()


def test_additive_migration_constraints_and_checksum():
    items = list(migrations())
    assert [i[0] for i in items] == [
        "001_bootstrap.sql",
        "002_risk_policies.sql",
        "002_subscription_state.sql",
        "003_safety_state.sql",
        "004_dispatch_evidence.sql",
        "005_history_indexes.sql",
        "006_user_authentication.sql",
        "007_account_risk.sql",
        "008_audit_correlation.sql",
        "009_risk_price_guard.sql",
        "010_benchmark_runs.sql",
        "011_operator_grants.sql",
        "012_021_order_mappings.sql",
        "013_closed_candles.sql",
    ]
    for name, checksum, sql in items:
        assert checksum == hashlib.sha256(sql.encode()).hexdigest()
        assert "DROP " not in sql.upper()
        assert "DELETE " not in sql.upper()
    assert "id TEXT PRIMARY KEY, order_id" in items[0][2]
    assert "filled <= quantity" in items[0][2]
    assert "REFERENCES algoshield.orders(id)" in items[0][2]
    assert "ALTER TABLE algoshield.subscriptions" in items[2][2]
    assert "enabled INTEGER NOT NULL DEFAULT 1" in items[2][2]


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
    Connection(raw).execute(
        "SELECT * FROM audit WHERE payload LIKE '%FILL_EVENT_REJECTED%'"
    )
    assert raw.sql == "SELECT * FROM audit WHERE payload LIKE '%%FILL_EVENT_REJECTED%%'"


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
        assert store.rows("PRAGMA user_version")[0][0] == 14
    finally:
        store.close()

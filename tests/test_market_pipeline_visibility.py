from decimal import Decimal

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import Candle, Tick
from backend.shared.postgres import PostgresStore


def _tick(ts, price, identity):
    return Tick("TCS", ts, Decimal(price), 0, identity, volume_available=False)


def _close_one_minute(platform):
    platform.tick(_tick(1_800_000_000, "100.25", "a"), replay=True)
    platform.tick(_tick(1_800_000_059, "101.50", "b"), replay=True)
    platform.tick(_tick(1_800_000_060, "100.75", "c"), replay=True)


def test_closed_candles_are_idempotent_provider_scoped_and_restart_safe(tmp_path):
    database = tmp_path / "market.db"
    first = Platform(str(database))
    try:
        _close_one_minute(first)
        rows = first.store.candle_rows("TCS", 60, 20, provider="replay")
        assert len(rows) == 1
        assert rows[0]["open"] == "100.25"
        assert rows[0]["high"] == "101.50"
        assert rows[0]["low"] == "100.25"
        assert rows[0]["close"] == "101.50"
        assert rows[0]["volume_available"] == 0

        original = Candle(
            "TCS",
            60,
            rows[0]["start_time"],
            rows[0]["end_time"],
            Decimal("1"),
            Decimal("2"),
            Decimal("1"),
            Decimal("2"),
            0,
            True,
            False,
            "MOCK_REPLAY",
        )
        first.store.save_candle(original, provider="other-source")
        first.store.save_candle(original, provider="replay")
        assert first.store.candle_count("replay") == 1
        assert first.store.candle_count("other-source") == 1
        assert first.store.candle_rows("TCS", 60, 20, "replay")[0]["close"] == "101.50"
    finally:
        first.close()

    restored = Platform(str(database))
    try:
        assert len(restored.closed_candles) == 1
        assert restored.closed_candles[0].data_source == "MOCK_REPLAY"
        assert (
            restored.store.candle_rows("TCS", 60, 20, "replay")[0]["close"] == "101.50"
        )
    finally:
        restored.close()


def test_authenticated_candle_api_filters_symbol_timeframe_and_provider():
    platform = Platform()
    try:
        _close_one_minute(platform)
        with TestClient(create_app(platform)) as client:
            assert client.get("/api/candles?symbol=TCS&interval=60").status_code == 401
            registered = client.post(
                "/api/auth/register",
                json={"username": "candles", "password": "password123"},
            )
            assert registered.status_code == 201
            rows = client.get("/api/candles?symbol=TCS&interval=60&limit=25")
            assert rows.status_code == 200
            assert rows.json()[0]["symbol"] == "TCS"
            assert rows.json()[0]["interval"] == 60
            assert rows.json()[0]["data_source"] == "MOCK_REPLAY"
            assert client.get("/api/candles?interval=120").status_code == 422
            assert client.get("/api/candles?symbol=INFY&interval=60").json() == []
    finally:
        platform.close()


def test_snapshot_exposes_forming_quote_and_candle_pipeline_reason():
    platform = Platform()
    try:
        platform.tick(_tick(1_800_000_000, "100.25", "one"), replay=True)
        evidence = platform.market_data_evidence()
        assert evidence["provider"] == "MOCK_REPLAY"
        assert evidence["feed_status"] == "MOCK_REPLAY"
        assert evidence["latest_quotes"][0]["price"] == "100.25"
        assert evidence["forming_candles"]
        assert all(item["is_closed"] is False for item in evidence["forming_candles"])
        assert evidence["chart_data_status"] == "FORMING"
        assert evidence["chart_data_reason"] == "WAITING_FOR_NEXT_BUCKET_OBSERVATION"
    finally:
        platform.close()


def test_account_snapshot_does_not_expose_other_replay_instruments():
    platform = Platform()
    try:
        platform.account("account-a")
        platform.strategies.subscribe("account-a", "mine", "momentum", "TCS")
        platform.tick(_tick(1_800_000_000, "100.25", "own"), replay=True)
        platform.tick(
            Tick("PRIVATE", 1_800_000_001, Decimal("99"), 0, "other"), replay=True
        )

        snapshot = platform.snapshot("account-a")
        assert [
            item["symbol"] for item in snapshot["market_data"]["latest_quotes"]
        ] == ["TCS"]
        assert {
            item["symbol"] for item in snapshot["market_data"]["forming_candles"]
        } == {"TCS"}
        assert {item["symbol"] for item in snapshot["candles"]} <= {"TCS"}
    finally:
        platform.close()


class _Cursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else {"n": 0}


class _CaptureDB:
    def __init__(self):
        self.calls = []

    def execute(self, query, args=()):
        self.calls.append((query, args))
        return _Cursor()

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_candle_repository_uses_migration_column_names():
    store = object.__new__(PostgresStore)
    store.db = _CaptureDB()
    store.depth = 0
    store.CANDLE_RETENTION_SECONDS = 365 * 24 * 60 * 60
    store.lock = __import__("threading").RLock()
    candle = Candle(
        "TCS",
        60,
        60,
        120,
        Decimal("1"),
        Decimal("2"),
        Decimal("1"),
        Decimal("2"),
        0,
        True,
        False,
        "021_LIVE",
    )
    store.save_candle(candle, provider="021")
    store.candle_rows("TCS", 60, 20, provider="021")
    insert_query = store.db.calls[0][0]
    select_query = store.db.calls[2][0]
    assert "interval_seconds" in insert_query
    assert "interval_seconds AS interval" in select_query
    assert store.db.calls[1][0].startswith("DELETE FROM algoshield.closed_candles")

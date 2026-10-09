from decimal import Decimal

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import Candle, Fill, Side
from backend.strategies.runtime import subscription_id_fragment


def register(client, username="batch_user"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "password123"},
    )
    assert response.status_code == 201
    return response.json()["user"]["account_id"]


def candle(symbol, start=0):
    return Candle(
        symbol,
        60,
        start,
        start + 60,
        Decimal("100"),
        Decimal("101"),
        Decimal("99"),
        Decimal("100"),
        10,
        True,
    )


def test_symbol_id_fragment_preserves_trading_symbol_separately():
    assert subscription_id_fragment("ABC.NS") == "abc-ns"


def test_batch_requires_authentication():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            response = client.post(
                "/api/subscriptions/batch",
                json={"kind": "momentum", "symbols": ["TCS"]},
            )
            assert response.status_code == 401
    finally:
        platform.close()


def test_batch_normalizes_deduplicates_and_creates_owned_instances():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            account = register(client)
            response = client.post(
                "/api/subscriptions/batch",
                json={
                    "kind": " MOMENTUM ",
                    "symbols": ["reliance", " RELIANCE ", "TCS", "abc.ns"],
                    "instance_prefix": " Swing Desk ",
                },
            )
            assert response.status_code == 201
            body = response.json()
            assert body["count"] == 3
            assert body["symbols"] == ["RELIANCE", "TCS", "ABC.NS"]
            assert [row["id"] for row in body["created"]] == [
                "swing-desk-reliance",
                "swing-desk-tcs",
                "swing-desk-abc-ns",
            ]
            assert {row["account"] for row in body["created"]} == {account}
            assert {
                row["symbol"] for row in client.get("/api/subscriptions").json()
            } == {"ABC.NS", "RELIANCE", "TCS"}
            events = platform.store.rows(
                "SELECT type FROM audit WHERE type='SUBSCRIPTIONS_BATCH_CREATED'"
            )
            assert len(events) == 1
    finally:
        platform.close()


def test_batch_collision_is_atomic_and_reports_existing_ids():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            register(client)
            platform.strategies.subscribe(
                "acc_batch_user", "momentum-tcs", "momentum", "TCS"
            )
            response = client.post(
                "/api/subscriptions/batch",
                json={"kind": "momentum", "symbols": ["RELIANCE", "TCS", "INFY"]},
            )
            assert response.status_code == 409
            assert response.json()["detail"] == {
                "code": "SUBSCRIPTION_BATCH_CONFLICT",
                "existing": ["momentum-tcs"],
            }
            rows = platform.store.rows("SELECT id FROM subscriptions ORDER BY id")
            assert [row["id"] for row in rows] == ["momentum-tcs"]
    finally:
        platform.close()


def test_batch_rows_are_visible_only_to_the_authenticated_owner():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as owner, TestClient(app) as other:
            owner_account = register(owner, "owner")
            register(other, "other")
            response = owner.post(
                "/api/subscriptions/batch",
                json={"kind": "momentum", "symbols": ["TCS", "INFY"]},
            )
            assert response.status_code == 201
            assert {row["account"] for row in response.json()["created"]} == {
                owner_account
            }
            assert other.get("/api/subscriptions").json() == []
    finally:
        platform.close()


def test_unknown_strategy_and_symbol_limit_create_nothing():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            register(client)
            unknown = client.post(
                "/api/subscriptions/batch",
                json={"kind": "made_up_strategy", "symbols": ["TCS"]},
            )
            assert unknown.status_code == 409
            too_many = client.post(
                "/api/subscriptions/batch",
                json={"kind": "momentum", "symbols": [f"S{i}" for i in range(21)]},
            )
            assert too_many.status_code == 422
            blank = client.post(
                "/api/subscriptions/batch",
                json={"kind": "momentum", "symbols": ["TCS", "   "]},
            )
            assert blank.status_code == 422
            forged_account = client.post(
                "/api/subscriptions/batch",
                json={
                    "kind": "momentum",
                    "symbols": ["TCS"],
                    "account_id": "someone_else",
                },
            )
            assert forged_account.status_code == 422
            assert platform.store.rows("SELECT id FROM subscriptions") == []
    finally:
        platform.close()


def test_runtime_symbol_stop_and_failure_isolation():
    platform = Platform()
    calls = []
    try:
        platform.account("isolation")

        def handler(subscription, _candle):
            calls.append(subscription["symbol"])
            if subscription["symbol"] == "TCS":
                raise RuntimeError("symbol-local failure")
            return None

        platform.strategies.register_strategy("isolated", handler, warmup=1)
        created = platform.strategies.subscribe_many(
            "isolation", "isolated", ["RELIANCE", "TCS", "INFY"], "iso"
        )
        assert len(created) == 3
        platform.strategies.enabled = True

        platform.strategies.on_candle(candle("RELIANCE"), platform.clock())
        assert calls == ["RELIANCE"]
        platform.strategies.on_candle(candle("TCS"), platform.clock())
        enabled = {
            row["symbol"]: row["enabled"]
            for row in platform.store.rows("SELECT symbol,enabled FROM subscriptions")
        }
        assert enabled == {"RELIANCE": 1, "TCS": 0, "INFY": 1}

        platform.strategies.set_enabled("isolation", "iso-infy", False)
        platform.strategies.on_candle(candle("RELIANCE", 60), platform.clock())
        platform.strategies.on_candle(candle("INFY", 60), platform.clock())
        assert calls == ["RELIANCE", "TCS", "RELIANCE"]
    finally:
        platform.close()


def test_replay_batch_and_financial_attribution_cover_all_symbols():
    platform = Platform()
    try:
        platform.account("portfolio")
        created = platform.strategies.subscribe_many(
            "portfolio", "momentum", ["RELIANCE", "TCS"], "multi"
        )
        ticks = platform.generate_simulation_batch(
            [row["symbol"] for row in created], minutes=2
        )
        symbols = {tick.symbol for tick in ticks}
        assert symbols == {"RELIANCE", "TCS"}
        for tick in ticks:
            platform.tick(tick, replay=True)
        candle_symbols = {
            row["symbol"] for row in platform.snapshot("portfolio")["candles"]
        }
        assert candle_symbols == {"RELIANCE", "TCS"}

        for index, row in enumerate(created, start=1):
            platform.ledger.apply(
                Fill(
                    f"fill-{index}",
                    f"order-{index}",
                    row["id"],
                    "portfolio",
                    row["symbol"],
                    Side.BUY,
                    index,
                    Decimal("100"),
                    float(index),
                    Decimal("0.10"),
                )
            )
        positions = platform.ledger.positions()
        assert positions[("portfolio", "multi-reliance", "RELIANCE")].net_quantity == 1
        assert positions[("portfolio", "multi-tcs", "TCS")].net_quantity == 2
    finally:
        platform.close()

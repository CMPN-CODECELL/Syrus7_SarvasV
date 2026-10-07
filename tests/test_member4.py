from decimal import Decimal as D

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.market_data.candles import CandleBuilder
from backend.platform import Platform
from backend.shared.contracts import Candle, OrderIntent, Side, Tick


def closed_candle(interval=60, start=0, open_price="100", close_price="101"):
    open_value = D(open_price)
    close_value = D(close_price)
    return Candle(
        "X",
        interval,
        start,
        start + interval,
        open_value,
        max(open_value, close_value),
        min(open_value, close_value),
        close_value,
        10,
        True,
    )


def configured_platform(path=":memory:"):
    platform = Platform(path)
    platform.account("a")
    for strategy, kind in (
        ("ema", "momentum"),
        ("mean", "mean_reversion"),
        ("range", "breakout"),
    ):
        platform.strategies.subscribe("a", strategy, kind, "X")
    platform.reliability.resume()
    return platform


def test_builtin_strategies_use_ema_mean_and_five_minute_breakout():
    platform = configured_platform()
    try:
        candles = [
            closed_candle(start=0, close_price="100"),
            closed_candle(start=60, close_price="102"),
            closed_candle(start=120, close_price="104"),
            closed_candle(start=180, close_price="106"),
            closed_candle(start=240, close_price="108"),
            closed_candle(300, 0, "100", "101"),
            closed_candle(300, 300, "102", "105"),
        ]
        intents = [
            intent
            for candle in candles
            for intent in platform.strategies.on_candle(candle, platform.clock())
        ]
        by_strategy = {intent.strategy_instance_id: intent for intent in intents}
        assert by_strategy["ema"].side == Side.BUY
        assert by_strategy["mean"].side == Side.SELL
        assert by_strategy["range"].side == Side.BUY
        assert "EMA" in by_strategy["ema"].reason
        assert "5m" in by_strategy["range"].reason
        assert {signal["interval"] for signal in platform.strategies.signals} == {
            60,
            300,
        }
    finally:
        platform.store.close()


def test_one_minute_strategies_require_full_five_candle_warmup():
    platform = configured_platform()
    try:
        warming = [
            closed_candle(start=minute * 60, close_price=str(100 + minute * 2))
            for minute in range(4)
        ]
        assert [
            intent
            for candle in warming
            for intent in platform.strategies.on_candle(candle, platform.clock())
        ] == []

        ready = platform.strategies.on_candle(
            closed_candle(start=240, close_price="108"), platform.clock()
        )
        assert {intent.strategy_instance_id for intent in ready} == {"ema", "mean"}

        platform.strategies.set_enabled("a", "ema", False)
        platform.strategies.set_enabled("a", "ema", True)
        for minute in range(4):
            assert all(
                intent.strategy_instance_id != "ema"
                for intent in platform.strategies.on_candle(
                    closed_candle(
                        start=600 + minute * 60,
                        close_price=str(110 + minute * 2),
                    ),
                    platform.clock(),
                )
            )
    finally:
        platform.store.close()


def test_callback_failure_stops_only_faulted_subscription():
    platform = configured_platform()

    def fail(_subscription, _candle):
        raise RuntimeError("private callback detail")

    platform.strategies.handlers["momentum"] = fail
    platform.strategies.handlers["mean_reversion"] = lambda _s, _c: (
        Side.SELL,
        "test signal",
    )
    try:
        intents = platform.strategies.on_candle(closed_candle(), platform.clock())
        assert [intent.strategy_instance_id for intent in intents] == ["mean"]
        rows = {
            row["id"]: row["enabled"]
            for row in platform.store.rows("SELECT id,enabled FROM subscriptions")
        }
        assert rows == {"ema": 0, "mean": 1, "range": 1}
        blocked = platform.risk.submit(
            OrderIntent("faulted", "ema", "a", "X", Side.BUY, 1, platform.clock())
        )
        assert blocked.reason_code == "RISK_STRATEGY_STOPPED"
        assert platform.risk.state == "RUNNING"
        assert platform.strategies.errors[0]["error_type"] == "RuntimeError"
        assert "private callback detail" not in str(platform.strategies.errors)
    finally:
        platform.store.close()


def test_subscription_stop_persists_and_start_requires_matching_account(tmp_path):
    path = str(tmp_path / "member4.db")
    platform = configured_platform(path)
    platform.strategies.set_enabled("a", "ema", False)
    platform.store.close()

    restarted = Platform(path)
    try:
        row = restarted.store.rows("SELECT enabled FROM subscriptions WHERE id='ema'")[
            0
        ]
        assert row["enabled"] == 0
        try:
            restarted.strategies.set_enabled("wrong", "ema", True)
        except ValueError as exc:
            assert "does not exist" in str(exc)
        else:
            raise AssertionError("cross-account strategy start was accepted")
        restarted.strategies.set_enabled("a", "ema", True)
        assert (
            restarted.store.rows("SELECT enabled FROM subscriptions WHERE id='ema'")[0][
                "enabled"
            ]
            == 1
        )
    finally:
        restarted.store.close()


def test_tick_deduplication_is_symbol_scoped_and_bounded():
    builder = CandleBuilder(max_seen_ids=2)
    assert builder.ingest(Tick("X", 0, D("100"), 1, "same")) == []
    assert builder.ingest(Tick("Y", 0, D("200"), 1, "same")) == []
    assert builder.stats()["tracked_event_ids"] == 2
    assert builder.ingest(Tick("X", 0, D("100"), 1, "same")) == []
    assert builder.stats()["duplicate_ticks"] == 1
    builder.ingest(Tick("X", 1, D("101"), 1, "next"))
    assert builder.stats()["tracked_event_ids"] == 2


def test_subscription_api_normalizes_inputs_and_controls_state():
    platform = Platform()
    with TestClient(create_app(platform)) as client:
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Independent strategy ledgers" in dashboard.text
        assert 'id="account-form"' in dashboard.text
        assert 'id="signals"' in dashboard.text
        assert (
            client.post("/api/accounts", json={"account_id": " a "}).status_code == 201
        )
        response = client.post(
            "/api/subscriptions",
            json={
                "account_id": "a",
                "strategy_instance_id": " ema ",
                "kind": " MOMENTUM ",
                "symbol": " x ",
            },
        )
        assert response.status_code == 201
        subscription = response.json()[0]
        assert (subscription["id"], subscription["kind"], subscription["symbol"]) == (
            "ema",
            "momentum",
            "X",
        )
        stopped = client.post(
            "/api/subscriptions/ema/stop", json={"account_id": "a"}
        ).json()[0]
        assert stopped["state"] == "STOPPED"
        started = client.post(
            "/api/subscriptions/ema/start", json={"account_id": "a"}
        ).json()[0]
        assert started["state"] == "READY"
    platform.store.close()


def test_demo_is_forbidden_when_persistent_mode_disables_it():
    platform = Platform(demo_enabled=False)
    with TestClient(create_app(platform)) as client:
        response = client.post("/api/demo")
        assert response.status_code == 403
        assert not platform.store.rows("SELECT id FROM accounts")
    platform.store.close()

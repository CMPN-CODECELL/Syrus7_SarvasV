from decimal import Decimal as D

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import Tick


class Clock:
    def __init__(self, value=1_700_000_000):
        self.value = value

    def __call__(self):
        return self.value


def tick(platform, clock, symbol, price, sequence):
    clock.value += 1
    platform.tick(Tick(symbol, clock.value, D(str(price)), 1, f"{symbol}-{sequence}"))


def running_platform():
    clock = Clock()
    platform = Platform(
        clock=clock,
        auto_lookback=3,
        auto_entry_momentum=D("0.01"),
        auto_take_profit=D("0.01"),
        auto_stop_loss=D("0.01"),
        auto_cooldown_seconds=0,
    )
    platform.account("account-a")
    platform.strategies.subscribe("account-a", "seed-a", "momentum", "AAA")
    platform.strategies.subscribe("account-a", "seed-b", "momentum", "BBB")
    assert platform.reliability.reconcile()
    platform.reliability.resume()
    platform.market_session.set_status("OPEN")
    return platform, clock


def test_auto_mode_buys_strongest_candidate_and_exits_at_profit_target():
    platform, clock = running_platform()
    try:
        evidence = platform.auto_mode.start("account-a")
        assert evidence["candidate_count"] == 2
        for index, price in enumerate((100, 100, 100)):
            tick(platform, clock, "BBB", price, index)
        for index, price in enumerate((100, 101)):
            tick(platform, clock, "AAA", price, index)
        assert platform.reliability.reconcile()
        platform.reliability.resume()
        tick(platform, clock, "AAA", 103, 2)

        orders = platform.store.rows(
            "SELECT side,status FROM orders WHERE strategy LIKE 'auto-%' ORDER BY created"
        )
        assert [(row["side"], row["status"]) for row in orders] == [("BUY", "FILLED")]
        assert (
            platform.snapshot("account-a")["auto_mode"]["decisions"][0]["action"]
            == "BUY"
        )
        assert (
            platform.snapshot("account-a")["auto_mode"]["decisions"][0][
                "selected_strategy"
            ]
            == "momentum"
        )

        tick(platform, clock, "AAA", 105, "profit")
        orders = platform.store.rows(
            "SELECT side,status FROM orders WHERE strategy LIKE 'auto-%' ORDER BY created,id"
        )
        assert [(row["side"], row["status"]) for row in orders] == [
            ("BUY", "FILLED"),
            ("SELL", "FILLED"),
        ]
        position = next(
            item
            for item in platform.snapshot("account-a")["positions"]
            if item["strategy_instance_id"].startswith("auto-")
        )
        assert position["net_quantity"] == 0
    finally:
        platform.close()


def test_auto_mode_never_bypasses_stopped_global_gate():
    platform, clock = running_platform()
    try:
        platform.auto_mode.start("account-a")
        platform.reliability.fail_closed("TEST_STOP")
        for index, price in enumerate((100, 100, 100)):
            tick(platform, clock, "BBB", price, index)
        for index, price in enumerate((100, 101, 103)):
            tick(platform, clock, "AAA", price, index)
        assert not platform.store.rows(
            "SELECT id FROM orders WHERE strategy LIKE 'auto-%'"
        )
        decision = platform.store.rows(
            "SELECT payload FROM audit WHERE type='RISK_DECISION' ORDER BY sequence DESC LIMIT 1"
        )[0]["payload"]
        assert "GLOBAL_GATE" in decision
    finally:
        platform.close()


def test_auto_mode_compares_momentum_breakout_and_mean_reversion():
    platform, _clock = running_platform()
    try:
        selected, score, scores = platform.auto_mode._strategy_opportunity(
            (D("105"), D("95"), D("97"))
        )
        assert selected == "mean_reversion"
        assert score == scores["mean_reversion"]
        assert set(scores) == {"momentum", "breakout", "mean_reversion"}
    finally:
        platform.close()


def test_auto_mode_api_is_authenticated_and_account_scoped():
    platform = Platform()
    platform.account("account-a")
    platform.strategies.subscribe("account-a", "seed-a", "momentum", "AAA")
    app = create_app(platform)
    try:
        with TestClient(app) as client:
            assert client.post("/api/auto-mode/start").status_code == 401
            client.post(
                "/api/auth/register",
                json={"username": "trader", "password": "Passw0rd!"},
            )
            response = client.post("/api/auto-mode/start")
            assert response.status_code == 200
            assert response.json()["enabled"] is True
            assert client.post("/api/auto-mode/stop").json()["enabled"] is False
    finally:
        platform.close()

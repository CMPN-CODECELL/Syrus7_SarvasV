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
        assert (
            platform.snapshot("account-a")["auto_mode"]["decisions"][0]["result"]
            == "APPROVED"
        )

        # Duplicate canonical ticks return before auto-mode evaluation, so the
        # accepted entry cannot create a second intent or broker order.
        platform.tick(Tick("AAA", clock(), D("103"), 1, "AAA-2"))
        assert (
            platform.store.rows(
                "SELECT COUNT(*) AS n FROM orders WHERE strategy LIKE 'auto-%'"
            )[0]["n"]
            == 1
        )

        platform.broker.all_market_symbols = lambda: ("BBB",)
        platform.auto_mode.scan_limit = 1
        platform.auto_mode.start("account-a")
        assert platform.auto_mode.market_symbols() == ("AAA",)

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


def test_auto_mode_counts_pending_entries_and_skips_repeatedly_rejected_symbols():
    platform, clock = running_platform()
    try:
        platform.broker.all_market_symbols = lambda: ("AAA", "BBB", "CCC")
        with platform.store.transaction() as db:
            for sequence in (1, 2):
                db.execute(
                    "INSERT INTO orders "
                    "(id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) "
                    "VALUES (?,?,?,?,?,?,?,?,0,0,1)",
                    (
                        f"rejected-{sequence}",
                        "auto-rejected-aaa",
                        "account-a",
                        "AAA",
                        "BUY",
                        1,
                        clock(),
                        "REJECTED",
                    ),
                )
            db.execute(
                "INSERT INTO orders "
                "(id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) "
                "VALUES ('pending','auto-pending-bbb','account-a','BBB','BUY',1,?,'OPEN',0,0,1)",
                (clock(),),
            )

        assert platform.auto_mode._position_count("account-a") == 1
        platform.auto_mode.scan_limit = 2
        platform.auto_mode.start("account-a")
        assert platform.auto_mode.market_symbols() == ("BBB", "CCC")
    finally:
        platform.close()


def test_prototype_defaults_trade_after_two_updates_for_one_warmed_symbol():
    clock = Clock()
    platform = Platform(clock=clock, auto_scan_limit=2)
    platform.account("account-a")
    platform.strategies.subscribe("account-a", "seed-a", "momentum", "AAA")
    assert platform.reliability.reconcile()
    platform.reliability.resume()
    platform.market_session.set_status("OPEN")
    try:
        platform.auto_mode.start("account-a")
        tick(platform, clock, "AAA", 100, 1)
        tick(platform, clock, "AAA", 100.02, 2)

        orders = platform.store.rows(
            "SELECT side,quantity,status FROM orders WHERE strategy LIKE 'auto-%'"
        )
        assert [tuple(row) for row in orders] == [("BUY", 1, "FILLED")]
        policy = platform.auto_mode.evidence("account-a")["policy"]
        assert policy["lookback_updates"] == 2
        assert policy["min_warmed_symbols"] == 1
        assert policy["max_positions"] == 1
        assert policy["cooldown_seconds"] == 2
    finally:
        platform.close()


def test_auto_mode_persists_selected_instance_before_entry_threshold():
    platform, clock = running_platform()
    try:
        platform.auto_mode.entry_momentum = D("0.50")
        platform.auto_mode.start("account-a")
        for index, price in enumerate((100, 100, 100)):
            tick(platform, clock, "BBB", price, index)
        for index, price in enumerate((100, 100, 101)):
            tick(platform, clock, "AAA", price, index)

        snapshot = platform.snapshot("account-a")
        auto = snapshot["auto_mode"]
        assert auto["selected_symbol"] == "AAA"
        assert auto["selected_strategy_instance_id"].startswith("auto-")
        assert len(auto["instances"]) == 1
        instance = auto["instances"][0]
        assert instance["symbol"] == "AAA"
        assert instance["readiness"] == {
            "samples": 3,
            "warmup": 3,
            "ready": True,
            "evidence": "NORMALIZED_MARKET_UPDATES",
        }
        assert instance["financial_position"]["evidence_status"] == "NO_FILLS"
        assert instance["latest_order"] is None
        assert not platform.store.rows(
            "SELECT id FROM orders WHERE strategy LIKE 'auto-%'"
        )
    finally:
        platform.close()


def test_auto_mode_retires_flat_unselected_instances():
    platform, _clock = running_platform()
    try:
        platform.strategies.subscribe(
            "account-a", "auto-retired-old", "auto_adaptive", "OLD"
        )
        platform.auto_mode.start("account-a")
        selected = platform.auto_mode._select_subscription(
            "account-a", "AAA", "momentum"
        )

        rows = {
            row["id"]: row
            for row in platform.store.rows(
                "SELECT id,enabled FROM subscriptions WHERE kind='auto_adaptive'"
            )
        }
        assert rows[selected]["enabled"] == 1
        assert rows["auto-retired-old"]["enabled"] == 0
        assert [
            row["id"]
            for row in platform.snapshot("account-a")["auto_mode"]["instances"]
        ] == [selected]
    finally:
        platform.close()


def test_auto_mode_restores_explicit_start_but_not_stop(tmp_path):
    path = str(tmp_path / "auto-restore.db")
    first = Platform(path)
    first.account("account-a")
    first.strategies.subscribe("account-a", "seed-a", "momentum", "AAA")
    first.auto_mode.start("account-a")
    first.close()

    restarted = Platform(path)
    try:
        assert restarted.auto_mode.restore() == ("account-a",)
        assert restarted.auto_mode.evidence("account-a")["enabled"] is True
        restarted.auto_mode.stop("account-a")
    finally:
        restarted.close()

    stopped = Platform(path)
    try:
        assert stopped.auto_mode.restore() == ()
        assert stopped.auto_mode.evidence("account-a")["enabled"] is False
    finally:
        stopped.close()


def test_subscription_without_fills_has_backend_zero_projection():
    platform, _clock = running_platform()
    try:
        subscription = next(
            row
            for row in platform.snapshot("account-a")["subscriptions"]
            if row["id"] == "seed-a"
        )
        assert subscription["financial_position"] == {
            "strategy_instance_id": "seed-a",
            "symbol": "AAA",
            "net_quantity": 0,
            "average_price": "0",
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "gross_pnl": "0",
            "charges": "0",
            "net_pnl": "0",
            "evidence_status": "NO_FILLS",
        }
        assert platform.snapshot("account-a")["positions"] == []
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

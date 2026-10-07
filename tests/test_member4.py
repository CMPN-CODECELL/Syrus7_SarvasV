import json
from decimal import Decimal as D

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.market_data.candles import CandleBuilder
from backend.market_data.session import MarketSession
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


def test_duplicate_tick_cannot_overwrite_latest_market_mark():
    platform = Platform()
    try:
        platform.tick(Tick("X", 0, D("100"), 1, "event-1"))
        platform.tick(Tick("X", 0, D("999"), 1, "event-1"))

        assert platform.ledger.marks["X"] == D("100")
        assert platform.candles.stats() == {
            "accepted_ticks": 1,
            "duplicate_ticks": 1,
            "late_ticks": 0,
            "tracked_event_ids": 1,
            "last_event_timestamp": {"X": 0},
        }
    finally:
        platform.store.close()


def test_rejected_tick_fails_closed_with_durable_sanitized_evidence():
    platform = configured_platform()
    try:
        platform.tick(Tick("X", 60, D("100"), 1, "newer"))

        try:
            platform.tick(Tick("X", 59, D("101"), 1, "late"))
        except ValueError as exc:
            assert "late tick" in str(exc)
        else:
            raise AssertionError("late tick was accepted")

        assert platform.risk.state == "UNCERTAIN"
        assert not platform.strategies.enabled
        evidence = platform.store.rows(
            "SELECT type,payload FROM audit WHERE type='MARKET_DATA_REJECTED'"
        )
        assert len(evidence) == 1
        assert '"symbol": "X"' in evidence[0]["payload"]
        assert '"event_id": "late"' in evidence[0]["payload"]
        assert '"reason": "LATE_TICK"' in evidence[0]["payload"]
    finally:
        platform.store.close()


def test_subscription_api_normalizes_inputs_and_controls_state():
    platform = Platform()
    with TestClient(create_app(platform)) as client:
        registered = client.post(
            "/api/auth/register",
            json={"username": "memberfour", "password": "password4"},
        )
        assert registered.status_code == 201
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Independent strategy ledgers" in dashboard.text
        assert 'id="account-form"' not in dashboard.text
        assert 'name="account_id"' not in dashboard.text
        assert 'id="subscription-form"' in dashboard.text
        assert "RSI reversal" in dashboard.text
        assert 'id="safety-state"' not in dashboard.text
        assert 'class="safety-strip"' in dashboard.text
        assert 'id="signals"' in dashboard.text
        response = client.post(
            "/api/subscriptions",
            json={
                "strategy_instance_id": " ema ",
                "kind": " MOMENTUM ",
                "symbol": " x ",
            },
        )
        assert response.status_code == 201
        subscription = response.json()[0]
        assert (
            subscription["id"],
            subscription["kind"],
            subscription["symbol"],
            subscription["account"],
        ) == (
            "ema",
            "momentum",
            "X",
            "acc_memberfour",
        )
        stopped = client.post("/api/subscriptions/ema/stop").json()[0]
        assert stopped["state"] == "STOPPED"
        started = client.post("/api/subscriptions/ema/start").json()[0]
        assert started["state"] == "READY"
    platform.store.close()


def test_demo_is_forbidden_when_persistent_mode_disables_it():
    platform = Platform(demo_enabled=False)
    with TestClient(create_app(platform)) as client:
        response = client.post("/api/demo")
        assert response.status_code == 403
        assert not platform.store.rows("SELECT id FROM accounts")
    platform.store.close()


def test_api_preserves_money_and_prices_as_decimal_strings():
    platform = Platform()
    with TestClient(create_app(platform)) as client:
        response = client.post("/api/demo")
        assert response.status_code == 200
        state = response.json()

        assert state["positions"]
        for position in state["positions"]:
            for field in (
                "average_price",
                "realized_pnl",
                "unrealized_pnl",
                "charges",
                "net_pnl",
            ):
                assert isinstance(position[field], str)

        assert state["candles"]
        for candle in state["candles"]:
            for field in ("open", "high", "low", "close"):
                assert isinstance(candle[field], str)

        for fill in state["fills"]:
            assert isinstance(fill["price"], str)
            assert isinstance(fill["charges"], str)
    platform.store.close()


def test_configurable_candle_builder_intervals_and_add_interval():
    builder = CandleBuilder(intervals=(15, 60))
    assert builder.intervals == (15, 60)
    # Ticks spanning across 15-second boundaries
    builder.ingest(Tick("XYZ", 0, D("100"), 10, "t1"))
    builder.ingest(Tick("XYZ", 10, D("102"), 5, "t2"))
    closed = builder.ingest(Tick("XYZ", 15, D("105"), 10, "t3"))
    # The 15s candle [0, 15) should close when tick at 15 arrives
    assert len(closed) == 1
    assert closed[0].interval == 15
    assert closed[0].start_time == 0
    assert closed[0].open == D("100")
    assert closed[0].high == D("102")
    assert closed[0].close == D("102")
    assert closed[0].volume == 15

    # Test adding an interval dynamically
    builder.add_interval(900)
    assert 900 in builder.intervals

    # Invalid intervals validation
    try:
        CandleBuilder(intervals=())
    except ValueError as exc:
        assert "at least one candle interval is required" in str(exc)

    try:
        CandleBuilder(intervals=(-10,))
    except ValueError as exc:
        assert "positive integers" in str(exc)


def test_rsi_reversal_strategy_warmup_and_signals():
    platform = configured_platform()
    try:
        platform.strategies.subscribe("a", "rsi_inst", "rsi_reversal", "X")
        # 14 candles warmup - no signals should be produced
        prices = [D("100") - D(i) for i in range(14)]
        for i, p in enumerate(prices):
            intents = platform.strategies.on_candle(
                closed_candle(
                    interval=60, start=i * 60, open_price=str(p), close_price=str(p)
                ),
                platform.clock(),
            )
            assert all(intent.strategy_instance_id != "rsi_inst" for intent in intents)

        # 15th candle with another decline -> RSI will be oversold (< 30)
        p15 = D("80")
        intents = platform.strategies.on_candle(
            closed_candle(
                interval=60, start=14 * 60, open_price=str(p15), close_price=str(p15)
            ),
            platform.clock(),
        )
        rsi_intents = [it for it in intents if it.strategy_instance_id == "rsi_inst"]
        assert len(rsi_intents) == 1
        assert rsi_intents[0].side == Side.BUY
        assert "RSI oversold reversal" in rsi_intents[0].reason

        # Now simulate a massive rally to push RSI > 70
        for i in range(15, 30):
            rally_p = D("80") + D((i - 14) * 10)
            intents = platform.strategies.on_candle(
                closed_candle(
                    interval=60,
                    start=i * 60,
                    open_price=str(rally_p),
                    close_price=str(rally_p),
                ),
                platform.clock(),
            )
        # Should have emitted a SELL signal when crossing into overbought
        overbought_intents = [
            signal
            for signal in platform.strategies.signals
            if signal["strategy"] == "rsi_inst" and signal["side"] == "SELL"
        ]
        assert len(overbought_intents) >= 1
        assert "overbought" in overbought_intents[0]["reason"]
    finally:
        platform.store.close()


def test_dynamic_strategy_registration_and_api():
    platform = Platform()
    try:
        # Register custom strategy
        def custom_scalp(_sub, candle):
            if candle.close > D("200"):
                return Side.BUY, "custom price trigger"
            return None

        platform.strategies.register_strategy(
            "custom_scalp",
            custom_scalp,
            interval=60,
            warmup=1,
            description="Scalping trigger when close > 200",
        )

        with TestClient(create_app(platform)) as client:
            assert (
                client.post(
                    "/api/auth/register",
                    json={"username": "customuser", "password": "password4"},
                ).status_code
                == 201
            )
            resp = client.get("/api/strategies")
            assert resp.status_code == 200
            registered = resp.json()
            kinds = {item["kind"] for item in registered}
            assert {
                "momentum",
                "mean_reversion",
                "breakout",
                "rsi_reversal",
                "custom_scalp",
            }.issubset(kinds)

            # Subscribe to the custom strategy via API
            sub_resp = client.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "scalp_1",
                    "kind": "custom_scalp",
                    "symbol": "X",
                },
            )
            assert sub_resp.status_code == 201
            platform.reliability.resume()

            intents = platform.strategies.on_candle(
                closed_candle(start=0, open_price="190", close_price="210"),
                platform.clock(),
            )
            scalp_intents = [
                it for it in intents if it.strategy_instance_id == "scalp_1"
            ]
            assert len(scalp_intents) == 1
            assert scalp_intents[0].side == Side.BUY
            assert scalp_intents[0].reason == "custom price trigger"
    finally:
        platform.store.close()


def test_market_session_hours_and_halt_logic():
    session = MarketSession(
        open_time_seconds=9 * 3600,
        close_time_seconds=15 * 3600,
        enforce_hours=True,
    )
    # Outside hours (e.g. 08:00 = 28800s)
    assert not session.is_open(28800)
    # Inside hours (e.g. 10:00 = 36000s)
    assert session.is_open(36000)
    # At exact open & close
    assert session.is_open(9 * 3600)
    assert session.is_open(15 * 3600)
    # Outside hours (e.g. 16:00 = 57600s)
    assert not session.is_open(57600)

    # Halt overrides hours
    session.halt("circuit breaker")
    assert session.status == "HALTED"
    assert not session.is_open(36000)
    session.resume()
    assert session.status == "OPEN"
    assert session.is_open(36000)

    # Manual override status
    session.set_status("CLOSED")
    assert session.status == "CLOSED"
    assert not session.is_open(36000)
    session.set_status("OPEN")
    assert session.is_open(57600)

    # Invalid status
    try:
        session.set_status("INVALID")
    except ValueError as exc:
        assert "status must be" in str(exc)


def test_market_session_coordinates_with_risk_evidence_gate():
    platform = configured_platform()
    try:
        now_ts = int(platform.clock())
        # Provide fresh mark and broker state
        platform.tick(Tick("X", now_ts, D("100"), 1, "t1"))
        platform.reliability.observe_tick(Tick("X", now_ts, D("100"), 1, "t1"))
        platform.reliability.last_broker_at = platform.clock()
        platform.reliability.report["verified"] = True
        platform.reliability._health("HEALTHY")

        intent = OrderIntent("intent_1", "ema", "a", "X", Side.BUY, 1, platform.clock())

        # When session is OPEN, intent passes evidence gate
        platform.market_session.set_status("OPEN")
        assert platform.reliability.check_evidence(intent) == ""

        # When session is HALTED, rejected with RISK_MARKET_HALTED
        platform.market_session.halt("Exchange circuit breaker")
        decision = platform.risk.submit(intent)
        assert not decision.allowed
        assert decision.reason_code == "RISK_MARKET_HALTED"
        assert (
            platform.risk.state == "RUNNING"
        )  # Does not trigger unneeded UNCERTAIN fail-closed

        # When session is CLOSED, rejected with RISK_MARKET_CLOSED
        platform.market_session.resume()
        platform.market_session.set_status("CLOSED")
        intent2 = OrderIntent(
            "intent_2", "ema", "a", "X", Side.BUY, 1, platform.clock()
        )
        decision2 = platform.risk.submit(intent2)
        assert not decision2.allowed
        assert decision2.reason_code == "RISK_MARKET_CLOSED"
        assert platform.risk.state == "RUNNING"
    finally:
        platform.store.close()


def test_market_session_api_and_snapshot():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            snap = client.get("/api/state").json()
            assert "market_session" in snap
            assert snap["market_session"]["status"] == "OPEN"

            # GET session endpoint
            resp = client.get("/api/market/session")
            assert resp.status_code == 200
            assert resp.json()["status"] == "OPEN"

            # POST session endpoint: change to CLOSED
            post_resp = client.post("/api/market/session", json={"status": "CLOSED"})
            assert post_resp.status_code == 200
            assert post_resp.json()["status"] == "CLOSED"
            assert platform.market_session.status == "CLOSED"

            # Invalid status rejected
            bad_resp = client.post("/api/market/session", json={"status": "UNKNOWN"})
            assert bad_resp.status_code == 400
    finally:
        platform.store.close()


def test_telemetry_stream_endpoint():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            with client.stream("GET", "/api/stream/telemetry?max_events=1") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                event_type = None
                payload = None
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event_type = line[len("event:") :].strip()
                    elif line.startswith("data:"):
                        payload = json.loads(line[len("data:") :].strip())
                        break
                assert event_type == "snapshot"
                assert payload is not None
                assert "gate" in payload
                assert "market_data" in payload
                assert "market_session" in payload
    finally:
        platform.store.close()

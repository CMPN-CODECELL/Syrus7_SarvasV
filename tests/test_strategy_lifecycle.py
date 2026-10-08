from decimal import Decimal as D
import threading
import time
import pytest

from backend.platform import Platform
from backend.shared.contracts import Candle, Side


def make_closed_candle(interval=60, start=0, close_price="100", symbol="TEST"):
    price = D(close_price)
    return Candle(
        symbol,
        interval,
        start,
        start + interval,
        price,
        price,
        price,
        price,
        10,
        True,
    )


# 1. Registration Validation Tests


def test_register_strategy_validates_inputs():
    platform = Platform()
    try:
        # Invalid handler
        with pytest.raises(ValueError, match="strategy handler must be callable"):
            platform.strategies.register_strategy("bad_h", None)

        # Invalid kind
        with pytest.raises(ValueError, match="strategy kind name required"):
            platform.strategies.register_strategy("   ", lambda s, c: None)

        # Invalid interval (<= 0, non-int, bool, float)
        with pytest.raises(ValueError, match="interval must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_inv1", lambda s, c: None, interval=0
            )
        with pytest.raises(ValueError, match="interval must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_inv2", lambda s, c: None, interval=-60
            )
        with pytest.raises(ValueError, match="interval must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_inv3", lambda s, c: None, interval=True
            )
        with pytest.raises(ValueError, match="interval must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_inv4",
                lambda s, c: None,
                interval="60",  # type: ignore
            )
        with pytest.raises(ValueError, match="interval must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_inv5",
                lambda s, c: None,
                interval=60.5,  # type: ignore
            )

        # Invalid warmup (<= 0, non-int, bool, float)
        with pytest.raises(ValueError, match="warmup must be a positive integer"):
            platform.strategies.register_strategy("bad_w1", lambda s, c: None, warmup=0)
        with pytest.raises(ValueError, match="warmup must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_w2", lambda s, c: None, warmup=-5
            )
        with pytest.raises(ValueError, match="warmup must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_w3", lambda s, c: None, warmup=True
            )
        with pytest.raises(ValueError, match="warmup must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_w4",
                lambda s, c: None,
                warmup="5",  # type: ignore
            )
        with pytest.raises(ValueError, match="warmup must be a positive integer"):
            platform.strategies.register_strategy(
                "bad_w5",
                lambda s, c: None,
                warmup=5.0,  # type: ignore
            )

        # Valid registration
        platform.strategies.register_strategy(
            "custom_ok", lambda s, c: (Side.BUY, "ok"), interval=120, warmup=10
        )
        assert "custom_ok" in platform.strategies.handlers
        meta = platform.strategies.registry["custom_ok"]
        assert meta["interval"] == 120
        assert meta["warmup"] == 10
    finally:
        platform.close()


# 2. Selected/Custom Interval Routing and CandleBuilder Wiring


def test_custom_interval_routing_and_candlebuilder_support():
    platform = Platform()
    try:
        platform.account("acc_test")

        # Register custom 120s strategy
        def handler_120(_sub, _candle):
            return Side.BUY, "custom 120 signal"

        platform.strategies.register_strategy(
            "custom_120", handler_120, interval=120, warmup=1
        )
        # Platform wiring ensures CandleBuilder supports that interval
        assert 120 in platform.candles.intervals

        platform.strategies.subscribe("acc_test", "sub_120", "custom_120", "TEST")
        platform.strategies.subscribe("acc_test", "sub_breakout", "breakout", "TEST")
        platform.reliability.resume()

        # Send 60s candle: Neither sub_120 nor sub_breakout (300s) should receive it
        c_60 = make_closed_candle(interval=60, start=0)
        intents_60 = platform.strategies.on_candle(c_60, platform.clock())
        assert len(intents_60) == 0

        # Send 120s candle: Only sub_120 should receive it
        c_120 = make_closed_candle(interval=120, start=0)
        intents_120 = platform.strategies.on_candle(c_120, platform.clock())
        assert len(intents_120) == 1
        assert intents_120[0].strategy_instance_id == "sub_120"
        assert intents_120[0].reason == "custom 120 signal"

        # Send 300s candle: Only sub_breakout should receive it
        c_300 = make_closed_candle(interval=300, start=0)
        intents_300 = platform.strategies.on_candle(c_300, platform.clock())
        # Breakout warmup needs 1 previous high/low candle
        assert len(intents_300) == 0
        c_300_break = make_closed_candle(interval=300, start=300, close_price="150")
        intents_300_2 = platform.strategies.on_candle(c_300_break, platform.clock())
        assert len(intents_300_2) == 1
        assert intents_300_2[0].strategy_instance_id == "sub_breakout"
    finally:
        platform.close()


# 3. Duplicate and Older Candle Rejection


def test_reject_duplicate_and_older_candles_before_callback():
    platform = Platform()
    try:
        platform.account("acc_test")
        call_count = [0]

        def counting_handler(_sub, _candle):
            call_count[0] += 1
            return Side.BUY, f"count {call_count[0]}"

        platform.strategies.register_strategy(
            "counting_strat", counting_handler, interval=60, warmup=1
        )
        platform.strategies.subscribe("acc_test", "sub_c", "counting_strat", "TEST")
        platform.reliability.resume()

        # First candle at start=120
        c1 = make_closed_candle(interval=60, start=120)
        res1 = platform.strategies.on_candle(c1, platform.clock())
        assert len(res1) == 1
        assert call_count[0] == 1

        # Duplicate candle with identical start=120 must be rejected before callback
        res_dup = platform.strategies.on_candle(c1, platform.clock())
        assert len(res_dup) == 0
        assert call_count[0] == 1, "Handler must not be invoked for duplicate candle"

        # Older candle with start=60 must be rejected before callback
        c_old = make_closed_candle(interval=60, start=60)
        res_old = platform.strategies.on_candle(c_old, platform.clock())
        assert len(res_old) == 0
        assert call_count[0] == 1, "Handler must not be invoked for older candle"

        # Newer candle with start=180 must be processed
        c_new = make_closed_candle(interval=60, start=180)
        res_new = platform.strategies.on_candle(c_new, platform.clock())
        assert len(res_new) == 1
        assert call_count[0] == 2
    finally:
        platform.close()


# 4. Out-of-Order Concurrent Callbacks Cannot Overwrite Newer Indicator State


def test_concurrent_same_instance_processing_commits_monotonically():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 2.0

        slow_gate = threading.Event()

        def reordering_handler(_sub, candle, state=None):
            # Slow down candle at start=60, but let candle at start=120 finish fast
            if candle.start_time == 60:
                slow_gate.wait(timeout=1.0)
            if state is not None:
                state["last_seen_candle"] = candle.start_time
            return Side.BUY, f"candle {candle.start_time}"

        platform.strategies.register_strategy(
            "reorder_strat", reordering_handler, interval=60, warmup=1
        )
        platform.strategies.subscribe("acc_test", "sub_ro", "reorder_strat", "TEST")
        platform.reliability.resume()

        # Dispatch candle 60 in thread 1 (will pause on slow_gate)
        candle_60 = make_closed_candle(interval=60, start=60)
        candle_120 = make_closed_candle(interval=60, start=120)

        t1_result = []

        def run_candle_60():
            t1_result.extend(platform.strategies.on_candle(candle_60, platform.clock()))

        t1 = threading.Thread(target=run_candle_60)
        t1.start()

        # Wait briefly to ensure thread 1 is paused inside handler
        time.sleep(0.05)

        # Thread 2 processes candle 120 and completes first
        res_120 = platform.strategies.on_candle(candle_120, platform.clock())
        assert len(res_120) == 1
        assert platform.strategies.indicators["sub_ro"]["last_seen_candle"] == 120

        # Release thread 1 now; candle 60 finishes after candle 120 was already committed
        slow_gate.set()
        t1.join(timeout=2.0)

        # Thread 1's older result must NOT overwrite the newer state at 120
        assert platform.strategies.indicators["sub_ro"]["last_seen_candle"] == 120
        # And thread 1 must not emit an out-of-order intent
        assert len(t1_result) == 0
    finally:
        platform.close()


# 5. Stop and Re-enable Resets Warmup and Invalidates Old Callbacks


def test_stop_reenable_invalidates_old_callback_and_resets_warmup():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 2.0

        callback_started = threading.Event()
        callback_gate = threading.Event()

        def slow_handler(_sub, _candle, state=None):
            callback_started.set()
            callback_gate.wait(timeout=2.0)
            if state is not None:
                state["committed"] = True
            return Side.BUY, "late signal"

        platform.strategies.register_strategy(
            "slow_stop_strat", slow_handler, interval=60, warmup=1
        )
        platform.strategies.subscribe("acc_test", "sub_ss", "slow_stop_strat", "TEST")
        platform.reliability.resume()

        candle = make_closed_candle(interval=60, start=60)
        t_res = []

        def run_cb():
            t_res.extend(platform.strategies.on_candle(candle, platform.clock()))

        t = threading.Thread(target=run_cb)
        t.start()

        assert callback_started.wait(timeout=1.0)

        # Stop and re-enable subscription while callback is in-flight
        platform.strategies.set_enabled("acc_test", "sub_ss", False)
        platform.strategies.set_enabled("acc_test", "sub_ss", True)

        # Warmup must be reset (no state in indicators)
        readiness = platform.strategies.readiness_for("sub_ss")
        assert readiness["samples"] == 0
        assert readiness["ready"] is False

        # Release callback
        callback_gate.set()
        t.join(timeout=2.0)

        # Old in-flight callback result must be invalidated
        assert len(t_res) == 0
        assert "sub_ss" not in platform.strategies.indicators
    finally:
        platform.close()


# 6. Global Stop / Resume During In-Flight Callback


def test_global_stop_and_resume_during_callback_invalidates_result():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 2.0

        callback_started = threading.Event()
        callback_gate = threading.Event()

        def slow_global_handler(_sub, _candle, state=None):
            callback_started.set()
            callback_gate.wait(timeout=2.0)
            if state is not None:
                state["done"] = True
            return Side.BUY, "epoch test signal"

        platform.strategies.register_strategy(
            "slow_global", slow_global_handler, interval=60, warmup=1
        )
        platform.strategies.subscribe("acc_test", "sub_sg", "slow_global", "TEST")
        platform.reliability.resume()

        candle = make_closed_candle(interval=60, start=60)
        t_res = []

        def run_cb():
            t_res.extend(platform.strategies.on_candle(candle, platform.clock()))

        t = threading.Thread(target=run_cb)
        t.start()

        assert callback_started.wait(timeout=1.0)

        # Global stop followed immediately by resume (enabled becomes True again)
        platform.strategies.enabled = False
        platform.strategies.enabled = True

        # Release callback
        callback_gate.set()
        t.join(timeout=2.0)

        # Even though platform.strategies.enabled is True, epoch advanced so result is discarded
        assert len(t_res) == 0
        assert "sub_sg" not in platform.strategies.indicators
    finally:
        platform.close()


# 7. Readiness Exposure: RSI Needs 15 Closes for 14 Price Changes


def test_readiness_exposure_and_rsi_warmup():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.subscribe("acc_test", "rsi_1", "rsi_reversal", "TEST")
        platform.reliability.resume()

        # Check initial readiness before any candles
        r0 = platform.strategies.readiness_for("rsi_1")
        assert r0["samples"] == 0
        assert r0["warmup"] == 15
        assert r0["ready"] is False

        # Feed 14 closes: samples should be 14, ready False, no intent emitted
        for i in range(14):
            c = make_closed_candle(
                interval=60,
                start=i * 60,
                close_price=str(100 - i * 2),  # oversold slope
            )
            intents = platform.strategies.on_candle(c, platform.clock())
            assert len(intents) == 0

        r14 = platform.strategies.readiness_for("rsi_1")
        assert r14["samples"] == 14
        assert r14["warmup"] == 15
        assert r14["ready"] is False

        # Feed 15th close: samples reaches 15, ready True!
        c15 = make_closed_candle(
            interval=60,
            start=14 * 60,
            close_price="65",
        )
        intents15 = platform.strategies.on_candle(c15, platform.clock())
        assert len(intents15) == 1
        assert intents15[0].strategy_instance_id == "rsi_1"
        assert "RSI oversold reversal" in intents15[0].reason

        r15 = platform.strategies.readiness_for("rsi_1")
        assert r15["samples"] == 15
        assert r15["warmup"] == 15
        assert r15["ready"] is True

        # Verify platform.snapshot includes readiness
        snap = platform.snapshot()
        sub_snap = next(s for s in snap["subscriptions"] if s["id"] == "rsi_1")
        assert sub_snap["readiness"]["samples"] == 15
        assert sub_snap["readiness"]["warmup"] == 15
        assert sub_snap["readiness"]["ready"] is True
    finally:
        platform.close()


# 8. Independent Strategy Instances and Process Restart Warmup


def test_independent_strategy_instances_and_restart():
    path = "scratch_test_lifecycle.db"
    import os

    if os.path.exists(path):
        os.remove(path)

    # Instance 1
    p1 = Platform(path)
    try:
        p1.account("acc1")
        p1.strategies.subscribe("acc1", "strat_a", "momentum", "TEST")
        p1.strategies.subscribe("acc1", "strat_b", "momentum", "TEST")
        p1.reliability.resume()

        # Feed 3 candles to both
        for i in range(3):
            c = make_closed_candle(interval=60, start=i * 60, close_price="100")
            p1.strategies.on_candle(c, p1.clock())

        assert p1.strategies.readiness_for("strat_a")["samples"] == 3
        assert p1.strategies.readiness_for("strat_b")["samples"] == 3

        # Disabling strat_a does not affect strat_b
        p1.strategies.set_enabled("acc1", "strat_a", False)
        assert p1.strategies.readiness_for("strat_a")["samples"] == 0
        assert p1.strategies.readiness_for("strat_b")["samples"] == 3
    finally:
        p1.close()

    # Instance 2 (Simulating process restart with persisted store)
    p2 = Platform(path)
    try:
        # Upon restart, local indicators must be empty and require fresh warmup
        assert p2.strategies.readiness_for("strat_b")["samples"] == 0
        assert p2.strategies.readiness_for("strat_b")["ready"] is False
    finally:
        p2.close()
        if os.path.exists(path):
            os.remove(path)


# 9. Task 3 Follow-up: Replay Join Time Deducted from Kill Deadline and Idempotent Gate


def test_kill_deadline_deducts_replay_join_time_and_is_idempotent():
    from fastapi.testclient import TestClient
    from backend.broker.mock_api import create_mock_broker_app
    from backend.broker.http_adapter import HTTPMockBrokerAdapter

    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        platform.account("acc_test")
        assert platform.start_replay_stream(interval=0.5)
        thread = platform._replay_thread
        assert thread is not None
        assert thread.is_alive()

        # Capture remaining deadline passed into reliability.kill
        passed_deadlines = []
        original_rel_kill = platform.reliability.kill

        def hooked_rel_kill(*args, **kwargs):
            passed_deadlines.append(kwargs.get("deadline_seconds"))
            return original_rel_kill(*args, **kwargs)

        platform.reliability.kill = hooked_rel_kill

        # Mock join to simulate consuming 0.3s of deadline
        original_join = thread.join

        def simulated_join(*args, **kwargs):
            time.sleep(0.3)
            return original_join(*args, **kwargs)

        thread.join = simulated_join

        cert = platform.kill(deadline_seconds=9)
        assert cert.status == "SUCCESS"

        # Verify that replay join time was deducted from the total 9s deadline
        assert len(passed_deadlines) == 1
        assert passed_deadlines[0] is not None
        assert passed_deadlines[0] < 8.8, (
            f"Deadline not deducted: {passed_deadlines[0]}"
        )

        # Idempotent kill: calling kill again is safe and returns SUCCESS
        cert2 = platform.kill(deadline_seconds=5)
        assert cert2.status == "SUCCESS"
    finally:
        platform.close()
        adapter.close()

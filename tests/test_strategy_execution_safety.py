from decimal import Decimal as D
import threading
import time

from backend.platform import Platform
from backend.shared.contracts import Candle, Side, Tick


def make_closed_candle(interval=60, start=0, close_price="100"):
    price = D(close_price)
    return Candle(
        "TEST",
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


def test_hung_callback_and_healthy_callback():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 0.15

        # Register hung strategy (sleeps 1s)
        def hung_handler(_sub, _candle):
            time.sleep(1.0)
            return Side.BUY, "hung signal"

        # Register healthy strategy (returns immediately)
        def healthy_handler(_sub, _candle):
            return Side.BUY, "healthy signal"

        platform.strategies.register_strategy("hung_strat", hung_handler)
        platform.strategies.register_strategy("healthy_strat", healthy_handler)

        platform.strategies.subscribe("acc_test", "sub_hung", "hung_strat", "TEST")
        platform.strategies.subscribe(
            "acc_test", "sub_healthy", "healthy_strat", "TEST"
        )
        platform.reliability.resume()

        t0 = time.monotonic()
        candle = make_closed_candle(start=0)
        intents = platform.strategies.on_candle(candle, platform.clock())
        elapsed = time.monotonic() - t0

        # Entire on_candle call was bounded by timeout (~0.15s) instead of waiting 1s
        assert elapsed < 0.6, f"Execution took too long: {elapsed}s"

        # Healthy strategy emitted intent
        assert len(intents) == 1
        assert intents[0].strategy_instance_id == "sub_healthy"
        assert intents[0].reason == "healthy signal"

        # Hung strategy was durably quarantined
        rows = {
            r["id"]: r["enabled"]
            for r in platform.store.rows("SELECT id,enabled FROM subscriptions")
        }
        assert rows["sub_healthy"] == 1
        assert rows["sub_hung"] == 0

        # Hung strategy has durable TimeoutError audit evidence
        assert len(platform.strategies.errors) == 1
        assert platform.strategies.errors[0]["strategy"] == "sub_hung"
        assert platform.strategies.errors[0]["error_type"] == "TimeoutError"

        audit_errors = platform.store.rows(
            "SELECT payload FROM audit WHERE type='STRATEGY_CALLBACK_FAILED'"
        )
        assert len(audit_errors) == 1
        assert "TimeoutError" in audit_errors[0]["payload"]
    finally:
        platform.close()


def test_kill_during_hung_callback():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 1.0

        hang_event = threading.Event()
        callback_started = threading.Event()

        def slow_handler(_sub, _candle):
            callback_started.set()
            hang_event.wait(timeout=2.0)
            return Side.BUY, "slow signal"

        platform.strategies.register_strategy("slow_strat", slow_handler)
        platform.strategies.subscribe("acc_test", "sub_slow", "slow_strat", "TEST")
        platform.reliability.resume()

        # Run tick in a background thread
        tick_finished = threading.Event()
        tick_error = None

        def run_tick():
            nonlocal tick_error
            try:
                # 60s tick closes the candle and dispatches slow_handler
                platform.tick(Tick("TEST", 0, D("100"), 1, "t0"))
                platform.tick(Tick("TEST", 60, D("101"), 1, "t60"))
            except Exception as e:
                tick_error = e
            finally:
                tick_finished.set()

        t_thread = threading.Thread(target=run_tick)
        t_thread.start()

        # Wait until the slow callback actually starts executing
        assert callback_started.wait(timeout=1.5), "Callback did not start"

        # Execute kill while the callback is still hanging!
        # Kill must NOT block on the slow callback because callbacks run outside the store lock.
        kill_t0 = time.monotonic()
        cert = platform.kill()
        kill_elapsed = time.monotonic() - kill_t0

        assert kill_elapsed < 5.0, f"Kill took {kill_elapsed}s, exceeded bounded SLA"
        assert cert.status in {"SUCCESS", "SAFE_LATE"}
        assert cert.virtual_positions_flat is True

        # Now release the hung callback
        hang_event.set()
        t_thread.join(timeout=2.0)

        # When the hung callback finally finished, its late results were discarded:
        # No signal was emitted, and no orders were placed
        assert len(platform.strategies.signals) == 0
        assert len(platform.broker.orders) == 0
    finally:
        hang_event.set()
        platform.close()


def test_stop_and_reenable_while_callback_runs():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 1.0

        release_callback = threading.Event()
        callback_active = threading.Event()

        def delay_handler(_sub, _candle, state=None):
            callback_active.set()
            release_callback.wait(timeout=2.0)
            if state is not None:
                state["stale_marker"] = True
            return Side.BUY, "delayed signal"

        platform.strategies.register_strategy("delay_strat", delay_handler)
        platform.strategies.subscribe("acc_test", "sub_delay", "delay_strat", "TEST")
        platform.reliability.resume()

        result_future = []

        def worker():
            candle = make_closed_candle(start=0)
            res = platform.strategies.on_candle(candle, platform.clock())
            result_future.extend(res)

        t = threading.Thread(target=worker)
        t.start()

        assert callback_active.wait(timeout=1.0)

        # While callback is running in worker, operator stops and re-enables the subscription
        platform.strategies.set_enabled("acc_test", "sub_delay", False)
        platform.strategies.set_enabled("acc_test", "sub_delay", True)

        # Release the callback to finish
        release_callback.set()
        t.join(timeout=2.0)

        # The candidate result from the stale run MUST be discarded!
        assert len(result_future) == 0
        assert len(platform.strategies.signals) == 0
        # Stale state marker must NOT have been committed
        committed_state = platform.strategies.indicators.get("sub_delay", {})
        assert "stale_marker" not in committed_state
    finally:
        release_callback.set()
        platform.close()


def test_late_completion_causes_no_state_signal_order_mutation():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 0.08  # 80ms timeout

        def late_handler(_sub, _candle, state=None):
            time.sleep(0.3)  # Sleep longer than timeout
            if state is not None:
                state["leaked_value"] = 999
            return Side.BUY, "late signal"

        platform.strategies.register_strategy("late_strat", late_handler)
        platform.strategies.subscribe("acc_test", "sub_late", "late_strat", "TEST")
        platform.reliability.resume()

        candle = make_closed_candle(start=0)
        intents = platform.strategies.on_candle(candle, platform.clock())

        # on_candle returns [] and quarantines the subscription
        assert len(intents) == 0
        assert not platform.strategies.is_subscription_enabled("sub_late")

        # Wait for the background thread to finish its sleep
        time.sleep(0.35)

        # Verify no mutations occurred after thread completion
        assert len(platform.strategies.signals) == 0
        assert "sub_late" not in platform.strategies.indicators
        assert len(platform.broker.orders) == 0
    finally:
        platform.close()


def test_repeated_hangs_cannot_create_unlimited_workers():
    platform = Platform()
    try:
        platform.account("acc_test")
        platform.strategies.callback_timeout = 0.05
        platform.strategies.max_workers = 2
        platform.strategies.max_outstanding = 2
        platform.strategies._executor._max_workers = 2

        initial_threads = threading.active_count()

        hang_events = [threading.Event() for _ in range(5)]

        def hanging_factory(i):
            def handler(_sub, _candle):
                hang_events[i].wait(timeout=1.0)
                return Side.BUY, f"hang_{i}"

            return handler

        for i in range(5):
            platform.strategies.register_strategy(f"hang_{i}", hanging_factory(i))
            platform.strategies.subscribe("acc_test", f"sub_h_{i}", f"hang_{i}", "TEST")

        platform.reliability.resume()

        # Ingest candle - attempts to execute 5 hanging callbacks with pool limit of 2
        candle = make_closed_candle(start=0)
        intents = platform.strategies.on_candle(candle, platform.clock())

        assert len(intents) == 0

        # Number of active threads in the process did not blow up
        current_threads = threading.active_count()
        # Max additional threads created by executor is at most max_workers (2)
        assert current_threads <= initial_threads + 4

        # All hanging subscriptions were quarantined
        for i in range(5):
            assert not platform.strategies.is_subscription_enabled(f"sub_h_{i}")

        # Clean up hanging threads
        for ev in hang_events:
            ev.set()
    finally:
        for ev in hang_events:
            ev.set()
        platform.close()

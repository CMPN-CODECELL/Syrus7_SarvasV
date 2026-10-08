import threading
import time

from fastapi.testclient import TestClient

from backend.broker.adapters import MockBrokerAdapter
from backend.broker.http_adapter import HTTPMockBrokerAdapter
from backend.broker.mock_api import create_mock_broker_app
from backend.platform import Platform
from backend.shared.contracts import GlobalTradingState, OrderIntent, Side


class SteppingClock:
    def __init__(self, start=1_000.0, step=0.1):
        self.current = start
        self.step = step
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            val = self.current
            self.current += self.step
            return val


def create_test_platform(clock=None, demo_enabled=True):
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    plat = Platform(
        path=":memory:",
        broker=adapter,
        clock=clock or time.time,
        demo_enabled=demo_enabled,
    )
    return plat, adapter


def test_simulation_cursor_strictly_monotonic_across_batches():
    clock = SteppingClock(start=500.0, step=1.0)
    platform, adapter = create_test_platform(clock=clock)
    try:
        # Generate 3 sequential batches of 1 minute each
        batch1 = platform.generate_simulation_batch(["DEMO"], minutes=1)
        batch2 = platform.generate_simulation_batch(["DEMO"], minutes=1)
        batch3 = platform.generate_simulation_batch(["DEMO"], minutes=1)

        assert len(batch1) == 3
        assert len(batch2) == 3
        assert len(batch3) == 3

        all_ticks = batch1 + batch2 + batch3
        timestamps = [t.event_timestamp for t in all_ticks]

        # Strictly increasing timestamps across batches
        for i in range(len(timestamps) - 1):
            assert timestamps[i] < timestamps[i + 1]

        # Verify unique event IDs for newly generated ticks
        event_ids = [t.event_id for t in all_ticks]
        assert len(set(event_ids)) == len(event_ids)

        # Ingest all ticks into platform
        for t in all_ticks:
            platform.tick(t, replay=True)

        stats = platform.candles.stats()
        assert stats["accepted_ticks"] == 9
        assert stats["late_ticks"] == 0
        assert stats["duplicate_ticks"] == 0
    finally:
        platform.close()
        adapter.close()


def test_simulation_separate_event_timestamps_from_receive_time():
    clock = SteppingClock(start=100.0, step=0.5)
    platform, adapter = create_test_platform(clock=clock)
    try:
        batch = platform.generate_simulation_batch(["DEMO"], minutes=1)
        for t in batch:
            platform.tick(t, replay=True)

        # Query risk_marks in DB to verify event_timestamp vs received_at
        rows = platform.store.rows("SELECT * FROM risk_marks WHERE symbol='DEMO'")
        assert len(rows) == 1
        mark = rows[0]
        # event_timestamp is simulated time (~1.7 billion)
        assert mark["event_timestamp"] >= 1_700_000_000
        # received_at is clock time (~100.0)
        assert 100.0 <= mark["received_at"] <= 110.0
        assert mark["source"] == "REPLAY"
    finally:
        platform.close()
        adapter.close()


def test_candle_bucket_crossings_and_closure():
    clock = SteppingClock(start=1000.0, step=1.0)
    platform, adapter = create_test_platform(clock=clock)
    try:
        # Generate 6 minutes of ticks (which crosses both 60s and 300s boundaries)
        batch = platform.generate_simulation_batch(["DEMO"], minutes=6, align=300)
        for t in batch:
            platform.tick(t, replay=True)

        stats = platform.candles.stats()
        assert stats["late_ticks"] == 0
        assert stats["accepted_ticks"] == 18  # 6 minutes * 3 offsets

        # Verify closed candles
        closed_1m = [c for c in platform.closed_candles if c.interval == 60]
        closed_5m = [c for c in platform.closed_candles if c.interval == 300]

        # 6 minutes means at least five 1m candles and one 5m candle closed
        assert len(closed_1m) >= 5
        assert len(closed_5m) >= 1

        # Check the 5m candle
        five_min = closed_5m[0]
        assert five_min.interval == 300
        assert five_min.is_closed is True
        assert five_min.volume > 0
    finally:
        platform.close()
        adapter.close()


def test_stream_repeated_starts_advance_monotonically():
    platform, adapter = create_test_platform()
    try:
        # Start stream briefly
        assert platform.start_replay_stream(interval=0.01)
        for _ in range(30):
            if platform.candles.stats()["accepted_ticks"] > 0:
                break
            time.sleep(0.01)
        platform.stop_replay_stream()

        first_count = platform.candles.stats()["accepted_ticks"]
        assert first_count > 0
        cursor_after_first = platform.get_simulation_cursor("DEMO")

        # Restart stream
        assert platform.start_replay_stream(interval=0.01)
        for _ in range(30):
            if platform.candles.stats()["accepted_ticks"] > first_count:
                break
            time.sleep(0.01)
        platform.stop_replay_stream()

        second_count = platform.candles.stats()["accepted_ticks"]
        assert second_count > first_count
        cursor_after_second = platform.get_simulation_cursor("DEMO")

        # Cursor strictly advanced
        assert cursor_after_second > cursor_after_first
        assert platform.candles.stats()["late_ticks"] == 0
    finally:
        platform.close()
        adapter.close()


def test_intentional_repeats_retain_ids_and_deduplicate():
    clock = SteppingClock(start=500.0, step=1.0)
    platform, adapter = create_test_platform(clock=clock)
    try:
        batch = platform.generate_simulation_batch(["DEMO"], minutes=1)
        # Ingest first time
        for t in batch:
            platform.tick(t, replay=True)

        stats_before = platform.candles.stats()
        assert stats_before["accepted_ticks"] == 3
        assert stats_before["duplicate_ticks"] == 0

        # Intentional duplicate replay of identical ticks
        for t in batch:
            platform.tick(t, replay=True)

        stats_after = platform.candles.stats()
        assert stats_after["accepted_ticks"] == 3
        assert stats_after["duplicate_ticks"] == 3
        assert stats_after["late_ticks"] == 0
    finally:
        platform.close()
        adapter.close()


def test_no_duplicate_stream_threads():
    platform, adapter = create_test_platform()
    try:
        assert platform.start_replay_stream(interval=0.05)
        initial_thread = platform._replay_thread
        assert initial_thread is not None
        assert initial_thread.is_alive()

        # Repeated call does not spawn a second thread
        assert platform.start_replay_stream(interval=0.05)
        assert platform._replay_thread is initial_thread

        # Count active replay threads
        replay_threads = [
            t
            for t in threading.enumerate()
            if t.name == "algoshield-replay-stream" and t.is_alive()
        ]
        assert len(replay_threads) == 1
    finally:
        platform.close()
        adapter.close()


def test_multiple_symbols_and_dynamic_new_symbol():
    clock = SteppingClock(start=500.0, step=1.0)
    platform, adapter = create_test_platform(clock=clock)
    try:
        platform.account("test-acc")
        platform.strategies.subscribe("test-acc", "strat-demo", "momentum", "DEMO")

        # Batch with single symbol
        batch1 = platform.generate_simulation_batch(["DEMO"], minutes=1)
        for t in batch1:
            platform.tick(t, replay=True)

        # Now dynamically subscribe a new symbol
        platform.strategies.subscribe("test-acc", "strat-infy", "momentum", "INFY")

        # Next batch with both symbols
        batch2 = platform.generate_simulation_batch(["DEMO", "INFY"], minutes=1)
        for t in batch2:
            platform.tick(t, replay=True)

        stats = platform.candles.stats()
        assert stats["late_ticks"] == 0
        assert stats["accepted_ticks"] == 3 + 6  # 3 from batch1 + 6 from batch2 (2*3)

        # Verify DEMO and INFY ticks in batch2 are synchronized in timestamps
        demo_ts = [t.event_timestamp for t in batch2 if t.symbol == "DEMO"]
        infy_ts = [t.event_timestamp for t in batch2 if t.symbol == "INFY"]
        assert demo_ts == infy_ts
    finally:
        platform.close()
        adapter.close()


def test_stop_and_kill_terminate_replay_stream_promptly():
    platform, adapter = create_test_platform()
    try:
        assert platform.start_replay_stream(interval=0.02)
        thread = platform._replay_thread
        assert thread.is_alive()

        # Stop joins cleanly
        platform.stop_replay_stream(timeout=1.0)
        assert not thread.is_alive()

        # Restart and test kill
        assert platform.start_replay_stream(interval=0.02)
        thread2 = platform._replay_thread
        assert thread2.is_alive()

        platform.kill()
        assert not thread2.is_alive()
        assert platform.risk.state == GlobalTradingState.KILLED

        # start_replay_stream fails when killed
        assert not platform.start_replay_stream()
    finally:
        platform.close()
        adapter.close()


def test_no_automatic_restart_after_recovery():
    platform, adapter = create_test_platform()
    try:
        assert platform.risk.state == GlobalTradingState.RECOVERING

        # Reconcile does NOT auto-start the stream
        assert platform.reliability.reconcile()
        assert platform.risk.state == GlobalTradingState.STOPPED
        assert platform._replay_thread is None

        # Broker disconnect / reconnect does NOT auto-start the stream
        platform.disconnect_broker()
        platform.reconnect_broker()
        assert platform._replay_thread is None
    finally:
        platform.close()
        adapter.close()


def test_replay_stream_is_mock_only():
    # MockBrokerAdapter is not HTTP mock adapter -> returns False
    p_mock = Platform(path=":memory:", broker=MockBrokerAdapter(), demo_enabled=True)
    try:
        assert not p_mock.start_replay_stream()
    finally:
        p_mock.close()

    # demo_enabled = False -> returns False
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    p_disabled = Platform(path=":memory:", broker=adapter, demo_enabled=False)
    try:
        assert not p_disabled.start_replay_stream()
    finally:
        p_disabled.close()
        adapter.close()


def test_broker_freshness_fail_closed_checks_preserved():
    now_base = time.time()
    clock = SteppingClock(start=now_base, step=0.0)
    platform, adapter = create_test_platform(clock=clock)
    try:
        platform.account("acc-fresh")
        assert platform.reliability.reconcile()

        # Fresh tick
        batch = platform.generate_simulation_batch(["DEMO"], minutes=1)
        for t in batch:
            platform.tick(t, replay=True)

        intent = OrderIntent(
            intent_id="fresh-1",
            strategy_instance_id="strat-1",
            account_id="acc-fresh",
            symbol="DEMO",
            side=Side.BUY,
            quantity=1,
            created_at=now_base,
        )

        # Freshness ok initially
        assert platform.reliability.check_evidence(intent) == ""

        # Advance clock beyond max_broker_age (5s)
        clock.current = now_base + 10.0
        # Broker freshness check fails closed
        reason = platform.reliability.check_evidence(intent)
        assert reason == "RISK_STALE_BROKER_STATE"
        assert platform.risk.state == GlobalTradingState.UNCERTAIN
    finally:
        platform.close()
        adapter.close()

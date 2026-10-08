from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.broker.http_adapter import HTTPMockBrokerAdapter
from backend.broker.mock_api import create_mock_broker_app
from backend.market_data.candles import CandleBuilder
from backend.platform import Platform
from backend.shared.contracts import GlobalTradingState, Tick


def make_tick(
    symbol="TEST",
    ts=0,
    price="100.0",
    qty=10,
    eid=None,
):
    return Tick(
        symbol=symbol,
        event_timestamp=ts,
        price=Decimal(str(price)),
        quantity=qty,
        event_id=eid or f"eid:{symbol}:{ts}:{price}",
    )


def test_half_open_buckets_boundary_ticks_belong_to_next_candle():
    """Boundary ticks t == start + interval belong strictly to the next candle."""
    builder = CandleBuilder(intervals=(60, 300))

    # Interval [0, 60) for 60s, [0, 300) for 300s
    t0 = make_tick(ts=0, price=100, qty=5, eid="t0")
    accepted, closed = builder.ingest_event(t0)
    assert accepted is True
    assert closed == []

    # Inside interval [0, 60)
    t59 = make_tick(ts=59, price=110, qty=10, eid="t59")
    accepted, closed = builder.ingest_event(t59)
    assert accepted is True
    assert closed == []

    # Exact boundary tick at t=60: closes [0, 60), belongs to [60, 120)
    t60 = make_tick(ts=60, price=105, qty=3, eid="t60")
    accepted, closed = builder.ingest_event(t60)
    assert accepted is True
    assert len(closed) == 1

    c60 = closed[0]
    assert c60.interval == 60
    assert c60.start_time == 0
    assert c60.end_time == 60
    assert c60.open == Decimal("100")
    assert c60.high == Decimal("110")
    assert c60.low == Decimal("100")
    assert c60.close == Decimal("110")
    assert c60.volume == 15
    assert c60.is_closed is True

    # Active 60s candle is now [60, 120) containing t60
    active_60 = builder.active[("TEST", 60)]
    assert active_60.start_time == 60
    assert active_60.end_time == 120
    assert active_60.open == Decimal("105")
    assert active_60.close == Decimal("105")
    assert active_60.volume == 3
    assert active_60.is_closed is False

    # Active 300s candle is still [0, 300) containing t0, t59, t60
    active_300 = builder.active[("TEST", 300)]
    assert active_300.start_time == 0
    assert active_300.end_time == 300
    assert active_300.open == Decimal("100")
    assert active_300.high == Decimal("110")
    assert active_300.close == Decimal("105")
    assert active_300.volume == 18

    # Inside interval [0, 300)
    t299 = make_tick(ts=299, price=120, qty=2, eid="t299")
    builder.ingest_event(t299)

    # Exact boundary tick at t=300: closes both 60s [240, 300) and 300s [0, 300)
    t300 = make_tick(ts=300, price=95, qty=7, eid="t300")
    accepted, closed = builder.ingest_event(t300)
    assert accepted is True
    assert len(closed) == 2  # 60s candle and 300s candle closed

    closed_300 = [c for c in closed if c.interval == 300][0]
    assert closed_300.start_time == 0
    assert closed_300.end_time == 300
    assert closed_300.open == Decimal("100")
    assert closed_300.high == Decimal("120")
    assert closed_300.low == Decimal("100")
    assert closed_300.close == Decimal("120")
    assert closed_300.volume == 20  # 5 + 10 + 3 + 2 = 20
    assert closed_300.is_closed is True

    # Active 300s candle is now [300, 600) containing t300
    active_300_new = builder.active[("TEST", 300)]
    assert active_300_new.start_time == 300
    assert active_300_new.end_time == 600
    assert active_300_new.open == Decimal("95")
    assert active_300_new.volume == 7


def test_correct_ohlcv_per_tick_quantity_and_independent_symbols():
    builder = CandleBuilder(intervals=(60,))

    # Ingest for SYM_A
    builder.ingest_event(make_tick(symbol="SYM_A", ts=0, price=100, qty=10, eid="a1"))
    builder.ingest_event(make_tick(symbol="SYM_A", ts=10, price=105, qty=5, eid="a2"))
    builder.ingest_event(make_tick(symbol="SYM_A", ts=20, price=95, qty=15, eid="a3"))
    builder.ingest_event(make_tick(symbol="SYM_A", ts=30, price=102, qty=20, eid="a4"))

    # Ingest for SYM_B interleaved
    builder.ingest_event(make_tick(symbol="SYM_B", ts=5, price=200, qty=1, eid="b1"))
    builder.ingest_event(make_tick(symbol="SYM_B", ts=15, price=210, qty=2, eid="b2"))
    builder.ingest_event(make_tick(symbol="SYM_B", ts=25, price=190, qty=3, eid="b3"))
    builder.ingest_event(make_tick(symbol="SYM_B", ts=35, price=205, qty=4, eid="b4"))

    # Cross 60s boundary for SYM_A
    _, closed_a = builder.ingest_event(
        make_tick(symbol="SYM_A", ts=60, price=103, qty=1, eid="a5")
    )
    assert len(closed_a) == 1
    ca = closed_a[0]
    assert ca.symbol == "SYM_A"
    assert ca.open == Decimal("100")
    assert ca.high == Decimal("105")
    assert ca.low == Decimal("95")
    assert ca.close == Decimal("102")
    assert ca.volume == 50  # 10 + 5 + 15 + 20

    # Cross 60s boundary for SYM_B
    _, closed_b = builder.ingest_event(
        make_tick(symbol="SYM_B", ts=60, price=206, qty=1, eid="b5")
    )
    assert len(closed_b) == 1
    cb = closed_b[0]
    assert cb.symbol == "SYM_B"
    assert cb.open == Decimal("200")
    assert cb.high == Decimal("210")
    assert cb.low == Decimal("190")
    assert cb.close == Decimal("205")
    assert cb.volume == 10  # 1 + 2 + 3 + 4


def test_identical_duplicates_change_neither_candles_nor_marks():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        t1 = make_tick(symbol="DEMO", ts=1000, price=100, qty=5, eid="dup-test-1")
        platform.tick(t1, replay=True)

        stats_before = platform.candles.stats()
        mark_before = platform.ledger.marks.get("DEMO")
        active_before = platform.candles.active[("DEMO", 60)]

        assert stats_before["accepted_ticks"] == 1
        assert stats_before["duplicate_ticks"] == 0
        assert mark_before == Decimal("100")
        assert active_before.volume == 5

        # Re-ingest exact identical tick
        platform.tick(t1, replay=True)

        stats_after = platform.candles.stats()
        mark_after = platform.ledger.marks.get("DEMO")
        active_after = platform.candles.active[("DEMO", 60)]

        # Neither candles nor marks changed
        assert stats_after["accepted_ticks"] == 1
        assert stats_after["duplicate_ticks"] == 1
        assert stats_after["late_ticks"] == 0
        assert mark_after == mark_before
        assert active_after == active_before
        assert active_after.volume == 5  # not 10
    finally:
        platform.close()
        adapter.close()


def test_conflicting_duplicates_and_late_ticks_retain_fail_closed():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        t1 = make_tick(symbol="DEMO", ts=1000, price=100, qty=5, eid="conflict-1")
        platform.tick(t1, replay=True)

        # 1. Conflicting duplicate: same (symbol, event_id) but different price
        t1_conflict = make_tick(
            symbol="DEMO", ts=1000, price=105, qty=5, eid="conflict-1"
        )
        platform.tick(t1_conflict, replay=True)

        # Fails closed, does not overwrite mark
        assert platform.risk.state == GlobalTradingState.UNCERTAIN
        assert platform.ledger.marks["DEMO"] == Decimal("100")  # untouched
        audits = platform.store.rows(
            "SELECT * FROM audit WHERE type='MARKET_DATA_REJECTED'"
        )
        assert len(audits) >= 1
        assert "CONFLICTING_DUPLICATE" in audits[-1]["payload"]

        # Reset gate for late tick test
        platform.risk.state = GlobalTradingState.RUNNING

        # 2. Late unique tick: timestamp earlier than last seen
        t_late = make_tick(symbol="DEMO", ts=900, price=100, qty=5, eid="late-1")
        with pytest.raises(ValueError, match="late tick"):
            platform.tick(t_late, replay=True)

        assert platform.risk.state == GlobalTradingState.UNCERTAIN
        assert platform.candles.stats()["late_ticks"] == 1
        audits = platform.store.rows(
            "SELECT * FROM audit WHERE type='MARKET_DATA_REJECTED'"
        )
        assert "LATE_TICK" in audits[-1]["payload"]
    finally:
        platform.close()
        adapter.close()


def test_bounded_dedupe_never_silently_double_counts_evicted_event():
    builder = CandleBuilder(max_seen=3, intervals=(60,))

    # Fill dedupe capacity with 3 ticks
    t1 = make_tick(ts=10, eid="e1")
    t2 = make_tick(ts=20, eid="e2")
    t3 = make_tick(ts=30, eid="e3")
    builder.ingest_event(t1)
    builder.ingest_event(t2)
    builder.ingest_event(t3)
    assert len(builder.seen) == 3

    # Ingest 4th tick: watermark advances past t1, so t1 is evicted
    t4 = make_tick(ts=40, eid="e4")
    builder.ingest_event(t4)
    assert len(builder.seen) == 3
    assert ("TEST", "e1") not in builder.seen

    # Now attempt to re-ingest evicted t1:
    # Because t1.event_timestamp (10) < builder.last (40), it is rejected as a late tick!
    with pytest.raises(ValueError, match="late tick"):
        builder.ingest_event(t1)

    assert builder.late_ticks == 1
    # Active candle volume did NOT double count t1
    active = builder.active[("TEST", 60)]
    assert active.volume == 40  # 4 ticks of 10 volume each

    # Also test capacity limit at the current timestamp:
    # When all seen ticks are at current timestamp, cannot evict without causal violation
    builder_small = CandleBuilder(max_seen=2, intervals=(60,))
    builder_small.ingest_event(make_tick(ts=100, eid="same-1"))
    builder_small.ingest_event(make_tick(ts=100, eid="same-2"))
    # 3rd tick at ts=100 reaches capacity
    with pytest.raises(ValueError, match="tick dedupe capacity reached"):
        builder_small.ingest_event(make_tick(ts=100, eid="same-3"))


def test_missing_intervals_create_no_invented_gap_candles():
    builder = CandleBuilder(intervals=(60,))

    # Minute 0: [0, 60)
    builder.ingest_event(make_tick(ts=10, price=100, qty=5, eid="m0"))

    # Large gap: no ticks for minutes 1, 2, 3, 4. Next tick arrives at minute 5: ts=300
    accepted, closed = builder.ingest_event(
        make_tick(ts=300, price=105, qty=8, eid="m5")
    )
    assert accepted is True
    # Exactly one candle closed: [0, 60)
    assert len(closed) == 1
    assert closed[0].start_time == 0
    assert closed[0].end_time == 60
    assert closed[0].is_closed is True

    # Active candle is [300, 360)
    active = builder.active[("TEST", 60)]
    assert active.start_time == 300
    assert active.end_time == 360

    # No candles were invented for 60, 120, 180, 240!


def test_final_incomplete_candles_emit_no_strategy_signals():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        platform.account("acc-sig")
        platform.strategies.subscribe("acc-sig", "strat-mom", "momentum", "DEMO")
        platform.reliability.resume()

        # Ingest ticks inside [1_700_000_100, 1_700_000_160) without crossing 60s boundary
        t1 = make_tick(symbol="DEMO", ts=1_700_000_100, price=100, qty=5, eid="s1")
        t2 = make_tick(symbol="DEMO", ts=1_700_000_120, price=101, qty=5, eid="s2")
        t3 = make_tick(symbol="DEMO", ts=1_700_000_140, price=102, qty=5, eid="s3")

        platform.tick(t1, replay=True)
        platform.tick(t2, replay=True)
        platform.tick(t3, replay=True)

        # No candles closed
        assert len(platform.closed_candles) == 0
        # No signals emitted
        assert len(platform.strategies.signals) == 0

        # Orders table is empty
        orders = platform.store.rows("SELECT * FROM orders")
        assert len(orders) == 0
    finally:
        platform.close()
        adapter.close()


def test_simulation_batches_across_boundaries_both_intervals():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        # Generate 11 minutes of simulation ticks across 60s and 300s boundaries
        batch = platform.generate_simulation_batch(["DEMO"], minutes=11, align=300)
        for t in batch:
            platform.tick(t, replay=True)

        stats = platform.candles.stats()
        assert stats["late_ticks"] == 0
        assert stats["duplicate_ticks"] == 0
        assert stats["accepted_ticks"] == 33  # 11 minutes * 3 offsets

        closed_1m = [c for c in platform.closed_candles if c.interval == 60]
        closed_5m = [c for c in platform.closed_candles if c.interval == 300]

        # 11 minutes (0..10) has 10 completed 1-minute candles
        assert len(closed_1m) == 10
        # and 2 completed 5-minute candles (minute 5 and minute 10)
        assert len(closed_5m) == 2

        # Check exact half-open boundaries on 5m candles
        c5_first, c5_second = closed_5m[0], closed_5m[1]
        assert c5_first.end_time == c5_first.start_time + 300
        assert c5_second.start_time == c5_first.end_time
        assert c5_second.end_time == c5_second.start_time + 300
    finally:
        platform.close()
        adapter.close()


def test_kill_closes_admission_before_replay_thread_join():
    """Integration check: kill closes execution admission gate before any replay thread join/wait."""
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        assert platform.start_replay_stream(interval=0.5)
        thread = platform._replay_thread
        assert thread is not None
        assert thread.is_alive()

        admission_closed_before_join = False
        original_join = thread.join

        def hooked_join(*args, **kwargs):
            nonlocal admission_closed_before_join
            # Check whether admission gate was closed before join was entered
            if (
                platform.risk.kill_requested.is_set()
                and platform.risk.state == GlobalTradingState.KILLING
                and platform.reliability.kill_latched
                and platform._replay_stop.is_set()
                and not platform.strategies.enabled
            ):
                admission_closed_before_join = True
            return original_join(*args, **kwargs)

        thread.join = hooked_join

        platform.kill()

        assert admission_closed_before_join is True
        assert platform.risk.state == GlobalTradingState.KILLED
        assert not thread.is_alive()
    finally:
        platform.close()
        adapter.close()

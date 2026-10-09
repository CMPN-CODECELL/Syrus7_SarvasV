import math
import multiprocessing
import queue
import time
from decimal import Decimal

import pytest

from backend.market_data.candles import ReplayMarketDataProvider
from backend.market_data.yahoo import (
    SOURCE,
    _queue_event,
    YahooMarketDataProvider,
    normalize_yahoo_message,
)
from backend.platform import Platform


CAPTURED_TCS = {
    "id": "TCS.NS",
    "price": 2190.8,
    "time": "1791521395000",
    "day_volume": "5338028",
    "last_size": "10",
}
CAPTURED_INFY = {
    "id": "INFY.NS",
    "price": "1025.25",
    "time": "1791521394000",
    "day_volume": "5674765",
    "last_size": "11",
}


def hanging_worker(_symbols, _output, stop_requested):
    while not stop_requested.wait(0.01):
        pass


def one_message_worker(_symbols, output, _stop_requested):
    now_ms = str(int(time.time() * 1000))
    for phase, elapsed in (
        ("import_started", 0.01),
        ("import_complete", 0.02),
        ("connection_subscription_started", 0.03),
        ("subscribed", 0.04),
    ):
        output.put(
            {
                "type": "lifecycle",
                "phase": phase,
                "child_elapsed_seconds": elapsed,
            }
        )
    output.put(
        {
            "type": "message",
            "payload": {"id": "TCS.NS", "price": "100.25", "time": now_ms},
        }
    )


def overflow_worker():
    events = queue.Queue(maxsize=1)
    events.put_nowait({"type": "existing"})
    _queue_event(events, {"type": "overflow"})


class FakeReliability:
    def __init__(self):
        self.failures = []

    def fail_closed(self, reason):
        self.failures.append(reason)


class FakePlatform:
    def __init__(self):
        self.reliability = FakeReliability()
        self.ticks = []

    def tick(self, tick, *, replay):
        self.ticks.append((tick, replay))


def test_captured_payload_normalizes_price_timestamp_symbol_and_unavailable_volume():
    tick = normalize_yahoo_message(CAPTURED_TCS, received_at=1791521395)

    assert tick.symbol == "TCS"
    assert tick.price == Decimal("2190.8")
    assert tick.event_timestamp == 1791521395
    assert tick.raw_event_timestamp == "1791521395000"
    assert tick.quantity == 0
    assert tick.volume_available is False
    assert tick.data_source == SOURCE
    assert tick.event_id.startswith("yahoo-quote:")


@pytest.mark.parametrize("price", [None, "NaN", "Infinity", "-1", "0", math.inf])
def test_rejects_missing_nonfinite_or_nonpositive_prices(price):
    with pytest.raises(ValueError, match="price"):
        normalize_yahoo_message(CAPTURED_TCS | {"price": price}, received_at=1791521395)


@pytest.mark.parametrize(
    ("change", "match"),
    [({"id": "AAPL"}, "symbol"), ({"time": "bad"}, "timestamp")],
)
def test_rejects_unknown_symbols_and_invalid_timestamps(change, match):
    with pytest.raises(ValueError, match=match):
        normalize_yahoo_message(CAPTURED_TCS | change, received_at=1791521395)


def test_rejects_implausible_timestamp_but_retains_captured_raw_milliseconds():
    with pytest.raises(ValueError, match="implausible"):
        normalize_yahoo_message(CAPTURED_INFY, received_at=1791522000)
    assert (
        normalize_yahoo_message(
            CAPTURED_INFY, received_at=1791521394
        ).raw_event_timestamp
        == "1791521394000"
    )


def test_duplicate_detection_is_bounded_and_not_claimed_as_trade_identity():
    platform = FakePlatform()
    provider = YahooMarketDataProvider(platform, duplicate_capacity=1)

    assert provider.ingest_payload(CAPTURED_TCS, received_at=1791521395)
    assert not provider.ingest_payload(CAPTURED_TCS, received_at=1791521395)
    assert provider.ingest_payload(CAPTURED_INFY, received_at=1791521394)
    assert len(provider._seen) == 1
    assert provider.telemetry()["duplicate_updates"] == 1
    assert "not an exchange trade ID" in provider.telemetry()["event_id_semantics"]
    assert all(replay is False for _, replay in platform.ticks)


def test_account_snapshot_exposes_configured_symbols_and_latest_quotes_without_subscriptions():
    platform = Platform()
    provider = YahooMarketDataProvider(platform)
    try:
        platform.account("trader")
        platform.configure_external_market_data(provider)
        assert provider.ingest_payload(CAPTURED_TCS, received_at=1791521395)

        market_data = platform.snapshot("trader")["market_data"]
        assert market_data["canonical_symbols"] == ["TCS", "INFY"]
        assert market_data["symbols"] == ["TCS.NS", "INFY.NS"]
        assert market_data["latest_quotes"] == [
            {
                "symbol": "TCS",
                "provider_symbol": "TCS.NS",
                "price": "2190.8",
                "event_timestamp": 1791521395,
                "raw_event_timestamp": "1791521395000",
                "received_at": 1791521395,
                "volume_available": False,
                "data_source": SOURCE,
            },
            {
                "symbol": "INFY",
                "provider_symbol": "INFY.NS",
                "price": None,
                "event_timestamp": None,
                "raw_event_timestamp": None,
                "received_at": None,
                "volume_available": False,
                "data_source": SOURCE,
            },
        ]
        assert platform.snapshot("trader")["subscriptions"] == []
    finally:
        platform.close()


def test_overflow_disconnect_and_staleness_fail_closed_without_resuming():
    platform = FakePlatform()
    provider = YahooMarketDataProvider(platform, clock=lambda: 100, stale_after=5)
    provider.record_queue_overflow()
    provider.record_disconnect("gap")
    provider._connected = True
    provider._last_received_at = 90

    assert provider.check_stale(now=100)
    assert platform.reliability.failures == [
        "YAHOO_FEED_QUEUE_OVERFLOW",
        "YAHOO_FEED_DISCONNECTED",
        "YAHOO_FEED_STALE",
    ]


def test_child_exits_with_distinct_status_on_bounded_queue_overflow():
    process = multiprocessing.Process(target=overflow_worker)
    process.start()
    try:
        process.join(10)
        assert not process.is_alive()
        assert process.exitcode == 73
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)


class HangingProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.join_calls = 0

    def join(self, _timeout):
        self.join_calls += 1

    def is_alive(self):
        return not self.terminated and not self.killed

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_stop_terminates_a_hanging_child_with_bounded_waits():
    provider = YahooMarketDataProvider(FakePlatform(), stop_timeout=0.01)
    process = HangingProcess()
    provider._process = process

    started = time.monotonic()
    assert provider.stop()

    assert time.monotonic() - started < 0.2
    assert process.terminated
    assert process.join_calls == 2
    assert provider.telemetry()["deadline_terminations"] == 1


def test_hanging_startup_is_bounded_and_child_is_reaped():
    platform = FakePlatform()
    provider = YahooMarketDataProvider(
        platform,
        startup_timeout=0.05,
        stop_timeout=0.1,
        reconnect_attempts=0,
        process_target=hanging_worker,
    )
    started = time.monotonic()
    provider.start()
    provider._thread.join(1)

    assert time.monotonic() - started < 1
    assert not provider._thread.is_alive()
    assert not provider._process.is_alive()
    assert "YAHOO_FEED_START_TIMEOUT" in platform.reliability.failures


def test_normal_worker_retains_message_and_completes_boundedly():
    platform = FakePlatform()
    provider = YahooMarketDataProvider(
        platform,
        startup_timeout=3,
        stop_timeout=0.1,
        reconnect_attempts=0,
        process_target=one_message_worker,
    )
    provider.start()
    provider._thread.join(5)

    assert not provider._thread.is_alive()
    assert not provider._process.is_alive()
    assert provider.telemetry()["received_messages"] == 1
    assert provider.telemetry()["accepted_updates"] == 1
    assert platform.ticks[0][0].price == Decimal("100.25")
    phases = [item["phase"] for item in provider.telemetry()["lifecycle"]]
    assert phases == [
        "process_started",
        "import_started",
        "import_complete",
        "connection_subscription_started",
        "subscribed",
    ]


def test_quote_derived_closed_candle_routes_through_platform_tick():
    platform = Platform(clock=lambda: 1791521460)
    closed = []
    platform.strategies.on_candle = lambda candle, now: closed.append(candle) or []
    provider = YahooMarketDataProvider(platform)
    try:
        platform.configure_external_market_data(provider)
        first = CAPTURED_TCS | {"time": "1791521395000"}
        second = CAPTURED_TCS | {"time": "1791521461000", "price": "2191.25"}
        assert provider.ingest_payload(first, received_at=1791521395)
        assert provider.ingest_payload(second, received_at=1791521461)

        minute = next(candle for candle in closed if candle.interval == 60)
        assert minute.symbol == "TCS"
        assert minute.volume == 0
        assert minute.volume_available is False
        assert minute.data_source == SOURCE
        assert platform.snapshot()["market_data"]["accepted_ticks"] == 2
    finally:
        platform.close()


def test_replay_defaults_and_source_remain_unchanged():
    ticks = list(ReplayMarketDataProvider.demo().ticks())
    platform = Platform(clock=lambda: 1_700_001_000)
    try:
        for tick in ticks[:4]:
            platform.tick(tick, replay=True)
        state = platform.snapshot()
        assert state["market_data"]["provider"] == "MOCK_REPLAY"
        assert state["market_data"]["volume_available"] is True
        assert state["mode"] == "MOCK / REPLAY"
    finally:
        platform.close()


def test_external_provider_is_opt_in_and_cannot_mix_with_replay():
    platform = Platform()
    provider = YahooMarketDataProvider(platform)
    try:
        platform.configure_external_market_data(provider)
        with pytest.raises(ValueError, match="cannot share"):
            platform.tick(next(ReplayMarketDataProvider.demo().ticks()), replay=True)
        with pytest.raises(ValueError, match="only configured Yahoo"):
            platform.tick(next(ReplayMarketDataProvider.demo().ticks()), replay=False)
        assert not platform.start_replay_stream()
        assert platform.snapshot()["mode"] == "YAHOO EXTERNAL QUOTES / MOCK EXECUTION"
    finally:
        platform.close()

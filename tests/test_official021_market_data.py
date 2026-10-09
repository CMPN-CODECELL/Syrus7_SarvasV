from decimal import Decimal
from threading import Event

from backend.broker.official021 import (
    Instrument021,
    MarketObservation021,
    ObservationKind,
)
from backend.market_data.official021 import MarketData021Provider


class FakeReliability:
    def __init__(self):
        self.failures = []

    def fail_closed(self, reason):
        self.failures.append(reason)


class FakePlatform:
    def __init__(self):
        self.reliability = FakeReliability()
        self.ticks = []
        self.store = type("StoreStub", (), {"rows": lambda self, *args: []})()

    def tick(self, tick, *, replay):
        self.ticks.append((tick, replay))


class FakeAdapter:
    instruments = {"TCS": Instrument021(1, 11536, "TCS")}


def observation(*, price="100.25", volume=100, timestamp=1791521395):
    return MarketObservation021(
        1,
        11536,
        ObservationKind.FULL,
        Decimal(price),
        cumulative_volume=volume,
        exchange_timestamp=timestamp,
    )


def test_first_cumulative_volume_is_baseline_then_delta_becomes_available(monkeypatch):
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    received = iter((1791521395, 1791521396))
    monkeypatch.setattr(
        "backend.market_data.official021.time.time", lambda: next(received)
    )

    provider._emit(observation(volume=100))
    provider._emit(observation(price="100.30", volume=104, timestamp=1791521396))

    first, second = [item[0] for item in platform.ticks]
    assert first.quantity == 0
    assert first.volume_available is False
    assert second.quantity == 4
    assert second.volume_available is True
    assert all(replay is False for _, replay in platform.ticks)
    telemetry = provider.telemetry()
    assert telemetry["latest_quotes"][0]["price"] == "100.30"
    assert telemetry["latest_quotes"][0]["raw_event_timestamp"] == 1791521396
    assert telemetry["last_event_timestamp"] == 1791521396
    assert telemetry["volume_available"] is False
    assert "not an exchange trade ID" in telemetry["event_id_semantics"]


def test_cumulative_volume_regression_is_rejected_and_fails_closed():
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    provider._emit(observation(volume=100))

    provider._emit(observation(price="100.30", volume=99, timestamp=1791521396))

    assert len(platform.ticks) == 1
    assert provider.telemetry()["errors"] == ["VOLUME_REGRESSION"]
    assert platform.reliability.failures == ["021_VOLUME_REGRESSION"]


def test_connected_telemetry_reflects_socket_state_not_thread_presence():
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    provider._thread = type("ThreadStub", (), {"is_alive": lambda self: True})()

    assert provider.telemetry()["connected"] is False


def test_latest_quotes_are_ordered_by_most_recent_receive_time():
    provider = MarketData021Provider(FakePlatform(), FakeAdapter(), ["TCS"])
    provider._latest_quotes = {
        "A_FIRST_ALPHABETICALLY": {
            "symbol": "A_FIRST_ALPHABETICALLY",
            "received_at": 10.0,
        },
        "Z_MOST_RECENT": {"symbol": "Z_MOST_RECENT", "received_at": 20.0},
    }

    quotes = provider.telemetry()["latest_quotes"]

    assert [quote["symbol"] for quote in quotes] == [
        "Z_MOST_RECENT",
        "A_FIRST_ALPHABETICALLY",
    ]


def test_implausible_exchange_epoch_uses_receive_time_for_candles(monkeypatch):
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    monkeypatch.setattr(
        "backend.market_data.official021.time.time", lambda: 1_791_529_395
    )

    provider._emit(observation(timestamp=2_106_901_823))

    tick = platform.ticks[0][0]
    assert tick.event_timestamp == 1_791_529_395
    assert tick.raw_event_timestamp == "2106901823"
    telemetry = provider.telemetry()
    assert telemetry["timestamp_fallbacks"] == 1
    assert telemetry["timestamp_future_fallbacks"] == 1
    assert telemetry["timestamp_past_fallbacks"] == 0
    assert provider.telemetry()["errors"] == []


def test_identical_provider_snapshot_is_dropped_before_canonical_tick(monkeypatch):
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    monkeypatch.setattr("backend.market_data.official021.time.time", lambda: 100)

    provider._emit(observation(timestamp=100, volume=10))
    provider._emit(observation(timestamp=100, volume=10))

    assert len(platform.ticks) == 1
    assert provider.telemetry()["provider_duplicates_dropped"] == 1
    assert platform.reliability.failures == []


def test_changed_snapshot_and_timestamp_regression_remain_safe(monkeypatch):
    platform = FakePlatform()
    provider = MarketData021Provider(
        platform, FakeAdapter(), ["TCS"], max_timestamp_skew_seconds=10
    )
    received = iter((100, 101, 102))
    monkeypatch.setattr(
        "backend.market_data.official021.time.time", lambda: next(received)
    )

    provider._emit(observation(timestamp=100, volume=10))
    provider._emit(observation(price="101.00", timestamp=100, volume=11))
    provider._emit(observation(price="101.10", timestamp=99, volume=12))

    ticks = [item[0] for item in platform.ticks]
    assert len(ticks) == 3
    assert ticks[1].event_timestamp == 100
    assert ticks[2].event_timestamp >= 102
    assert provider.telemetry()["timestamp_fallbacks"] == 1
    assert provider.telemetry()["timestamp_reorder_fallbacks"] == 1


def test_market_socket_disconnect_fails_closed_then_reconnects_with_fresh_key():
    connected_twice = Event()

    class Adapter(FakeAdapter):
        base_url = "https://example.test/api/developer-api/v1"

        def __init__(self):
            self.keys = 0

        def _instrument(self, symbol):
            return self.instruments[symbol]

        def ephemeral_key(self):
            self.keys += 1
            return f"key-{self.keys}"

    class Socket:
        def __init__(self, closes):
            self.closes = closes

        def send(self, _message):
            pass

        def recv(self, timeout=1):
            if self.closes:
                return None
            connected_twice.set()
            connected_twice.wait(0.01)
            raise TimeoutError

        def close(self):
            pass

    sockets = iter((Socket(True), Socket(False)))
    adapter = Adapter()
    provider = MarketData021Provider(
        FakePlatform(), adapter, ["TCS"], socket_factory=lambda _url: next(sockets)
    )

    assert provider.start() is True
    assert connected_twice.wait(2)
    assert provider.stop() is True
    telemetry = provider.telemetry()
    assert adapter.keys == 2
    assert telemetry["reconnect_attempts"] == 1
    assert "021_FEED_DISCONNECTED" in provider.platform.reliability.failures


def test_live_universe_is_only_pinned_plus_enabled_strategy_symbols():
    class StoreStub:
        subscriptions = [{"symbol": "INFY"}]

        def rows(self, *_args):
            return self.subscriptions

    class Adapter:
        instruments = {
            "TCS": Instrument021(1, 11536, "TCS"),
            "INFY": Instrument021(1, 1594, "INFY"),
        }

        def _instrument(self, symbol):
            try:
                return self.instruments[symbol]
            except KeyError as exc:
                from backend.broker.official021 import Provider021Blocked

                raise Provider021Blocked("unsupported") from exc

    platform = FakePlatform()
    platform.store = StoreStub()
    provider = MarketData021Provider(platform, Adapter(), ["TCS"])

    assert provider._resolve_universe() == ("TCS", "INFY")
    platform.store.subscriptions = [{"symbol": "UNKNOWN"}]
    assert provider._resolve_universe() == ("TCS",)
    assert provider.telemetry()["unsupported_symbols"] == ["UNKNOWN"]

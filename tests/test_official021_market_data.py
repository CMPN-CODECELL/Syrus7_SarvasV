from decimal import Decimal

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


def test_first_cumulative_volume_is_baseline_then_delta_becomes_available():
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])

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


def test_implausible_exchange_epoch_uses_receive_time_for_candles(monkeypatch):
    platform = FakePlatform()
    provider = MarketData021Provider(platform, FakeAdapter(), ["TCS"])
    monkeypatch.setattr("backend.market_data.official021.time.time", lambda: 1_791_529_395)

    provider._emit(observation(timestamp=2_106_901_823))

    tick = platform.ticks[0][0]
    assert tick.event_timestamp == 1_791_529_395
    assert tick.raw_event_timestamp == "2106901823"
    assert "EXCHANGE_TIMESTAMP_FALLBACK_RECEIVE_TIME" in provider.telemetry()["errors"]

from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import replace
from decimal import Decimal
from typing import Protocol

from backend.market_data.official021 import MarketData021Provider  # noqa: F401
from backend.shared.contracts import Candle, Tick


class MarketDataProvider(Protocol):
    def ticks(self) -> Iterable[Tick]: ...


class ReplayMarketDataProvider:
    def __init__(self, ticks):
        self.events = tuple(ticks)

    def ticks(self):
        return iter(self.events)

    @classmethod
    def demo(cls, start=1_700_000_100, symbol="DEMO"):
        start -= start % 300
        return cls(
            Tick(
                symbol,
                start + minute * 60 + offset,
                Decimal(100 + minute + offset // 20),
                5,
                f"{start}:{minute}:{offset}",
            )
            for minute in range(11)
            for offset in (0, 20, 40)
        )


class CandleBuilder:
    """UTC half-open buckets; close only upon next bucket, no invented gap candles."""

    def __init__(self, max_seen_ids=100_000, *, max_seen=None, intervals=(60, 300)):
        if max_seen is not None:
            max_seen_ids = max_seen
        if type(max_seen_ids) is not int or max_seen_ids < 1:
            raise ValueError("tick dedupe capacity must be a positive integer")
        if not intervals:
            raise ValueError("at least one candle interval is required")
        for inv in intervals:
            if type(inv) is not int or inv <= 0:
                raise ValueError("candle intervals must be positive integers")
        self.intervals = tuple(sorted(set(intervals)))
        self.max_seen = max_seen_ids
        self.active = {}
        self.seen = OrderedDict()
        self.last = {}
        self.accepted_ticks = 0
        self.duplicate_ticks = 0
        self.late_ticks = 0

    def add_interval(self, interval: int):
        if type(interval) is not int or interval <= 0:
            raise ValueError("candle interval must be a positive integer")
        if interval not in self.intervals:
            self.intervals = tuple(sorted(set(self.intervals + (interval,))))

    def ingest(self, tick):
        _, closed = self.ingest_event(tick)
        return closed

    def ingest_event(self, tick):
        """Return whether the tick was accepted and any newly closed candles."""
        identity = (tick.symbol, tick.event_id)
        if identity in self.seen:
            self.duplicate_ticks += 1
            if self.seen[identity] != tick:
                raise ValueError("conflicting duplicate tick")
            return False, []
        if (
            not tick.symbol
            or not tick.event_id
            or not isinstance(tick.event_timestamp, int)
            or tick.event_timestamp < 0
            or tick.price <= 0
            or tick.quantity < 0
        ):
            raise ValueError("invalid tick")
        if tick.event_timestamp < self.last.get(tick.symbol, -1):
            self.late_ticks += 1
            raise ValueError("late tick: replay must be ordered before ingestion")
        if any(
            self.active.get((tick.symbol, interval)) is not None
            and self.active[(tick.symbol, interval)].data_source
            not in {"UNSPECIFIED", tick.data_source}
            and tick.data_source != "UNSPECIFIED"
            for interval in self.intervals
        ):
            raise ValueError("mixed market-data sources in candle")
        if len(self.seen) >= self.max_seen:
            oldest_identity, oldest_tick = next(iter(self.seen.items()))
            watermark = (
                tick.event_timestamp
                if oldest_identity[0] == tick.symbol
                else self.last.get(oldest_identity[0], -1)
            )
            if oldest_tick.event_timestamp >= watermark:
                raise ValueError("tick dedupe capacity reached at current timestamp")
            self.seen.popitem(last=False)
        self.seen[identity] = tick
        self.last[tick.symbol] = tick.event_timestamp
        self.accepted_ticks += 1
        closed = []
        for interval in self.intervals:
            key = (tick.symbol, interval)
            start = tick.event_timestamp // interval * interval
            c = self.active.get(key)
            if c and c.start_time != start:
                closed.append(replace(c, is_closed=True))
                c = None
            if c is None:
                c = Candle(
                    tick.symbol,
                    interval,
                    start,
                    start + interval,
                    tick.price,
                    tick.price,
                    tick.price,
                    tick.price,
                    tick.quantity,
                    False,
                    tick.volume_available,
                    tick.data_source,
                )
            else:
                c = replace(
                    c,
                    high=max(c.high, tick.price),
                    low=min(c.low, tick.price),
                    close=tick.price,
                    volume=c.volume + tick.quantity,
                    volume_available=c.volume_available and tick.volume_available,
                    data_source=(
                        tick.data_source
                        if c.data_source == "UNSPECIFIED"
                        else c.data_source
                    ),
                )
            self.active[key] = c
        return True, closed

    def stats(self):
        return {
            "accepted_ticks": self.accepted_ticks,
            "duplicate_ticks": self.duplicate_ticks,
            "late_ticks": self.late_ticks,
            "tracked_event_ids": len(self.seen),
            "last_event_timestamp": dict(self.last),
        }

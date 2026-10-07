from dataclasses import replace
from decimal import Decimal
from collections import deque
from typing import Iterable, Protocol

from backend.shared.contracts import Candle, Tick


class MarketDataProvider(Protocol):
    def ticks(self) -> Iterable[Tick]: ...


class ReplayMarketDataProvider:
    def __init__(self, ticks):
        self.events = tuple(ticks)

    def ticks(self):
        return iter(self.events)

    @classmethod
    def demo(cls, start=1_700_000_100):
        start -= start % 300
        return cls(
            Tick(
                "DEMO",
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

    def __init__(self, max_seen_ids=100_000):
        if max_seen_ids <= 0:
            raise ValueError("max_seen_ids must be positive")
        self.active = {}
        self.seen = set()
        self.seen_order = deque()
        self.max_seen_ids = max_seen_ids
        self.last = {}
        self.accepted_ticks = 0
        self.duplicate_ticks = 0
        self.late_ticks = 0

    def ingest(self, tick):
        identity = (tick.symbol, tick.event_id)
        if identity in self.seen:
            self.duplicate_ticks += 1
            return []
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
        self.seen.add(identity)
        self.seen_order.append(identity)
        if len(self.seen_order) > self.max_seen_ids:
            self.seen.remove(self.seen_order.popleft())
        self.last[tick.symbol] = tick.event_timestamp
        self.accepted_ticks += 1
        closed = []
        for interval in (60, 300):
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
                )
            else:
                c = replace(
                    c,
                    high=max(c.high, tick.price),
                    low=min(c.low, tick.price),
                    close=tick.price,
                    volume=c.volume + tick.quantity,
                )
            self.active[key] = c
        return closed

    def stats(self):
        return {
            "accepted_ticks": self.accepted_ticks,
            "duplicate_ticks": self.duplicate_ticks,
            "late_ticks": self.late_ticks,
            "tracked_event_ids": len(self.seen),
            "last_event_timestamp": dict(self.last),
        }


class MarketData021Provider:
    def __init__(self):
        raise NotImplementedError("021 feed contract unconfirmed")

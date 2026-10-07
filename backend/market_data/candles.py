from dataclasses import replace
from collections import OrderedDict
from decimal import Decimal
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

    def __init__(self, max_seen=10000):
        if type(max_seen) is not int or max_seen < 1:
            raise ValueError("tick dedupe capacity must be a positive integer")
        self.max_seen = max_seen
        self.active = {}
        self.seen = OrderedDict()
        self.last = {}

    def ingest(self, tick):
        if tick.event_id in self.seen:
            if self.seen[tick.event_id] != tick:
                raise ValueError("conflicting duplicate tick")
            return []
        if tick.price <= 0 or tick.quantity < 0:
            raise ValueError("invalid tick")
        if tick.event_timestamp < self.last.get(tick.symbol, -1):
            raise ValueError("late tick: replay must be ordered before ingestion")
        if len(self.seen) >= self.max_seen:
            _, oldest = next(iter(self.seen.items()))
            watermark = (
                tick.event_timestamp
                if oldest.symbol == tick.symbol
                else self.last.get(oldest.symbol, -1)
            )
            if oldest.event_timestamp >= watermark:
                raise ValueError("tick dedupe capacity reached at current timestamp")
            self.seen.popitem(last=False)
        self.seen[tick.event_id] = tick
        self.last[tick.symbol] = tick.event_timestamp
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


class MarketData021Provider:
    def __init__(self):
        raise NotImplementedError("021 feed contract unconfirmed")

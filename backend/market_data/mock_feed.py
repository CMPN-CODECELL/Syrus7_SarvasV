"""Standalone Mock Market Data Streaming Feed API for AlgoShield PS-06 prototype.

IMPORTANT DISCLAIMER:
This API is an AlgoShield prototype market data simulator for testing, demos, and replay
scenarios while official sponsor 021 API documentation and live feeds are unavailable.
It is NOT an imitation of the sponsor's undocumented 021 API.
"""

from collections import deque
from decimal import Decimal
import json
import time
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from backend.market_data.candles import CandleBuilder, ReplayMarketDataProvider
from backend.shared.contracts import Candle, Tick


class RawTickRequest(BaseModel):
    symbol: str
    price: Annotated[Decimal, Field(gt=0)]
    quantity: Annotated[int, Field(ge=0)] = 1
    event_timestamp: int | None = None
    event_id: str | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            if not v:
                raise ValueError("symbol is required")
            return v
        return v

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


def serialize_tick(tick: Tick) -> dict:
    return {
        "symbol": tick.symbol,
        "event_timestamp": tick.event_timestamp,
        "price": str(tick.price),
        "quantity": tick.quantity,
        "event_id": tick.event_id,
    }


def serialize_candle(c: Candle) -> dict:
    return {
        "symbol": c.symbol,
        "interval": c.interval,
        "start_time": c.start_time,
        "end_time": c.end_time,
        "open": str(c.open),
        "high": str(c.high),
        "low": str(c.low),
        "close": str(c.close),
        "volume": c.volume,
        "is_closed": c.is_closed,
    }


class MockMarketDataServer:
    def __init__(self, max_history=10_000):
        self.max_history = max_history
        self.ticks = deque(maxlen=max_history)
        self.candle_builder = CandleBuilder()
        self.closed_candles = deque(maxlen=1000)

    def publish(self, tick: Tick) -> list[Candle]:
        self.ticks.append(tick)
        _, closed = self.candle_builder.ingest_event(tick)
        for c in closed:
            self.closed_candles.append(c)
        return closed

    def load_demo(self, start=None):
        count = 0
        provider = ReplayMarketDataProvider.demo(start or int(time.time()))
        for t in provider.ticks():
            self.publish(t)
            count += 1
        return count


def create_mock_feed_app(server: MockMarketDataServer | None = None) -> FastAPI:
    app = FastAPI(title="AlgoShield Mock Market Data Feed")
    feed = server if server is not None else MockMarketDataServer()
    app.state.feed = feed

    @app.get("/health")
    def health():
        return {
            "service": "algoshield-mock-market-data",
            "status": "UP",
            "ticks_count": len(feed.ticks),
            "candles_count": len(feed.closed_candles),
        }

    @app.get("/ticks")
    def get_ticks(
        symbol: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
    ):
        matching = [
            serialize_tick(t)
            for t in reversed(feed.ticks)
            if symbol is None or t.symbol == symbol.upper().strip()
        ][:limit]
        return matching

    @app.post("/ticks", status_code=201)
    def post_tick(body: RawTickRequest):
        now = int(time.time())
        ts = body.event_timestamp if body.event_timestamp is not None else now
        eid = body.event_id or f"{body.symbol}:{ts}:{len(feed.ticks) + 1}"
        tick = Tick(body.symbol, ts, body.price, body.quantity, eid)
        closed = feed.publish(tick)
        return {
            "tick": serialize_tick(tick),
            "closed_candles": [serialize_candle(c) for c in closed],
        }

    @app.post("/ticks/batch", status_code=201)
    def post_ticks_batch(ticks: list[RawTickRequest]):
        published = []
        all_closed = []
        for body in ticks:
            now = int(time.time())
            ts = body.event_timestamp if body.event_timestamp is not None else now
            eid = body.event_id or f"{body.symbol}:{ts}:{len(feed.ticks) + 1}"
            t = Tick(body.symbol, ts, body.price, body.quantity, eid)
            closed = feed.publish(t)
            published.append(serialize_tick(t))
            all_closed.extend([serialize_candle(c) for c in closed])
        return {
            "count": len(published),
            "ticks": published,
            "closed_candles": all_closed,
        }

    @app.post("/replay/demo")
    def replay_demo(start: int | None = None):
        loaded = feed.load_demo(start)
        return {"loaded_ticks": loaded}

    @app.get("/candles")
    def get_candles(
        symbol: str | None = None,
        interval: int | None = None,
        limit: int = Query(100, ge=1, le=500),
    ):
        matching = [
            serialize_candle(c)
            for c in reversed(feed.closed_candles)
            if (symbol is None or c.symbol == symbol.upper().strip())
            and (interval is None or c.interval == interval)
        ][:limit]
        return matching

    @app.get("/stream/ticks")
    async def stream_ticks(request: Request, limit: int = 10):
        async def event_generator():
            recent = list(feed.ticks)[-limit:]
            for t in recent:
                data = json.dumps(serialize_tick(t))
                yield f"data: {data}\n\n"
            yield f"event: ping\ndata: {json.dumps({'time': time.time()})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app

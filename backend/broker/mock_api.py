"""Standalone Mock Broker HTTP API for AlgoShield PS-06 prototype.

IMPORTANT DISCLAIMER:
This API is an AlgoShield prototype broker simulator for testing, demos, and failure lab
scenarios while official sponsor 021 API documentation and sandbox credentials are unavailable.
It is NOT an imitation of the sponsor's undocumented 021 API.
"""

from decimal import Decimal
import os
from pathlib import Path
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from backend.broker.adapters import MockBrokerAdapter
from backend.shared.contracts import (
    BrokerSnapshot,
    BrokerUpdate,
    CanonicalOrder,
    Fill,
    OrderIntent,
    Side,
)


class OrderRequest(BaseModel):
    intent_id: str
    strategy_instance_id: str
    account_id: str
    symbol: str
    side: Side
    quantity: Annotated[int, Field(gt=0)]
    order_type: str = "MARKET"
    limit_price: Decimal | None = None
    created_at: float | None = None

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, v):
        if isinstance(v, str):
            return Side(v.strip().upper())
        return v

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("order_type", mode="before")
    @classmethod
    def normalize_order_type(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("limit_price", mode="before")
    @classmethod
    def parse_limit_price(cls, v):
        if v is not None and isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class FillRequest(BaseModel):
    quantity: Annotated[int, Field(gt=0)]
    price: Annotated[Decimal, Field(gt=0)]
    charges: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    timestamp: float | None = None
    allow_late: bool = False

    @field_validator("price", "charges", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


def serialize_order(order: CanonicalOrder) -> dict:
    return {
        "order_id": order.order_id,
        "intent_id": order.intent.intent_id,
        "strategy_instance_id": order.intent.strategy_instance_id,
        "account_id": order.intent.account_id,
        "symbol": order.intent.symbol,
        "side": order.intent.side.value,
        "quantity": order.intent.quantity,
        "order_type": order.intent.order_type,
        "limit_price": (
            str(order.intent.limit_price)
            if order.intent.limit_price is not None
            else None
        ),
        "status": order.status.value,
        "filled_quantity": order.filled_quantity,
        "remaining_quantity": order.remaining_quantity,
        "created_at": order.intent.created_at,
    }


def serialize_fill(fill: Fill) -> dict:
    return {
        "fill_id": fill.fill_id,
        "broker_order_id": fill.broker_order_id,
        "strategy_instance_id": fill.strategy_instance_id,
        "account_id": fill.account_id,
        "symbol": fill.symbol,
        "side": fill.side.value,
        "quantity": fill.quantity,
        "price": str(fill.price),
        "charges": str(fill.charges),
        "timestamp": fill.timestamp,
    }


def serialize_positions(positions: dict[tuple[str, str], int]) -> list[dict]:
    return [
        {"account_id": acc, "symbol": sym, "quantity": qty}
        for (acc, sym), qty in positions.items()
        if qty != 0
    ]


def serialize_update(update: BrokerUpdate) -> dict:
    return {
        "update_id": update.update_id,
        "order_id": update.order_id,
        "update_type": update.update_type.value,
        "status": update.status.value if update.status is not None else None,
        "fill": serialize_fill(update.fill) if update.fill is not None else None,
        "timestamp": update.timestamp,
    }


def serialize_snapshot(snapshot: BrokerSnapshot) -> dict:
    return {
        "orders": [serialize_order(o) for o in snapshot.orders],
        "fills": [serialize_fill(f) for f in snapshot.fills],
        "positions": serialize_positions(snapshot.positions),
        "is_complete": snapshot.is_complete,
        "observed_at": snapshot.observed_at or time.time(),
    }


def create_mock_broker_app(
    adapter: MockBrokerAdapter | None = None,
    storage_path: Path | str | None = None,
) -> FastAPI:
    path = storage_path or os.environ.get("MOCK_BROKER_STORAGE_PATH")
    broker = adapter or MockBrokerAdapter(path)

    app = FastAPI(title="AlgoShield Mock Broker HTTP API")
    app.state.broker = broker

    @app.exception_handler(ConnectionError)
    async def connection_error_handler(_: Request, exc: ConnectionError):
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "connected": False},
        )

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(_: Request, exc: TimeoutError):
        return JSONResponse(
            status_code=504,
            content={"detail": str(exc), "simulated_timeout": True},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError):
        msg = str(exc)
        status_code = 404 if "not found" in msg.lower() else 409
        return JSONResponse(
            status_code=status_code,
            content={"detail": msg},
        )

    # -------------------------------------------------------------------------
    # Core Broker Endpoints
    # -------------------------------------------------------------------------

    @app.get("/health")
    def health():
        return {
            "service": "algoshield-mock-broker",
            "connected": broker.connected,
        }

    @app.post("/orders", status_code=201)
    def place_order(body: OrderRequest):
        broker._check()
        created_at = body.created_at if body.created_at is not None else time.time()
        intent = OrderIntent(
            intent_id=body.intent_id,
            strategy_instance_id=body.strategy_instance_id,
            account_id=body.account_id,
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
            order_type=body.order_type,
            limit_price=body.limit_price,
            created_at=created_at,
        )
        order = broker.submit(intent)
        return serialize_order(order)

    @app.get("/orders")
    def get_orders():
        broker._check()
        return [serialize_order(o) for o in broker.orders.values()]

    @app.get("/orders/{order_id}")
    def get_order(order_id: str):
        broker._check()
        order = broker.orders.get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail=f"order {order_id} not found")
        return serialize_order(order)

    @app.post("/orders/{order_id}/fills", status_code=201)
    def create_fill(order_id: str, body: FillRequest):
        broker._check()
        if order_id not in broker.orders:
            raise HTTPException(status_code=404, detail=f"order {order_id} not found")
        ts = body.timestamp if body.timestamp is not None else time.time()
        fill = broker.execute(
            order_id=order_id,
            quantity=body.quantity,
            price=body.price,
            timestamp=ts,
            charges=body.charges,
            allow_late=body.allow_late,
        )
        return serialize_fill(fill)

    @app.get("/fills")
    def get_fills():
        broker._check()
        return [serialize_fill(f) for f in broker.fills.values()]

    @app.get("/orders/{order_id}/fills")
    def get_order_fills(order_id: str):
        broker._check()
        if order_id not in broker.orders:
            raise HTTPException(status_code=404, detail=f"order {order_id} not found")
        return [
            serialize_fill(f)
            for f in broker.fills.values()
            if f.broker_order_id == order_id
        ]

    @app.post("/orders/{order_id}/cancel")
    def cancel_order(order_id: str):
        broker._check()
        if order_id not in broker.orders:
            raise HTTPException(status_code=404, detail=f"order {order_id} not found")
        broker.cancel(order_id)
        return serialize_order(broker.orders[order_id])

    @app.get("/positions")
    def get_positions():
        broker._check()
        snap = broker.snapshot()
        return {"positions": serialize_positions(snap.positions)}

    @app.get("/snapshot")
    def get_snapshot():
        broker._check()
        snap = broker.snapshot()
        return serialize_snapshot(snap)

    @app.get("/updates")
    def get_updates():
        broker._check()
        return [serialize_update(u) for u in broker.updates]

    @app.post("/updates/drain")
    def drain_updates():
        broker._check()
        return [serialize_update(u) for u in broker.drain_updates()]

    # -------------------------------------------------------------------------
    # Controlled Failure Injection & Simulation (/mock/*)
    # -------------------------------------------------------------------------

    @app.post("/mock/reject-next")
    def mock_reject_next():
        broker.reject_next = True
        return {"reject_next": True}

    @app.post("/mock/timeout-after-accept")
    def mock_timeout_after_accept():
        broker.timeout_after_accept = True
        return {"timeout_after_accept": True}

    @app.post("/mock/disconnect")
    def mock_disconnect():
        broker.disconnect()
        return {"connected": False}

    @app.post("/mock/reconnect")
    def mock_reconnect():
        broker.reconnect()
        return {"connected": True}

    @app.post("/mock/orders/{order_id}/external-fill", status_code=201)
    def mock_external_fill(order_id: str, body: FillRequest):
        """Simulate execution on the broker while normal client connection is marked disconnected."""
        if order_id not in broker.orders:
            raise HTTPException(status_code=404, detail=f"order {order_id} not found")
        ts = body.timestamp if body.timestamp is not None else time.time()
        fill = broker.execute_external(
            order_id=order_id,
            quantity=body.quantity,
            price=body.price,
            timestamp=ts,
            charges=body.charges,
            allow_late=body.allow_late,
        )
        return serialize_fill(fill)

    @app.post("/mock/reset")
    def mock_reset():
        broker.reset()
        return {"reset": True, "connected": True}

    return app


app = create_mock_broker_app()

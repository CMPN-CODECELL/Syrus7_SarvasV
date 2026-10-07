import sqlite3
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, StrictInt, field_validator
from psycopg.errors import UniqueViolation

from backend.platform import Platform
from backend.reliability.failure_lab import FailureLab
from backend.shared.config import settings
from backend.shared.contracts import RiskPolicy, StrategyState
from backend.shared.postgres import PostgresStore


class AccountRequest(BaseModel):
    account_id: str

    @field_validator("account_id")
    @classmethod
    def normalize_account_id(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("account ID is required")
        return value


class SubscriptionRequest(BaseModel):
    account_id: str
    strategy_instance_id: str
    kind: str
    symbol: str

    @field_validator("account_id", "strategy_instance_id")
    @classmethod
    def normalize_ids(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("identifier is required")
        return value

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value):
        return value.strip().lower()

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value):
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol is required")
        return value


class PolicyRequest(BaseModel):
    max_daily_loss: Decimal
    max_position: StrictInt
    max_orders_per_minute: StrictInt


class StrategyStateRequest(BaseModel):
    state: StrategyState


class MarketSessionRequest(BaseModel):
    status: str


def financial_json(value):
    return JSONResponse(content=jsonable_encoder(value, custom_encoder={Decimal: str}))


def create_app(platform=None):
    config = (
        settings()
        if platform is None
        else {"sqlite_path": ":memory:", "database_url": ""}
    )
    engine = platform or Platform(
        config["sqlite_path"],
        store=PostgresStore(config["database_url"]) if config["database_url"] else None,
        demo_enabled=not bool(config["database_url"]),
    )

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if platform is None:
                engine.store.close()

    app = FastAPI(title="AlgoShield mock control plane", lifespan=lifespan)
    app.state.platform = engine

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/")
    def dashboard():
        return FileResponse(
            Path(__file__).resolve().parent.parent / "frontend/index.html"
        )

    @app.get("/health")
    def health():
        return {
            "process": "UP",
            "trading": engine.risk.state,
            "reconciliation": engine.reliability.health,
        }

    @app.get("/api/state")
    def state():
        return financial_json(engine.snapshot())

    @app.get("/api/fills")
    def fills(limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
        return engine.history("fills", limit, offset)

    @app.get("/api/orders")
    def orders(limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
        return engine.history("orders", limit, offset)

    @app.post("/api/orders/{order_id}/cancel")
    def cancel_order(order_id: str):
        try:
            return financial_json(engine.cancel(order_id))
        except ValueError as exc:
            if "not found" in str(exc):
                raise HTTPException(404, str(exc)) from None
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/broker/updates/sync")
    def sync_broker_updates():
        results = engine.sync_broker_updates()
        return financial_json({"processed": len(results), "updates": results})

    @app.post("/api/broker/disconnect")
    def disconnect_broker():
        return financial_json(engine.disconnect_broker())

    @app.post("/api/broker/reconnect")
    def reconnect_broker():
        return financial_json(engine.reconnect_broker())

    @app.post("/api/accounts", status_code=201)
    def account(body: AccountRequest):
        try:
            engine.account(body.account_id)
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "account exists") from None
        return {"account_id": body.account_id}

    @app.get("/api/strategies")
    def list_strategies():
        return engine.strategies.list_registered()

    @app.get("/api/market/session")
    def get_market_session():
        return financial_json(engine.market_session.to_dict(engine.clock()))

    @app.post("/api/market/session")
    def set_market_session(body: MarketSessionRequest):
        try:
            engine.market_session.set_status(body.status)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return financial_json(engine.market_session.to_dict(engine.clock()))

    @app.post("/api/subscriptions", status_code=201)
    def subscribe(body: SubscriptionRequest):
        try:
            engine.strategies.subscribe(
                body.account_id, body.strategy_instance_id, body.kind, body.symbol
            )
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "strategy instance exists") from None
        return engine.snapshot()["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/start")
    def start_subscription(strategy_instance_id: str, body: AccountRequest):
        engine.strategies.set_enabled(body.account_id, strategy_instance_id, True)
        return engine.snapshot()["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/stop")
    def stop_subscription(strategy_instance_id: str, body: AccountRequest):
        engine.strategies.set_enabled(body.account_id, strategy_instance_id, False)
        return engine.snapshot()["subscriptions"]

    @app.post("/api/demo")
    def demo():
        if not engine.demo_enabled:
            raise HTTPException(403, "replay demo is disabled for this database")
        return financial_json(engine.demo())

    @app.put("/api/risk/policies/{strategy}")
    def policy(strategy: str, body: PolicyRequest):
        engine.risk.policies[strategy] = RiskPolicy(**body.model_dump())
        return financial_json(engine.risk.policies[strategy])

    @app.put("/api/risk/strategies/{strategy}")
    def strategy_control(strategy: str, body: StrategyStateRequest):
        engine.risk.set_strategy_state(strategy, body.state)
        return {
            "strategy_instance_id": strategy,
            "state": engine.risk.strategy_state(strategy),
        }

    @app.get("/api/risk/budgets")
    def budgets():
        return financial_json(engine.snapshot()["risk_budgets"])

    @app.post("/api/failure-lab/{scenario}")
    def failure_lab(scenario: str):
        return financial_json(FailureLab(engine).run(scenario))

    @app.post("/api/reconcile")
    def reconcile():
        return financial_json(
            {
                "reconciled": engine.reliability.reconcile(),
                "state": engine.snapshot(),
            }
        )

    @app.post("/api/resume")
    def resume():
        engine.reliability.resume()
        return financial_json(engine.snapshot())

    @app.post("/api/reduce-only")
    def reduce_only():
        engine.reliability.resume(reduce_only=True)
        return financial_json(engine.snapshot())

    @app.post("/api/kill/reset")
    def reset_kill():
        engine.reliability.reset_kill()
        return financial_json(engine.snapshot())

    @app.post("/api/kill")
    def kill():
        return engine.kill()

    return app

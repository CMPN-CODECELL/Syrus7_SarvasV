import sqlite3
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from contextlib import asynccontextmanager
from pydantic import BaseModel, StrictInt
from psycopg.errors import UniqueViolation

from backend.platform import Platform
from backend.shared.config import settings
from backend.shared.postgres import PostgresStore
from backend.reliability.failure_lab import FailureLab
from backend.shared.contracts import RiskPolicy, StrategyState


class AccountRequest(BaseModel):
    account_id: str


class SubscriptionRequest(BaseModel):
    account_id: str
    strategy_instance_id: str
    kind: str
    symbol: str


class PolicyRequest(BaseModel):
    max_daily_loss: Decimal
    max_position: StrictInt
    max_orders_per_minute: StrictInt


class StrategyStateRequest(BaseModel):
    state: StrategyState


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

    @app.post("/api/accounts", status_code=201)
    def account(body: AccountRequest):
        try:
            engine.account(body.account_id)
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "account exists") from None
        return {"account_id": body.account_id}

    @app.post("/api/subscriptions", status_code=201)
    def subscribe(body: SubscriptionRequest):
        try:
            engine.strategies.subscribe(
                body.account_id, body.strategy_instance_id, body.kind, body.symbol
            )
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "strategy instance exists") from None
        return engine.snapshot()["subscriptions"]

    @app.post("/api/demo")
    def demo():
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

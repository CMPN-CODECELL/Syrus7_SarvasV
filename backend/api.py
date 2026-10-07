import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from psycopg.errors import UniqueViolation

from backend.platform import Platform
from backend.shared.config import settings
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
    app = FastAPI(title="AlgoShield mock bootstrap")
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
        return engine.snapshot()

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
        return engine.demo()

    @app.post("/api/reconcile")
    def reconcile():
        return {
            "reconciled": engine.reliability.reconcile(),
            "state": engine.snapshot(),
        }

    @app.post("/api/resume")
    def resume():
        engine.reliability.resume()
        return engine.snapshot()

    @app.post("/api/kill")
    def kill():
        return engine.kill()

    return app

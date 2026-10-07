import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from psycopg.errors import UniqueViolation

from backend.platform import Platform
from backend.shared.config import settings
from backend.shared.postgres import PostgresStore
from backend.reliability.failure_lab import FailureLab


class AccountRequest(BaseModel):
    account_id: str


class SubscriptionRequest(BaseModel):
    account_id: str
    strategy_instance_id: str
    kind: str
    symbol: str


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

    @app.post("/api/demo")
    def demo():
        return engine.demo()

    @app.post("/api/failure-lab/{scenario}")
    def failure_lab(scenario: str):
        return FailureLab(engine).run(scenario)

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

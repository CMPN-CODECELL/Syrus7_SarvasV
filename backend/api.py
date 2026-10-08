import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, ConfigDict, StrictInt, field_validator
from psycopg.errors import UniqueViolation
from starlette.websockets import WebSocketDisconnect

from backend.platform import Platform
from backend.broker.http_adapter import HTTPMockBrokerAdapter
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
    model_config = ConfigDict(extra="forbid")

    strategy_instance_id: str
    kind: str
    symbol: str

    @field_validator("strategy_instance_id")
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


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value):
        if len(value) < 6:
            raise ValueError("password must be at least 6 characters")
        return value


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value


def financial_json(value):
    return JSONResponse(content=jsonable_encoder(value, custom_encoder={Decimal: str}))


def create_app(platform=None):
    config = (
        settings()
        if platform is None
        else {"sqlite_path": ":memory:", "database_url": ""}
    )
    broker = None
    mock_broker_url = config.get("mock_broker_url", "")
    if mock_broker_url:
        broker = HTTPMockBrokerAdapter(mock_broker_url)
    # PostgreSQL is safe for replay only when the caller explicitly points at
    # a loopback HTTP mock broker.  Remote/mock-looking URLs must never enable
    # seeded replay against a durable or production database.
    broker_host = urlparse(mock_broker_url).hostname if mock_broker_url else None
    local_mock = broker_host in {"127.0.0.1", "localhost", "::1"}
    engine = platform or Platform(
        config["sqlite_path"],
        broker=broker,
        store=PostgresStore(config["database_url"]) if config["database_url"] else None,
        demo_enabled=not bool(config["database_url"]) or local_mock,
    )

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if platform is None:
                if broker is not None:
                    broker.close()
                engine.close()

    app = FastAPI(title="AlgoShield mock control plane", lifespan=lifespan)
    app.state.platform = engine
    session_cookie = "algoshield_session"

    def request_token(request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ").strip()
        return request.cookies.get(session_cookie, "")

    def require_user(request: Request):
        user = engine.auth.verify_token(request_token(request))
        if not user:
            raise HTTPException(401, "authentication required")
        return user

    def set_session_cookie(response, token: str):
        response.set_cookie(
            key=session_cookie,
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=engine.auth.token_ttl_seconds,
            path="/",
        )

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/")
    def dashboard(request: Request):
        if not engine.auth.verify_token(request_token(request)):
            return RedirectResponse("/login", status_code=303)
        return FileResponse(
            Path(__file__).resolve().parent.parent / "frontend/index.html"
        )

    @app.get("/login")
    def login_page():
        return FileResponse(
            Path(__file__).resolve().parent.parent / "frontend/login.html"
        )

    @app.get("/register")
    def register_page():
        return FileResponse(
            Path(__file__).resolve().parent.parent / "frontend/register.html"
        )

    @app.post("/api/auth/register", status_code=201)
    def register(body: RegisterRequest, response: Response):
        try:
            res = engine.auth.register(body.username, body.password)
            set_session_cookie(response, res["token"])
            return {
                "user": {"username": res["username"], "account_id": res["account_id"]},
                "token": res["token"],
            }
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "username already exists") from None
        except ValueError as exc:
            msg = str(exc)
            if "already exists" in msg or "already taken" in msg:
                raise HTTPException(409, msg) from None
            raise HTTPException(400, msg) from None

    @app.post("/api/auth/login")
    def login(body: LoginRequest, response: Response):
        res = engine.auth.login(body.username, body.password)
        if not res:
            raise HTTPException(401, "invalid credentials")
        set_session_cookie(response, res["token"])
        return {
            "user": {"username": res["username"], "account_id": res["account_id"]},
            "token": res["token"],
        }

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        token = request_token(request)
        if token:
            engine.auth.logout(token)
        response.delete_cookie(session_cookie, path="/")
        return {"status": "logged_out"}

    @app.get("/api/auth/me")
    def current_user(request: Request):
        return {"user": require_user(request)}

    @app.get("/health")
    def health():
        return {
            "process": "UP",
            "trading": engine.risk.state,
            "reconciliation": engine.reliability.health,
        }

    @app.get("/api/state")
    def state(request: Request):
        user = require_user(request)
        return financial_json(engine.snapshot(account_id=user["account_id"]))

    @app.get("/api/stream/telemetry")
    async def stream_telemetry(
        request: Request,
        max_events: int | None = Query(None, ge=1),
    ):
        token = request.query_params.get("token") or request_token(request)
        user = engine.auth.verify_token(token)
        if not user:
            raise HTTPException(401, "authentication required")

        account_id = user["account_id"]

        async def event_generator():
            count = 0
            current_user = engine.auth.verify_token(token)
            if not current_user:
                return
            snapshot = engine.snapshot(account_id=account_id)
            payload = json.dumps(
                jsonable_encoder(snapshot, custom_encoder={Decimal: str})
            )
            yield f"event: snapshot\ndata: {payload}\n\n"
            count += 1
            if max_events is not None and count >= max_events:
                return
            try:
                while True:
                    await asyncio.sleep(0.1)
                    current_user = engine.auth.verify_token(token)
                    if not current_user:
                        break
                    snapshot = engine.snapshot(account_id=account_id)
                    payload = json.dumps(
                        jsonable_encoder(snapshot, custom_encoder={Decimal: str})
                    )
                    yield f"event: telemetry\ndata: {payload}\n\n"
                    count += 1
                    if max_events is not None and count >= max_events:
                        break
            except (asyncio.CancelledError, GeneratorExit):
                return

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.websocket("/api/stream/ws")
    async def stream_websocket(websocket: WebSocket):
        """Push backend snapshots over a persistent browser connection."""
        token = (
            websocket.cookies.get(session_cookie)
            or websocket.query_params.get("token")
            or ""
        )
        if not token:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()

        user = engine.auth.verify_token(token)
        if not user:
            await websocket.close(code=1008, reason="authentication required")
            return

        await websocket.accept()
        account_id = user["account_id"]
        try:
            while True:
                current_user = engine.auth.verify_token(token)
                if not current_user:
                    await websocket.close(code=1008, reason="session expired")
                    break
                snapshot = engine.snapshot(account_id=account_id)
                await websocket.send_json(
                    jsonable_encoder(snapshot, custom_encoder={Decimal: str})
                )
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return

    @app.get("/api/fills")
    def fills(
        request: Request,
        limit: int = Query(200, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        user = require_user(request)
        return engine.history("fills", limit, offset, account_id=user["account_id"])

    @app.get("/api/orders")
    def orders(
        request: Request,
        limit: int = Query(200, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        user = require_user(request)
        return engine.history("orders", limit, offset, account_id=user["account_id"])

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

    @app.get("/api/subscriptions")
    def list_subscriptions(request: Request):
        user = require_user(request)
        return engine.snapshot(account_id=user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions", status_code=201)
    def subscribe(body: SubscriptionRequest, request: Request):
        user = require_user(request)
        try:
            engine.strategies.subscribe(
                user["account_id"], body.strategy_instance_id, body.kind, body.symbol
            )
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "strategy instance exists") from None
        return engine.snapshot(account_id=user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/start")
    def start_subscription(strategy_instance_id: str, request: Request):
        user = require_user(request)
        rows = engine.store.rows(
            "SELECT account FROM subscriptions WHERE id=?", (strategy_instance_id,)
        )
        if not rows:
            raise HTTPException(404, "subscription does not exist")
        if rows[0]["account"] != user["account_id"]:
            raise HTTPException(
                403, "access denied: subscription belongs to another account"
            )
        engine.strategies.set_enabled(user["account_id"], strategy_instance_id, True)
        return engine.snapshot(account_id=user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/stop")
    def stop_subscription(strategy_instance_id: str, request: Request):
        user = require_user(request)
        rows = engine.store.rows(
            "SELECT account FROM subscriptions WHERE id=?", (strategy_instance_id,)
        )
        if not rows:
            raise HTTPException(404, "subscription does not exist")
        if rows[0]["account"] != user["account_id"]:
            raise HTTPException(
                403, "access denied: subscription belongs to another account"
            )
        engine.strategies.set_enabled(user["account_id"], strategy_instance_id, False)
        return engine.snapshot(account_id=user["account_id"])["subscriptions"]

    @app.post("/api/demo")
    def demo():
        if not engine.demo_enabled:
            raise HTTPException(403, "replay demo is disabled for this database")
        # A restart begins RECOVERING. A deliberate replay action may perform
        # the required authoritative broker check first, but it must never
        # bypass an actual drift/uncertainty result.
        if engine.risk.state == "RECOVERING" and not engine.reliability.reconcile():
            raise HTTPException(409, "reconciliation required")
        state = engine.demo()
        engine.start_replay_stream()
        return financial_json(state)

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
    def budgets(request: Request):
        user = require_user(request)
        return financial_json(
            engine.snapshot(account_id=user["account_id"])["risk_budgets"]
        )

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

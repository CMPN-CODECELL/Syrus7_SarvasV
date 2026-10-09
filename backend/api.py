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
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from backend.platform import Platform
from backend.market_data.yahoo import YahooMarketDataProvider
from backend.market_data.official021 import MarketData021Provider
from backend.broker.adapters import Broker021Adapter, MockBrokerAdapter
from backend.broker.http_adapter import HTTPMockBrokerAdapter
from backend.reliability.failure_lab import FailureLab, SCENARIOS, SCENARIO_METADATA
from backend.shared.config import settings
from backend.shared.contracts import AccountRiskPolicy, RiskPolicy, StrategyState
from backend.shared.postgres import PostgresStore
from backend.shared.store import Store
from backend.shared.presentation import AccountResponseScope
from backend.shared.browser_security import (
    DEFAULT_ORIGINS,
    LoginLimiter,
    origin_allowed,
)
from backend.strategies.runtime import (
    MAX_BATCH_SYMBOLS,
    MAX_INSTANCE_PREFIX_LENGTH,
    SubscriptionBatchConflict,
    normalize_subscription_symbols,
)


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


class BatchSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    symbols: list[str]
    instance_prefix: str | None = None

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError("strategy kind is required")
        return value

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value):
        normalized = normalize_subscription_symbols(value)
        if len(normalized) > MAX_BATCH_SYMBOLS:
            raise ValueError(f"no more than {MAX_BATCH_SYMBOLS} symbols are allowed")
        return normalized

    @field_validator("instance_prefix")
    @classmethod
    def normalize_prefix(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("instance prefix cannot be blank")
        if len(value) > MAX_INSTANCE_PREFIX_LENGTH:
            raise ValueError(
                f"instance prefix must be at most {MAX_INSTANCE_PREFIX_LENGTH} characters"
            )
        return value


class PolicyRequest(BaseModel):
    max_daily_loss: Decimal
    max_position: StrictInt
    max_orders_per_minute: StrictInt
    max_price_deviation_bps: StrictInt = 500


class AccountPolicyRequest(BaseModel):
    max_net_position_per_symbol: StrictInt | None = None
    max_gross_virtual_position_per_symbol: StrictInt | None = None


class StrategyStateRequest(BaseModel):
    state: StrategyState


class MarketSessionRequest(BaseModel):
    status: str


class SafetyBenchRequest(BaseModel):
    iterations: StrictInt = 1


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


def create_app(platform=None, *, trusted_origins=None):
    config = (
        settings()
        if platform is None
        else {"sqlite_path": ":memory:", "database_url": ""}
    )
    broker = None
    application_store = None
    mock_broker_url = config.get("mock_broker_url", "")
    if config.get("021_enabled"):
        application_store = (
            PostgresStore(config["database_url"])
            if config["database_url"]
            else Store(config["sqlite_path"])
        )
        broker = Broker021Adapter(
            application_store,
            enabled=True,
            base_url=config.get("021_base_url"),
            username=config.get("021_username"),
            password=config.get("021_password"),
            access_token=config.get("021_token"),
            instrument_cache=config.get("021_instrument_cache"),
        )
    elif mock_broker_url:
        broker = HTTPMockBrokerAdapter(mock_broker_url)
    # PostgreSQL is safe for replay only when the caller explicitly points at
    # a loopback HTTP mock broker.  Remote/mock-looking URLs must never enable
    # seeded replay against a durable or production database.
    broker_host = urlparse(mock_broker_url).hostname if mock_broker_url else None
    local_mock = broker_host in {"127.0.0.1", "localhost", "::1"}
    engine = platform or Platform(
        config["sqlite_path"],
        broker=broker,
        store=application_store
        or (PostgresStore(config["database_url"]) if config["database_url"] else None),
        demo_enabled=(
            False
            if config.get("021_enabled")
            else not bool(config["database_url"]) or local_mock
        ),
    )
    if platform is None and config.get("market_data_provider") == "021":
        if not isinstance(broker, Broker021Adapter):
            raise RuntimeError("021 market data requires ALGOSHIELD_021_ENABLED=true")
        symbols = config.get("021_symbols")
        if not symbols:
            # The catalogue is the source of truth when no explicit universe is
            # configured.  The provider applies 021's connection/instrument
            # limits and reports any truncation in telemetry.
            symbols = broker.all_market_symbols()
            if not symbols:
                raise RuntimeError("021 instrument catalogue contains no cash-equity symbols")
        engine.configure_external_market_data(
            MarketData021Provider(
                engine,
                broker,
                symbols,
            )
        )
    elif platform is None and config.get("market_data_provider") == "yahoo":
        yahoo = YahooMarketDataProvider(
            engine, symbols=config.get("yahoo_symbols", ("TCS.NS", "INFY.NS"))
        )
        engine.configure_external_market_data(yahoo)

    @asynccontextmanager
    async def lifespan(app):
        try:
            if platform is None and engine.external_market_data is not None:
                engine.start_external_market_data()
            yield
        finally:
            if platform is None:
                if broker is not None:
                    broker.close()
                engine.close()

    app = FastAPI(title="AlgoShield mock control plane", lifespan=lifespan)
    app.state.platform = engine
    if trusted_origins is None:
        import os

        configured = os.environ.get(
            "ALGOSHIELD_TRUSTED_ORIGINS", config.get("trusted_origins")
        )
        trusted_origins = (
            configured.split(",") if configured is not None else DEFAULT_ORIGINS
        )
    trusted_origins = frozenset(
        value.strip() for value in trusted_origins if value.strip()
    )
    app.state.login_limiter = LoginLimiter()

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            bearer = request.headers.get("authorization", "").startswith("Bearer ")
            if not origin_allowed(request.headers, trusted_origins, bearer=bearer):
                result = JSONResponse(
                    status_code=403, content={"detail": "untrusted browser origin"}
                )
            else:
                result = await call_next(request)
        else:
            result = await call_next(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["X-Frame-Options"] = "DENY"
        result.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return result

    session_cookie = "algoshield_session"
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (frontend_dist / "assets").is_dir():
        app.mount(
            "/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets"
        )

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

    def require_operator(request: Request):
        user = require_user(request)
        if not user["is_operator"]:
            raise HTTPException(403, "operator authority required")
        return user

    def account_response(user, value):
        with engine.store.lock:
            encoded = jsonable_encoder(value, custom_encoder={Decimal: str})
            return financial_json(
                AccountResponseScope(engine.store, user["account_id"]).project(encoded)
            )

    def require_strategy_owner(request: Request, strategy: str):
        user = require_user(request)
        rows = engine.store.rows(
            "SELECT account FROM subscriptions WHERE id=?", (strategy,)
        )
        if not rows:
            raise HTTPException(404, "strategy subscription not found")
        if rows[0]["account"] != user["account_id"]:
            raise HTTPException(
                403, "access denied: strategy belongs to another account"
            )
        return user

    def require_order_owner(request: Request, order_id: str):
        user = require_user(request)
        rows = engine.store.rows("SELECT account FROM orders WHERE id=?", (order_id,))
        if not rows:
            raise HTTPException(404, "order not found")
        if rows[0]["account"] != user["account_id"]:
            raise HTTPException(403, "order belongs to another account")
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

        message = str(exc)
        safe_messages = (
            "synthetic Failure Lab injection requires the offline mock broker",
            "demo replay requires an explicitly enabled local mock broker",
        )
        return JSONResponse(
            status_code=409,
            content={
                "detail": message
                if message.startswith(safe_messages)
                else "operation rejected; inspect authorized local audit evidence"
            },
        )

    @app.get("/")
    def dashboard(request: Request):
        if not engine.auth.verify_token(request_token(request)):
            return RedirectResponse("/login", status_code=303)
        if not (frontend_dist / "index.html").is_file():
            raise HTTPException(
                503, "React build missing; run npm --prefix frontend run build"
            )
        return FileResponse(frontend_dist / "index.html")

    @app.get("/login")
    def login_page():
        if not (frontend_dist / "index.html").is_file():
            raise HTTPException(
                503, "React build missing; run npm --prefix frontend run build"
            )
        return FileResponse(frontend_dist / "index.html")

    @app.get("/register")
    def register_page():
        if not (frontend_dist / "index.html").is_file():
            raise HTTPException(
                503, "React build missing; run npm --prefix frontend run build"
            )
        return FileResponse(frontend_dist / "index.html")

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
    def login(body: LoginRequest, response: Response, request: Request):
        # Use peer identity only; configure uvicorn --no-proxy-headers.
        peer = request.client.host if request.client else "unknown"
        ticket = app.state.login_limiter.acquire(peer)
        if not ticket:
            raise HTTPException(
                429,
                "authentication temporarily unavailable",
                headers={"Retry-After": "60"},
            )
        res = engine.auth.login(body.username, body.password)
        if res:
            app.state.login_limiter.succeeded(peer, ticket)
        with engine.store.transaction():
            engine.store.audit(
                "LOGIN_SUCCEEDED" if res else "LOGIN_FAILED",
                {"outcome": "success" if res else "failure"},
            )
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
        return financial_json(engine.snapshot(user["account_id"]))

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
            if not engine.auth.verify_token(token):
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
                    if await request.is_disconnected():
                        break
                    await asyncio.sleep(0.1)
                    if not engine.auth.verify_token(token):
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
        cookie_token = websocket.cookies.get(session_cookie)
        explicit_bearer = not cookie_token and websocket.headers.get(
            "authorization", ""
        ).startswith("Bearer ")
        if not origin_allowed(
            websocket.headers, trusted_origins, bearer=explicit_bearer
        ):
            await websocket.close(code=1008, reason="untrusted browser origin")
            return
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
                if not engine.auth.verify_token(token):
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
    def cancel_order(order_id: str, request: Request):
        user = require_order_owner(request, order_id)
        try:
            return account_response(user, engine.cancel(order_id))
        except ValueError as exc:
            if "not found" in str(exc):
                raise HTTPException(404, "order not found") from None
            raise HTTPException(400, "operation rejected") from None

    @app.post("/api/broker/updates/sync")
    def sync_broker_updates(request: Request):
        user = require_operator(request)
        results = engine.sync_broker_updates()
        return account_response(user, {"processed": len(results), "updates": results})

    @app.post("/api/broker/disconnect")
    def disconnect_broker(request: Request):
        user = require_operator(request)
        return account_response(user, engine.disconnect_broker())

    @app.post("/api/broker/reconnect")
    def reconnect_broker(request: Request):
        user = require_operator(request)
        return account_response(user, engine.reconnect_broker())

    @app.post("/api/accounts", status_code=201)
    def account(body: AccountRequest, request: Request):
        require_operator(request)
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

    @app.get("/api/candles")
    def historical_candles(
        request: Request,
        symbol: str | None = None,
        interval: int = Query(60, ge=60, le=300),
        limit: int = Query(200, ge=1, le=1000),
    ):
        require_user(request)
        if interval not in {60, 300}:
            raise HTTPException(422, "interval must be 60 or 300 seconds")
        provider = (
            engine.market_data_evidence().get("provider")
            if engine.external_market_data is not None
            else "replay"
        )
        rows = engine.store.candle_rows(
            symbol=symbol,
            interval=interval,
            limit=limit,
            provider=provider,
        )
        return financial_json([dict(row) for row in rows])

    @app.post("/api/market/session")
    def set_market_session(body: MarketSessionRequest, request: Request):
        user = require_operator(request)
        try:
            engine.market_session.set_status(body.status)
        except ValueError:
            raise HTTPException(400, "operation rejected") from None
        return account_response(user, engine.market_session.to_dict(engine.clock()))

    @app.post("/api/subscriptions", status_code=201)
    def subscribe(body: SubscriptionRequest, request: Request):
        user = require_user(request)
        try:
            engine.strategies.subscribe(
                user["account_id"], body.strategy_instance_id, body.kind, body.symbol
            )
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "strategy instance exists") from None
        return engine.snapshot(user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions/batch", status_code=201)
    def subscribe_batch(body: BatchSubscriptionRequest, request: Request):
        user = require_user(request)
        try:
            created = engine.strategies.subscribe_many(
                user["account_id"],
                body.kind,
                body.symbols,
                body.instance_prefix,
            )
        except SubscriptionBatchConflict as exc:
            raise HTTPException(
                409,
                {
                    "code": "SUBSCRIPTION_BATCH_CONFLICT",
                    "existing": exc.existing,
                },
            ) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {
            "created": created,
            "count": len(created),
            "symbols": [row["symbol"] for row in created],
        }

    @app.get("/api/subscriptions")
    def subscriptions(request: Request):
        user = require_user(request)
        return engine.snapshot(account_id=user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/start")
    def start_subscription(strategy_instance_id: str, request: Request):
        user = require_strategy_owner(request, strategy_instance_id)
        engine.strategies.set_enabled(user["account_id"], strategy_instance_id, True)
        return engine.snapshot(user["account_id"])["subscriptions"]

    @app.post("/api/subscriptions/{strategy_instance_id}/stop")
    def stop_subscription(strategy_instance_id: str, request: Request):
        user = require_strategy_owner(request, strategy_instance_id)
        engine.strategies.set_enabled(user["account_id"], strategy_instance_id, False)
        return engine.snapshot(user["account_id"])["subscriptions"]

    @app.post("/api/demo")
    def demo(request: Request):
        user = require_operator(request)
        if not engine.demo_enabled:
            raise HTTPException(403, "replay demo is disabled for this database")
        # A restart begins RECOVERING. A deliberate replay action may perform
        # the required authoritative broker check first, but it must never
        # bypass an actual drift/uncertainty result.
        if engine.risk.state == "RECOVERING" and not engine.reliability.reconcile():
            raise HTTPException(409, "reconciliation required")
        engine.demo(user["account_id"])
        engine.start_replay_stream()
        return account_response(user, engine.snapshot(user["account_id"]))

    @app.put("/api/risk/policies/{strategy}")
    def policy(strategy: str, body: PolicyRequest, request: Request):
        require_strategy_owner(request, strategy)
        engine.risk.policies[strategy] = RiskPolicy(**body.model_dump())
        return financial_json(engine.risk.policies[strategy])

    @app.put("/api/risk/strategies/{strategy}")
    def strategy_control(strategy: str, body: StrategyStateRequest, request: Request):
        require_strategy_owner(request, strategy)
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

    @app.get("/api/risk/account-policy")
    def get_account_policy(request: Request):
        user = require_user(request)
        return engine.risk.account_policies.get(user["account_id"]).__dict__

    @app.put("/api/risk/account-policy")
    def set_account_policy(body: AccountPolicyRequest, request: Request):
        user = require_user(request)
        policy = AccountRiskPolicy(**body.model_dump())
        return engine.risk.account_policies.set(user["account_id"], policy).__dict__

    @app.get("/api/safety-proof")
    def safety_proof(request: Request):
        user = require_user(request)
        return account_response(user, engine.safety_proof.build())

    @app.get("/api/reconciliation")
    def reconciliation_center(request: Request):
        user = require_user(request)
        return account_response(user, engine.reliability.reconciliation_center())

    @app.get("/api/provider-readiness")
    def provider_readiness(request: Request):
        user = require_user(request)
        return account_response(user, engine.provider_readiness(user["account_id"]))

    @app.get("/api/traces")
    def recent_traces(request: Request, limit: int = Query(20, ge=1, le=100)):
        user = require_user(request)
        return account_response(
            user, engine.traces.recent_traces(limit, user["account_id"])
        )

    @app.get("/api/traces/{trace_id}")
    def trace(trace_id: str, request: Request):
        user = require_user(request)
        try:
            return account_response(
                user, engine.traces.trace(trace_id, user["account_id"])
            )
        except PermissionError:
            raise HTTPException(403, "trace belongs to another account") from None

    @app.get("/api/metrics")
    def metrics(request: Request):
        user = require_user(request)
        return account_response(user, engine.metrics.snapshot())

    @app.post("/api/safety-bench/run")
    def run_safety_bench(body: SafetyBenchRequest, request: Request):
        user = require_operator(request)
        engine.require_offline_demo()
        return account_response(user, engine.safety_bench.run(body.iterations))

    @app.get("/api/safety-bench/latest")
    def latest_safety_bench(request: Request):
        user = require_user(request)
        result = engine.safety_bench.latest()
        if result is None:
            raise HTTPException(404, "no completed SafetyBench run")
        return account_response(user, result)

    @app.get("/api/failure-lab/scenarios")
    def failure_lab_scenarios(request: Request):
        require_user(request)
        return {
            "scenarios": sorted(SCENARIOS),
            "details": SCENARIO_METADATA,
        }

    @app.post("/api/failure-lab/{scenario}")
    async def failure_lab(scenario: str, request: Request):
        user = require_operator(request)
        params = {}
        try:
            body = await request.body()
            if body:
                params = json.loads(body.decode("utf-8"))
        except Exception:
            params = {}
        sandbox = None
        target = engine
        if not engine.demo_enabled:
            # Live 021 state is never mutated by synthetic scenarios. Run the
            # same FailureLab contract against a fresh in-memory mock sandbox.
            sandbox = Platform(":memory:", broker=MockBrokerAdapter(), demo_enabled=True)
            target = sandbox
        try:
            result = FailureLab(target).run(scenario, params=params)
            if sandbox is not None:
                result["execution_context"] = "ISOLATED_OFFLINE_SANDBOX"
                result["live_provider_untouched"] = True
            return result if sandbox is not None else account_response(user, result)
        finally:
            if sandbox is not None:
                sandbox.close()

    @app.post("/api/reconcile")
    def reconcile(request: Request):
        user = require_operator(request)
        return account_response(
            user,
            {
                "reconciled": engine.reliability.reconcile(),
                "state": engine.snapshot(user["account_id"]),
            },
        )

    @app.post("/api/resume")
    def resume(request: Request):
        user = require_operator(request)
        engine.reliability.resume()
        return account_response(user, engine.snapshot(user["account_id"]))

    @app.post("/api/reduce-only")
    def reduce_only(request: Request):
        user = require_operator(request)
        engine.reliability.resume(reduce_only=True)
        return account_response(user, engine.snapshot(user["account_id"]))

    @app.post("/api/kill/reset")
    def reset_kill(request: Request):
        user = require_operator(request)
        engine.reliability.reset_kill()
        return account_response(user, engine.snapshot(user["account_id"]))

    @app.post("/api/kill")
    def kill(request: Request):
        user = require_operator(request)
        return account_response(user, engine.kill())

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa_fallback(spa_path: str, request: Request):
        if spa_path == "api" or spa_path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        if not engine.auth.verify_token(request_token(request)):
            return RedirectResponse("/login", status_code=303)
        if not (frontend_dist / "index.html").is_file():
            raise HTTPException(
                503, "React build missing; run npm --prefix frontend run build"
            )
        return FileResponse(frontend_dist / "index.html")

    return app

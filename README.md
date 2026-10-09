# AlgoShield

Current team workflow: [execution plan](docs/TEAM_EXECUTION_PLAN.md), [validation](docs/TESTING.md). Team members can directly push branches with repository write permission; PRs are optional. Integrate tested checkpoints on dev; only promote validated commits to main after successful CI. Never force-push or bypass server rules.

Safety control plane for untrusted trading strategies, built for SYRUS 7.0 FinTech PS-06.

`tick -> 1m/5m candle -> strategy -> intent -> risk reservation -> order manager -> broker -> fill ledger -> reconciliation -> dashboard`

## Official 021-03 reference rules and status

The canonical wire source is [docs/021/OFFICIAL_API_CONTRACT.md](docs/021/OFFICIAL_API_CONTRACT.md); implementation order is [docs/021/INTEGRATION_BLUEPRINT.md](docs/021/INTEGRATION_BLUEPRINT.md). The official API is **DOCUMENTED**. Authenticated read-only REST, ephemeral-key, market-WebSocket and order-WebSocket handshakes were live-verified on 2026-10-09; no sandbox order was placed. Price/quantity normalization and TC1/TC3/TC4/TC8 decoding are fixture-verified. Live writes remain operator-controlled, and order-WebSocket trade notices never become fills without REST `tradeId` evidence.

The three 021-03 reference strategies are:

1. `time_0915_1515`: one fresh-evidence, risk-approved INTRADAY entry only during 09:15 Asia/Kolkata; no late catch-up. At/after 15:15 it may emit one reducing intent for the strategy's fill-attributed residual only when account square-off evidence provides a compatible bound.
2. `open_1pct_tp5_sl5`: one directional entry per session when LTP crosses 1% from the verified official daily open. After actual fills, application-managed TP/SL is 5% from fill-derived WAP and sizes only the residual; it is a normal intent through RiskGateway, never a broker-side SL shortcut.
3. `momentum`: existing own strategy using 1-minute candles, 3/5 EMA warm-up/crossover, quantity 1, and central risk limits. A 15:15 custom-strategy exit is not yet integrated, so this is not claimed live-complete.

The first two policies are registered in normal subscription/runtime composition and route their canonical intents through RiskGateway and OrderManager. Their deterministic runtime path is fixture-verified. Live execution and reconciliation remain blocked until 021 can attest a complete broker evidence horizon; today's documented lists are not treated as cross-day truth.

## Start here

Read [Project Truth](docs/PROJECT_TRUTH.md), [Implementation Delta](docs/IMPLEMENTATION_DELTA.md), [requirement traceability](docs/REQUIREMENTS_TRACEABILITY.md), then [research decisions](docs/RESEARCH_DECISIONS.md). See [current verification](docs/progress/INTEGRATION.md) and [operator provisioning](docs/SECURITY_OPERATIONS.md).

## Run locally

Python 3.11+ required. From the repository root (PowerShell or a POSIX shell):

```sh
python -m venv .venv
# Windows PowerShell:
.venv/Scripts/Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -e ".[dev]"
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Open http://127.0.0.1:8000, register or sign in, explicitly provision the intended operator as described below, and click **Run replay** from that operator session. Registration assigns a trading account ID from the authenticated username; the dashboard never asks users to type or choose it. Four built-in strategies consume completed candles concurrently in one serialized event loop: a 3/5 EMA crossover, five-period mean reversion, a 5-minute range breakout and 14-period RSI reversal. The Strategies page accepts one or many stock symbols and atomically creates one independent single-symbol strategy instance for each; each instance retains its own warm-up, failure state, risk, position and P&L. The demo stops after replay and displays actual signals, orders, unique fills, charges, virtual positions, market-data counters and audit events. The dashboard supports durable per-strategy start/stop controls. Click **Kill all** to cancel, flatten and verify. API docs: http://127.0.0.1:8000/docs.

The Strategies page also provides an explicit **Auto mode**. It scans a bounded,
catalogue-derived cash-equity universe, compares momentum, breakout and
mean-reversion opportunities, and selects the strongest qualified stock and
policy. It creates ordinary one-symbol strategy instances only when needed and
emits quantity-one long entries plus take-profit, stop-loss or reversal exits.
It reports BUY, SELL or HOLD, the selected policy, and the subsequent risk result.
It never calls the broker directly,
never bypasses reconciliation/risk, starts disabled after every process restart,
and does not guarantee profit. Stopping it does not implicitly liquidate existing
positions. Configure its bounded policy with the
`ALGOSHIELD_AUTO_*` placeholders in `.env.example`.

```sh
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
```

For frontend development, run FastAPI on port 8000 and `npm --prefix frontend run dev` in a second terminal. Vite proxies `/api`, `/health`, and `/api/stream/ws`; application code always uses relative backend URLs. Vite is development-only. FastAPI serves `frontend/dist` with SPA fallback in production, including direct refreshes such as `/strategies` and `/failure-lab`.

Docker alternative: `docker build -t algoshield .`, then `docker run --rm -p 8000:8000 -v algoshield-data:/app/data algoshield`.

### Local PostgreSQL

When a local PostgreSQL server and peer-authenticated development role are available, create isolated application and test databases and apply the reviewed additive migrations with:

```sh
sh scripts/setup_local_postgres.sh
```

Use `DATABASE_URL=postgresql:///algoshield_local` for the application. Run the rollback-only PostgreSQL integration test with `ALGOSHIELD_TEST_DATABASE_URL=postgresql:///algoshield_test python -m pytest -q tests/test_postgres_integration.py`. Database names can be overridden with `ALGOSHIELD_LOCAL_DATABASE` and `ALGOSHIELD_LOCAL_TEST_DATABASE`; the script never drops databases or resets data. Keep machine-specific URLs in ignored `.env.local`, not tracked configuration. For complete local HTTP simulation, run `uvicorn backend.broker.mock_api:app --host 127.0.0.1 --port 9001`, set `MOCK_BROKER_URL=http://127.0.0.1:9001`, then start the control plane. A loopback mock URL enables replay with isolated local PostgreSQL; remote URLs never enable seeded replay.

## Current implementation and limits

`DEMO_PAPER` is the explicit backend operating mode for the isolated offline replay path. It uses the real risk gateway, order manager, mock broker, fill ingestion and Decimal ledger; it never submits to 021. The compatibility `mode` field continues to report `MOCK / REPLAY`, while `/api/state.operating_mode` reports `DEMO_PAPER`. Authenticated `GET /api/instruments` exposes the bounded demo catalogue (search with `q`); rows are replay/display instruments, not live 021 identities. Mock/replay remains the fully verified execution mode. **021 read transport is live-verified; order writes are not.** FastAPI serves the compiled React/Vite SPA and pushes authenticated account-scoped snapshots through one WebSocket connection. SQLite offline schema v14 stores accounts, durable subscription enablement, policies, marks, approved orders, fills, dispatch/correlation evidence, provider-order mappings, closed candles and safety/audit state. Strategy callback failures quarantine only the affected subscription; risk policies and live budgets are durable; Decimal amounts are serialized as strings. Start with `RECOVERING`; explicit reconciliation and resume are required. Configure the DB with `ALGOSHIELD_DB` (default `data/platform.db`); leave `DATABASE_URL` empty for SQLite or explicitly set an approved PostgreSQL URL. Process environment overrides `.env.local`, which overrides `.env`; a supplied PostgreSQL URL fails on connection/migration errors and never falls back to SQLite. Never put real values in tracked examples.

Cookie and proxy policy: local HTTP uses `ALGOSHIELD_SECURE_COOKIE=false`. Set it to `true` only behind approved TLS, with an exact `ALGOSHIELD_TRUSTED_ORIGINS` allowlist for the deployed browser origin. Run one Uvicorn worker with `--no-proxy-headers`; do not infer client identity or Origin trust from forwarded headers. Cookie and explicit `Authorization: Bearer` authentication are supported for telemetry; URL query tokens are rejected.

Offline SQLite mode persists external mock evidence separately in `<database>.broker.json`, using atomic file replacement. Restart loads both independent stores, keeps trading RECOVERING, and requires reconciliation/explicit resume. An explicitly injected fresh broker against existing local history still fails closed. Never discard execution history to pretend recovery succeeded. The JSON file is a mock fixture only, not an assumed 021 persistence format.

The dashboard exposes candles, orders/fills/P&L and compact backend-derived safety indicators. Raw fail-closed evidence stays out of the main strategy workflow. Failure Lab supports partial/rejected orders, pending-position/rate rejections, duplicate/conflicting/missed fills, ambiguous acceptance, disconnect/reconnect, stale feed, injected external drift/recovery and partial-fill kill. Conflicts, disconnection and ambiguity leave trading closed; use Reconcile to inspect recovery, then explicit Resume. Stale-feed injection requires a new tick/replay before exposure. Failure injection remains refused against PostgreSQL; replay is allowed only with an explicitly configured loopback HTTP mock broker and an isolated local database.

Kill latches durably and converges through verified cancellation/fill evidence and attributed exits, with bounded broker waits and a nine-second default deadline. SUCCESS means verified flat under ten seconds; SAFE_LATE is verified but misses the SLA; FAILED retains uncertainty. A timed-out external operation may complete later; it is never blindly retried. Verified kill reset requires no open orders and zero broker/virtual positions, leaves STOPPED, and retains the historical certificate. Fresh broker evidence is required within five seconds and LIVE market event/receive evidence within fifteen seconds; offline REPLAY is labeled and uses receive freshness.

This is a local development tool, not a production service. It has a basic durable local login/session boundary and authenticated local WebSocket telemetry, but no production identity provider or arbitrary strategy upload. The documented 021 REST/auth transport, durable order mapping, sampled market provider, reconnect workers and telemetry are implemented behind an explicit server-side feature flag. Credentials, charges, corrections, complete history and live kill semantics are not claimed. Failure Lab and SafetyBench run only in a fresh isolated mock sandbox even while the primary provider is 021; they never inject fake events into 021 state. No profitability or live kill SLA claim is made.

Provider selection is explicit: when `ALGOSHIELD_021_ENABLED=true`, 021 is the primary market/broker provider and `ALGOSHIELD_MARKET_DATA_PROVIDER` must be `021` (or omitted). The dashboard labels it `021 LIVE / REAL MARKET DATA`. A failed 021 connection fails closed; it never triggers automatic fallback, source mixing, backfill or trading resume. To use Yahoo as the fallback, stop the process and start a fresh mock-broker timeline with `ALGOSHIELD_021_ENABLED=false`, `ALGOSHIELD_MARKET_DATA_PROVIDER=yahoo`, and the `yahoo` dependency extra installed. The default with 021 disabled and no explicit provider is `MOCK / REPLAY`. The Market Data page's Source card, `market_data.provider`, `market_data.source`, `market_data.label`, and candle `data_source` are the authoritative indicators.

The 021 market universe is dynamic: enabled strategy symbols, active auto-mode
scan candidates, open exposure/order symbols, plus optional pinned
`ALGOSHIELD_021_SYMBOLS`. Without any of these the feed remains idle. Auto mode
uses a configurable bounded, evenly sampled cash-equity subset rather than an
unbounded whole-catalogue socket. Universe changes fail closed, rebuild bounded
sockets, obtain fresh ephemeral keys, and require reconciliation plus explicit
resume. Configure timestamp, broker deadlines and auto policy using the
placeholder-only settings documented in `.env.example`.

PowerShell clean-start Yahoo fallback (set the database path to an isolated SQLite file appropriate for the run):

```powershell
$env:ALGOSHIELD_021_ENABLED="false"
$env:ALGOSHIELD_MARKET_DATA_PROVIDER="yahoo"
$env:ALGOSHIELD_YAHOO_SYMBOLS="TCS.NS,INFY.NS"
$env:ALGOSHIELD_DB="data/yahoo-fallback.db"
.\.venv\Scripts\python.exe -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
```

## Repository map

- `AGENTS.md`: canonical engineering rules and reading order.
- `backend/shared`: canonical contracts and transactional store.
- `backend/accounting`: Member 1, fill-derived Decimal accounting.
- `backend/broker`, `backend/execution`: Member 2, mock adapter and order lifecycle.
- `backend/risk`, `backend/reliability`: Member 3, atomic reservations, recovery, verified kill.
- `backend/market_data`, `backend/strategies`: Member 4, replay, candles, subscriptions and signals.
- `backend/platform.py`, `backend/api.py`: composition and API; frontend panels follow module ownership.
- `frontend/src`: modular React routes, session context, single telemetry provider, API client, components and responsive styles.
- `tests/test_safety.py`: deterministic unit and integration foundation.
- `tests/test_member4.py`: market-data, strategy, subscription and dashboard coverage.
- `docs/IMPLEMENTATION_DELTA.md`: active gap-first plan; `docs/PHASE_PLAN.md` preserves historical phases.

Read the [architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md), [contracts](docs/CONTRACTS.md), [safety invariants](docs/SAFETY_INVARIANTS.md) and [021 unknowns](docs/021_API_UNKNOWN.md) before extending the system.

## Neon and database workflow
Requested project: `muddy-tooth-14996153`, branch: `production`. Intended linkage is not proof of authenticated access. See `docs/progress/INTEGRATION.md` for actual setup status.

```sh
npm install
npm run check
neon login
neon skills -y
neon mcp -y
neon link --project-id muddy-tooth-14996153 --branch production -y
neon config init
python -m backend.shared.migrate
# After reviewing existing schema and the additive migration:
python -m backend.shared.migrate --apply
neon deploy
```

On PowerShell where execution policy blocks npm/neon scripts, use `npm.cmd` and `neon.cmd`. Global install: `npm.cmd i -g neon@latest`. Keep existing requested neon.ts when config init offers a scaffold. CLI linking may write credentials into ignored `.env.local`/`.env`; never print or commit them.

`DATABASE_URL` enables psycopg PostgreSQL persistence. Migration runner first inspects table names; `--apply` creates only dedicated `algoshield` schema/tables, records checksums, and refuses unmanaged collisions/changed history. Startup verifies migrations and takes an advisory ownership lock; connection failure does not silently switch databases. Run one worker. No implicit schema creation on startup. Never seed `/api/demo` data into production. Use the SQLite fallback or a separately authorized isolated dev database for replay/tests. An optional rollback-only integration test uses `ALGOSHIELD_TEST_DATABASE_URL`; never set it to production.

`neon deploy` publishes the requested hello function/auth/private uploads policy; it does **not** deploy the Python trading service. Neon Auth configuration also does not automatically secure the existing FastAPI endpoints.

If Windows denies access to a previous pytest temp directory, use a new directory under ignored `data/`, for example `python -m pytest -q -p no:cacheprovider --basetemp=data/new-test-run`. Do not change safety assertions to work around filesystem permissions.

## Explicit operator provisioning

Register the intended username normally. Stop the backend, then run:

```powershell
python -m backend.shared.provision_operator --sqlite-path data/platform.db --username alice
# Revoke an existing grant:
python -m backend.shared.provision_operator --sqlite-path data/platform.db --username alice --revoke
```

Restart the backend and sign in. The command requires an existing offline SQLite file and user, ignores DATABASE_URL, and records grants/revocations durably. It never assigns first-user privileges or accepts public promotion. All global kill/resume/reconcile, broker controls, replay, market overrides, account administration, and mock fault/benchmark mutations require an operator. Ordinary users retain own-account controls and scoped views. PostgreSQL migration 011 is additive and not applied remotely; isolated PostgreSQL validation/provisioning remains blocked here. See [security operations](docs/SECURITY_OPERATIONS.md).

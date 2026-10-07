# AlgoShield

Safety control plane for untrusted trading strategies, built for SYRUS 7.0 FinTech PS-06.

`tick -> 1m/5m candle -> strategy -> intent -> risk reservation -> order manager -> broker -> fill ledger -> reconciliation -> dashboard`

## Run locally

Python 3.11+ required. From the repository root (PowerShell or a POSIX shell):

```sh
python -m venv .venv
# Windows PowerShell:
.venv/Scripts/Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and click **Run replay**. Three built-in strategies consume completed candles concurrently in one serialized event loop: a 3/5 EMA crossover, five-period mean reversion and a 5-minute range breakout. The demo stops after replay and displays actual signals, orders, unique fills, charges, virtual positions, market-data counters and audit events. The dashboard also supports account creation, strategy subscription and durable per-strategy start/stop controls. Click **Kill all** to cancel, flatten and verify. API docs: http://127.0.0.1:8000/docs.

```sh
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

Docker alternative: `docker build -t algoshield .`, then `docker run --rm -p 8000:8000 -v algoshield-data:/app/data algoshield`.

## Current implementation and limits

Mock/replay bootstrap only; **021 sandbox integration remains mandatory and incomplete**. FastAPI serves a responsive static dashboard with two-second state polling. SQLite offline schema v2 stores accounts, durable subscription enablement, approved orders, fills and audit events. Strategy callback failures quarantine only the affected subscription; risk rejects stopped strategies. Decimal values remain exact in persistence, although FastAPI currently emits position Decimals as JSON numbers. Start with `RECOVERING`; explicit reconciliation and resume are required. Configure the DB with `ALGOSHIELD_DB` (default `data/platform.db`); copy `.env.example` to ignored `.env.local` if needed. Process environment overrides `.env.local`, which overrides `.env`. Never put real values in tracked examples.

Mock broker state is external to platform state and currently lives in memory. Recreating the server with an existing local DB and a fresh broker correctly fails reconciliation. For a fresh demo use a new DB path; do not erase execution history to pretend recovery succeeded. Restart tests retain an external mock broker while recreating the platform. A durable broker fixture or documented 021 history is the next integration step.

This is a local development tool, not a production service: no authentication, arbitrary strategy upload, broker modification, live feeds or WebSocket transport yet. Only market orders are implemented. Demo charges are **synthetic 0.01 per fill**, not an Indian fee schedule. No profitability or live kill SLA claim is made.

## Repository map

- `AGENTS.md`: canonical engineering rules and reading order.
- `backend/shared`: canonical contracts and transactional store.
- `backend/accounting`: Member 1, fill-derived Decimal accounting.
- `backend/broker`, `backend/execution`: Member 2, mock adapter and order lifecycle.
- `backend/risk`, `backend/reliability`: Member 3, atomic reservations, recovery, verified kill.
- `backend/market_data`, `backend/strategies`: Member 4, replay, candles, subscriptions and signals.
- `backend/platform.py`, `backend/api.py`: composition and API; frontend panels follow module ownership.
- `tests/test_safety.py`: deterministic unit and integration foundation.
- `tests/test_member4.py`: market-data, strategy, subscription and dashboard coverage.
- `docs/PHASE_PLAN.md`: current completion status and remaining mandatory work.

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

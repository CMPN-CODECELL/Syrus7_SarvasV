# Architecture

Current operational boundaries and dependency gates are in [TEAM_EXECUTION_PLAN](TEAM_EXECUTION_PLAN.md). Member 1 owns persistence/accounting, Member 2 provider contracts/execution, Member 3 shared security/reliability integration, Member 4 frontend/feed consumers. SQLite mock evidence does not prove PostgreSQL or live-provider behavior.

## Goal and flow

Untrusted strategies express intent. Platform services own execution authority. Fills create financial truth; broker snapshots verify external truth. One deployable Python/FastAPI modular monolith runs a serialized control plane, Neon PostgreSQL durable store (SQLite offline fallback), and a React SPA driven by authenticated backend telemetry. PostgreSQL is configured through the centralized Store boundary and versioned additive migrations; Redis is unnecessary now. A database advisory ownership lock rejects a second backend process, but multi-process execution is still unsupported.

`ReplayMarketDataProvider -> CandleBuilder -> StrategyRuntime -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter -> Fill -> Ledger -> Reliability -> API/dashboard`

Composition lives in `backend/platform.py`; domain modules import `backend/shared/contracts.py`, never raw 021 payloads. Runtime receives candles and emits intents, with no broker reference. Built-in strategies are trusted code implementations representing untrusted decision logic; accepting arbitrary executable user code would require process isolation and capability restrictions.

Member 4 runtime uses completed 1-minute candles for 3/5 EMA crossover, five-period mean reversion and 14-period RSI reversal, and completed 5-minute candles for previous-range breakout. Indicator state is process-local and requires a complete warm-up after restart or explicit re-enable. Subscription enablement is durable; a callback exception atomically disables only that subscription and records a sanitized audit event. The risk gateway independently rejects intents from stopped subscriptions. Recent signal and callback evidence is restored from durable audit history for the dashboard. API money and price fields are exact decimal strings rather than binary JSON numbers.

Multi-stock strategy execution is orchestration over the existing model: one strategy instance still owns exactly one symbol. `POST /api/subscriptions/batch` validates and normalizes up to 20 symbols, preflights every deterministic instance ID, and inserts all single-symbol rows plus audit evidence in one transaction. A collision or validation failure creates zero rows. Indicator state, callback quarantine, risk, execution attribution, accounting and start/stop control therefore remain isolated per generated instance. Replay derives its symbol set from enabled subscription rows and needs no separate multi-symbol strategy object.

The dashboard route requires a valid HttpOnly local session cookie. Registration assigns the durable trading account identity; strategy subscription/start/stop endpoints derive account ownership from that verified session and reject caller-supplied account IDs. This is the bootstrap identity boundary, not a claim of Neon Auth or production authentication readiness.

## Frontend boundary

The React/Vite application lives in `frontend/`. `AuthProvider` owns session discovery, `TelemetryProvider` owns the single authenticated WebSocket plus bounded reconnect and snapshot fallback, and the shared API client always includes session credentials. React renders backend values and sends commands; it performs no risk, P&L, reconciliation, or kill-success calculation. Vite proxies backend routes only during development. Production contains no Node server: a multi-stage image builds static assets and FastAPI serves `frontend/dist`, with API/WebSocket routes registered before SPA fallback.

## Execution and concurrency

A process-wide reentrant lock serializes local risk checks, durable reservations, dispatch start, fill processing and kill gate changes. Network waits occur outside it. Run **one backend worker**. A reservation is committed before submission; dispatch is durably UNKNOWN before external work starts. One bounded broker session allows only one active call. Timeout retains uncertainty and blocks further mutation until a settled complete snapshot is verified. No blind submission retry. Kill signals the admission gate before waiting for the controller and uses a nine-second total deadline.

Check worst-case endpoints independently: `q + pending buys + new buys` and `q - pending sells - new sells`. Both must have absolute value <= max position. Pending buys and sells do not offset. Rejections/cancel confirmations release remaining reservation; partial fills transfer executed exposure into the ledger. Rate limits count admitted submissions over `(now-60, now]`, including broker rejections; emergency exits have separately audited authority.

## Accounting

Append-only unique fill ledger with Decimal prices/charges. Weighted average entry, partial exit, reversal, realized and marked unrealized P&L are replayed from executions ordered by `(timestamp, fill_id)`. Conflicting duplicate IDs block trading. Every fill must match its canonical order's account, strategy, symbol and side. Average price resets at flat. Net P&L = realized + unrealized - charges.

Daily loss decision: session realized less session charges plus current unrealized, calendar day in Asia/Kolkata. Session cutoffs and overnight mark policy require sponsor confirmation. Risk-owned mark persistence restores cached prices without changing accounting formulas. Broker verification older than 5s or LIVE event/receive evidence older than 15s blocks new exposure; labeled offline REPLAY uses receive freshness. Live adapters must supply bounded fresh snapshot/feed evidence.

## Reconciliation and restart

Start RECOVERING with runtime disabled. Load policies/halts, orders/fills, marks and kill latch/certificate. Require complete fresh broker snapshots; compare order identity/status, unique fill history, cumulative quantities and account positions independently. Replay missing attributed fills through accounting. Missing/unknown/conflicting history or unexplained external positions remain DRIFTED/UNCERTAIN with durable reasons. No synthetic balancing adjustments. Success leaves STOPPED (KILLED if latched); explicit resume reconciles again. REDUCE_ONLY admits only non-reversing closes without pending strategy/symbol exposure.

## Kill protocol

Close gate -> disable callbacks -> cancel open broker orders -> reconcile executions -> authorize attributed emergency exits -> ingest actual fills -> reconcile -> verify no open broker orders, no broker positions, and flat virtual positions. Latch/certificate persist across processes; explicit reset requires fresh verified flat/no-order evidence. SUCCESS requires verified state in <10 seconds; SAFE_LATE records safe completion outside target; FAILED leaves gate uncertain. Certification includes duration and final evidence.

Opposing virtual positions can externally net to zero while still carrying strategy exposure. Bootstrap closes each strategy through broker executions; this may temporarily increase broker net exposure. Do not fabricate cross-strategy fills. Sponsor must confirm whether only net account flatness is required and whether shorting/close sequencing is supported. Live close sequencing remains a release blocker; the durable mock kill latch is already implemented and regression-tested.

## Failure handling

| Failure | Bootstrap response / next work |
|---|---|
| Strategy error | Faulted subscription is durably stopped and audited; other callbacks continue |
| Partial/rejected order | Filled quantity only; release terminal remainder |
| Duplicate fill | Same payload ignored, conflicting payload blocks |
| Missed/out-of-order fills | Snapshot replay; deterministic timestamp/ID accounting order |
| Timeout/disconnect | UNKNOWN reservation, gate uncertain, snapshot reconciliation |
| Duplicate/late tick | Bounded symbol-scoped dedupe; duplicates cannot update marks, while late unique ticks reject, disable trading and leave sanitized durable evidence |
| Concurrent intents | Check/reserve/dispatch serialized |
| Drift/manual position | Fail closed; external position model pending |
| Restart | Recover durable local state; no automatic resume |
| Kill race | Shared lock; no ordinary dispatch after gate closure |

The Python lock does not provide multi-process safety; PostgreSQL adds a session advisory ownership lock to reject duplicate control planes. Real broker adapter contract tests, deadlines, durable health/latches, feed freshness and authenticated account boundaries must land before live execution.

## USP operational evidence layer

The platform projects a read-only evidence layer over the existing control plane. `SafetyProofService` evaluates invariants I1-I10 from durable orders, decisions, fills, positions, reconciliation freshness and kill evidence; it never mutates trading state and uses `UNKNOWN` when proof is unavailable. Account net/gross limits and LIMIT-price deviation checks execute inside the serialized risk reservation boundary. Additive audit correlation supports server-built execution traces. `MetricsRegistry` keeps bounded process-local samples and is isolated from safety decisions.

Failure Lab V2 and SafetyBench remain SQLite/mock-only; SafetyBench creates a fresh platform per case and persists only completed summaries. The reconciliation center reports local/broker deltas and recovered canonical fill IDs without synthetic balancing fills. Kill certificates add protocol-stage timing and final evidence without changing SUCCESS/SAFE_LATE/FAILED semantics. Authenticated snapshots scope subscriptions, positions, orders, fills, signals, decisions and traces to the current account; strategy/order mutations also verify ownership.

## Account presentation and operator authority (DEC-026)

DEC-027 adds an explicit configured Origin boundary before unsafe HTTP/cookie
WebSocket access, versioned PBKDF2 with safe legacy upgrade, bounded local login
throttling and outcome-only audits. See SECURITY_OPERATIONS for transport/proxy
policy. Broker normalized identity and unsupported correction/fee capabilities
are specified in CONTRACTS. No ledger, candle or persistence schema was replaced.

AuthService joins durable operator_grants during local session validation. Global controls require that grant before invoking platform operations; own-strategy/account/order controls retain ownership checks. AccountResponseScope projects copies after authoritative calculations and is applied to scoped snapshots (including SSE/WS), action responses, proof, reconciliation, traces and broker evidence. It removes foreign attributed records/references, scopes historical counts from verified account breakdowns, and handles nested JSON audit payloads. It preserves global verdicts and certificate timing/status. Internal ledger/reconciliation inputs remain global. Offline provisioning is documented in SECURITY_OPERATIONS.md; production identity and real PostgreSQL validation are still incomplete.

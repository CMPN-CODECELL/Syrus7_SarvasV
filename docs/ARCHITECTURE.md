# Architecture

## Goal and flow

Untrusted strategies express intent. Platform services own execution authority. Fills create financial truth; broker snapshots verify external truth. One deployable Python/FastAPI modular monolith runs a serialized control plane, Neon PostgreSQL durable store (SQLite offline fallback) and static polling dashboard. PostgreSQL is configured through the centralized Store boundary and versioned additive migrations; Redis is unnecessary now. A database advisory ownership lock rejects a second backend process, but multi-process execution is still unsupported.

`ReplayMarketDataProvider -> CandleBuilder -> StrategyRuntime -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter -> Fill -> Ledger -> Reliability -> API/dashboard`

Composition lives in `backend/platform.py`; domain modules import `backend/shared/contracts.py`, never raw 021 payloads. Runtime receives candles and emits intents, with no broker reference. Built-in strategies are trusted code implementations representing untrusted decision logic; accepting arbitrary executable user code would require process isolation and capability restrictions.

Member 4 runtime uses completed 1-minute candles for 3/5 EMA crossover and five-period mean reversion, and completed 5-minute candles for previous-range breakout. Indicator state is process-local and warms up after restart. Subscription enablement is durable; a callback exception atomically disables only that subscription and records a sanitized audit event. The risk gateway independently rejects intents from stopped subscriptions. Recent signal and callback evidence is restored from durable audit history for the dashboard.

## Execution and concurrency

A single process-wide reentrant lock serializes risk checks, durable reservations, dispatch, fill processing and kill gate changes. Run **one backend worker**. A reservation is an order row committed before broker submission. UNKNOWN submissions retain exposure and stop the gate; do not blindly retry. Reconcile by client identity/history through the adapter. Real integration must add bounded network deadlines so a broker call cannot indefinitely delay kill.

Check worst-case endpoints independently: `q + pending buys + new buys` and `q - pending sells - new sells`. Both must have absolute value <= max position. Pending buys and sells do not offset. Rejections/cancel confirmations release remaining reservation; partial fills transfer executed exposure into the ledger. Rate limits count admitted submissions over `(now-60, now]`, including broker rejections; emergency exits have separately audited authority.

## Accounting

Append-only unique fill ledger with Decimal prices/charges. Weighted average entry, partial exit, reversal, realized and marked unrealized P&L are replayed from executions ordered by `(timestamp, fill_id)`. Conflicting duplicate IDs block trading. Every fill must match its canonical order's account, strategy, symbol and side. Average price resets at flat. Net P&L = realized + unrealized - charges.

Daily loss decision: session realized less session charges plus current unrealized, calendar day in Asia/Kolkata. Session cutoffs and overnight mark policy require sponsor confirmation. Demo marks come from replay ticks; live feed freshness gating is not implemented yet and must precede live trading.

## Reconciliation and restart

Start RECOVERING with runtime disabled. Load persisted accounts/subscriptions/orders/fills. Fetch canonical external snapshot, replay missing attributed fills through accounting, compare order identity and cumulative executed quantity, then compare aggregate virtual positions to broker positions. Missing orders, unknown attribution or unexplained external positions remain DRIFTED/UNCERTAIN. No synthetic fill or balancing adjustment repairs an unexplained difference. Success leaves STOPPED; explicit resume reconciles again before RUNNING. Automatic reconnect monitoring remains phase 2 work.

## Kill protocol

Close gate -> disable callbacks -> cancel open broker orders -> reconcile executions -> authorize attributed emergency exits -> ingest actual fills -> reconcile -> verify no open broker orders, no broker positions, and flat virtual positions. Kill is latched in process. SUCCESS requires verified state in <10 seconds; SAFE_LATE records safe completion outside target; FAILED leaves gate uncertain. Certification includes duration and final evidence.

Opposing virtual positions can externally net to zero while still carrying strategy exposure. Bootstrap closes each strategy through broker executions; this may temporarily increase broker net exposure. Do not fabricate cross-strategy fills. Sponsor must confirm whether only net account flatness is required and whether shorting/close sequencing is supported. Live close sequencing and durable kill latch are release blockers.

## Failure handling

| Failure | Bootstrap response / next work |
|---|---|
| Strategy error | Faulted subscription is durably stopped and audited; other callbacks continue |
| Partial/rejected order | Filled quantity only; release terminal remainder |
| Duplicate fill | Same payload ignored, conflicting payload blocks |
| Missed/out-of-order fills | Snapshot replay; deterministic timestamp/ID accounting order |
| Timeout/disconnect | UNKNOWN reservation, gate uncertain, snapshot reconciliation |
| Duplicate/late tick | Bounded symbol-scoped dedupe; late unique tick rejects and disables trading |
| Concurrent intents | Check/reserve/dispatch serialized |
| Drift/manual position | Fail closed; external position model pending |
| Restart | Recover durable local state; no automatic resume |
| Kill race | Shared lock; no ordinary dispatch after gate closure |

The Python lock does not provide multi-process safety; PostgreSQL adds a session advisory ownership lock to reject duplicate control planes. Real broker adapter contract tests, deadlines, durable health/latches, feed freshness and authenticated account boundaries must land before live execution.

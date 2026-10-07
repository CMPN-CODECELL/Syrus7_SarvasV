# Architecture

## Goal and flow

Untrusted strategies express intent. Platform services own execution authority. Fills create financial truth; broker snapshots verify external truth. One deployable Python/FastAPI modular monolith runs a serialized control plane, Neon PostgreSQL durable store (SQLite offline fallback) and static polling dashboard. PostgreSQL is configured through the centralized Store boundary and versioned additive migrations; Redis is unnecessary now. A database advisory ownership lock rejects a second backend process, but multi-process execution is still unsupported.

`ReplayMarketDataProvider -> CandleBuilder -> StrategyRuntime -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter -> Fill -> Ledger -> Reliability -> API/dashboard`

Composition lives in `backend/platform.py`; domain modules import `backend/shared/contracts.py`, never raw 021 payloads. Runtime receives candles and emits intents, with no broker reference. Built-in strategies are trusted code implementations representing untrusted decision logic; accepting arbitrary executable user code would require process isolation and capability restrictions.

Member 4 runtime uses completed 1-minute candles for 3/5 EMA crossover and five-period mean reversion, and completed 5-minute candles for previous-range breakout. Indicator state is process-local; the one-minute strategies require five new completed candles after restart or explicit re-enable before they may emit, while breakout requires a prior completed 5-minute range. Subscription enablement is durable; a callback exception atomically disables only that subscription and records a sanitized audit event. The risk gateway independently rejects intents from stopped subscriptions. Recent signal and callback evidence is restored from durable audit history for the dashboard. API money and price fields are exact decimal strings rather than binary JSON numbers.

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

Opposing virtual positions can externally net to zero while still carrying strategy exposure. Bootstrap closes each strategy through broker executions; this may temporarily increase broker net exposure. Do not fabricate cross-strategy fills. Sponsor must confirm whether only net account flatness is required and whether shorting/close sequencing is supported. Live close sequencing and durable kill latch are release blockers.

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

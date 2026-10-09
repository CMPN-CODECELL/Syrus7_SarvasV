# Architectural decisions

These entries record meaningful decisions supported by current repository context, not invented historical dates or git changes. Dates are the recording date. Classification: CONFIRMED_REQUIREMENT, CONFIRMED_021_BEHAVIOR, DESIGN_DECISION, ASSUMPTION, OPEN_QUESTION.

## Evidence and open questions
CONFIRMED_REQUIREMENT: repository PS-06 baseline in REQUIREMENTS.md. Original sponsor statement is absent (PS.md); obtain it without weakening requirements. No CONFIRMED_021_BEHAVIOR exists. Public [021 Carbon page](https://carbon.021.trade/auth?show=signup) does not establish an API contract. Questions remain in 021_API_UNKNOWN.md. Demo charges are ASSUMPTION (synthetic 0.01/fill), never a real fee schedule. Live kill/shorting/overlapping-exit semantics and snapshot completeness remain OPEN_QUESTION.

References: [SQLite isolation](https://www.sqlite.org/isolation.html), [Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html), [Neon config package](https://www.npmjs.com/package/@neon/config), [Neon CLI](https://www.npmjs.com/package/neon). CLI config inspection supports deprecated preview configuration; requested layout is retained.

## DEC-001 ? Modular monolith and small bootstrap stack
Date: 2026-10-07
Status: ACCEPTED

### Context
A four-person hackathon needs a coherent runnable vertical slice.

### Decision
DESIGN_DECISION: One Python/FastAPI backend with isolated packages and static polling UI; one worker.

### Reason
Fewer deployment/race surfaces; language/framework were previously unselected.

### Impact
backend packages, API, frontend, dependency tooling.

### Alternatives
Microservices, Redis and an early UI framework were not needed.

### Reversal
Split services only with measured need and preserved risk/ledger contracts.

## DEC-002 ? Untrusted strategies and centralized execution authority
Date: 2026-10-07
Status: ACCEPTED

### Context
Strategies may spam or fail and must never control broker authority.

### Decision
DESIGN_DECISION: Strategy -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter. Durable reservation precedes dispatch.

### Reason
Makes risk non-bypassable at the service boundary; one lock serializes check/reserve/kill.

### Impact
Strategy runtime, risk, execution and shared contracts.

### Alternatives
Direct broker calls from strategy callbacks are forbidden.

### Reversal
Only explicit sponsor evidence can justify a boundary change; safety tests must remain valid.

## DEC-003 ? Fills and independent virtual ledgers create financial truth
Date: 2026-10-07
Status: ACCEPTED

### Context
Submitted orders, partial fills and opposing strategies differ from actual account exposure.

### Decision
DESIGN_DECISION: Unique attributed immutable fills, Decimal accounting, weighted average entry/exit/reversal; independent strategy ledgers and account aggregation.

### Reason
Exactly-once accounting effect and auditable financial evidence.

### Impact
Ledger, Fill contract, strategy positions/P&L, charges and tests.

### Alternatives
Submitted quantity or fabricated internal crossing fills are rejected.

### Reversal
A new accounting method requires replay-equivalence tests and an explicit migration.

## DEC-004 ? Broker abstraction and deterministic mock/replay
Date: 2026-10-07
Status: ACCEPTED

### Context
Sponsor API contract/credentials are not available.

### Decision
DESIGN_DECISION: Canonical BrokerAdapter/MarketDataProvider contracts; mock/replay runs offline; 021 placeholders raise NotImplementedError.

### Reason
Development and reliability tests remain independent of sponsor availability.

### Impact
Broker, market data, composition and failure fixtures.

### Alternatives
Invented endpoints/auth/statuses/charges are forbidden.

### Reversal
Replace boundary adapters only after authoritative contract fixtures pass.

## DEC-005 ? Fail-closed restart and reconciliation before resume
Date: 2026-10-07
Status: ACCEPTED

### Context
Timeouts, crashes and missed events create uncertain external state.

### Decision
DESIGN_DECISION: Start RECOVERING; replay missing attributed fills and compare orders/fills/positions; successful reconciliation leaves STOPPED and resume is explicit. UNKNOWN reservations are retained.

### Reason
Never infer safe external state from local intent alone.

### Impact
Reliability, execution, durable orders/fills and health API.

### Alternatives
Blind retries, auto-resume and made-up balancing adjustments are rejected.

### Reversal
Any recovery automation must prove complete authoritative snapshots and preserve fail-closed tests.

## DEC-006 ? Verified kill and virtual-position evidence
Date: 2026-10-07
Status: ACCEPTED

### Context
Submitted cancel/flatten commands do not prove the required safe state.

### Decision
DESIGN_DECISION: Gate -> stop -> cancel -> reconcile -> attributed emergency exits -> reconcile -> verify. SUCCESS requires no open orders, zero broker/virtual positions and <10s.

### Reason
Separates emergency requests from observable safe completion.

### Impact
Reliability kill certificate, emergency authorization, audit and UI.

### Alternatives
Fake success and synthetic opposing fills are rejected.

### Reversal
Sponsor-confirmed target semantics may change virtual-close sequencing; document and retest before live trading.

## DEC-007 ? Deterministic candle and daily-loss conventions
Date: 2026-10-07
Status: ACCEPTED

### Context
Tick/session semantics need explicit defaults without inventing 021 behavior.

### Decision
DESIGN_DECISION: UTC half-open 60/300s candles; duplicates ignored, late unique ticks fail closed. Daily loss uses Asia/Kolkata day realized less charges plus current unrealized.

### Reason
Deterministic replay and explicit risk inputs.

### Impact
CandleBuilder, Ledger.daily_net, risk tests.

### Alternatives
Silent late-tick correction or fabricated empty candles.

### Reversal
Confirm sponsor volume/timestamp/session semantics, add fixtures, then adapt normalization/session policy.

## DEC-008 ? SQLite bootstrap persistence
Date: 2026-10-07
Status: SUPERSEDED

### Context
The first slice needed persistence without external services.

### Decision
DESIGN_DECISION: SQLite schema v1 initially supplied local durable state; DEC-009 supersedes its role as the primary durable database. SQLite remains offline mock/replay fallback.

### Reason
Simple fresh-clone setup while safety contracts stabilize.

### Impact
Store and local tests.

### Alternatives
Mandatory PostgreSQL services for the first offline slice.

### Reversal
Keep offline support until PostgreSQL is continuously available; never silently fall back after configured PostgreSQL failure.

## DEC-009 ? Neon PostgreSQL durable relational persistence
Date: 2026-10-07
Status: ACCEPTED

### Context
User explicitly requests Neon project muddy-tooth-14996153, branch production.

### Decision
DESIGN_DECISION: Neon PostgreSQL is the durable target; centralized psycopg Store, versioned checksum migrations in dedicated algoshield schema. No ORM added. DATABASE_URL selects PostgreSQL; absent URL selects offline SQLite.

### Reason
Relational transactions and constraints fit orders, fills, ledgers, risk and audit. Reuses existing service boundary with minimal driver integration.

### Impact
PostgresStore, migrations/config, pyproject dependencies, README/environment. Project linkage is intended until authenticated verification; credentials never recorded.

### Alternatives
Multiple ORMs and frontend/strategy SQL access rejected. No destructive resets or fake seeds on production.

### Reversal
Safely migrate/export durable data and preserve identity/accounting before changing provider; inspect schema and use additive migrations.

## DEC-010 ? Progress handoff and durable decision logging
Date: 2026-10-07
Status: ACCEPTED

### Context
Four developers and AI agents need persistent actual implementation state.

### Decision
DESIGN_DECISION: Member logs plus INTEGRATION.md record completed/tests/blockers; DEC entries record meaningful architecture changes; AGENTS completion protocol requires updates.

### Reason
Prevents false DONE claims and stale architecture context.

### Impact
AGENTS.md, docs/progress, DECISIONS.md.

### Alternatives
Duplicating full implementation docs or treating decisions as a git changelog.

### Reversal
Change logging format with team coordination; retain historical decisions and actual test evidence.

## DEC-011 ? Requested Neon infrastructure policy and credential handling
Date: 2026-10-07
Status: ACCEPTED

### Context
User requests auth, private uploads and hello function configuration and deployment.

### Decision
DESIGN_DECISION: Keep requested neon.ts/hello.ts exactly. Pin @neon/config and lock dependencies. Real values only in ignored .env/.env.local or process environment. Neon hello function is an infrastructure smoke endpoint, not the Python backend.

### Reason
Honors requested scope without redesigning the trading stack; no secret output or tracked credentials.

### Impact
neon.ts, hello.ts, package/TS config, environment ignores, infrastructure CLI workflow.

### Alternatives
No different project/branch; AI Gateway remains disabled; no automatic policy overrides.

### Reversal
Review an explicit policy diff and affected backend contracts before enabling more services or changing deployment scope.

## DEC-012 — Durable subscription control and callback quarantine
Date: 2026-10-07
Status: ACCEPTED

### Context
Global runtime enablement did not let an operator stop one strategy, and one callback exception could interrupt the complete candle fan-out. A process-local stop would reset after restart and would not prevent a direct intent from reaching risk.

### Decision
DESIGN_DECISION: Persist an `enabled` flag per subscription. Strategy runtime emits only for enabled subscriptions; a callback exception atomically disables only the faulted subscription and records a sanitized audit event. Risk independently rejects disabled subscriptions with `RISK_STRATEGY_STOPPED`. Re-enablement is an explicit account-scoped operator action.

### Reason
Individual strategy state must survive restart and remain non-bypassable at the risk boundary while healthy strategies continue processing the same candle.

### Impact
SQLite schema v2, PostgreSQL migration 002, strategy runtime, risk reasons, account/subscription APIs, dashboard state and Member 4 tests.

### Alternatives
Process-local halted sets and UI-only stop controls were rejected because they reset on restart and could be bypassed by direct intent submission.

### Reversal
A future subscription state machine may replace the boolean only through an additive migration and coordinated contract tests preserving stopped-strategy risk rejection.

## DEC-013 — Isolated local PostgreSQL development databases
Date: 2026-10-07
Status: ACCEPTED

### Context
PostgreSQL persistence and migrations were only locally unit-tested because an isolated Neon database was unavailable. Production data must never be used for integration tests, while SQLite alone cannot validate psycopg behavior, advisory ownership or PostgreSQL migration application.

### Decision
DESIGN_DECISION: Support peer-authenticated local PostgreSQL with separate `algoshield_local` application and `algoshield_test` rollback-only test databases. `scripts/setup_local_postgres.sh` creates missing databases and applies the same reviewed additive migrations without dropping, resetting or seeding data. Machine-specific URLs remain in ignored `.env.local`; Neon PostgreSQL remains the durable deployment target.

### Reason
Developers can validate the real PostgreSQL store and migrations safely without production access or stored local credentials.

### Impact
Local setup documentation, environment template, migration validation and PostgreSQL integration testing.

### Alternatives
Using production/Neon data for tests, silently falling back to SQLite, or maintaining a second PostgreSQL schema path were rejected.

### Reversal
Replace the local launcher when the team adopts a different isolated development environment, while preserving separate application/test databases and the existing migration history.

## DEC-014 — Durable offline mock and P0 failure evidence
Date: 2026-10-07
Status: ACCEPTED

### Context
In-memory external mock state prevented teammates from restarting the runnable demo. Partial fills and rejections existed in code but were not observable through the frontend.

### Decision
Persist canonical mock orders/fills independently of the platform DB via atomic JSON replacement; load it only for offline SQLite mode. Add risk-routed deterministic Failure Lab scenarios, real order/candle displays and CI. Refuse all demo seeding against PostgreSQL.

### Reason
Restart reconciliation now compares independently retained external evidence; P0 is testable from API and dashboard without 021 or Neon authentication.

### Impact
Minimal cross-owner changes: mock persistence (Member 2), platform/API/frontend wiring (Members 3/4), P0 integration tests and ignores. Shared financial models/formulas are unchanged. `design.md` remains removed per user instruction.

### Alternatives
Reconstructing broker truth from the platform ledger would hide drift and was rejected.

### Reversal
Replace the mock fixture with an independently hosted simulator or a documented adapter, retaining recovery and drift tests.

## DEC-015 — Durable validated policies and risk budgets
Date: 2026-10-07
Status: ACCEPTED

### Context
Restart reset configurable risk policies and individual halt state. There was no authoritative API to inspect pending exposure or change limits.

### Decision
Add risk-owned risk_policies/strategy_controls via additive PostgreSQL and versioned SQLite migrations. Validate finite positive loss limits and strict positive integer quantities/limits. Preserve existing policy mapping access. Derive loss/rate consumption from durable fills/orders; persist loss halts. Extend RiskDecision additively with reason/time/reservation details and introduce enums retaining existing state values. Expose budgets and policy/state APIs. Normalize migration SQL line endings before hashing.

### Reason
Restarts cannot erase configured limits or loss evidence; pending exposure survives policy changes. Canonical hashes stay stable across Windows/Linux checkouts.

### Impact
Member 3 risk service/API/tests, shared contracts/store/migration packaging and documentation. No accounting formula changes. PostgreSQL migration execution remains unverified until isolated DB access is available.

### Alternatives
Mutable process dictionaries and UI-authoritative limits were rejected.

### Reversal
Migrate policy/control history through a versioned schema change and retain restart, validation and concurrent-reservation tests.

## DEC-016 — Complete evidence, freshness and durable fail-closed recovery
Date: 2026-10-07
Status: ACCEPTED

### Context
Matching net positions alone could hide missing round-trip trades. Restart erased marks and kill latches; stale data had no risk effect.

### Decision
Snapshot completeness is an explicit fail-closed contract (default False). Validate identities, statuses, complete unique fill history, cumulative totals and positions before importing financial events. Persist safety state, kill latch/certificate, risk marks and timestamped audits via additive migration 003. Recovered marks preserve loss inputs; startup operational state stays RECOVERING. Add fresh broker/feed gating, explicit REDUCE_ONLY and verified operator kill reset.

### Reason
No green reconciliation from an empty/incomplete snapshot or stale cached price. Kill cannot silently unlatch after restart.

### Impact
Member 3 reliability/risk tests and APIs; minimal shared snapshot/validation/schema additions and mock completeness attestation. Existing states/fields retain names. Mock/replay is labeled explicitly; no 021 snapshot or volume behavior inferred.

### Alternatives
Implicitly complete snapshots, process-only latches and cancel-submitted success were rejected.

### Reversal
Any snapshot scope/freshness/session changes need documented provider evidence plus missing-history, stale-feed, reduce-only and restart tests.

## DEC-017 — Bounded broker work and convergent kill (2026-10-07)
Date: 2026-10-07
Status: ACCEPTED

### Context
Broker calls could block the control plane and kill could report submitted requests instead of verified state.

### Decision
BrokerSession permits one external call at a time, with bounded caller waits. Its daemon worker never writes local financial state. Timeout does not cancel external work: the session requires settled complete reconciliation before further broker mutations. Local transactions cover admission/reservation and dispatch start; waits occur outside the DB lock. Migration 004 distinguishes never-dispatched reservations from ambiguous submissions. Complete settled history can resolve an absent UNKNOWN as never accepted; other missing history still fails closed.

### Reason
Kill signals admission closed immediately, durably latches, then observes/cancels/reconciles and progresses attributed risk-authorized exits. Default total deadline is nine seconds, with finite rounds. Requests never prove cancellation or flatness. SUCCESS requires verified broker and virtual flatness with no open orders or unsettled call under ten seconds; verified later is SAFE_LATE. Unknown external close semantics remain an explicit adapter capability, false by default; only the mock currently confirms it.

### Impact
Bounded broker execution, durable dispatch evidence, kill/recovery state, risk-authorized emergency exits and deterministic reliability tests.

### Alternatives
Unbounded broker calls, cancellation by thread interruption, or treating submitted cancellation/flatten requests as proof were rejected.

### Reversal
Any provider-specific timeout or emergency-close semantics require confirmed adapter evidence and new race/deadline tests.

## DEC-018 — Session-derived trading account ownership
Date: 2026-10-07
Status: ACCEPTED

### Context
The dashboard and strategy subscription form exposed editable account IDs. A caller could select another account identifier, while the dashboard itself remained available without login despite durable local users and sessions already existing.

### Decision
Require a valid HttpOnly, SameSite=Strict local session cookie before serving the dashboard. Registration assigns the local trading account as `acc_<normalized username>`. Subscription create/start/stop endpoints derive the account exclusively from the verified session and reject extra caller-supplied account fields. Keep bearer-token verification for API clients. Represent safety evidence as compact backend-derived indicators in the strategy dashboard instead of raw safety JSON.

### Reason
Account attribution must come from authenticated identity rather than editable UI state. HttpOnly cookies keep the browser session out of JavaScript storage, and the compact safety rail preserves honest fail-closed visibility without overwhelming the strategy workflow.

### Impact
Authentication API cookies, dashboard routing, subscription request contract, responsive frontend, auth/member tests and documentation. This is a local bootstrap boundary; it does not claim production identity-provider readiness.

### Alternatives
LocalStorage bearer tokens, hidden account inputs and UI-only redirects were rejected because they still expose session credentials or trust caller-selected ownership.

### Reversal
Replace the local session implementation with the selected production identity provider while retaining server-derived account ownership and dashboard access tests.

## DEC-019 — Bounded strategy callback execution outside control-plane lock
Date: 2026-10-08
Status: ACCEPTED

### Context
Strategy callbacks were previously executed synchronously inside `with self.store.lock:` within `Platform.tick`. A slow or hanging callback blocked the entire control plane, preventing order cancellation, reconciliation, and the 10-second kill switch SLA. Additionally, a hung callback could pollute indicator state if it completed late or after a subscription restart.

### Decision
Execute strategy callbacks strictly outside `store.lock`. Run callbacks in an isolated bounded worker pool (`BoundedStrategyExecutor` with configurable timeout `callback_timeout` and bounded concurrency `max_workers`). Durably quarantine timed-out subscriptions (`enabled=0`, audit `STRATEGY_CALLBACK_FAILED` with `TimeoutError`) while healthy strategies continue uninterrupted. Track run generation per subscription; discard late results after timeout, stop/re-enable, global stop, or kill. Commit candidate indicator updates only if the originating run generation matches and remains valid upon completion. Workers are denied store locks and broker authority.

### Reason
Strategies are untrusted workloads and must never block control-plane operations or compromise the kill switch SLA. Latency isolation and fail-closed timeout enforcement ensure safety without allowing thread exhaustion.

### Impact
`StrategyRuntime`, `Platform.tick`, `docs/CONTRACTS.md`, `tests/test_strategy_execution_safety.py`. Trusted callback limits are documented: threads provide latency isolation, not a security sandbox for arbitrary untrusted bytecode.

### Alternatives
Running synchronous sequential callbacks with in-band timeouts or killing threads via OS signals was rejected because Python threads cannot be safely terminated asynchronously and store locks must not be held across untrusted code.

### Reversal
Arbitrary untrusted user strategy upload requires process-level sandboxing (e.g. WASM or container isolation) rather than thread-level latency bounding.

## DEC-020 — Monotonic simulation cursor and bounded replay stream lifecycle
Date: 2026-10-08
Status: ACCEPTED

### Context
`Platform.start_replay_stream` previously calculated tick start timestamps using wall-clock time (`int(self.clock()) + 60`) on every batch loop iteration. Because simulation batches spanned 11 minutes (660 seconds) while real wall-clock time advanced only seconds between iterations, subsequent batches jumped backwards in simulated time, triggering `ValueError("late tick: replay must be ordered before ingestion")` and failing closed with `REPLAY_STREAM_FAILED`. Repeated replay actions, multiple symbols, and stream restarts also suffered from clumping and duplicate event IDs.

### Decision
Introduce a monotonic simulation cursor (`_simulation_cursor`) on `Platform` that strictly advances beyond previously emitted ticks across repeated replay actions, stream restarts, and batches.
1. `generate_simulation_batch` queries the latest simulation timestamp across active symbols (from cursor, `candles.last`, `risk_marks`, and order IDs) and schedules subsequent batches strictly after the latest timestamp (`start_ts = (latest // align + 1) * align`).
2. Separate simulated event timestamps from receive time: ticks carry simulated timestamps (`tick.event_timestamp`), while receive time is independently recorded via `self.clock()` during ingestion (`self.reliability.observe_tick`).
3. Generate globally unique event IDs (`sim:{sym}:{ts}:{seq}`) for newly simulated ticks, while intentional duplicate replays retain identical IDs and attributes, allowing `CandleBuilder` to deduplicate idempotently without raising conflicting-duplicate errors.
4. Synchronize multi-symbol batches: at each simulated second, all enabled symbols emit synchronized ticks, avoiding inter-symbol lag.
5. Thread-safe stream lifecycle: `start_replay_stream` uses `_replay_lock` to prevent duplicate threads; returns `False` if kill is active or latched; terminates promptly upon stop, kill, or platform shutdown; and never automatically restarts following recovery or reconciliation. Replay remains strictly mock-only.

### Reason
Trading simulations must never violate causality or emit backward/overlapping timestamps. Ingestion pipelines and candle builders require deterministic ordering and unique event IDs while preserving broker freshness and safety invariants.

### Impact
`Platform` (`get_simulation_cursor`, `generate_simulation_batch`, `start_replay_stream`, `stop_replay_stream`, `demo`, `tick`), `tests/test_replay_stream.py`. Full suite passes (237 passed, 1 skipped).

### Alternatives
Deriving simulation time directly from wall-clock sleep intervals was rejected because it creates clock drift, breaks fast-forward testing, and produces backward jumps across restarts. Auto-restarting streams after recovery was rejected as it violates AGENTS.md rule 13.

### Reversal
Live market data connections (e.g., 021 WebSocket feeds) will replace synthetic simulation batches entirely with the external broker/exchange feed adapter; the simulation cursor remains strictly within the mock/replay harness.

## DEC-021 — Asia/Kolkata market session boundaries and kill deadline budget exhaustion
Date: 2026-10-08
Status: ACCEPTED

### Context
`MarketSession` previously evaluated raw UTC epoch modulo 86400, ignoring local exchange timezone (`Asia/Kolkata`, UTC+05:30) and failing closed or open incorrectly depending on UTC date alignment. Boundaries were not clearly documented, missing timestamps risked ambiguity, and exhausted kill budgets caused an unhandled `ValueError` when passing non-positive time to `Deadline`. Additionally, same-strategy concurrent callbacks risked computing on uncommitted indicator states if not serialized prior to copying.

### Decision
1. **Asia/Kolkata Session Handling**:
   - `MarketSession` converts timestamps to `Asia/Kolkata` (`ZoneInfo("Asia/Kolkata")`) before computing seconds into the day.
   - Continuous hours defined as half-open interval `[09:15:00, 15:30:00)` IST (`open_time_seconds <= sec < close_time_seconds`). Exactly 09:15:00 is `OPEN`; 15:30:00 and after is `CLOSED`.
   - Preserve default `enforce_hours=False` for mock replay compatibility.
   - When hours are enforced, missing timestamp (`None` with no clock) fails closed (`is_open() -> False`, `status_at() -> "CLOSED"`).
   - Consistent state precedence: `HALTED` overrides all; manual `OPEN`/`CLOSED` override schedule; `AUTO` adheres to schedule. Sourced identically by `is_open()`, `status_at()`, `to_dict()` snapshot, and `Reliability.check_evidence()`.
2. **Kill Deadline Budget Exhaustion**:
   - `Platform.kill` and `Reliability.kill` accept pre-configured `deadline` objects and gracefully handle non-positive remaining budget (`<= 0`). If deadline budget is exhausted, a truthful failure certificate (`status="FAILED", reason="KILL_DEADLINE_EXPIRED"`) is returned rather than raising an unhandled `ValueError` from `Deadline`. Total elapsed time includes admission closure and replay join.
3. **Same-Strategy Callback Serialization**:
   - In `StrategyRuntime.worker_task`, acquire a per-instance lock (`inst_lock`) *before* copying working state and release only *after* committing updated indicator state, ensuring intermediate candle updates are never lost or computed concurrently from stale indicator states.

### Reason
Trading exchange operations must respect exact local exchange operating hours and fail closed safely on missing context. Risk and kill mechanisms must provide truthful audit certificates rather than throwing unhandled exceptions on budget exhaustion.

### Impact
`MarketSession`, `Reliability`, `Platform.kill`, `StrategyRuntime`, `CONTRACTS.md`, `tests/test_market_session.py`, `tests/test_strategy_lifecycle.py`. Full test suite passes (262 passed, 1 skipped).

### Alternatives
Using raw UTC day offsets rejected due to day boundary errors across UTC midnight (03:45 UTC is 09:15 IST). Silent OPEN on missing timestamps rejected due to fail-closed principles.

### Reversal
Any future multi-exchange support or exchange holiday calendar will be introduced via clean pluggable session provider adapters without altering risk layer contracts.

## DEC-022 — Worker callback storage isolation, control-plane commit, and bounded shutdown
Date: 2026-10-08
Status: ACCEPTED

### Context
`StrategyRuntime.close` previously used `shutdown(wait=True)` to avoid SQLite teardown access violations under the assumption that waiting for workers prevented teardown errors. However, if a callback hung or blocked indefinitely, `close()` would block forever, violating bounded platform shutdown SLAs. Inspection of the worker path revealed that workers called `may_run` and `is_subscription_enabled` (executing SQL on SQLite) and committed indicator state directly from worker threads while holding instance locks across untrusted callbacks. If a worker timed out, it retained instance locks, blocking controls or future candles, and if SQLite was closed, delayed worker threads triggered SQLite access violations.

### Decision
Amends DEC-021 item 3:
1. **Worker Storage Isolation**: Callback worker tasks run purely isolated calculations on copies of working indicator state and immutable candle inputs. Workers never hold SQLite connections, never call `Store`, never access broker authority, and never commit runtime state.
2. **Control-Plane Validation and Commit**: The control plane thread in `on_candle` dispatches candidate work, bounds wait time by `callback_timeout`, and validates candidate outputs (`_enabled`, `_global_epoch`, `_subscription_generations`, `is_subscription_enabled`, `may_run`, and candle monotonic start time). Only valid, timely outputs have their indicator state and order intents committed to platform state. Timed-out or invalidated candidate results cannot mutate any platform or indicator state.
3. **Bounded Non-Blocking Shutdown**: `StrategyRuntime.close()` invalidates pending results (`_global_epoch += 1`, `_enabled = False`) and immediately cancels queued work via `self._executor.shutdown(wait=False, cancel_futures=True)`. Because daemon worker threads have zero DB handles and commit no state, storage can close immediately; late worker thread completions execute zero database queries and trigger no access violations.
4. **Lock Non-Retention on Timeout**: Instance-level locks (`inst_lock`) serialize same-instance callbacks in the control plane to preserve sequential indicator updates without letting a timed-out worker retain locks needed by `kill`, `set_enabled` (stop/re-enable), `close`, or healthy strategies. Stopping or halting a subscription provisions a fresh instance lock.

### Reason
Strategies are untrusted workloads. Workers must never have database or mutation authority, and process shutdown must never hang on slow or infinite callbacks. Pure computation in workers and control-plane state commits completely eliminate SQLite teardown race conditions and lock contention.

### Impact
`backend/strategies/runtime.py`, `docs/CONTRACTS.md`, `tests/test_strategy_execution_safety.py`. Full test suite passes (265 passed, 1 skipped).

### Alternatives
Using unbounded `shutdown(wait=True)` was rejected because it violates shutdown SLAs when callbacks hang. Allowing workers to query SQLite or commit state directly was rejected because it causes teardown access violations and state corruptions.

## DEC-023 — Authenticated, account-scoped user workflow and telemetry isolation
Date: 2026-10-08
Status: ACCEPTED

### Context
Task 6 requires a complete authenticated Member 4 user workflow (`register/login -> subscribe -> start -> observe readiness/signals/P&L -> stop`) with strictly server-side account-scoped isolation. Account identity must be derived exclusively from verified server-side sessions, never from client requests or frontend filtering. Subscription responses, state projections, positions, orders, fills, signals, errors, risk budgets, and audit evidence must never leak other accounts. WebSocket and SSE telemetry streams must be authenticated before sending data, revalidate sessions during streaming, and terminate immediately on logout or token expiration. When sessions expire or backend becomes unavailable, frontend UI must clear stale state rather than retaining cached cross-account or out-of-date records.

### Decision
1. **Server-Side Account Derivation & Scoping**:
   - Authentication tokens (cookie or Authorization header) are verified via `engine.auth.verify_token`. Anonymous reads to `/api/state`, `/api/orders`, `/api/fills`, `/api/subscriptions`, `/api/risk/budgets`, `/api/stream/ws`, and `/api/stream/telemetry` return HTTP 401 Unauthorized (or WS close code 1008). No anonymous fallback is permitted on risk budgets; global inspection is denied until formal roles are implemented.
   - In `backend/platform.py`, `Platform.snapshot(account_id=...)` strictly scopes subscriptions, positions, orders, fills, counts, signals, strategy errors, and audit events to the verified account. Safety payloads (`virtual`, `broker`, `unknown_orders`, `fills.unique_applied`) and counts are isolated so no cross-account exposure exists.
   - Deep nested safety audit:
     - Position comparison: preserves raw `UNKNOWN` or `FAILED` status; filtering never converts uncertainty into a safety pass.
     - Reconciliation reports: `broker_positions` and `unexplained_positions` filtered to `account_id`; `orders`, `unique_fills`, `open_orders`, `duplicate_snapshot_fills`, and `unattributed_fills` describe the verified snapshot at `observed_at` sourced from `accounts[account_id]`. If verified account breakdown is absent or unverified, reconciliation counts report `null` rather than substituting live local counts. Honest global verification flags (`verified`, `reason`, `observed_at`) are preserved.
     - Kill certificates: historical evidence is strictly preserved. `open_orders`, `virtual_positions_flat`, `status`, and `reason` reflect the verified historical certificate at kill time and are never rewritten with current account state (later trades do not alter historical certificates, and failed kills retain uncertainty). `broker_positions` dictionary is filtered strictly to keys starting with `f"{account_id}/"`.
     - Fill counters: `unique_applied`, `duplicates_ignored`, and `rejected_events` scoped strictly to the caller's account; `unattributed_in_last_verified_snapshot` is sourced from verified account breakdown at `observed_at` (returns 0 only when verified to be 0; returns `null`/unknown if unattributed fills exist, snapshot is unverified, or account evidence is missing). Never hardcoded to 0.
     - Unknown orders: filtered strictly by `account == user.account_id`.
     - Audit payloads: only events where `account == user.account_id` or `strategy` belongs to the user's subscriptions are returned; nested payloads with `broker_positions` are sanitized to strip other accounts.
   - History queries (`history` and `history_count`) accept an optional `account_id` parameter filtering `WHERE account = ?`.
2. **Subscription Mutation Authorization**:
   - `POST /api/subscriptions` creates subscriptions for the authenticated session's `account_id` and returns user-scoped subscriptions.
   - `POST /api/subscriptions/{strategy_instance_id}/start` and `/stop` look up the subscription by ID: if not found, return 404; if owned by another account, return 403 Forbidden without mutating state or leaking details. Responses return user-scoped subscriptions.
3. **Telemetry Streaming Authentication & Eviction**:
   - SSE (`GET /api/stream/telemetry`) and WebSocket (`/api/stream/ws`) require verified authentication before sending any data.
   - Streaming loops revalidate the session token before emitting snapshots (`engine.auth.verify_token(token)`). If the session expires or the user logs out, SSE returns/terminates and WebSocket closes immediately with close code 1008 (`WS_1008_POLICY_VIOLATION`).
4. **Stale UI Cleared on Session Termination & Disconnection**:
   - In `frontend/index.html`, upon HTTP 401 or WebSocket 1008 close code, `clearStaleData()` resets subscriptions, positions, orders, fills, signals, errors, budgets, and safety indicators to prevent stale account data from remaining visible.
5. **Team Ownership & Remaining Unprotected Global Mutation Endpoints**:
   - Ownership alignment: Ram is Member 3 (risk, security, reliability, trading gates, kill switch). Akshat is Member 1 (accounting, ledgers, fills, positions). Member 4 owns market data, strategy runtimes, and user-scoped workflow.
   - Platform-wide operator authorization is NOT complete. Ram (Member 3) must implement role-based operator authorization for remaining unprotected global mutation endpoints:
     - `PUT /api/risk/policies/{strategy}`
     - `PUT /api/risk/strategies/{strategy}`
     - `POST /api/reconcile`
     - `POST /api/resume`
     - `POST /api/reduce-only`
     - `POST /api/kill/reset`
     - `POST /api/kill`
     - `POST /api/failure-lab/{scenario}`
     - `POST /api/broker/disconnect`
     - `POST /api/broker/reconnect`
     - `POST /api/broker/updates/sync`
     - `POST /api/orders/{order_id}/cancel`
     - `POST /api/market/session`
     - `POST /api/demo`
     - `POST /api/accounts`

### Reason
Multi-tenant security requires defense-in-depth where server-side boundaries enforce strict data isolation. Client-side filtering is inherently insecure. Streaming connections must enforce authentication continuously to prevent unauthorized data exposure following logout or token revocation. Global mutations must be explicitly guarded by operator roles rather than left open.

### Impact
`backend/platform.py`, `backend/api.py`, `backend/strategies/runtime.py`, `backend/execution/orders.py`, `backend/reliability/control.py`, `frontend/index.html`, `tests/test_member4_workflow.py`. Full test suite passes (272 passed, 1 skipped). Ruff check/format and TypeScript pass.

### Alternatives
Preserving anonymous risk budgets was rejected because it leaks strategy budgets without authentication. Client-side filtering was rejected as it exposes private order and position data in network payloads. Passing client-provided `account_id` was rejected because users could forge accounts. Revalidating auth only upon initial WebSocket handshake was rejected because logged-out users would continue receiving live account updates.

## DEC-024 — Evidence-first operational layer
Date: 2026-10-08
Status: ACCEPTED

### Decision
Keep account-wide risk and LIMIT-price validation inside the gateway; expose conservative Safety Proof, server-built traces, reconciliation recovery evidence, bounded process metrics, Failure Lab V2, and Kill Certificate V2. Run SafetyBench only on an isolated in-memory SQLite/mock platform. Protect evidence APIs with local sessions and scope user financial projections to the authenticated account.

### Reason
The platform needs judge-visible proof without weakening fill, reconciliation, or kill invariants and without inventing unknown 021 behavior.

### Impact
SQLite schema v11 and PostgreSQL migrations 007-010 add correlation, policy, and benchmark records. Metrics reset on process restart; historical policy reconstruction remains explicitly unknown.

## DEC-025 — React SPA as a presentation-only deployment artifact
Date: 2026-10-08
Status: ACCEPTED

### Decision
Replace the legacy HTML pages with a modular React/Vite SPA. Keep session discovery in one auth provider, telemetry in one authenticated WebSocket provider, and HTTP behavior in one credentialed API client. React displays backend evidence without calculating financial or safety truth. Vite is development-only; production builds assets in a Node stage and FastAPI serves them with API/WebSocket route priority and SPA fallback.

### Reason
The operational surface now spans independent workflows that need routing, shared state, testable session handling, and responsive navigation without duplicating backend rules.

### Impact
`frontend/src` becomes the UI source, `frontend/dist` remains generated and ignored, legacy login/register pages are removed, and direct-route refresh requires a completed frontend build. Backend-only environments receive an explicit 503 build instruction when assets are absent.

## DEC-026 — Explicit operators and shared account response projection
Date: 2026-10-09
Status: ACCEPTED

### Context
Authenticated ordinary users could invoke platform-wide mutations, and several
action/evidence endpoints returned global snapshots. A two-account probe proved
that `POST /api/reconcile` disclosed another account's subscription. Public
registration could not safely imply administrative authority.

### Decision
Add durable `operator_grants` through forward-only SQLite migration 012 and
PostgreSQL migration 011. Resolve grants during existing session validation. No
HTTP endpoint grants authority; a local offline command provisions an existing
registered user. Global controls require an operator while own-account actions
retain ownership checks.

Apply reusable `AccountResponseScope` after authoritative calculations to
snapshots, streams, actions, proof, reconciliation, traces, broker evidence and
nested audit payloads. Operators also receive only their account's private
evidence. Preserve global gate/health/proof verdicts, kill result/timing and
aggregate diagnostics. Internal reconciliation, ledger and risk inputs remain
unfiltered. Unknown or unattributed traces are denied.

### Reason
This closes function-level authorization and response leakage without changing
financial truth or adding an external dependency to the kill path. Durable
grants support restart and immediate revocation for existing sessions.

### Impact
SQLite provisioning and two-account/operator regressions are
IMPLEMENTED_VERIFIED. PostgreSQL migration/provisioning is
IMPLEMENTED_UNVERIFIED pending an isolated database. Production identity,
cookie/TLS and operator governance remain BLOCKED. Existing migrations are
immutable and 021 semantics are unchanged.

## DEC-027 — Targeted Round 2 security, identity and evidence integration
Date: 2026-10-09
Status: ACCEPTED

### Decision
Permit authoritative OPEN → REJECTED only with zero executed quantity; retain
filled/terminal/UNKNOWN guards. Reject mock order identity reuse with different
intent/account. Keep canonical platform IDs and specify scoped provider mapping
in CONTRACTS; defer real mapping until sponsor evidence, without a new column.

Use configured browser Origins for unsafe HTTP and cookie WebSockets; deny
missing/untrusted Origin with an explicit nonbrowser Bearer exception. Never
derive trust from Host/forwarded headers. Ship `--no-proxy-headers` and document
shared-peer limits. Upgrade legacy passwords on successful login using versioned
standard-library PBKDF2-SHA256/600000 with compare-and-swap. Add bounded monotonic
single-worker login attempts and outcome-only audit. Preserve DEC-026 authority
and projection. Render executed/requested quantities and actual candle-linked
signals through existing React telemetry, without financial calculations.

### Reason and impact
Current-dev regressions proved rejection, Origin/hash and mock identity gaps;
member reports were candidate evidence, not merge-ready branches. Existing TEXT
hash/salt columns suffice: SQLite stays v12, no migration/dependency/lock changes.
Corrections/late fees remain unsupported pending event contracts; no ledger or
candle rewrite. Archive inspected superseded plans/visual reference with redirects
and repaired links; preserve canonical docs, original research and decision history.
Member logs become optional startup evidence. Exact checks and blockers are in
ROUND2_INTEGRATION_AUDIT and progress/INTEGRATION.

## DEC-028 — Direct branch pushes and unified execution plan
Date: 2026-10-09
Status: ACCEPTED

### Decision
Team members may directly push branches with repository write access; pull
requests are optional. This supersedes previous dev-only/no-main operational
instructions. The integration lead promotes validated dev checkpoints to main by
normal fast-forward push after successful CI; no force or server-rule bypass.
Application operator grants remain unchanged.

`TEAM_EXECUTION_PLAN.md` is the sole active four-member task/dependency plan.
`REQUIREMENTS_TRACEABILITY.md` records scoped code/test evidence, while
`IMPLEMENTATION_DELTA.md` summarizes remaining gaps. Preserve historical
decisions, research and migrations. Provider contracts, isolated PostgreSQL and
current browser coverage remain blockers, not inferred successes.

### Reason and impact
The owner explicitly authorized safe main promotion and then removed the
mandatory PR workflow. Commit `63266eb` repaired push CI ordering, passed GitHub
CI and was normally fast-forwarded to `origin/main`; PR #1 was closed without
merge. No GitHub permission/protection changes were made.

## DEC-029 — Optional supervised Yahoo quote evidence
Date: 2026-10-09
Status: ACCEPTED

### Decision
Keep replay as the default and provide Yahoo only as an explicit optional dependency/configuration. Run yfinance 1.7.0 in a bounded child process behind a bounded queue; normalize only the verified `id`, `price`, and plausible millisecond `time` fields into canonical ticks and route them through `Platform.tick`. Preserve raw time, label source/volume availability on ticks and candles, and restrict this source to mock execution. Treat every overflow, gap, disconnect, stale period, or malformed update as fail-closed without automatic resume.

### Reason
Task 9A confirmed sampled price messages but did not establish complete exchange-tick coverage, volume semantics, or unique trade identity. Process supervision contains ambiguous third-party cancellation behavior, while explicit evidence labels prevent sampled Yahoo quotes or zero compatibility quantity from being mistaken for exchange executions or observed volume.

### Impact
`Tick` and `Candle` gain additive source and volume-availability evidence. The `yahoo` extra pins the probed yfinance 1.7.0, which resolves with the existing `websockets>=13,<16` constraint (validated with 15.0.1). Yahoo can never be mixed with replay in a running timeline and does not establish 021 compatibility.

## DEC-030 — Atomic multi-stock subscription orchestration
Date: 2026-10-09
Status: ACCEPTED

### Context
Traders need to apply one strategy kind to several stocks without manually repeating subscription creation. The existing safety and accounting model is explicitly keyed by strategy instance and symbol, so changing one subscription row to own many symbols would couple indicator state, failure handling, risk and P&L and weaken existing invariants.

### Decision
Keep one strategy instance equal to one symbol. Add authenticated `POST /api/subscriptions/batch` as an orchestration boundary that normalizes up to 20 unique symbols, generates deterministic instance IDs, checks all collisions, and inserts all ordinary subscription rows and audit evidence in one database transaction. A failure creates no rows. In-memory generations and instance locks are initialized only after commit. The React form uses this endpoint for both one-stock and multi-stock creation and displays only backend-confirmed outcomes.

### Reason
This provides a simple trader workflow while preserving per-instance candle state, callback quarantine, risk decisions, broker attribution, ledger keys, start/stop control and reconciliation behavior.

### Impact
No schema or broker/provider contract changes. Existing `POST /api/subscriptions` remains compatible. Replay already discovers unique enabled subscription symbols. It remains the explicit default/fallback mode when Yahoo is unavailable, selected at clean process startup; there is no automatic source switch, candle-timeline mixing, backfill, or trading resume. Live 021 symbol-subscription behavior remains unknown and is not inferred.

### Alternatives
A symbols array or JSON column on one subscription was rejected because it creates shared failure and accounting state. Repeated frontend calls were rejected because they can partially succeed. A second multi-symbol execution model was rejected because it duplicates existing contracts.

## DEC-031 — Official 021-03 normalization and conservative strategy policies
Date: 2026-10-09
Status: ACCEPTED

### Decision
Treat `docs/021/OFFICIAL_API_CONTRACT.md` as the canonical official wire detail and `docs/021/INTEGRATION_BLUEPRINT.md` as the 021-specific implementation order. Normalize paise, signed provider quantity, instruments, HTTP uncertainty and strict TC1/TC3/TC4/TC8 frames behind the provider boundary. Market packets are sampled observations; order-WS trade events without documented `tradeId` never become fills. Keep the adapter and live transport OFF by default.

Implement isolated policies for the mandatory 09:15/15:15 INTRADAY strategy and 1%-from-official-open strategy with application-managed 5% WAP exits. Persist trigger identity before emitting each canonical intent, use attributed residual fills for exits, and fail closed on stale/ambiguous evidence. Runtime composition remains a separate gate and cannot be claimed from policy fixture tests.

### Reason and impact
The official source removes earlier endpoint/packet uncertainty but leaves trade association scope, complete history, charges, account mapping, opposing close behavior and live kill feasibility unresolved. This smallest slice makes documented transformations executable without inventing those semantics or weakening existing RiskGateway, ledger, reconciliation or mock behavior. No schema, migration, dependency, live credential, broker write, or remote database change is included.

## DEC-032 — Bounded 021 transport with durable provider-order identity
Date: 2026-10-09
Status: ACCEPTED

### Decision
Implement the documented 021 REST/auth and sampled market WebSocket paths behind `Broker021Adapter` and `MarketData021Provider`, enabled only by explicit server-side configuration. Load and validate instruments from the documented gzip CSV, encode signed quantities and paise at the provider boundary, and persist a unique `(provider, account, provider_order_id)` mapping before treating an order as usable locally. Poll per-order REST trades for canonical fills; require a non-empty provider `tradeId`. Treat 500/503 writes and incomplete broker evidence as uncertain and fail closed.

When live 021 mode is enabled, 021 is the required primary market source. Yahoo remains an explicit clean-process-start fallback only with live 021 mode disabled. Never switch automatically after a disconnect, mix provider timelines, backfill a gap, or auto-resume trading. The first cumulative-volume observation is a baseline with unavailable volume; only later monotonic deltas may contribute candle volume.

### Reason and impact
This converts the documented wire contract into a testable integration without leaking provider details into risk, execution, ledger or UI modules. The official material still does not define charges, corrections, complete history, manual-trade attribution, account mapping, or verified kill semantics, so those remain explicitly unknown; zero charges in the adapter are not a claim that live net P&L is exact. No live order or secret is included in this change.

## DEC-033 — Evidence-separated provider readiness projection

Date: 2026-10-09
Status: ACCEPTED

### Decision

Expose one account-scoped, read-only provider-readiness projection from the
existing platform/reliability composition. Connectivity, provider subscription
evidence, market freshness, broker freshness, snapshot coverage, reconciliation,
explicit-resume status, action class, and current kill verification remain
separate fields. Missing evidence is `UNKNOWN`; connection or send success never
proves subscription readiness. A historical kill certificate cannot prove
current flatness without current complete, fresh reconciliation evidence.

The projection grants no execution authority and does not alter RiskGateway,
OrderManager, provider modules, cancellation states, or reconciliation. Existing
explicit resume remains mandatory after startup/reconnect, while the projection
also states whether all currently modeled evidence would make resume eligible.
Provider-owned canonical acknowledgement/coverage fields require Member 2 review
before later admission integration.

### Reason and impact

One composite `connected` or `HEALTHY` label can conceal independent uncertainty
and encourage unsafe recovery. The additive projection freezes honest semantics
without weakening the conservative 021 `is_complete=False` boundary or inventing
provider behavior. Live 021 execution readiness remains blocked on the handoffs
listed in the Member 3 and integration progress records.

## DEC-034 — Canonical admission, pre-dispatch, and recovery safety enforcement
Date: 2026-10-09
Status: ACCEPTED

### Decision
Implement one canonical safety evidence evaluator `Reliability.evaluate_safety_evidence(*, account_id=None, symbols=None, external_market_data=None, broker_connected=None)` that assesses physical evidence dimensions (broker connectivity, settlement/uncertainty state, market feed freshness, broker state freshness, snapshot completeness, reconciliation status, external provider subscription review, and unresolved unknown orders) completely decoupled from execution gate state (`CLOSED`/`RUNNING`) or strategy runtime state (`is_enabled`).

Enforce action-specific readiness:
1. New directional exposure strictly requires fresh broker/market evidence, complete reconciliation, verified external provider subscriptions (when external feed is used), and zero unresolved unknown orders across relevant accounts. Missing/unverified provider evidence remains `UNKNOWN` and blocks new exposure with canonical reason codes (`RISK_BROKER_DISCONNECTED`, `RISK_PROVIDER_SUBSCRIPTION_UNAVAILABLE`, `RISK_UNKNOWN_ORDERS_PRESENT`, `RISK_STALE_MARKET_DATA`, `RISK_STALE_BROKER_STATE`, `RISK_RECONCILIATION_REQUIRED`).
2. Order cancellations and emergency reducing exits retain their existing contracts and are exempt from new-exposure blocking rules.
3. Pre-dispatch revalidation occurs inside `RiskGateway.authorize_dispatch(intent, row)` under the serialized store lock immediately before `dispatch_started=1`/`UNKNOWN` is committed and before `broker.submit()`. If evidence or gate state has invalidated since initial reservation, authorization is safely rejected and the reservation released without broker submission and without fabricating a broker rejection. Once dispatch has commenced, uncertainty retains `UNKNOWN` status and potential exposure without retry.
4. Hardened global resume evaluates cross-account evidence across all execution-relevant accounts, never scoped solely to the operator's account, and re-validates the kill latch, disconnect, and snapshot completeness inside `with self.store.lock:` before opening the gate. Reconnections and feed arrivals never automatically resume trading.

### Reason and impact
Prevents race conditions between risk reservation and broker dispatch, eliminates blind auto-resumption, guarantees cross-account safety prior to opening the execution gate, and ensures that missing provider evidence fails closed without altering fill ingestion, accounting, or mock/replay contracts. Zero changes to raw provider modules or orders.py were made. All 447 backend tests pass cleanly.

## DEC-035 — Explicit cookie transport and no URL credentials
Date: 2026-10-09
Status: ACCEPTED

### Decision
Local HTTP explicitly uses `ALGOSHIELD_SECURE_COOKIE=false`; deployment behind approved TLS must explicitly set it to `true`. Login and logout use matching cookie attributes. The server is started with one worker and `--no-proxy-headers`; it does not trust arbitrary forwarded headers. SSE and WebSocket reject URL query tokens, accepting only the authenticated session cookie or an explicit Bearer credential where the transport supports it. Browser WebSocket uses its same-site cookie and Origin policy; native browser WebSocket cannot attach an arbitrary Authorization header.

### Reason and impact
URL credentials leak through browser history, logs, and referrers. Explicit configuration prevents a local development default from silently asserting TLS transport or proxy trust. This does not invent a production origin, proxy allowlist, or identity provider, and does not alter account-scoped server authorization.

## DEC-036 — Guarded, bounded automatic strategy mode

Date: 2026-10-09
Status: ACCEPTED

### Decision

Add an authenticated, explicitly started auto mode over a configurable bounded
set of provider-supported cash equities. It compares momentum, breakout and
rebound-confirmed mean-reversion evidence, chooses a strongest qualified
stock/policy pair for a quantity-one long entry, bounds concurrent attributed
positions, and exits on configured take-profit, stop-loss or reversal evidence.

Auto creates ordinary one-symbol subscriptions and canonical `OrderIntent`
values. RiskGateway, OrderManager, broker fills, ledger attribution,
reconciliation, market-session controls and the global gate remain
non-bypassable. Durable start/stop evidence restores scanning after restart but
never reopens the gate; reconciliation and authorized resume remain mandatory.

### Reason and impact

This makes inactive strategies understandable and offers a hands-off workflow
without inventing a second execution path, unbounded whole-market sockets,
short-selling assumptions or a profitability claim. Loss remains possible and
live 021 writes remain subject to DEC-033/034 reconciliation limits. No schema,
migration, provider wire contract or broker authority changed.

## DEC-037 — Adaptive auto-policy evidence and backend-owned empty financial state

Date: 2026-10-09
Status: ACCEPTED

### Context

The first auto-mode presentation exposed internal subscription rows and rendered
missing fill-derived positions as dashes. It also described one momentum score,
which did not meet the requested adaptive strategy-selection workflow. Replacing
dashes in React with computed zeroes would violate the backend financial-truth
boundary.

### Decision

Clarify and extend DEC-036: Auto mode compares momentum, breakout and
rebound-confirmed mean-reversion scores after bounded cross-stock coverage, and
records the selected policy and score with BUY/SELL/HOLD evidence. Internal
`auto_*` subscriptions remain durable attribution/control records but are not
listed as user-created manual strategy instances; open auto positions remain
visible in the Auto mode panel and full order/fill history remains available.

The backend subscription projection, not React, supplies a zero-valued financial
view tagged `NO_FILLS` when no attributed fill exists. The authoritative
positions collection remains fill-derived and omits that synthetic display row.
Once fills exist, the subscription view is tagged `FILL_DERIVED` and uses Ledger
output. Zero therefore means verified absence of attributed fills in local
history, not an invented trade or broker-safety claim.

### Impact

No schema, provider contract, execution authority, fill semantics or risk rule
changes. Auto selection remains a simple deterministic policy comparison, not
ML, portfolio optimization, a claim of the objectively best strategy, or a
profit guarantee. Live 021 writes retain all DEC-033/034 blockers.

## DEC-038 — Isolated 021 ledger and strict empty virtual-account bootstrap

Date: 2026-10-09
Status: ACCEPTED

### Context

Fresh authenticated reads returned HTTP 200 with empty orders, trades,
positions and holdings, but no pagination, history-start or atomic snapshot
metadata. The configured SQLite file also contained an older offline mock/replay
timeline (159 orders, 132 fills and 12 non-terminal orders) with no 021 order
mapping. Treating those two broker timelines as one made safe reconciliation
impossible. DEC-034 remains correct for arbitrary and non-empty 021 snapshots,
but did not define a bootstrap for a provably unused virtual account.

### Decision

When 021 is enabled without PostgreSQL, use `ALGOSHIELD_021_DB` with the default
`data/platform-021.db`; never reuse `ALGOSHIELD_DB`, which remains the offline
mock/replay ledger. Preserve the old database and history.

Permit one narrow complete snapshot: all authenticated 021 orders, aggregate
trades, positions and holdings must simultaneously be empty; the dedicated 021
store must contain no local order, fill or 021 mapping. Any non-empty provider
view or any local execution history leaves snapshot completeness false under
DEC-033/034. Fresh accepted market marks for every required symbol, plus the
provider's active subscribed-symbol set and connected state, constitute serving
subscription evidence; sending a subscription alone does not.

An empty bootstrap only allows reconciliation to become verified. It leaves the
gate STOPPED and still requires an authorized explicit resume. After the first
order, ordinary mapped order/trade/position reconciliation applies and the
today-only cross-day limitation remains fail-closed on restart until a complete
history horizon is established.

### Impact

This enables a genuinely unused 021 virtual account without deleting or
ignoring prior financial history. It does not certify arbitrary empty responses,
non-empty accounts, cross-day recovery, charges, corrections or kill behavior.
It introduces no broker bypass and does not submit a live order during bootstrap.

## DEC-039 — Provider-derived 021 demo execution without fabricated portfolio state

Date: 2026-10-09
Status: ACCEPTED

### Context

The virtual exchange rejects some cash instruments for intraday eligibility,
pre-open state or illiquid market-order restrictions. It may express a
definitive rejection as HTTP 4xx, an application-failure envelope, or an
`orderId=0` followed by a terminal zero-fill row. Treating all of those as an
uncertain submission stopped Auto even though the provider proved no exposure.
The provider's optional order WebSocket also closes independently while REST
orders and per-order trades remain the documented execution authority.

### Decision

Never seed holdings, fills or P&L for demonstrations. Configure the documented
021 product with `ALGOSHIELD_021_PRODUCT`; use `CNC` for the cash-equity demo.
Map only definitive, zero-execution provider failures to `REJECTED`. Timeouts,
transport failures, ambiguous responses and any executed quantity remain
`UNKNOWN` and fail closed. Terminal provider rows with zero traded quantity do
not poison an otherwise empty-account bootstrap.

Rank 021 cash-equity Auto candidates by provider freeze quantity as a bounded
liquidity proxy; do not hardcode stock names. The order WebSocket remains
optional lifecycle telemetry: disconnects are audited, while REST freshness,
reconciliation and per-order trades retain execution/fill authority. Market
feed loss, REST uncertainty and unknown submissions still close the gate.

### Impact

The demo shows genuine strategy intents, risk decisions and 021 responses. A
provider rejection is visible as rejection, an accepted order remains open
until provider lifecycle evidence arrives, and portfolio/P&L changes only from
unique REST trade fills. This does not promise execution or profit.

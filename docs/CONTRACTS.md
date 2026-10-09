# Shared contracts

Shared-contract changes have one writer and affected-owner review under [TEAM_EXECUTION_PLAN](TEAM_EXECUTION_PLAN.md). Member 2 must establish verified sponsor schemas before provider-specific behavior is implemented. No financial or broker contract is changed by DEC-028.

Canonical executable definitions: `backend/shared/contracts.py`. Documentation describes them; modules must import them rather than create local variants.

## Bootstrap conventions

- UTC epoch seconds for timestamps; money is Decimal, persisted/JSON amounts are strings.
- Quantity is a positive integer; signed quantity uses Side.sign. BUY/SELL are canonical enums.
- `Tick`: symbol, event_timestamp, price, quantity (per-tick volume), event_id. Adapter must normalize cumulative volume if needed.
- `Candle`: symbol, interval (60/300 seconds), start_time, end_time, OHLCV, is_closed. Half-open UTC windows; no empty gap candles; no end-of-replay fabricated closure.
- `OrderIntent`: intent_id, strategy_instance_id, account_id, symbol, side, quantity, created_at, order_type, limit_price, reason. MARKET and LIMIT are accepted; LIMIT requires a positive Decimal limit_price.
- `RiskDecision`: intent_id, allowed, reason_code, projected_position, reason_text, rule_results, created_at, reservation_id. New fields have backward-compatible defaults. Approval indicates admission, **not broker acceptance**; inspect canonical order status.
- `CanonicalOrder`: order_id, intent, status, filled_quantity, derived remaining_quantity. Mock broker order ID equals intent ID; real adapter must retain explicit broker/client mapping.
- `Fill`: fill_id, broker_order_id, strategy_instance_id, account_id, symbol, side, quantity, price, timestamp, charges. IDs unique across configured provider/account; adapter must namespace them if broker IDs are only locally unique.
- `StrategyPosition`: strategy_instance_id, symbol, net_quantity, average_price, realized_pnl, unrealized_pnl, gross_pnl, charges, net_pnl. API adds account_id.
- `RiskPolicy`: finite positive Decimal max_daily_loss, positive integer max_position/max_orders_per_minute. Gateway mapping persists configurable policies by globally unique strategy ID; durable strategy_controls preserve manual/loss halts. Unconfigured strategies use documented defaults.
- Subscription rows: globally unique strategy instance ID, account, kind, symbol and durable `enabled` flag. Disabled subscriptions emit no callbacks and are rejected independently by risk. `READY` means enabled while the global runtime is stopped; it is not a claim of broker connectivity.
- Dashboard subscription commands never accept a client-selected account ID. The API derives `account_id` from the verified HttpOnly session created by login/registration; registration assigns `acc_<normalized username>` in the local bootstrap.
- `BrokerSnapshot`: orders/fills history and positions keyed by `(account_id,symbol)`, is_complete (defaults False), observed_at (optional provider UTC epoch time). Mock explicitly attests completeness. Query completion time is used if no provider timestamp exists; stale/uncertain/incomplete evidence blocks reconciliation. Real adapters must attest complete paginated history for the configured platform scope and keep provider-specific identity mapping inside the adapter.
- `KillCertificate`: status, elapsed_seconds, open_orders, broker_positions, virtual_positions_flat, reason. Unknown open count = -1, never verified safe.

## Broker identity boundary (DEC-027)

Platform order identity is the globally unique `OrderIntent.intent_id`, persisted
as orders.id and retained through cancellation, recovery and restart. Canonical
order/update/fill references use that platform identity, despite the historical
`Fill.broker_order_id` field name. Current in-process/HTTP mocks use the same ID
externally. An identical retry is idempotent at the adapter; reusing an ID for a
different intent/account is rejected without changing the original order.
Platform UNKNOWN submissions are never automatically retried.

A real adapter must resolve the compound `(provider, account, broker_order_id)`
to the platform ID; a raw broker string must never be an unrestricted alternate
lookup. Broker execution dedupe similarly requires provider/account scope if
raw execution IDs are not globally unique. Reject conflicting mappings, foreign
accounts, unknown IDs and unattributed executions; retain ambiguity and fail
closed. Do not map by symbol, quantity or timestamp similarity.

Persist a verified mapping before consuming dependent events; retain it over
restart. Cancellation translates platform ID to its matching scoped provider ID.
Events and complete snapshots normalize back to the same platform ID before
domain verification. Snapshot completeness, identity, executed quantity and
fill economics are independently checked. Missing mapping cannot certify safety.
No provider field, persistence schema or API is invented here; real mapping
implementation remains DEFERRED — DEPENDENCY on the authenticated 021 contract.
The tested mocks need no extra nullable broker-ID column or migration.

## Financial event capability boundary

| Evidence | Current support | Safety behavior |
|---|---|---|
| Unique attributed fill, attached nonnegative Decimal charges | Supported mock canonical contract | One fill-derived financial effect |
| Exact duplicate fill | Supported | Idempotent, no second charge/position effect |
| Conflicting duplicate economics | Supported containment | Preserve original; fail closed, no silent overwrite |
| Referenced execution correction or trade bust | Unsupported; 021 unknown | No automatic economics adjustment or invented replacement fill; quarantine/hold at future adapter boundary |
| Standalone later fee revision | Unsupported; 021 unknown | No final-live-net-P&L certification; require verified normalized evidence and a new accepted model |
| Missing execution history/unknown identity | Supported containment | Reconciliation cannot verify; no synthetic balancing fill |

Corrections require replacement-versus-delta rules, target identity, causal
ordering, session/fee treatment and replay fixtures before implementation.
Synthetic demo fees are not a statutory fee model.

## Interfaces and state transitions

`MarketDataProvider.ticks() -> Iterable[Tick]`.
`BrokerAdapter.submit(intent) -> CanonicalOrder`, `cancel(order_id)`, `snapshot() -> BrokerSnapshot`.
Mock exposes `execute(...)` for deterministic fill injection; it is not part of the real broker interface. 021 adapter placeholders raise NotImplementedError.

Order: RESERVED -> OPEN / REJECTED / UNKNOWN; OPEN -> PARTIALLY_FILLED -> FILLED, or CANCELLED. Authoritative zero-fill rejection may move OPEN to REJECTED; filled rejection is forbidden. Late evidenced executions may increase executed quantity after cancel; full evidence produces FILLED. Snapshot confirmation resolves UNKNOWN. Order statuses never create financial state without fills.

Global: RECOVERING -> STOPPED after successful reconciliation -> RUNNING (or explicit REDUCE_ONLY) after resume; uncertainty -> UNCERTAIN; kill -> KILLING -> KILLED or UNCERTAIN. Health: RECOVERING / HEALTHY / DEGRADED / DRIFTED. REDUCE_ONLY admits only a non-reversing close with zero pending exposure for that strategy/symbol. Runtime.enabled is actual callback state, not broker connectivity proof.

Audit schema: durable monotonic sequence, type, JSON payload, recorded_at UTC epoch timestamp; relevant state change and audit commit together. Legacy rows have recorded_at=0 (unknown). API state adds safety and risk_budgets to its real state projection.
Strategy signal, sanitized callback-failure and rejected-market-data events provide durable Member 4 evidence. API state also exposes subscriptions, positions, orders, fills, candles, signals, callback errors, market-data counters, audit, kill and explicit mode.

## Strategy Callback Execution Contract

- Callbacks execute strictly outside `store.lock` with bounded execution (`callback_timeout`, default 0.5s) and bounded concurrency (`max_workers`).
- Workers are strictly isolated: callback workers never receive store locks, SQLite connections, broker authority, or runtime mutation capability. Workers compute pure candidate signals over isolated working state copies and return candidate results to the control plane.
- The control plane thread validates and commits candidate results: state updates and order intents are committed ONLY if the originating run remains valid upon completion (matching subscription generation, enabled subscription, active runtime epoch, unhalted risk gate, and monotonic candle ordering). Timed-out or invalidated results cannot mutate runtime or persistent state.
- Bounded shutdown: `StrategyRuntime.close()` invalidates pending results and cancels queued futures without unbounded thread waiting (`shutdown(wait=False, cancel_futures=True)`). Late callback releases after store closure execute zero database calls and trigger no access violations.
- Same-instance serialization: callbacks for the same subscription instance serialize sequential indicator updates without allowing a timed-out worker to retain locks needed by `kill`, `set_enabled` (stop/re-enable), `close`, or healthy strategies. Timeouts and subscription state changes provision fresh instance locks.
- Timed-out callbacks are durably quarantined (`enabled=0`, audit `STRATEGY_CALLBACK_FAILED` with `TimeoutError`); healthy subscriptions continue processing.
- Bounded concurrency limits active threads: repeated hangs cannot create unlimited workers.
- Trusted callback limit: threads provide latency isolation and fail-closed timeout bounding; they are not an arbitrary-code security sandbox against CPU spinning or malicious bytecode.

## Candle and Market Data Processing Contract

- **Timestamp Policy**: UTC epoch integer seconds. Half-open intervals `[start_time, end_time)` where `start_time <= event_timestamp < end_time`. Boundary ticks `t == end_time` strictly belong to the succeeding candle `[end_time, end_time + interval)`.
- **Volume Policy**: Per-tick volume (`tick.quantity >= 0`). Candle volume is the sum of per-tick quantities ingested within the bucket. Adapters and providers must normalize cumulative volume into incremental per-tick volume if needed. Zero-volume ticks update OHLC without increasing volume. Negative volume is rejected as invalid tick.
- **Gap Policy**: Missing intervals create no invented gap candles. A candle closes only upon the arrival of the first subsequent tick in a later bucket. Incomplete candles are never closed artificially at end of feed or replay.
- **Deduplication Policy**: Idempotent symbol-scoped deduplication (`(symbol, event_id)`). Identical duplicates return `False`, increment `duplicate_ticks`, and modify neither active candles nor ledger marks. Conflicting duplicates (differing price/quantity/timestamp for the same ID) raise `ValueError("conflicting duplicate tick")`, audit `MARKET_DATA_REJECTED` (`CONFLICTING_DUPLICATE`), and fail closed with `MARKET_EVENT_REJECTED`.
- **Late-Tick Policy**: Ticks with `event_timestamp < last_event_timestamp[symbol]` are rejected with `ValueError("late tick: replay must be ordered before ingestion")`, audit `MARKET_DATA_REJECTED` (`LATE_TICK`), increment `late_ticks`, and fail closed. Evicted ticks from the bounded dedupe cache cannot be silently re-ingested or double-counted because their timestamps precede the advance watermark.
- **Incomplete Candle Policy**: Incomplete/active candles remain unclosed and are never dispatched to strategy callbacks or signal generation until closed by a subsequent bucket crossing.


## Risk reasons

ALLOWED, RISK_GLOBAL_GATE, RISK_DUPLICATE_INTENT, RISK_NOT_SUBSCRIBED, RISK_STRATEGY_STOPPED, RISK_MAX_DAILY_LOSS, RISK_RATE_LIMIT, RISK_MAX_POSITION.

RISK_STRATEGY_HALTED blocks manually/loss halted strategy instances. GlobalTradingState, StrategyState and ReconciliationState add typed names without renaming existing values. Policy PUT and strategy-control PUT are authoritative local development API actions. Budgets report directional capacity, not an assumption that opposite pending orders offset.

RISK_NO_HEALTH_EVIDENCE, RISK_RECONCILIATION_REQUIRED, RISK_STALE_BROKER_STATE, RISK_STALE_MARKET_DATA, RISK_NOT_REDUCING. LIVE source event age and receive age both matter; labeled offline REPLAY uses receive age. Broker verification defaults to max age 5s; market freshness defaults to 15s. Persisted marks retain loss input, but do not establish fresh broker truth after restart.

Kill latch/certificate and last reconciliation report persist in risk-owned safety_values. Startup always resets operational gate/health to RECOVERING. `/api/kill/reset` requires a new complete reconciliation, no open orders and zero broker/virtual positions, leaves STOPPED and never auto-resumes. Certificate remains historical after reset. Read freshness fields before treating historical reports as current evidence.

No module may rename fields silently. Limit/modify, external positions, typed health/audit envelopes and real broker events are coordinated contract extensions, not fabricated 021 behavior.

Orders persist dispatch_started: new reservations are 0; dispatch commits UNKNOWN/1 before the external call. Never-dispatched rejected reservations need not exist at the broker. A complete settled snapshot may resolve an absent UNKNOWN as rejected/0, never retry it automatically. BrokerSession bounds waits and blocks mutations after uncertain calls until reconciliation. Emergency orders require risk authorization of actual reducing strategy exposure and are permitted only under the latched KILLING gate. Kill uses a nine-second deadline and verifies cancellation/fills/flatness in repeated rounds.

## Broker Adapter Contract

Every broker adapter (including `MockBrokerAdapter` and the eventual `Broker021Adapter`) must satisfy this minimum behavioral contract:

1. **Operations Provided**:
   - `submit(intent: OrderIntent) -> CanonicalOrder`: Dispatches an approved order intent; returns canonical order state. Must preserve intent attribution (strategy, account, symbol, side, quantity).
   - `cancel(order_id: str) -> None`: Cancels open or partially filled order. Must never undo or reverse already executed fills.
   - `snapshot() -> BrokerSnapshot`: Provides complete authoritative view of orders, fills, and net positions. `is_complete` must be explicitly attested.
   - `drain_updates() -> list[BrokerUpdate]`: Exposes canonical broker-originated updates (`ORDER_ACCEPTED`, `ORDER_REJECTED`, `ORDER_CANCELLED`, `ORDER_STATUS`, `FILL`).
   - `disconnect() / reconnect()`: Explicit connection lifecycle. Operations must fail safely when disconnected rather than fabricating success.
2. **Attribution & Mapping Invariants**:
   - Deterministic mapping from broker evidence back to the original approved `intent_id`.
   - Fills must possess stable, unique identifiers suitable for idempotent deduplication.
   - Partial fills must accurately report `filled_quantity` and remaining quantity.
   - A real adapter (`Broker021Adapter`) must translate broker-specific payloads (e.g. 021 JSON schemas) into AlgoShield's canonical contracts inside the adapter; raw provider payloads must never leak into execution, risk, or accounting modules.

## Strategy Runtime Lifecycle and Interval Routing Contract

1. **Registration & Validation**:
   - `register_strategy(kind, handler, *, interval=60, warmup=5, description="")`:
     Requires non-empty string `kind`, callable `handler`, and strict positive integers (`type is int and val > 0`) for both `interval` and `warmup`.
   - Dynamic registration wires the interval into `CandleBuilder.add_interval(interval)` via `StrategyRuntime.on_interval_registered`.
2. **Interval Routing**:
   - Closed candles are routed strictly to subscriptions registered for that candle's interval (`candle.interval == registered_interval`). Mismatched intervals are skipped before worker thread allocation or callback execution.
3. **Execution & Commit Serialization**:
   - Process each closed candle at most once per strategy run (`(strategy_id, generation)`). Duplicate candles (`start_time == last_processed`) and older out-of-order candles (`start_time < last_processed`) are rejected prior to worker dispatch.
   - Candidate indicator state commits are serialized under `_state_lock`. If callbacks complete out of order, older candle results (`start_time <= last_committed`) cannot overwrite newer indicator states.
4. **Lifecycle & Epoch Invalidation**:
   - A monotonic `_global_epoch` counter invalidates in-flight results across global stop, resume, kill, and broker recovery boundaries, even if the runtime is re-enabled before the callback worker finishes execution.
   - Stopping/re-enabling an individual subscription increments its `_subscription_generations`, invalidates in-flight callback results, and completely resets indicator warmup (`samples = 0, ready = False`).
   - Process restarts start with empty in-memory indicator states, requiring full warmup before risk-increasing order intents may be emitted.
5. **Readiness & Sample Counting**:
   - `readiness_for(strategy_id)` exposes `samples`, `warmup`, and `ready` (`samples >= warmup`).
   - Momentum: EMA sample count, warmup 5.
   - Mean reversion: close count in deque, warmup 5.
   - Breakout: previous range established, warmup 1.
   - RSI reversal: 15 closed candles required to calculate 14 price changes, warmup 15.
   - Subscription snapshots project `readiness` for UI telemetry.
6. **Kill Deadline & Admission Idempotency**:
   - `Platform.kill(deadline_seconds, deadline_clock)` measures total execution time starting before admission closure and joins `_replay_thread` bounded by `min(1.0, deadline.remaining)`.
   - Remaining deadline is passed directly into `reliability.kill(deadline=deadline)`. If the deadline budget is already exhausted (`deadline is None or not deadline.remaining`), `kill` returns a truthful failure certificate (`status="FAILED", reason="KILL_DEADLINE_EXPIRED"`) rather than raising a `ValueError` from `Deadline`.
   - Admission closure (`kill_requested.set()`, `kill_latched=True`, `risk.state=KILLING`, `strategies.enabled=False`, `invalidate_in_flight()`) is strictly idempotent.

## Market Session and Execution Hours Contract

1. **Timezone & Representation**:
   - Trading session timestamps are evaluated in `Asia/Kolkata` (`UTC+05:30`).
   - UTC epoch timestamps are converted to `Asia/Kolkata` time using `datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Kolkata"))` before comparing against session boundary seconds.
2. **Session Boundaries**:
   - Continuous market hours use a half-open interval `[open_time_seconds, close_time_seconds)` (`09:15:00 <= t < 15:30:00 IST`).
   - Exact open (`09:15:00 IST`) is evaluated as `OPEN`.
   - Exact close (`15:30:00 IST`) and later is evaluated as `CLOSED`.
   - Before open (`09:14:59 IST`) is evaluated as `CLOSED`.
3. **Mock Replay & Enforcement**:
   - `MarketSession(enforce_hours=False)` is the default to support offline mock replay across all hours.
   - When `enforce_hours=True`, missing timestamps (`timestamp is None` with no injected clock) fail closed (`is_open() -> False`, `status_at() -> "CLOSED"`). A missing timestamp must never silently imply `OPEN`.
4. **State Machine & Precedence Consistency**:
   - Status values: `OPEN`, `CLOSED`, `HALTED`, `AUTO`.
   - `HALTED` takes precedence over manual `OPEN` and scheduled hours.
   - Manual `OPEN` forces open state when not halted.
   - Manual `CLOSED` forces closed state even during market hours.
   - Manual `AUTO` clears manual status and delegates strictly to scheduled hours.
   - Consistency is preserved across `is_open()`, `status_at()`, `to_dict()` snapshot projection, and `Reliability.check_evidence()` (`RISK_MARKET_HALTED` vs `RISK_MARKET_CLOSED`).
5. **No Invented Provider Behaviors**:
   - Exchange holidays, special muhurat sessions, and unverified 021 sandbox session rules are not invented. Boundary checks are deterministic and configurable.

## Optional Yahoo External Quote Contract

1. **Opt-in and source separation**:
   - Replay remains the default. Yahoo is enabled only with `ALGOSHIELD_MARKET_DATA_PROVIDER=yahoo` and the optional `yahoo` dependency extra.
   - The supported external mapping is explicit: `TCS.NS -> TCS`, `INFY.NS -> INFY`. Other Yahoo symbols fail validation.
   - Replay and Yahoo updates cannot share one running candle timeline. Yahoo is restricted to mock execution and cannot authorize 021 execution.
2. **Normalization**:
   - A Yahoo message requires a supported `id`, finite positive `price`, and plausible decimal-string Unix-millisecond `time` near receipt time.
   - Price is converted with `Decimal(str(value))`. `Tick.event_timestamp` is normalized to UTC epoch seconds and `Tick.raw_event_timestamp` preserves the original decimal string.
   - `Tick.data_source` is `YAHOO_EXTERNAL_QUOTES`. Updates enter the system exclusively through `Platform.tick(..., replay=False)` and therefore use existing LIVE freshness evidence.
3. **Price-only and candle evidence**:
   - `day_volume` and `last_size` have unconfirmed semantics and are never mapped to `Tick.quantity`.
   - Canonical `quantity=0` represents a price-only update only when `volume_available=False`. Quote-derived candles retain numeric volume 0 for contract compatibility while `volume_available=False`; UI/API consumers must display that volume as unavailable, not as observed zero volume.
   - Quote-derived candles carry `data_source=YAHOO_EXTERNAL_QUOTES`. They are sampled quote evidence, not verified complete exchange-tick candles.
4. **Duplicate identity**:
   - The adapter hashes available message fields into a bounded best-effort duplicate key with a bounded LRU set. The generated `yahoo-quote:*` value is not an exchange trade ID, and no unique provider trade/message ID is claimed.
5. **Lifecycle and failure behavior**:
   - yfinance runs in a supervised child process and communicates through a bounded queue, so its callback cannot block strategy execution or hold the store lock.
   - Startup, reconnect attempts, staleness detection, stop, and forced termination are bounded. Queue overflow, disconnect, malformed data, startup timeout, or staleness invokes the existing fail-closed safety transition. Fresh messages do not automatically resume trading.
   - Telemetry exposes provider/label, connection state, configured Yahoo symbols, received and normalized event times (including raw timestamp), message/update/duplicate counts, volume availability, bounded errors, queue capacity, and forced-termination count.

## Account-Scoped User Workflow and Telemetry Isolation Contract

1. **Identity & Session Derivation**:
   - User identity (`account_id`) is strictly derived server-side from verified sessions (`engine.auth.verify_token`). Client-supplied `account_id` query parameters or JSON body fields are never trusted or permitted to override server session identity.
   - Anonymous requests to `/api/state`, `/api/orders`, `/api/fills`, `/api/subscriptions`, `/api/risk/budgets`, `/api/stream/ws`, and `/api/stream/telemetry` return HTTP 401 Unauthorized (or WS close code 1008). No anonymous compatibility fallback is permitted.
2. **Server-Side Projection Scoping & Leak Elimination**:
   - `Platform.snapshot(account_id=...)` returns strictly filtered projections when `account_id` is supplied:
     - Subscriptions: only subscriptions belonging to the caller's `account_id`.
     - Positions: only positions where `account_id == user.account_id`.
     - Risk budgets: only budgets matching the caller's strategy instances (`account == user.account_id`).
     - Orders and fills: only records attributed to the caller's `account_id`.
     - Signals and strategy callback errors: only events attributed to the caller's `account_id` / strategies.
     - Audit events: only events where `account == user.account_id` or `strategy` belongs to the user's subscriptions. Nested payloads with `broker_positions` are sanitized to strip other accounts.
     - Safety evidence:
       - Virtual positions and broker positions: only records where `account_id == user.account_id`.
       - Position comparison: preserves raw `UNKNOWN` or `FAILED` status; filtering never converts uncertainty into a safety pass.
       - Reconciliation report: `broker_positions` and `unexplained_positions` filtered to `account_id`; `orders`, `unique_fills`, `open_orders`, `duplicate_snapshot_fills`, and `unattributed_fills` describe the verified snapshot at `observed_at` sourced from `accounts[account_id]`. If verified account breakdown is absent or unverified, reconciliation counts report `null` rather than substituting live local counts. Honest global verification flags (`verified`, `reason`, `observed_at`) are preserved.
       - Kill certificate: historical evidence is strictly preserved. `open_orders`, `virtual_positions_flat`, `status`, and `reason` reflect the verified historical certificate at kill time and are never rewritten with current account state (later trades do not alter historical certificates, and failed kills retain uncertainty). `broker_positions` dictionary is filtered strictly to keys starting with `f"{account_id}/"`.
       - Fill counters: `unique_applied`, `duplicates_ignored`, and `rejected_events` scoped strictly to the caller's account; `unattributed_in_last_verified_snapshot` is sourced from verified account breakdown at `observed_at` (returns 0 only when verified to be 0; returns `null`/unknown if unattributed fills exist, snapshot is unverified, or account evidence is missing). Never hardcoded to 0.
       - Unknown orders: filtered strictly by `account == user.account_id`.
3. **Subscription Mutation Authorization**:
   - `POST /api/subscriptions` creates subscriptions attributed to the caller's session `account_id` and returns user-scoped subscription list.
   - `POST /api/subscriptions/{strategy_instance_id}/start` and `/stop` verify ownership:
     - Unknown strategy instance ID returns HTTP 404 Not Found.
     - Strategy instance belonging to a different account returns HTTP 403 Forbidden with zero mutation.
     - Valid request returns user-scoped subscriptions.
4. **Streaming Telemetry Authentication & Eviction**:
   - WebSocket (`/api/stream/ws`) and SSE (`/api/stream/telemetry`) require valid authentication prior to transmitting any data.
   - Streaming loops continuously revalidate the session token before pushing snapshots.
   - Upon user logout or session expiration, SSE streams terminate immediately and WebSockets close with status code 1008 (`WS_1008_POLICY_VIOLATION`).
5. **Stale UI Clearance on Invalidation**:
   - On HTTP 401 responses or WebSocket close code 1008, the React providers clear the current account snapshot, clearing subscriptions, positions, orders, fills, signals, errors, budgets, and safety indicators, and redirects to `/login`.
6. **Historical pre-DEC-026 authorization gap**:
   - Ownership: Member 3 (Ram) owns risk, security, reliability, global trading gates, kill switch, and platform-level reconciliation. Member 1 (Akshat) owns accounting, fill ledgers, and financial positions. Member 4 owns market data, strategy runtimes, and user workflow.
   - The following list records the earlier gap inventory. DEC-026 supersedes it: global mutations now require durable operator authority; own strategy policies/controls and order cancellation require ownership. Current rules and provisioning are in SECURITY_OPERATIONS.md.
     - `PUT /api/risk/policies/{strategy}` (risk policy modifications)
     - `PUT /api/risk/strategies/{strategy}` (manual strategy halt/resume)
     - `POST /api/reconcile` (platform-wide broker reconciliation trigger)
     - `POST /api/resume` (global gate resume)
     - `POST /api/reduce-only` (global gate reduce-only)
     - `POST /api/kill/reset` (kill latch reset)
     - `POST /api/kill` (emergency platform kill)
     - `POST /api/failure-lab/{scenario}` (synthetic failure injection)
     - `POST /api/broker/disconnect` (manual broker disconnect)
     - `POST /api/broker/reconnect` (manual broker reconnect)
     - `POST /api/broker/updates/sync` (broker event sync)
     - `POST /api/orders/{order_id}/cancel` (order cancellation without caller ownership check)
     - `POST /api/market/session` (market session override)
     - `POST /api/demo` (replay stream trigger)
     - `POST /api/accounts` (unauthenticated account creation)

## Evidence and operations contract

- Account risk and limit-price checks run inside the serialized risk gateway; strategies cannot bypass them.
- Safety Proof and execution traces are server-built, read-only projections of persisted evidence. Missing evidence is reported as `UNKNOWN`, never inferred as safe.
- Reconciliation reports include position differences and recovered fill identifiers. Recovery never manufactures fills.
- Kill certificates retain stage timings and final broker/virtual evidence. A successful certificate still requires verified flat state within the deadline.
- Operational metrics are bounded, process-local diagnostics and are not financial truth. SafetyBench uses an isolated SQLite/mock platform and is disabled for PostgreSQL and non-mock providers.
- Failure injection remains local mock-only. No endpoint claims real 021 connectivity while provider details remain unknown.

## React presentation contract

- Browser sessions use the HttpOnly cookie through `credentials: include`; no token is stored in local storage.
- Protected routes render no account data until `/api/auth/me` succeeds. HTTP 401 or WebSocket close 1008 clears the current snapshot.
- One telemetry provider owns `/api/stream/ws`, reconnects with a bounded backoff, and refreshes from `/api/state`; pages do not open independent streams.
- Mutations wait for backend responses and then refresh backend state. They never optimistically set `VERIFIED`, `MATCHED`, `SUCCESS`, positions, P&L, or fill status.
- `FAILED`, `UNKNOWN`, and `SAFE_LATE` are displayed verbatim and must not be mapped to successful labels.
- Failure Lab choices come from authenticated `GET /api/failure-lab/scenarios`; strategy choices come from `GET /api/strategies`. The UI must not maintain duplicate capability lists.
- Nested backend evidence is rendered as labeled fields, lists, and status indicators. Raw JSON is not the user-facing representation.

## DEC-026 current authorization contract

Verified sessions include is_operator (0/1), resolved from durable operator_grants on each request. No public API grants authority. Anonymous global actions return 401; authenticated ordinary users return 403 before mutation. Operators may execute global controls but account-facing responses still exclude other accounts. Own policy/start/stop/cancel actions remain owner-only even for operators. AccountResponseScope is the shared nested projection; unknown/unowned trace access is denied. Exceptions from global domain operations expose a generic conflict message rather than broker/private IDs. SQLite v12 and PostgreSQL migration 011 add only operator_grants; earlier migration files are immutable. Global gate/health/verdict, historical kill status/timing and aggregate diagnostics are explicitly permitted, while financial/identity records remain scoped. See SECURITY_OPERATIONS.md for provisioning and current environment limits.

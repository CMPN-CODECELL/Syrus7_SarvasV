# Shared contracts

Canonical executable definitions: `backend/shared/contracts.py`. Documentation describes them; modules must import them rather than create local variants.

## Bootstrap conventions

- UTC epoch seconds for timestamps; money is Decimal, persisted/JSON amounts are strings.
- Quantity is a positive integer; signed quantity uses Side.sign. BUY/SELL are canonical enums.
- `Tick`: symbol, event_timestamp, price, quantity (per-tick volume), event_id. Adapter must normalize cumulative volume if needed.
- `Candle`: symbol, interval (60/300 seconds), start_time, end_time, OHLCV, is_closed. Half-open UTC windows; no empty gap candles; no end-of-replay fabricated closure.
- `OrderIntent`: intent_id, strategy_instance_id, account_id, symbol, side, quantity, created_at, order_type, limit_price, reason. MARKET only in bootstrap.
- `RiskDecision`: intent_id, allowed, reason_code, projected_position, reason_text, rule_results, created_at, reservation_id. New fields have backward-compatible defaults. Approval indicates admission, **not broker acceptance**; inspect canonical order status.
- `CanonicalOrder`: order_id, intent, status, filled_quantity, derived remaining_quantity. Mock broker order ID equals intent ID; real adapter must retain explicit broker/client mapping.
- `Fill`: fill_id, broker_order_id, strategy_instance_id, account_id, symbol, side, quantity, price, timestamp, charges. IDs unique across configured provider/account; adapter must namespace them if broker IDs are only locally unique.
- `StrategyPosition`: strategy_instance_id, symbol, net_quantity, average_price, realized_pnl, unrealized_pnl, gross_pnl, charges, net_pnl. API adds account_id.
- `RiskPolicy`: finite positive Decimal max_daily_loss, positive integer max_position/max_orders_per_minute. Gateway mapping persists configurable policies by globally unique strategy ID; durable strategy_controls preserve manual/loss halts. Unconfigured strategies use documented defaults.
- Subscription rows: globally unique strategy instance ID, account, kind, symbol and durable `enabled` flag. Disabled subscriptions emit no callbacks and are rejected independently by risk. `READY` means enabled while the global runtime is stopped; it is not a claim of broker connectivity.
- Dashboard subscription commands never accept a client-selected account ID. The API derives `account_id` from the verified HttpOnly session created by login/registration; registration assigns `acc_<normalized username>` in the local bootstrap.
- `BrokerSnapshot`: orders/fills history and positions keyed by `(account_id,symbol)`, is_complete (defaults False), observed_at (optional provider UTC epoch time). Mock explicitly attests completeness. Query completion time is used if no provider timestamp exists; stale/uncertain/incomplete evidence blocks reconciliation. Real adapters must attest complete paginated history for the configured platform scope and keep provider-specific identity mapping inside the adapter.
- `KillCertificate`: status, elapsed_seconds, open_orders, broker_positions, virtual_positions_flat, reason. Unknown open count = -1, never verified safe.

## Interfaces and state transitions

`MarketDataProvider.ticks() -> Iterable[Tick]`.
`BrokerAdapter.submit(intent) -> CanonicalOrder`, `cancel(order_id)`, `snapshot() -> BrokerSnapshot`.
Mock exposes `execute(...)` for deterministic fill injection; it is not part of the real broker interface. 021 adapter placeholders raise NotImplementedError.

Order: RESERVED -> OPEN / REJECTED / UNKNOWN; OPEN -> PARTIALLY_FILLED -> FILLED, or CANCELLED. Late evidenced executions may increase executed quantity after cancel; full evidence produces FILLED. Snapshot confirmation resolves UNKNOWN. Order statuses never create financial state without fills.

Global: RECOVERING -> STOPPED after successful reconciliation -> RUNNING (or explicit REDUCE_ONLY) after resume; uncertainty -> UNCERTAIN; kill -> KILLING -> KILLED or UNCERTAIN. Health: RECOVERING / HEALTHY / DEGRADED / DRIFTED. REDUCE_ONLY admits only a non-reversing close with zero pending exposure for that strategy/symbol. Runtime.enabled is actual callback state, not broker connectivity proof.

Audit schema: durable monotonic sequence, type, JSON payload, recorded_at UTC epoch timestamp; relevant state change and audit commit together. Legacy rows have recorded_at=0 (unknown). API state adds safety and risk_budgets to its real state projection.
Strategy signal, sanitized callback-failure and rejected-market-data events provide durable Member 4 evidence. API state also exposes subscriptions, positions, orders, fills, candles, signals, callback errors, market-data counters, audit, kill and explicit mode.

## Strategy Callback Execution Contract

- Callbacks execute strictly outside `store.lock` with bounded execution (`callback_timeout`, default 0.5s) and bounded concurrency (`max_workers`).
- Timed-out callbacks are durably quarantined (`enabled=0`, audit `STRATEGY_CALLBACK_FAILED` with `TimeoutError`); healthy subscriptions continue processing.
- Candidate indicator updates run on isolated working state. Indicator state is committed and intents emitted ONLY if the originating run remains valid upon completion (matching subscription generation, active subscription, enabled runtime, and unhalted gate).
- Late completions after timeout, stop/re-enable, global stop, or kill are discarded with zero state or order mutations.
- Workers receive only plain subscription metadata and immutable candles; they never receive store locks or broker authority.
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
   - Remaining deadline is passed directly into `reliability.kill(deadline_seconds=deadline.remaining)`.
   - Admission closure (`kill_requested.set()`, `kill_latched=True`, `risk.state=KILLING`, `strategies.enabled=False`, `invalidate_in_flight()`) is strictly idempotent.

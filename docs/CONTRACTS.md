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
- `StrategyPosition`: strategy_instance_id, symbol, net_quantity, average_price, realized_pnl, unrealized_pnl, charges, net_pnl. API adds account_id.
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

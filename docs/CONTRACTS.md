# Shared contracts

Canonical executable definitions: `backend/shared/contracts.py`. Documentation describes them; modules must import them rather than create local variants.

## Bootstrap conventions

- UTC epoch seconds for timestamps; money is Decimal, persisted/JSON amounts are strings.
- Quantity is a positive integer; signed quantity uses Side.sign. BUY/SELL are canonical enums.
- `Tick`: symbol, event_timestamp, price, quantity (per-tick volume), event_id. Adapter must normalize cumulative volume if needed.
- `Candle`: symbol, interval (60/300 seconds), start_time, end_time, OHLCV, is_closed. Half-open UTC windows; no empty gap candles; no end-of-replay fabricated closure.
- `OrderIntent`: intent_id, strategy_instance_id, account_id, symbol, side, quantity, created_at, order_type, limit_price, reason. MARKET only in bootstrap.
- `RiskDecision`: intent_id, allowed, reason_code, projected_position. Approval indicates admission, **not broker acceptance**; inspect canonical order status.
- `CanonicalOrder`: order_id, intent, status, filled_quantity, derived remaining_quantity. Mock broker order ID equals intent ID; real adapter must retain explicit broker/client mapping.
- `Fill`: fill_id, broker_order_id, strategy_instance_id, account_id, symbol, side, quantity, price, timestamp, charges. IDs unique across configured provider/account; adapter must namespace them if broker IDs are only locally unique.
- `StrategyPosition`: strategy_instance_id, symbol, net_quantity, average_price, realized_pnl, unrealized_pnl, charges, net_pnl. API adds account_id.
- `RiskPolicy`: max_daily_loss, max_position, max_orders_per_minute. Gateway dictionary keyed by globally unique strategy instance ID. Bootstrap defaults reset on restart; editable durable policies are pending.
- Subscription rows: globally unique strategy instance ID, account, kind, symbol and durable `enabled` flag. Disabled subscriptions emit no callbacks and are rejected independently by risk. `READY` means enabled while the global runtime is stopped; it is not a claim of broker connectivity.
- `BrokerSnapshot`: complete orders/fills history and positions keyed by `(account_id,symbol)`. Adapter must reject incomplete/uncertain snapshots rather than return an empty success.
- `KillCertificate`: status, elapsed_seconds, open_orders, broker_positions, virtual_positions_flat, reason. Unknown open count = -1, never verified safe.

## Interfaces and state transitions

`MarketDataProvider.ticks() -> Iterable[Tick]`.
`BrokerAdapter.submit(intent) -> CanonicalOrder`, `cancel(order_id)`, `snapshot() -> BrokerSnapshot`.
Mock exposes `execute(...)` for deterministic fill injection; it is not part of the real broker interface. 021 adapter placeholders raise NotImplementedError.

Order: RESERVED -> OPEN / REJECTED / UNKNOWN; OPEN -> PARTIALLY_FILLED -> FILLED, or CANCELLED. Late evidenced executions may increase executed quantity after cancel; full evidence produces FILLED. Snapshot confirmation resolves UNKNOWN. Order statuses never create financial state without fills.

Global: RECOVERING -> STOPPED after successful reconciliation -> RUNNING after explicit resume; uncertainty -> UNCERTAIN; kill -> KILLING -> KILLED or UNCERTAIN. Health: RECOVERING / HEALTHY / DRIFTED. Runtime.enabled is actual callback state, not broker connectivity proof.

Audit schema: durable monotonic sequence, type, JSON payload; relevant state change and audit commit together. UTC audit timestamps/event envelopes are a follow-up contract extension. Strategy signal, sanitized callback-failure and rejected-market-data events provide durable Member 4 evidence. API state is a read projection with gate, health, subscriptions, positions, orders, fills, candles, signals, callback errors, market-data counters, audit, kill and explicit mode.

## Risk reasons

ALLOWED, RISK_GLOBAL_GATE, RISK_DUPLICATE_INTENT, RISK_NOT_SUBSCRIBED, RISK_STRATEGY_STOPPED, RISK_MAX_DAILY_LOSS, RISK_RATE_LIMIT, RISK_MAX_POSITION.

No module may rename fields silently. Limit/modify, external positions, typed health/audit envelopes and real broker events are coordinated contract extensions, not fabricated 021 behavior.

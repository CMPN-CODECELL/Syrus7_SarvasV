# AlgoShield — 021 Trade Full Fixing & Implementation Plan

## Purpose

This plan fixes and completes the **021 Trade → AlgoShield backend → AlgoShield React frontend** integration in the current project baseline:

- Project baseline: `Syrus7_SarvasV(2).zip`
- Live broker/market provider: 021 Trade developer sandbox
- Existing architecture: FastAPI backend + React/Vite frontend
- Existing safety model: fail-closed, reconciliation-gated recovery, independent RiskGateway, durable audit trail
- Existing multi-stock model: one strategy instance per symbol

The goal is not to redesign AlgoShield. The goal is to make the existing 021 adapter layer **correct, reliable, observable, testable, and truly end-to-end**.

---

# 1. Definition of Done

The 021 integration is complete only when this exact flow passes:

```text
021 live market WebSocket
        ↓
canonical Tick
        ↓
CandleBuilder
        ↓
1m / 5m candles
        ↓
enabled StrategyRuntime instance
        ↓
Trade Intent
        ↓
RiskGateway
        ↓
021 REST order submission
        ↓
021 order/trade evidence
        ↓
BrokerUpdate / Fill
        ↓
OrderManager
        ↓
Position + P&L ledger
        ↓
Reconciliation
        ↓
FastAPI snapshot / telemetry
        ↓
React UI
```

For a controlled live test:

```text
RELIANCE live quote visible in React
→ candle created
→ strategy can evaluate
→ risk decision visible
→ one sandbox order can be submitted
→ order status/fill is ingested exactly once
→ local position matches broker position
→ P&L updates
→ reconciliation reports safe/known state
→ no duplicate-fill, overfill, stale-data, or silent-disconnect violations
```

The implementation must preserve AlgoShield's central invariant:

> **Failure must never silently increase risk.**

---

# 2. Current State

The current code already includes:

- `backend/market_data/official021.py`
  - live 021 market WebSocket provider
  - 100 instruments per socket
  - up to 20 sockets
  - binary frame parsing
  - timestamp fallback logic
  - cumulative-volume handling
  - live telemetry and latest quotes

- `backend/broker/official021.py`
  - wire-format parsing
  - 021 instrument contract
  - order/status normalization
  - market observation structures

- `backend/broker/official021_http.py`
  - authentication
  - instrument download/cache
  - REST order submit/modify/cancel
  - snapshot/reconciliation evidence
  - trade-to-fill normalization
  - ephemeral WebSocket key
  - order WebSocket connector/parser

- `backend/strategies/official021.py`
  - `time_0915_1515`
  - `open_1pct_tp5_sl5`

- `frontend/src/pages/EvidencePages.jsx`
  - live market data page
  - latest quote table
  - event/raw/receive timestamps
  - candles
  - watchlist
  - provider lifecycle errors

- tests:
  - `tests/test_official021.py`
  - `tests/test_official021_market_data.py`
  - `tests/test_official021_rest.py`

The architecture is sound. The remaining problems are primarily integration correctness, lifecycle management, order-event sequencing, and production wiring.

---

# 3. Confirmed High-Priority Problems

## P0-1 — Over-broad market universe

Current startup behavior in `backend/api.py`:

```text
ALGOSHIELD_021_SYMBOLS absent
        ↓
broker.all_market_symbols()
        ↓
entire cash-equity catalogue
        ↓
MarketData021Provider truncates to 2,000 symbols
```

This causes unnecessary sockets, load, random stock traffic, large telemetry, and makes debugging harder.

### Required behavior

The 021 subscription universe must be:

```text
explicit configured symbols
        +
symbols used by enabled strategy subscriptions
```

with deterministic deduplication.

The system must **never silently subscribe to thousands of symbols by default**.

### P0 minimum behavior

If no symbols are configured and there are no enabled strategy symbols:

- do not auto-subscribe to the whole exchange
- either:
  - start provider in idle/unsubscribed mode, or
  - refuse startup with a clear configuration message

Preferred hackathon behavior:

```text
enabled strategy subscriptions are source of truth
```

Optional explicit operator seed:

```env
ALGOSHIELD_021_SYMBOLS=RELIANCE,TCS
```

---

## P0-2 — Conflicting duplicate live snapshots

A real repeated 021 snapshot may have the same:

- exchange
- token
- event timestamp
- LTP
- cumulative volume

but current volume-state transitions can cause the normalized `Tick` to differ between first and second observation even while the generated event ID is identical.

That can become:

```text
same event_id
+
different canonical Tick
=
CONFLICTING_DUPLICATE
```

### Required fix

Deduplicate at the **021 observation boundary before building a canonical Tick**.

Maintain a per-instrument snapshot fingerprint:

```text
(exchange, token, raw exchange timestamp, LTP, cumulative volume, official open)
```

If the next observation fingerprint is identical:

```text
drop as benign provider duplicate
increment duplicate counter
do NOT call platform.tick()
do NOT fail closed
```

Important:

- repeated identical snapshots are not protocol errors
- a true event-ID collision with different economic data must still fail safely
- volume baseline state must not change the identity of an otherwise identical provider snapshot

Add telemetry:

```json
{
  "provider_duplicates_dropped": 123
}
```

---

## P0-3 — Timestamp normalization is too permissive

Current logic allows an exchange timestamp to differ from receive time by up to 24 hours.

For live trading, that is far too broad.

### Required model

Keep three timestamps:

```text
raw_event_timestamp
normalized_event_timestamp
received_at
```

Never discard raw evidence.

Create one central normalization function, for example:

```python
normalize_021_timestamp(
    raw_timestamp,
    received_at,
    prior_symbol_timestamp,
    max_clock_skew_seconds,
)
```

Recommended default:

```env
ALGOSHIELD_021_MAX_TIMESTAMP_SKEW_SECONDS=10
```

Configurable range may be 5–30 seconds.

Behavior:

1. no raw timestamp → use receive time
2. raw timestamp plausible and within skew → use raw timestamp
3. raw timestamp implausible / wrong epoch / far future / far past → use receive time
4. normalized timestamp goes backward for the same symbol → use monotonic receive-time-safe value
5. preserve raw timestamp in telemetry/audit
6. increment explicit fallback counters

Do not fail closed solely because 021 supplies a broken timestamp if reliable receive-time evidence exists.

Do fail closed if:
- no trustworthy time evidence exists, or
- market freshness cannot be established

Telemetry should expose:

```json
{
  "timestamp_fallbacks": 4,
  "timestamp_future_fallbacks": 2,
  "timestamp_past_fallbacks": 1,
  "timestamp_reorder_fallbacks": 1
}
```

---

## P0-4 — REST update ordering can emit FILLED before Fill

Current `Broker021Adapter.drain_updates()` processes order rows before trade fills.

This can produce:

```text
ORDER_STATUS(FILLED)
→ local filled quantity still 0
→ IllegalOrderTransition
→ FILL arrives afterward
```

### Required fix

Broker evidence must be applied in execution-safe order.

Preferred design:

1. fetch broker orders
2. fetch mapped trades
3. construct new fills
4. emit all unseen fills first
5. derive/emit status changes afterward

For a completely filled order:

```text
FILL(s)
→ local cumulative executed quantity reaches order quantity
→ FILLED status
```

Alternative:
- let fill application derive `PARTIALLY_FILLED` / `FILLED`
- suppress redundant FILLED status from polling

But retain:
- rejection
- cancellation
- acceptance/open
- unknown provider status evidence

### Required deduplication

Trade IDs remain authoritative fill identity:

```text
021:<tradeId>
```

Never apply the same fill twice across:
- REST polling
- reconnect
- reconciliation
- WebSocket status events

---

## P0-5 — Order WebSocket exists but is not started

Current adapter exposes:

```python
connect_order_websocket()
parse_order_update()
```

but no long-running worker consumes it.

### Required implementation

Add a dedicated order-event provider/worker.

Suggested file:

```text
backend/broker/official021_order_stream.py
```

or keep lifecycle code close to the adapter if architecture conventions prefer that.

Responsibilities:

```text
start
→ obtain ephemeral key
→ connect to /api/developer/websocket/orders
→ receive binary frames
→ parse order event
→ resolve provider order ID → platform order ID
→ enqueue normalized BrokerUpdate
→ update telemetry
→ reconnect safely when disconnected
→ never manufacture fills when WS packet lacks reliable trade identity
```

Important:
- the organizer's order stream can update order state
- REST trade evidence remains authoritative for exact fill identity unless the documented WS packet contains a reliable unique trade ID
- WebSocket status should accelerate UI/state awareness, not invent fills

### Integration

`BrokerSession.drain_updates()` must receive:
- queued WebSocket status updates
- authoritative unseen REST fills/status evidence

Provide deterministic merging/deduplication.

---

## P0-6 — Market WebSocket reconnect/resubscribe is missing

A connection ending currently fails closed and exits the worker.

Fail-closed behavior is correct. Permanent thread death is not.

### Required lifecycle

For every socket chunk:

```text
CONNECTED
    ↓
receive
    ↓
disconnect / protocol transport error
    ↓
fail closed immediately
    ↓
mark provider degraded
    ↓
backoff
    ↓
obtain fresh ephemeral key if needed
    ↓
reconnect
    ↓
resubscribe current symbol chunk
    ↓
perform/read broker reconciliation
    ↓
remain STOPPED/UNCERTAIN
    ↓
operator explicitly resumes only after safe evidence
```

Reconnect must **never automatically reopen the trading gate**.

### Recommended backoff

```text
1s → 2s → 5s → 10s → cap 30s
```

with bounded jitter optional.

Expose:

```json
{
  "reconnect_attempts": 3,
  "last_disconnect_reason": "...",
  "last_connected_at": ...,
  "last_disconnected_at": ...
}
```

---

# 4. Dynamic Multi-Stock Subscription Architecture

## Problem

Current 021 market symbols are mostly determined at startup.

But AlgoShield supports:

```text
one strategy kind + N stocks
→ N independent strategy instances
```

If a user later enables:

```text
Momentum → INFY
```

the live feed must start supplying INFY without restarting the backend.

## Required architecture

Introduce a symbol-universe manager.

Suggested component:

```text
backend/market_data/universe.py
```

Responsibilities:

- query enabled strategy subscriptions
- merge explicit operator-pinned 021 symbols
- normalize/dedupe canonical symbols
- validate against 021 instrument catalogue
- compare desired universe vs currently subscribed universe
- apply subscribe/unsubscribe deltas
- respect 021 limits

Conceptually:

```text
enabled subscriptions
       ↓
{RELIANCE, TCS, INFY}
       ↓
desired universe
       ↓
current universe {RELIANCE,TCS}
       ↓
subscribe INFY
```

When a strategy is disabled:

```text
if no other enabled strategy needs symbol
and symbol is not pinned
→ unsubscribe it
```

## Socket allocation

Do not rebuild every connection for every single symbol change unless necessary.

Maintain:
- up to 100 instruments/socket
- max 20 sockets
- deterministic chunk/socket membership where possible

For hackathon simplicity, a controlled rebuild of market sockets after universe change is acceptable if:
- trading fails closed during rebuild
- reconnect + reconciliation occurs
- explicit resume is required

A more advanced delta subscribe/unsubscribe implementation is optional.

---

# 5. 021 Official Strategy Runtime Integration

The current official strategy classes exist but are not registered in normal runtime.

Current registry:

```text
momentum
mean_reversion
breakout
rsi_reversal
```

Required additions:

```text
time_0915_1515
open_1pct_tp5_sl5
```

## Do not merely add names to `KINDS`

These strategies require additional context beyond ordinary candle close:

### `time_0915_1515`
Needs:
- Asia/Kolkata session time
- market-session state
- broker evidence freshness
- strategy-attributed residual position
- safe account square-off bound

### `open_1pct_tp5_sl5`
Needs:
- verified 021 `official_open`
- current LTP
- actual entry fill WAP
- residual strategy-attributed position
- entry-order-open state
- broker evidence freshness

## Preserve official open

`MarketObservation021.official_open` currently exists.

Do not discard it.

Add a durable/current quote state accessible to strategies, for example:

```text
MarketEvidenceStore:
  symbol
  ltp
  official_open
  raw timestamp
  normalized timestamp
  received_at
  source
```

This can be in-memory for hot state with audit/snapshot evidence where appropriate.

Then `StrategyRuntime` should obtain verified market evidence through a stable interface rather than importing the provider directly.

---

# 6. Broker Call Timeout Fix

Current:

```python
BrokerSession(adapter, call_timeout=1.0)
```

This is too short for multi-call 021 reconciliation.

## Required split

Do not use one timeout for every broker operation.

Add configuration such as:

```env
ALGOSHIELD_BROKER_READ_TIMEOUT_SECONDS=8
ALGOSHIELD_BROKER_WRITE_TIMEOUT_SECONDS=8
ALGOSHIELD_RECONCILIATION_TIMEOUT_SECONDS=10
```

Keep emergency kill deadlines separately bounded.

Recommended behavior:

- normal snapshot/reconciliation: 5–10 sec
- writes: adapter/network timeout remains bounded, but uncertain write behavior must still trigger reconciliation
- kill switch: use its own overall Deadline and remaining-time budget

Never blindly retry an uncertain order write.

---

# 7. Order Event Architecture

Use explicit evidence authority.

## WebSocket is good for

```text
order accepted
order pending
order rejected
order cancelled
order state changed
```

## REST trade endpoints are authoritative for

```text
unique trade ID
fill quantity
fill price
fill timestamp
```

unless future verified organizer documentation proves equivalent unique fill evidence from WebSocket.

### Unified ingestion pipeline

```text
021 order WS ───────┐
                    ├─→ BrokerUpdateQueue
021 REST poll ──────┤
                    └─→ dedupe / sequence
                              ↓
                       OrderManager
```

Rules:

1. fill evidence first
2. terminal status after required executed quantity evidence
3. duplicate status is harmless
4. duplicate trade ID is ignored
5. conflicting fill identity fails closed
6. unknown mapped order event is audited
7. unmapped provider order must never silently mutate local state

---

# 8. Market Event Architecture

## Provider boundary

Do all provider-specific quirks here:

```text
021 binary frame
→ parse_market_frames()
→ MarketObservation021
→ timestamp normalization
→ duplicate suppression
→ cumulative-volume delta
→ canonical Tick
```

The rest of AlgoShield must not know about:
- 021 epochs
- 021 exchange codes
- binary layout
- ephemeral keys

## Duplicate fingerprint

Recommended:

```python
fingerprint = (
    observation.exchange,
    observation.token,
    observation.exchange_timestamp,
    observation.ltp,
    observation.cumulative_volume,
    observation.official_open,
)
```

If same fingerprint repeats:
- count
- drop

If raw timestamp is absent, fingerprint still includes observed economic fields and can use a short receive-window rule if necessary.

---

# 9. Frontend Requirements

Existing `MarketDataPage` is a good base.

Complete the following.

## Market Data page

Show:

- provider: 021 LIVE
- connection state
- desired symbols
- actually subscribed symbols
- number of market sockets
- latest quote per symbol
- normalized event timestamp
- raw 021 timestamp
- receive timestamp
- official open where available
- cumulative volume / volume availability
- duplicate snapshots dropped
- timestamp fallbacks
- reconnect attempts
- last disconnect reason
- accepted ticks
- late/conflicting duplicates
- current data age/freshness

## Provider health status

Use clear states:

```text
CONNECTED
DEGRADED
RECONNECTING
DISCONNECTED
```

Do not say simply "Connected" if only one of many sockets is connected.

Expose:

```text
connected_sockets / expected_sockets
```

## Strategy page

When enabling stocks:
- backend validates 021 instrument availability
- frontend displays unsupported symbols before activation
- after creation, desired live universe changes automatically

Do not let React talk directly to 021.

All 021 credentials and WebSockets remain backend-only.

---

# 10. Backend Telemetry Contract

Extend market telemetry to a stable shape:

```json
{
  "provider": "021",
  "source": "021_LIVE",
  "health": "CONNECTED",
  "connected": true,
  "connected_sockets": 1,
  "expected_sockets": 1,
  "desired_symbols": ["RELIANCE", "TCS"],
  "subscribed_symbols": ["RELIANCE", "TCS"],
  "canonical_symbols": ["RELIANCE", "TCS"],
  "received_messages": 1000,
  "accepted_updates": 950,
  "provider_duplicates_dropped": 48,
  "timestamp_fallbacks": 2,
  "reconnect_attempts": 0,
  "last_disconnect_reason": null,
  "last_event_timestamp": 0,
  "last_raw_event_timestamp": 0,
  "last_received_at": 0,
  "latest_quotes": []
}
```

Never expose:
- password
- access token
- ephemeral key
- Authorization header

---

# 11. Security & Secret Handling

The live credentials supplied to the coding agent must only be used for runtime verification.

Rules:

1. never commit `.env`
2. never print password/token in logs
3. never put credentials in generated Markdown
4. never put token in React/Vite environment variables
5. never include credentials in screenshots/test snapshots
6. use backend environment only
7. `.env.example` contains names/placeholders only
8. redact HTTP Authorization headers
9. redact WebSocket `?token=` URLs in telemetry and exceptions

If the current ZIP contains a real `.env`, leave it untracked and do not copy it into artifacts.

---

# 12. Live Verification Safety Gates

Live verification must occur in stages.

## Stage A — Read-only authentication

Verify:

```text
POST /auth/token
GET /instruments
GET /orders
GET /trades
GET /portfolio/positions
GET /websocket/ephemeral-key
```

No order writes yet.

## Stage B — Market feed

Use 1–3 symbols only:

```text
RELIANCE
TCS
INFY
```

Verify:
- socket connects
- quote appears
- no false duplicate failures
- timestamps are sane
- data ages correctly
- 1m candle closes
- React displays same quote/candle evidence

## Stage C — Order stream read-only

Connect `/websocket/orders`.

Verify:
- worker starts
- reconnect works
- telemetry visible
- no local state mutation from unknown/unmapped events

## Stage D — Controlled sandbox execution

Only after A–C pass and only against organizer sandbox.

Use:
- one supported liquid cash symbol
- quantity 1
- smallest normal sandbox exposure
- market order if organizer workflow expects it

Verify:

```text
intent
→ risk decision
→ provider order mapping
→ broker order
→ status event
→ REST trade ID
→ fill once
→ local position
→ broker position
→ reconciliation
```

No automated repeated orders.

---

# 13. Exact Implementation Phases

## Phase 0 — Protect repository and establish baseline

Before editing:

```bash
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate -15
```

Preserve all local work.

If dirty:

```bash
git stash push -u -m "pre-021-hardening"
```

Then:

```bash
git fetch origin --prune
```

Inspect divergence.

If safe:
- fast-forward or merge `origin/main`
- restore stash
- resolve conflicts semantically

Never:

```text
git reset --hard
git clean -fd
```

Create local branch:

```bash
git switch -c fix/021-end-to-end-hardening
```

Do not push unless explicitly requested.

Run baseline tests before code changes.

---

## Phase 1 — Universe control

Files likely touched:

```text
backend/api.py
backend/shared/config.py
backend/market_data/official021.py
backend/strategies/runtime.py
tests/test_official021_market_data.py
tests/test_multi_stock_subscriptions.py
```

Implement:
- no whole-exchange fallback
- strategy-derived desired symbols
- pinned configured symbols
- validation against instrument catalogue
- universe telemetry

Acceptance:
- no config + no strategy → no 2,000-stock subscription
- enabled RELIANCE/TCS → exactly RELIANCE/TCS desired
- adding INFY updates desired universe
- unsupported symbol produces explicit validation failure

---

## Phase 2 — Duplicate suppression and timestamp normalization

Primary:

```text
backend/market_data/official021.py
tests/test_official021_market_data.py
```

Refactor `_emit()` into smaller pure helpers:
- resolve instrument
- duplicate fingerprint
- normalize timestamp
- calculate volume delta
- construct Tick
- update quote telemetry

Tests:
- repeated identical first snapshot does not conflict
- repeated identical later snapshot does not conflict
- same timestamp but changed LTP accepted
- same LTP but increased cumulative volume accepted
- changed economic data with accidental same event ID cannot silently overwrite
- future timestamp fallback
- old timestamp fallback
- monotonic timestamp fallback
- plausible timestamp preserved

---

## Phase 3 — Market reconnect state machine

Primary:

```text
backend/market_data/official021.py
```

Optional reusable helper:

```text
backend/reliability/reconnect.py
```

Implement:
- per-socket reconnect loop
- fresh ephemeral token when appropriate
- bounded exponential backoff
- stop-event interruptibility
- subscription replay
- health telemetry
- fail-closed on first disconnect
- never auto-resume trading

Tests with fake sockets:
- timeout != disconnect
- None/closed socket triggers reconnect
- connection exception triggers reconnect
- resubscription message is sent
- stop exits promptly
- no trading-gate auto-open

---

## Phase 4 — Correct fill/status sequencing

Primary:

```text
backend/broker/official021_http.py
backend/platform.py
tests/test_official021_rest.py
tests/test_broker_updates.py
```

Implement:
- unseen fills emitted before terminal FILLED status
- terminal status suppressed if fill application already derives correct terminal state
- rejection/cancel preserved
- stable status dedupe

Tests:
- one complete fill does not raise IllegalOrderTransition
- two partial fills → partial then filled
- repeated REST poll → no duplicate fill
- REST + WS status → still one fill
- overfill → fail closed
- side mismatch → fail closed

---

## Phase 5 — Start real order WebSocket worker

Files:

```text
backend/broker/official021_http.py
new backend/broker/official021_order_stream.py  (recommended)
backend/platform.py
backend/api.py
tests/test_official021_order_stream.py          (new)
```

Implement:
- lifecycle object
- start/stop
- ephemeral key
- binary receives
- parse
- queue
- reconnect
- telemetry

Integrate into application lifespan.

Do not let it directly modify DB from its receive thread.

Preferred:

```text
WS thread
→ thread-safe queue
→ Platform sync boundary
→ process_broker_update()
```

This maintains deterministic platform mutation.

---

## Phase 6 — Broker timeout and reconciliation

Files:

```text
backend/reliability/broker_calls.py
backend/shared/config.py
backend/platform.py
tests/test_reconciliation_center.py
tests/test_disconnect_recovery.py
```

Implement:
- configurable timeout
- snapshot-specific timeout
- deadline propagation
- preserve uncertain write semantics
- reconnect requires reconciliation
- no automatic risk-gate resume

Tests:
- snapshot lasting 2 sec succeeds under configured 8 sec
- timeout still fails closed when truly exceeded
- uncertain write blocks next risk-increasing write
- successful reconciliation clears uncertainty only through explicit verified path

---

## Phase 7 — Official strategy integration

Files:

```text
backend/strategies/runtime.py
backend/strategies/official021.py
backend/market_data/official021.py
backend/platform.py
frontend/src/pages/StrategiesPage.jsx
tests/test_official021.py
tests/test_strategy_execution_safety.py
```

Implement runtime registration and required evidence interface.

Do not hack these classes into candle-only strategy signatures if that loses official-open or fill-WAP semantics.

Add explicit strategy runtime adapters if necessary.

Tests:
- 09:15 entry only within correct minute
- no late catch-up
- once/session persistence
- 15:15 exit only attributed residual
- breakout requires official open
- 1% threshold correct
- 5% TP/SL from actual fill WAP
- stale feed blocks new entry
- stale broker evidence blocks new entry
- strategy instances remain symbol-isolated

---

## Phase 8 — Frontend operational evidence

Files:

```text
frontend/src/pages/EvidencePages.jsx
frontend/src/test/integrationGaps.test.jsx
```

Add:
- provider health
- socket counts
- desired/subscribed symbol counts
- duplicate suppression counter
- timestamp fallback counter
- reconnect attempts
- official open
- quote age/freshness
- clear "021 LIVE" label

Do not display secrets.

---

## Phase 9 — End-to-end automated tests

Add a deterministic fake 021 system.

Suggested:

```text
tests/fakes/fake_021.py
```

It should emulate:
- auth
- instruments
- ephemeral key
- market WS
- order REST
- order WS
- trade endpoints
- positions
- disconnects
- duplicated snapshots
- partial fills
- delayed fills
- rejected orders

Then create:

```text
tests/test_021_end_to_end.py
```

Test:

```text
fake live quote
→ candle
→ strategy
→ risk
→ order
→ fill
→ position
→ reconciliation
→ snapshot telemetry
```

This is essential because live 021 availability should not be required for regression tests.

---

# 14. Test Matrix

## Market feed

- valid LTP
- full quote
- heartbeat
- empty/zero quote fields
- identical duplicate
- changed duplicate timestamp
- cumulative volume baseline
- cumulative volume increment
- cumulative volume regression
- old timestamp
- future timestamp
- out-of-order timestamp
- malformed frame
- socket quiet period
- socket close
- reconnect
- resubscribe
- multi-socket universe

## Order flow

- submit success
- submit 4xx
- timeout before confirmed write
- uncertain write
- accepted
- rejected
- cancelled
- partial fill
- full fill
- duplicate trade
- late fill after cancel
- WS status before REST fill
- broker/local mapping missing
- provider unknown status
- side mismatch
- overfill

## Reconciliation

- exact match
- local missing broker order
- broker missing local order
- position drift
- incomplete snapshot
- timeout
- reconnect then reconcile
- gate remains closed until explicit resume

## Frontend

- 021 connected
- degraded
- reconnecting
- disconnected
- multiple stocks
- latest quote changes
- candles appear
- raw vs normalized timestamp
- no secret leakage
- provider errors visible

---

# 15. Metrics to Add

Instrument all of these:

```text
021_market_frames_received_total
021_market_observations_total
021_market_updates_accepted_total
021_market_duplicates_dropped_total
021_market_timestamp_fallback_total
021_market_protocol_errors_total
021_market_reconnect_total
021_market_connected_sockets
021_market_desired_symbols
021_market_subscribed_symbols

021_order_ws_frames_total
021_order_ws_reconnect_total
021_rest_requests_total
021_rest_errors_total
021_rest_latency_ms

broker_updates_applied_total
fills_applied_total
duplicate_fills_dropped_total
reconciliation_runs_total
reconciliation_failures_total
```

If the existing metrics registry uses another naming convention, follow it instead of creating a parallel metrics system.

---

# 16. Audit Events to Add

Examples:

```text
021_MARKET_CONNECTED
021_MARKET_DISCONNECTED
021_MARKET_RECONNECT_ATTEMPT
021_MARKET_RESUBSCRIBED
021_MARKET_DUPLICATE_DROPPED
021_TIMESTAMP_FALLBACK

021_ORDER_STREAM_CONNECTED
021_ORDER_STREAM_DISCONNECTED
021_ORDER_STREAM_RECONNECT_ATTEMPT

021_FILL_INGESTED
021_DUPLICATE_FILL_IGNORED
021_UNKNOWN_PROVIDER_ORDER
021_RECONCILIATION_STARTED
021_RECONCILIATION_COMPLETED
```

Keep payload bounded and redact secrets.

Do not audit every market tick to durable storage.

---

# 17. Performance / Scale Targets

The organizer feed is snapshot-oriented and can update roughly every few hundred milliseconds.

Targets for the hackathon:

- 1–20 active symbols normal demo
- 100 active symbols should remain stable
- architecture respects documented max 2,000 instruments
- do not make 2,000 the default
- market ingest must not block risk/order paths
- React should not render thousands of rows every update
- quote table should remain bounded/paginated/filtered

The goal is correctness and safety, not HFT latency.

---

# 18. Documentation Updates

After code is working, update:

```text
docs/021/OFFICIAL_API_CONTRACT.md
docs/021/INTEGRATION_BLUEPRINT.md
docs/PROJECT_TRUTH.md
docs/ARCHITECTURE.md
docs/TESTING.md
README.md
.env.example
```

Document:
- exact production/live state
- what has been fixture tested
- what has been live verified
- current known limitations
- how to enable 021
- how to choose symbols
- how reconnect/reconciliation works
- how order WebSocket and REST trade evidence interact

Never claim:
- raw exchange tick-by-tick delivery
- zero latency
- complete broker history unless proven
- every order WS frame uniquely identifies a fill unless verified

---

# 19. Live Verification Report

The implementation agent must produce a final report with:

```text
AUTH                PASS/FAIL
INSTRUMENTS         PASS/FAIL
MARKET WS           PASS/FAIL
MULTI-STOCK         PASS/FAIL
TIMESTAMPS          PASS/FAIL
DUPLICATES          PASS/FAIL
CANDLES             PASS/FAIL
RECONNECT           PASS/FAIL
ORDER REST          PASS/FAIL/NOT RUN
ORDER WS            PASS/FAIL
FILLS               PASS/FAIL/NOT RUN
POSITION            PASS/FAIL/NOT RUN
RECONCILIATION      PASS/FAIL/NOT RUN
REACT LIVE QUOTES   PASS/FAIL
REACT CANDLES       PASS/FAIL
SECRET LEAK CHECK   PASS/FAIL
```

For every FAIL:
- exact observed error
- source file/function
- whether safety failed closed
- next fix

Do not call the integration complete until all critical rows pass.

---

# 20. Final Acceptance Checklist

## P0 mandatory

- [ ] no default 2,000-symbol subscription
- [ ] strategy symbols drive live universe
- [ ] benign duplicate snapshots dropped before canonical Tick
- [ ] timestamp skew bounded and raw evidence retained
- [ ] market reconnect/resubscribe implemented
- [ ] trading remains fail-closed after reconnect
- [ ] fills applied before terminal FILLED status
- [ ] duplicate fill IDs ignored
- [ ] order WS worker actually running
- [ ] order WS reconnect implemented
- [ ] REST remains fill authority unless unique WS trade identity verified
- [ ] broker timeout suitable for 021 reconciliation
- [ ] React shows live 021 evidence
- [ ] no secrets reach frontend/logs/git

## P1 strongly recommended

- [ ] official 021 strategies registered and executable
- [ ] official open preserved into strategy evidence
- [ ] dynamic subscribe/unsubscribe on strategy changes
- [ ] 021 end-to-end fake integration test
- [ ] provider metrics/audit complete
- [ ] reconnect and failure tests

## P2 polish

- [ ] reconnect health badges
- [ ] socket-level diagnostics
- [ ] bounded watchlist
- [ ] performance measurements
- [ ] live verification report stored under docs

---

# 21. Non-Negotiable Safety Rules

1. **Never retry an uncertain write blindly.**
2. **Never auto-resume trading after provider reconnect.**
3. **Never manufacture a fill without unique broker evidence.**
4. **Never allow stale market data to create new exposure.**
5. **Never expose 021 credentials to React.**
6. **Never silently ignore broker/local position drift.**
7. **Never let one strategy's symbol/fills/P&L contaminate another.**
8. **Never reset/clean away existing user work to simplify implementation.**
9. **Never push to remote unless explicitly requested.**
10. **Never label the integration fully live-verified unless the end-to-end evidence proves it.**

---

# 22. Recommended Final Architecture

```text
                          ┌─────────────────────────────┐
                          │        021 TRADE            │
                          │                             │
                          │ Market WS     Order WS      │
                          │    │             │          │
                          │ REST Orders / Trades / Pos  │
                          └────┼─────────────┼──────────┘
                               │             │
                    ┌──────────▼───┐   ┌────▼──────────┐
                    │MarketData021 │   │021OrderStream │
                    │ Provider     │   │ Worker        │
                    └──────┬───────┘   └────┬──────────┘
                           │                │
                    normalize/dedupe       │ status
                           │                │
                         Tick              │
                           │          ┌─────▼───────┐
                           │          │BrokerUpdate │
                           │          │ Queue       │
                           │          └─────┬───────┘
                           ▼                │
                    ┌────────────┐          │
                    │CandleBuilder│         │
                    └─────┬──────┘          │
                          ▼                 │
                    ┌────────────┐          │
                    │Strategies  │          │
                    └─────┬──────┘          │
                          ▼                 │
                    ┌────────────┐          │
                    │RiskGateway │          │
                    └─────┬──────┘          │
                          ▼                 │
                    ┌────────────┐          │
                    │OrderManager├──────────┘
                    └─────┬──────┘
                          │
                     REST submit
                          │
                          ▼
                    ┌────────────┐
                    │021 Adapter │
                    └─────┬──────┘
                          │
                     trades/fills
                          │
                          ▼
                    ┌────────────┐
                    │Ledger/P&L  │
                    └─────┬──────┘
                          ▼
                    ┌──────────────┐
                    │Reconciliation│
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │FastAPI State │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │React UI      │
                    └──────────────┘
```

This keeps provider-specific behavior at the edges while preserving the existing AlgoShield safety architecture.

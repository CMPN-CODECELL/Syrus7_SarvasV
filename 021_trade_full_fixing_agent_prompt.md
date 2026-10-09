# Coding-Agent Prompt — Complete and Harden AlgoShield's 021 Trade Integration

You are working on the current AlgoShield repository. Your job is to **fix, complete, test, and live-verify the 021 Trade integration end-to-end** without redesigning the rest of the platform.

The current project already has a substantial 021 implementation. Do not replace it with a parallel subsystem. Inspect the existing architecture first and improve it in place.

## Primary objective

Make this path correct and demonstrably working:

```text
021 Trade live market data
→ AlgoShield market provider
→ canonical ticks
→ candles
→ strategies
→ risk gateway
→ order manager
→ 021 REST order execution
→ 021 order/trade evidence
→ fills
→ positions/P&L
→ reconciliation
→ FastAPI state/telemetry
→ React frontend
```

The project is reliability-first. The governing invariant is:

> Failure must never silently increase risk.

---

# A. Repository safety — do this before editing

Run:

```bash
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate -15
```

Preserve all existing work.

If the working tree is dirty, use a safe stash/checkpoint:

```bash
git stash push -u -m "pre-021-hardening"
```

Then:

```bash
git fetch origin --prune
```

Inspect local-vs-origin divergence.

If appropriate:
- fast-forward when possible
- otherwise merge `origin/main`
- restore the stash
- resolve conflicts semantically, preserving the newest React, USP, multi-stock, Failure Lab, risk, and 021 work

Never use destructive shortcuts such as:

```text
git reset --hard
git clean -fd
```

Create a local branch:

```bash
git switch -c fix/021-end-to-end-hardening
```

**DO NOT PUSH** unless explicitly asked.

Run baseline backend and frontend tests before changing behavior.

---

# B. Secret handling

You may be supplied 021 credentials/access token separately for live verification.

Treat them as secrets.

Rules:

- use backend environment variables only
- `.env` or `.env.local` must remain gitignored
- do not hardcode credentials
- do not put password/token in source, Markdown, screenshots, test fixtures, or final report
- do not expose access token or ephemeral WebSocket key to React
- do not log Authorization headers
- redact WebSocket URLs that contain `?token=...`
- `.env.example` contains placeholders only

Prefer an existing valid access token when supplied. If authentication needs refresh, use the supplied UCC/password through the documented backend authentication flow.

---

# C. Read these files first

Inspect at minimum:

```text
backend/api.py
backend/platform.py
backend/shared/config.py

backend/market_data/official021.py
backend/market_data/candles.py
backend/market_data/session.py

backend/broker/official021.py
backend/broker/official021_http.py
backend/broker/adapters.py

backend/reliability/broker_calls.py

backend/strategies/runtime.py
backend/strategies/official021.py

frontend/src/pages/EvidencePages.jsx
frontend/src/pages/StrategiesPage.jsx
frontend/src/api/client.js

tests/test_official021.py
tests/test_official021_market_data.py
tests/test_official021_rest.py
tests/test_multi_stock_subscriptions.py
tests/test_broker_updates.py
tests/test_disconnect_recovery.py
tests/test_reconciliation_center.py

docs/021/OFFICIAL_API_CONTRACT.md
docs/021/INTEGRATION_BLUEPRINT.md
docs/SAFETY_INVARIANTS.md
docs/ARCHITECTURE.md
```

Understand existing contracts before editing them.

---

# D. Current known defects — fix all of these

## 1. Stop subscribing to the whole 021 cash catalogue by default

Current startup falls back to `broker.all_market_symbols()` when `ALGOSHIELD_021_SYMBOLS` is absent. This can result in roughly 2,000 live subscriptions.

Replace this behavior.

Desired universe:

```text
operator-pinned symbols from ALGOSHIELD_021_SYMBOLS
+
symbols required by enabled AlgoShield strategy subscriptions
```

If neither exists:
- do not subscribe to thousands of stocks
- either start idle or fail startup with a clear message

Preferred behavior is strategy-driven live universe.

Validate every desired symbol using the 021 instrument catalogue.

Expose desired and subscribed symbols in telemetry.

---

## 2. Fix benign duplicate snapshot handling

The current provider can generate `CONFLICTING_DUPLICATE` for repeated identical 021 snapshots because volume baseline state changes the canonical tick while event identity stays equal.

Deduplicate at the provider-observation boundary before constructing `Tick`.

Use a per-instrument fingerprint based on provider evidence such as:

```python
(
    exchange,
    token,
    exchange_timestamp,
    ltp,
    cumulative_volume,
    official_open,
)
```

Identical repeat:
- drop silently as benign provider duplicate
- increment `provider_duplicates_dropped`
- do not call `platform.tick()`
- do not fail closed

Changed economic data:
- accept as new evidence
- do not incorrectly suppress it

Write regression tests reproducing the current conflict.

---

## 3. Replace 24-hour timestamp tolerance

Current live normalization allows about 86,400 seconds of skew. That is too large.

Add configuration:

```env
ALGOSHIELD_021_MAX_TIMESTAMP_SKEW_SECONDS=10
```

Implement a central timestamp normalizer.

Keep:

```text
raw_event_timestamp
normalized_event_timestamp
received_at
```

Behavior:

- missing raw timestamp → receive time
- plausible raw timestamp within threshold → preserve
- future/past timestamp outside threshold → receive time fallback
- symbol timestamp regression → monotonic safe fallback
- preserve raw timestamp for evidence
- increment detailed fallback counters

Do not allow a timestamp several hours away from receive time to be treated as live.

---

## 4. Fix REST fill/status ordering

Inspect `Broker021Adapter.drain_updates()`.

Current ordering can emit:

```text
ORDER_STATUS FILLED
before
FILL
```

which can trigger `IllegalOrderTransition` because local executed quantity has not yet been applied.

Refactor so that:

```text
new unseen fills
→ apply cumulative quantity
→ terminal FILLED status only after evidence supports it
```

Acceptable alternative:
- fill application derives final status
- polling suppresses redundant FILLED status

Do not lose:
- accepted/open
- rejected
- cancelled
- unknown state evidence

Trade ID is the authoritative fill deduplication key.

Test:
- one full fill
- two partial fills
- repeated REST polling
- REST + WS status overlap
- overfill
- wrong side

---

## 5. Actually start the 021 order WebSocket

The adapter already has:

```python
connect_order_websocket()
parse_order_update()
```

but currently no live worker calls them.

Implement a dedicated order stream lifecycle.

Recommended new module:

```text
backend/broker/official021_order_stream.py
```

Responsibilities:

```text
start
→ ephemeral key
→ connect /api/developer/websocket/orders
→ receive binary packet
→ parse
→ map provider order ID to platform order ID
→ enqueue BrokerUpdate
→ reconnect when disconnected
→ telemetry
→ stop cleanly
```

Do not mutate platform DB directly from the receive thread.

Use a thread-safe queue. Apply events from a controlled platform synchronization boundary.

Important:
- WS order status is useful
- do not invent a fill when the WS packet lacks unique trade identity
- REST order/trade endpoints remain fill authority unless live evidence/doc proves otherwise

Wire worker start/stop into application lifecycle.

---

## 6. Add market WebSocket reconnect/resubscribe

Current market worker fails closed when connection ends but then exits.

Replace with a reconnect state machine.

Required:

```text
disconnect
→ immediately fail closed
→ provider health = RECONNECTING
→ bounded backoff
→ fresh ephemeral key if required
→ reconnect
→ resend subscription for the same current universe
→ trigger broker reconciliation/readiness path
→ trading remains STOPPED/UNCERTAIN
→ only explicit operator resume can reopen trading
```

Suggested backoff:

```text
1, 2, 5, 10, 30 seconds max
```

No automatic gate reopening.

Make stop event interrupt the backoff promptly.

Add reconnect telemetry.

---

# E. Dynamic symbol universe

AlgoShield supports multiple strategy instances:

```text
Momentum + [RELIANCE,TCS,INFY]
→ momentum-reliance
→ momentum-tcs
→ momentum-infy
```

021 market subscription must follow enabled strategy symbols dynamically.

Implement a market-universe coordinator.

Suggested file:

```text
backend/market_data/universe.py
```

It should compute:

```text
desired = enabled_strategy_symbols ∪ pinned_021_symbols
```

and expose:
- desired symbols
- validated symbols
- current subscribed symbols
- unsupported symbols

When strategies are added/disabled, update the live universe.

For simplicity, controlled socket rebuild is acceptable if:
- fail closed
- reconnect/resubscribe
- reconciliation
- explicit resume

Do not subscribe to unrelated exchange symbols.

---

# F. Broker timeout/reconciliation hardening

`BrokerSession` currently defaults to about 1 second.

That is too short for 021 snapshot/reconciliation calls that may involve multiple HTTP requests.

Add configurable timeouts, for example:

```env
ALGOSHIELD_BROKER_READ_TIMEOUT_SECONDS=8
ALGOSHIELD_BROKER_WRITE_TIMEOUT_SECONDS=8
ALGOSHIELD_RECONCILIATION_TIMEOUT_SECONDS=10
```

Follow project naming conventions if equivalent settings already exist.

Requirements:

- normal read/snapshot path can take several seconds
- writes remain bounded
- uncertain writes are never blindly retried
- kill-switch deadlines remain separate and strict
- reconnect does not clear uncertainty by itself
- verified reconciliation is required

---

# G. Wire official 021 strategies into normal runtime

Existing:

```text
backend/strategies/official021.py
  Time0915Strategy
  OpenBreakoutStrategy
```

Current normal runtime kinds do not fully expose them.

Integrate:

```text
time_0915_1515
open_1pct_tp5_sl5
```

Do not merely add two strings if required evidence is missing.

### Time strategy requires

- IST time
- safe market session
- broker evidence freshness
- strategy-attributed residual quantity
- safe square-off bound

### Open-breakout requires

- 021 official open
- LTP
- actual entry fill WAP
- residual attributed quantity
- entry order status
- feed freshness
- broker evidence freshness

The 021 parser already has `official_open`. Preserve it through a provider-neutral market-evidence interface.

Do not make StrategyRuntime import provider-specific code directly.

Test symbol isolation.

---

# H. Complete frontend evidence

Keep all 021 connectivity server-side.

Enhance `MarketDataPage` to display:

- 021 provider status
- CONNECTED / DEGRADED / RECONNECTING / DISCONNECTED
- connected socket count / expected socket count
- desired symbols
- subscribed symbols
- latest quote
- official open
- raw timestamp
- normalized timestamp
- received timestamp
- quote age
- cumulative/volume availability
- provider duplicate snapshots dropped
- timestamp fallbacks
- reconnect attempts
- last disconnect reason
- accepted ticks
- late/conflicting events
- 1m/5m candles

Do not expose any secret/token.

Update frontend tests.

---

# I. Stable telemetry contract

Return something equivalent to:

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
  "received_messages": 100,
  "accepted_updates": 90,
  "provider_duplicates_dropped": 8,
  "timestamp_fallbacks": 2,
  "reconnect_attempts": 0,
  "last_disconnect_reason": null,
  "last_received_at": 0,
  "last_event_timestamp": 0,
  "last_raw_event_timestamp": 0,
  "latest_quotes": []
}
```

Follow existing API naming where already established.

---

# J. Build a deterministic fake 021 end-to-end test

Live API cannot be the regression suite.

Create a fake 021 integration that supports:

- auth
- instrument catalogue
- ephemeral key
- market WS frames
- order REST
- order WS
- trades
- positions
- duplicate snapshots
- partial fills
- rejects
- disconnect/reconnect

Suggested:

```text
tests/fakes/fake_021.py
tests/test_021_end_to_end.py
```

End-to-end automated scenario:

```text
market update
→ canonical tick
→ candle
→ strategy
→ risk approved
→ submit order
→ order state
→ trade fill
→ local position
→ broker position
→ reconciliation
→ frontend snapshot telemetry
```

Also simulate:
- duplicate market frame
- market disconnect
- order WS disconnect
- duplicate trade
- delayed REST call

---

# K. Required test cases

At minimum implement/regress:

## Market
- first cumulative volume is baseline
- next cumulative volume becomes delta
- cumulative-volume regression fails safely
- identical provider snapshot is dropped
- changed price is accepted
- changed cumulative volume is accepted
- future timestamp fallback
- old timestamp fallback
- timestamp regression fallback
- plausible timestamp preserved
- 1-second quiet socket does not disconnect
- real close triggers reconnect
- resubscribe after reconnect
- stop interrupts reconnect

## Broker
- complete fill before FILLED
- two partial fills
- duplicate trade ID
- cancelled order
- rejected order
- WS status + REST fill coexist
- unknown provider order audited
- overfill rejected
- side mismatch rejected
- uncertain write requires reconciliation

## Multi-stock
- only enabled/pinned symbols subscribed
- no 2,000-symbol default
- adding strategy adds symbol
- disabling final strategy removes symbol
- symbols remain isolated

## Frontend
- latest live quote appears
- multiple symbols filter correctly
- provider health displayed
- timestamp evidence displayed
- reconnect counters displayed
- no credentials appear

---

# L. Metrics and audit

Use the existing metrics/audit systems. Do not build a second one.

Track at least:

```text
market frames
market observations
accepted market updates
provider duplicates dropped
timestamp fallbacks
market reconnects
connected socket count

order WS frames
order WS reconnects
021 REST latency/errors

fills applied
duplicate fills ignored
reconciliation success/failure
```

Useful audit events:

```text
021_MARKET_CONNECTED
021_MARKET_DISCONNECTED
021_MARKET_RECONNECT_ATTEMPT
021_MARKET_RESUBSCRIBED
021_TIMESTAMP_FALLBACK

021_ORDER_STREAM_CONNECTED
021_ORDER_STREAM_DISCONNECTED

021_FILL_INGESTED
021_DUPLICATE_FILL_IGNORED
021_UNKNOWN_PROVIDER_ORDER
```

Do not persist an audit row for every tick.

---

# M. Run tests continuously

After each phase run targeted tests.

At the end run:

```bash
pytest -q
```

and frontend tests/build using the repository's package scripts.

If packaged `node_modules` is broken, do not assume source failure. Restore dependencies using the lockfile in a clean local install and then rerun.

Do not silently delete or overwrite the lockfile.

Also run lint/type checks already defined by the project.

---

# N. Live verification sequence

Only after automated tests pass.

The supplied credentials belong to the organizer's developer sandbox.

## N1. Read-only

Verify:

```text
auth
instrument download/cache
orders list
trades list
positions
ephemeral key
```

Record PASS/FAIL without printing secrets.

## N2. Market WebSocket

Use only a tiny symbol set, e.g.:

```text
RELIANCE,TCS
```

Verify:
- current snapshot arrives
- updates continue
- raw timestamps
- normalized timestamps
- React quote table
- candle creation
- duplicate suppression
- no false disconnect from short idle periods

## N3. Reconnect

Safely force a test socket close if possible.

Verify:
- fail closed
- reconnect
- resubscribe
- gate stays closed
- reconciliation/readiness evidence
- manual resume required

## N4. Order WebSocket

Verify it actually runs and receives organizer events.

No write required merely to prove lifecycle if existing sandbox events are available.

## N5. Controlled sandbox order

Only when the prior stages pass.

Use a single quantity-1 sandbox order in a supported liquid cash instrument.

Verify exact chain:

```text
local intent ID
→ provider order ID
→ durable mapping
→ order status
→ REST trade ID
→ one Fill
→ local cumulative filled qty
→ final order state
→ local position
→ broker position
→ reconciliation
→ frontend
```

Do not generate repeated live orders.

If an order write becomes uncertain:
- do not retry
- reconcile first

---

# O. Final verification report

Create:

```text
docs/021/LIVE_VERIFICATION_REPORT.md
```

Do not put credentials in it.

Format:

```text
AUTH                    PASS/FAIL
INSTRUMENTS             PASS/FAIL
MARKET WS               PASS/FAIL
MARKET DUPLICATES       PASS/FAIL
TIMESTAMP NORMALIZATION PASS/FAIL
MULTI-STOCK             PASS/FAIL
CANDLE PIPELINE         PASS/FAIL
MARKET RECONNECT        PASS/FAIL
ORDER REST              PASS/FAIL/NOT RUN
ORDER WS                PASS/FAIL
FILL INGESTION          PASS/FAIL/NOT RUN
POSITION                PASS/FAIL/NOT RUN
RECONCILIATION          PASS/FAIL/NOT RUN
REACT LIVE QUOTES       PASS/FAIL
REACT CANDLES           PASS/FAIL
SECRET LEAK CHECK       PASS/FAIL
FULL PYTEST             PASS/FAIL
FRONTEND TESTS          PASS/FAIL
FRONTEND BUILD          PASS/FAIL
```

For each failure include:
- observed symptom
- source function
- whether platform failed closed
- fix/status

Be precise about what was fixture-verified versus live-verified.

---

# P. Update documentation after implementation

Update:

```text
docs/021/OFFICIAL_API_CONTRACT.md
docs/021/INTEGRATION_BLUEPRINT.md
docs/PROJECT_TRUTH.md
docs/ARCHITECTURE.md
docs/TESTING.md
README.md
.env.example
```

Do not claim:
- exchange tick-by-tick completeness
- guaranteed total latency
- complete historical broker truth
- WebSocket fills with unique identity unless proven

Use language such as:

> 021 live WebSocket snapshot feed

when that is what the API provides.

---

# Q. Final response to me

When done, report:

1. exact files changed
2. root cause of every defect
3. implementation for each fix
4. tests added
5. backend test result
6. frontend test/build result
7. live 021 verification result
8. any remaining known limitation
9. whether a live sandbox order was run
10. whether credentials were confirmed absent from Git and frontend
11. git status
12. do not push unless I explicitly request it

Do not simply say "integration complete." Prove it with the required test and live-verification evidence.

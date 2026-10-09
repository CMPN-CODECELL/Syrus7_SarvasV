# AlgoShield Multi-Stock Strategy Implementation Plan

**Project:** AlgoShield — SYRUS 7.0 PS-06
**Feature:** Run one strategy type across multiple stocks while preserving one independent strategy instance per stock
**Current baseline:** `Syrus7_SarvasV` with React/Vite frontend + USP safety layer
**Implementation principle:** **One strategy instance = one symbol remains unchanged.** Multi-stock is an orchestration/UI feature that creates and manages multiple independent instances.

---

# 1. Goal

Allow the user to configure:

```text
Strategy: Momentum / EMA-like strategy
Stocks:
✓ RELIANCE
✓ TCS
✓ INFY
✓ HDFCBANK
```

and click:

```text
RUN ON 4 STOCKS
```

AlgoShield should internally create:

```text
momentum-reliance → momentum → RELIANCE
momentum-tcs      → momentum → TCS
momentum-infy     → momentum → INFY
momentum-hdfcbank → momentum → HDFCBANK
```

Each instance keeps its own:

```text
strategy_instance_id
symbol
indicator state
position
P&L
orders
fills
risk budget
halt state
lifecycle
```

This is much safer than changing one strategy instance to own multiple symbols.

---

# 2. Current Code Already Supports the Core Multi-Symbol Runtime

The current repository already has the important data-path behavior.

## Strategy subscription schema

Current subscriptions already contain:

```text
id
account
kind
symbol
enabled
```

The existing API currently accepts one:

```text
POST /api/subscriptions
```

with:

```json
{
  "strategy_instance_id": "ema-reliance",
  "kind": "momentum",
  "symbol": "RELIANCE"
}
```

## Strategy runtime is symbol-scoped

Current `backend/strategies/runtime.py` processes a closed candle by querying:

```sql
SELECT *
FROM subscriptions
WHERE symbol=? AND enabled=1
ORDER BY id
```

Therefore:

```text
RELIANCE candle
    ↓
only RELIANCE strategy instances

TCS candle
    ↓
only TCS strategy instances
```

This is already the correct architecture.

## Replay market data already supports multiple symbols

Current `Platform.generate_simulation_batch(symbols, ...)` accepts an iterable of symbols.

Current replay/demo code builds the symbol set from enabled subscriptions:

```text
SELECT symbol
FROM subscriptions
WHERE enabled=1
```

Therefore, after creating:

```text
momentum-reliance
momentum-tcs
momentum-infy
```

the replay stream can already generate ticks for:

```text
RELIANCE
TCS
INFY
```

No CandleBuilder rewrite is required.

---

# 3. Do NOT Implement Multi-Stock This Way

Do NOT change the subscription model to:

```json
{
  "strategy_instance_id": "momentum-1",
  "symbols": ["RELIANCE", "TCS", "INFY"]
}
```

Do NOT make one indicator-state dictionary shared across multiple stocks.

Do NOT make one P&L ledger shared across symbols.

Do NOT change RiskGateway to treat one multi-symbol object as a strategy.

That would unnecessarily complicate:

```text
indicator state
position attribution
risk calculation
P&L
failure isolation
strategy halting
order attribution
testing
reconciliation
```

The correct model remains:

```text
1 strategy instance
+
1 symbol
```

Multi-stock is:

```text
1 user action
→ N strategy instances
```

---

# 4. FIRST TASK — Safely Integrate Latest `origin/main`

The coding agent must do this BEFORE implementation.

The latest uploaded project snapshot was on:

```text
main
```

with local uncommitted changes.

The actual repository may have changed since then, so re-check.

---

## 4.1 Inspect current Git state

Run:

```bash
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate -10
```

Store current branch:

```bash
CURRENT_BRANCH="$(git branch --show-current)"
```

Never run destructive commands such as:

```text
git reset --hard
git checkout .
git restore .
git clean -fd
```

against user changes.

---

## 4.2 Preserve local modifications

If working tree is dirty:

```bash
git diff
git diff --staged
git status --short
```

Then safely stash including untracked files:

```bash
git stash push -u -m "pre-multi-stock implementation backup"
```

Record the stash ref:

```bash
git stash list
```

Do not drop it yet.

Alternative: if the local changes are clearly complete and intended, make a checkpoint commit.

Never checkpoint:

```text
secrets
.env files
tokens
database files
node_modules
frontend/dist
temporary test artifacts
```

---

## 4.3 Fetch remote

```bash
git fetch origin --prune
```

Inspect divergence:

```bash
git rev-list --left-right --count origin/main...HEAD
git log --oneline --left-right --cherry-pick origin/main...HEAD
```

---

## 4.4 Integrate latest main

If currently on `main` and there are no local divergent commits:

```bash
git merge --ff-only origin/main
```

If local commits exist or current branch is a feature branch:

```bash
git merge origin/main
```

Resolve conflicts manually.

Do not use repository-wide:

```text
-X ours
-X theirs
```

Preserve the newest:

```text
USP safety logic
React migration
Failure Lab changes
risk/reliability changes
API authorization
tests
```

---

## 4.5 Reapply local work

If a stash was created:

```bash
git stash pop
```

Resolve conflicts carefully.

Then:

```bash
git status
```

Do not drop any remaining stash until successful verification.

---

## 4.6 Create a local feature branch

If implementation is currently happening directly on `main`, prefer:

```bash
git switch -c feature/multi-stock-strategies
```

If already on an appropriate feature branch, stay there.

The task is to implement locally.

Do NOT push unless explicitly instructed.

---

# 5. Verify Baseline Before Feature Work

Run backend tests:

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

Run frontend checks:

```bash
npm --prefix frontend ci
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
```

If `node_modules` exists but is broken/stale, remove only generated frontend dependencies and reinstall:

```bash
rm -rf frontend/node_modules
npm --prefix frontend ci
```

Never delete source files.

If environment dependencies such as PostgreSQL drivers prevent backend tests, report the exact blocker and run the largest valid subset.

---

# 6. Feature Architecture

Final flow:

```text
React Strategies Page
       ↓
User selects:
kind = momentum
symbols = [RELIANCE, TCS, INFY]
       ↓
POST /api/subscriptions/batch
       ↓
Backend validates entire request
       ↓
Single transaction
       ↓
Create:
momentum-reliance
momentum-tcs
momentum-infy
       ↓
Existing runtime handles each independently
       ↓
Existing replay stream sees all enabled symbols
       ↓
Ticks → candles → matching strategy instance
```

Important:

```text
No new trading engine.
No new candle architecture.
No shared multi-symbol strategy state.
```

---

# 7. Backend Feature — Batch Subscription API

Add:

```text
POST /api/subscriptions/batch
```

This should create multiple subscriptions in ONE request.

Do not make the React UI send N independent create calls.

Reason:

```text
RELIANCE creation succeeds
TCS creation succeeds
INFY creation fails
```

would leave a partial configuration.

The backend batch operation should be atomic.

---

# 8. Batch API Contract

Recommended request:

```json
{
  "kind": "momentum",
  "symbols": [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK"
  ],
  "instance_prefix": "momentum"
}
```

Response:

```json
{
  "created": [
    {
      "id": "momentum-reliance",
      "kind": "momentum",
      "symbol": "RELIANCE",
      "enabled": true
    },
    {
      "id": "momentum-tcs",
      "kind": "momentum",
      "symbol": "TCS",
      "enabled": true
    }
  ],
  "count": 4,
  "symbols": [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK"
  ]
}
```

The response may use the existing subscription snapshot format if that is more consistent with the final merged repository.

Do not invent duplicate contract structures unnecessarily.

---

# 9. New Pydantic Request Model

In `backend/api.py`, add something equivalent to:

```python
class BatchSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    symbols: list[str]
    instance_prefix: str | None = None
```

Validation rules:

```text
kind required
symbols required
1 <= number of unique symbols <= 20
symbols trimmed
symbols uppercased
empty symbols rejected
duplicate symbols deduplicated or rejected consistently
instance_prefix trimmed
prefix length bounded
```

Recommended behavior:

```text
["RELIANCE", " reliance ", "TCS"]
```

normalizes to:

```text
["RELIANCE", "TCS"]
```

Do not accept hundreds/thousands of symbols through this hackathon endpoint.

Recommended max:

```text
20
```

This can later be made configurable.

---

# 10. Strategy Instance ID Generation

The backend should generate deterministic IDs.

Recommended:

```text
{prefix}-{normalized-symbol}
```

Examples:

```text
momentum-reliance
momentum-tcs
breakout-infy
```

If no `instance_prefix` is supplied:

```text
prefix = kind
```

Normalize the symbol component for IDs:

```text
RELIANCE → reliance
HDFCBANK → hdfcbank
ABC.NS → abc-ns
```

Use a small helper.

Do not use the display ID as the trading symbol.

Store the original normalized symbol separately:

```text
id     = momentum-abc-ns
symbol = ABC.NS
```

---

# 11. Collision Rules

Before inserting anything, calculate all IDs.

Then validate ALL of them.

If any target ID already exists:

```text
409 Conflict
```

with useful detail:

```json
{
  "detail": {
    "code": "SUBSCRIPTION_BATCH_CONFLICT",
    "existing": [
      "momentum-reliance"
    ]
  }
}
```

If the repository's error format is simpler, remain consistent.

Most important behavior:

```text
NO PARTIAL INSERTS.
```

If one conflicts:

```text
create zero.
```

---

# 12. Backend Runtime Method

Add a method to `backend/strategies/runtime.py` such as:

```python
subscribe_many(account, kind, symbols, instance_prefix=None)
```

or:

```python
subscribe_batch(...)
```

Responsibilities:

1. validate strategy kind;
2. normalize symbols;
3. generate IDs;
4. validate account;
5. check all collisions;
6. insert all subscription rows inside one transaction;
7. update `_subscription_generations`;
8. initialize/reset per-instance runtime state;
9. audit the batch operation;
10. return created rows.

Do not implement the database insert loop in the API layer if runtime/service ownership can handle it.

---

# 13. Atomic Transaction

Pseudo-flow:

```text
BEGIN

validate account
validate kind

generate 4 subscription IDs

check all 4 do not already exist

INSERT RELIANCE
INSERT TCS
INSERT INFY
INSERT HDFCBANK

audit batch creation

COMMIT
```

If any error occurs:

```text
ROLLBACK ALL
```

After commit, update in-memory runtime structures safely.

Be careful:

If in-memory state initialization could fail after DB commit, design initialization to be trivial/non-failing or perform required preparation first.

---

# 14. Audit Events

Keep individual subscription evidence if existing code depends on it.

Recommended audit:

```text
SUBSCRIPTIONS_BATCH_CREATED
```

Payload:

```json
{
  "account": "...",
  "kind": "momentum",
  "instance_prefix": "momentum",
  "symbols": ["RELIANCE", "TCS", "INFY"],
  "strategy_instances": [
    "momentum-reliance",
    "momentum-tcs",
    "momentum-infy"
  ]
}
```

Optionally retain existing:

```text
SUBSCRIBED
```

per strategy if other tooling relies on it.

Avoid unnecessary duplicate audit spam unless useful.

---

# 15. Existing Single-Stock API Must Stay

Do NOT remove:

```text
POST /api/subscriptions
```

It remains useful for:

```text
single stock
tests
manual setup
backward compatibility
```

The new endpoint is additive.

---

# 16. Optional Bulk Start/Stop

After multi-stock creation, users may want:

```text
Stop all TCS/RELIANCE/INFY instances created from this setup
```

This is useful, but secondary.

Recommended endpoint:

```text
POST /api/subscriptions/batch/state
```

Request:

```json
{
  "strategy_instance_ids": [
    "momentum-reliance",
    "momentum-tcs",
    "momentum-infy"
  ],
  "enabled": false
}
```

Rules:

```text
all IDs must belong to current authenticated account
all IDs validated before mutation
operation should be atomic where practical
one user's request cannot control another user's instances
```

This is P1.

If implementation time is limited, individual start/stop buttons are enough for P0.

---

# 17. Do We Need a Database Migration?

For P0:

```text
NO.
```

The existing `subscriptions` table already stores:

```text
one row per strategy instance
one symbol per row
```

That is exactly what we need.

Avoid adding a `symbols JSON` column.

Avoid adding a group table unless there is a real product requirement.

---

# 18. Optional Strategy Group Concept — NOT Required for P0

If later you want persistent user-facing groups:

```text
Momentum Large Caps
  ├── RELIANCE
  ├── TCS
  └── INFY
```

you could eventually add:

```text
strategy_groups
subscription.group_id
```

But DO NOT add this merely to implement multi-stock.

For the hackathon, grouping can be derived in the React UI by:

```text
kind
instance prefix
```

without altering financial architecture.

---

# 19. React Strategies Page

Current page:

```text
frontend/src/pages/StrategiesPage.jsx
```

currently provides:

```text
Strategy instance ID
Strategy dropdown
Single Symbol input
Subscribe strategy
```

Enhance it.

---

# 20. New Multi-Stock Form

Recommended UI:

```text
ADD MULTI-STOCK STRATEGY

Strategy
[ Momentum ▼ ]

Instance prefix
[ momentum ]

Stocks
[ RELIANCE           ] [Add]

Selected:
[ RELIANCE × ] [ TCS × ] [ INFY × ] [ HDFCBANK × ]

or paste:
[ RELIANCE, TCS, INFY, HDFCBANK ]

4 stocks selected

Preview
momentum-reliance
momentum-tcs
momentum-infy
momentum-hdfcbank

[ RUN ON 4 STOCKS ]
```

Keep the wording simple.

---

# 21. Symbol Entry UX

P0 should NOT require a huge hardcoded list of Indian stocks.

Support:

```text
type symbol
press Enter
comma-separated paste
remove chip
clear all
```

Normalize:

```text
uppercase
trim spaces
deduplicate
```

Examples accepted:

```text
RELIANCE
TCS
INFY
HDFCBANK
```

If later using Yahoo symbols:

```text
RELIANCE.NS
TCS.NS
```

the symbol should be preserved.

Do not silently append `.NS` in the UI unless the market-data provider contract explicitly requires it.

---

# 22. Frontend API Integration

Do not scatter raw `fetch`.

Use the existing shared `api` client.

Call:

```text
POST /api/subscriptions/batch
```

once.

Show:

```text
Creating 4 strategy instances...
```

then:

```text
Created successfully:
RELIANCE
TCS
INFY
HDFCBANK
```

On conflict:

```text
Could not create the set.

Already exists:
momentum-reliance

Nothing was created.
```

The UI must reflect the backend's atomic behavior.

---

# 23. Preserve Single-Stock Creation

Two acceptable UX options:

## Option A — One form supports both

If selected symbols = 1:

```text
Create strategy
```

If selected symbols > 1:

```text
Run on 4 stocks
```

This is preferred.

## Option B — Tabs

```text
Single Stock | Multi Stock
```

Avoid duplicating too much form code.

---

# 24. Strategy Table

The existing table already contains:

```text
Strategy
Kind
Symbol
State
Control
```

This naturally supports multiple stocks.

Enhance with optional filters:

```text
Filter by strategy kind
Filter by symbol
Filter by RUNNING/STOPPED/HALTED
```

Example:

```text
Kind: Momentum
Symbol: All
State: Running
```

These are frontend presentation filters only.

---

# 25. Grouped View

Optional P1 UI:

```text
Momentum
────────────────────────────
RELIANCE     RUNNING
TCS          RUNNING
INFY         STOPPED

3 stocks · 2 running
```

Do not hide individual strategy instance IDs completely.

Technical evidence still needs them.

---

# 26. Overview Page

Add a small multi-stock summary.

Example:

```text
Active Stocks     4
Strategy Instances 7
```

Stocks can be derived from:

```text
unique subscription.symbol
```

This is display-only aggregation and is safe to calculate client-side.

Do not change backend financial state for this.

---

# 27. Market Data Page

The current backend replay already uses enabled subscription symbols.

Enhance Market Data page with symbol filtering:

```text
All
RELIANCE
TCS
INFY
HDFCBANK
```

Show:

```text
feed freshness by symbol if available
recent ticks
candles
signals
```

Do not add direct browser calls to Yahoo/021.

React continues to consume AlgoShield backend data.

---

# 28. Risk Page

No risk-engine rewrite should be needed.

Current per-strategy risk already keys by:

```text
strategy_instance_id
symbol
```

Account risk is also symbol-aware.

The page should display multi-symbol budgets cleanly:

```text
RELIANCE
  momentum-reliance
  breakout-reliance

TCS
  momentum-tcs
```

Optional frontend grouping by symbol is useful.

---

# 29. Orders / Fills / Traces

No backend architecture change required.

These records already contain symbols.

Add symbol filters where useful:

```text
Orders page
Fills page
Traces page
Audit page
```

Do not alter order attribution.

---

# 30. Market Data Behavior

For the current deterministic replay mode:

```text
enabled subscription symbols
       ↓
Platform.start_replay_stream()
       ↓
generate_simulation_batch(symbols)
       ↓
ticks for all symbols
```

This already supports multiple stocks.

Add tests proving it.

---

# 31. Future Real Market Feed Rule

If a live market-data provider is later added, its subscription logic must dynamically subscribe to the set:

```text
enabled strategy symbols
```

Concept:

```text
subscriptions changed
       ↓
desired_symbols = unique enabled symbols
       ↓
MarketDataProvider.update_subscriptions(desired_symbols)
```

Do NOT implement this provider change unless a real live provider currently exists in the merged repository.

For the current replay architecture, no extra provider work is necessary.

---

# 32. Failure Isolation

Critical test:

```text
momentum-reliance callback fails
```

Expected:

```text
momentum-reliance → STOPPED/HALTED

momentum-tcs → continues

momentum-infy → continues
```

One stock/instance failure must not halt every instance of the same strategy kind.

The existing one-instance-per-symbol design makes this possible.

---

# 33. Indicator Isolation

Critical test:

Feed:

```text
RELIANCE prices:
100, 101, 102...

TCS prices:
300, 280, 260...
```

Expected:

```text
momentum-reliance indicator state
!=
momentum-tcs indicator state
```

No candle from one stock may update another stock's strategy state.

Test the existing behavior explicitly.

---

# 34. P&L Isolation

Example:

```text
momentum-reliance → +100 shares
momentum-tcs      → -40 shares
```

Expected:

```text
separate strategy positions
separate average prices
separate realized P&L
separate unrealized P&L
```

Account-level summaries can aggregate them where appropriate.

Do not merge their strategy ledgers.

---

# 35. Risk Isolation

Per-strategy rule:

```text
momentum-reliance limit = 100
momentum-tcs limit      = 50
```

A RELIANCE rejection must not incorrectly consume TCS risk.

Account risk remains symbol-specific according to the current USP design.

---

# 36. Start/Stop Isolation

Test:

```text
Stop momentum-tcs
```

Expected:

```text
momentum-reliance RUNNING
momentum-tcs      STOPPED
momentum-infy     RUNNING
```

Replay may continue to produce TCS ticks if another enabled TCS subscription exists.

If no enabled strategy requires TCS, the current symbol selection may naturally remove it from new replay batches.

---

# 37. Duplicate Rules

This should be allowed:

```text
momentum-reliance
breakout-reliance
mean-reversion-reliance
```

because these are independent strategies on the same stock.

This should conflict:

```text
momentum-reliance
momentum-reliance
```

same instance ID.

Whether two differently named instances of the same kind+symbol are allowed should remain consistent with the existing architecture.

Recommended:

```text
allowed
```

because strategy instance ID is the true identity.

Example:

```text
momentum-fast-reliance
momentum-slow-reliance
```

may later support different parameters.

---

# 38. Backend Tests

Add a focused file such as:

```text
tests/test_multi_stock_subscriptions.py
```

Required tests:

### Batch creation

```text
POST 3 symbols
→ creates 3 subscription rows
```

### Normalization

```text
reliance
 RELIANCE
TCS

→ unique RELIANCE, TCS
```

### Atomic conflict

Existing:

```text
momentum-tcs
```

Batch:

```text
RELIANCE
TCS
INFY
```

Expected:

```text
409
no RELIANCE created
no INFY created
existing TCS unchanged
```

### Unknown strategy

```text
kind = made_up_strategy
→ 409/validation failure
→ zero rows created
```

### Authentication

```text
anonymous batch request
→ 401
```

### Account ownership

Created instances belong only to authenticated account.

### Upper bound

```text
>20 symbols
→ validation error
```

### Runtime symbol isolation

RELIANCE candle only invokes RELIANCE subscriptions.

### Multiple symbols same kind

Momentum on RELIANCE and TCS can both run.

### Stop isolation

Stop TCS instance; RELIANCE continues.

### Indicator isolation

States remain separate.

### Replay symbols

Enabled multi-stock subscriptions cause replay generation for each selected symbol.

### Financial attribution

Fills/positions remain attributed to their specific instance+symbol.

---

# 39. Frontend Tests

Add/update tests around `StrategiesPage`.

Suggested:

```text
frontend/src/test/multiStockStrategies.test.jsx
```

Test:

```text
strategy registry loads
user can add symbol chip
comma-separated symbols normalize
duplicates removed
symbol chip can be removed
preview IDs shown
button says Run on N stocks
single POST batch request sent
loading state prevents double submission
successful response refreshes snapshot
409 conflict displays useful message
no fake partial success
max symbol count handled
existing subscription table still renders
start/stop buttons still work
```

---

# 40. No Fake Stock Availability

Do not hard-code claims that a stock is actually available from a live exchange feed.

Current deterministic replay can simulate arbitrary normalized symbols.

If/when a real provider is active, validation should come from:

```text
backend provider capability
```

not a frontend hard-coded stock list.

---

# 41. Optional Symbol Presets

P1 convenience only:

```text
Popular Demo Stocks:
RELIANCE
TCS
INFY
HDFCBANK
ICICIBANK
SBIN
```

These should be labeled:

```text
Quick select
```

not:

```text
Only supported stocks
```

The manual symbol field remains available.

---

# 42. API Security

Batch endpoint:

```text
require_user(request)
```

Account ID must be derived from authenticated session.

Do NOT accept:

```json
{
  "account_id": "someone-else"
}
```

from the frontend.

This mirrors the existing secure `/api/subscriptions` behavior.

---

# 43. Rate / Resource Limits

Batch endpoint max symbols:

```text
20
```

recommended.

Also bound:

```text
symbol length
prefix length
request payload
```

Use Pydantic validation.

Do not let one request create thousands of runtime instances.

---

# 44. Error Cases

Handle clearly:

```text
empty symbol list
duplicate symbols
unknown strategy kind
invalid/blank symbols
instance ID collision
too many symbols
authentication failure
backend unavailable
reconciliation/gate state restrictions if existing subscribe path enforces any
database failure
```

Never tell the UI:

```text
4 strategies created
```

unless the transaction committed.

---

# 45. Audit / Traceability

After successful batch creation, the Audit page should make it clear:

```text
MULTI-STOCK SUBSCRIPTION CREATED

Strategy kind: momentum
Symbols: RELIANCE, TCS, INFY
Instances: 3
```

If individual `SUBSCRIBED` events are preserved, the existing audit page can also show each instance.

---

# 46. Documentation Updates

Update relevant:

```text
README.md
docs/ARCHITECTURE.md
docs/CONTRACTS.md
docs/TESTING.md
docs/DECISIONS.md
docs/PHASE_PLAN.md
docs/progress/INTEGRATION.md
```

Document clearly:

> Multi-stock execution is implemented as multiple independent single-symbol strategy instances created in one atomic batch. A strategy instance itself remains single-symbol.

This is an important architectural decision.

---

# 47. Recommended Architecture Documentation

Add:

```text
User chooses:
Momentum + [RELIANCE, TCS, INFY]

            ↓

Subscription Batch Service

       ┌────┼────┐
       ↓    ↓    ↓
   momentum momentum momentum
   RELIANCE   TCS    INFY

       ↓      ↓      ↓

Independent:
state
risk
orders
fills
P&L
```

---

# 48. Implementation Phases

## Phase 0 — Git integration

```text
preserve local changes
fetch origin
merge latest main
reapply local changes
baseline tests
create local feature branch if needed
```

## Phase 1 — Batch backend contract

```text
BatchSubscriptionRequest
ID normalization helper
subscribe_many()
POST /api/subscriptions/batch
```

## Phase 2 — Backend tests

```text
atomicity
auth
normalization
symbol isolation
replay support
```

## Phase 3 — React multi-symbol form

```text
strategy select
prefix
symbol chips
comma paste
preview
batch submit
```

## Phase 4 — Multi-stock presentation

```text
strategy table filters
active stock count
Market Data symbol filter
Risk grouping if useful
```

## Phase 5 — Frontend tests

```text
form
request
errors
refresh
```

## Phase 6 — Full regression

```text
pytest
ruff
frontend test
frontend lint
frontend build
browser smoke
```

## Phase 7 — Documentation

Update canonical docs and integration progress.

---

# 49. Definition of Done

Feature is complete only when:

## Git

- latest `origin/main` safely integrated;
- no local user work lost;
- implementation exists locally on current/feature branch;
- no push performed unless requested.

## Backend

- `POST /api/subscriptions/batch` exists;
- authenticated account derived server-side;
- creates N independent single-symbol instances;
- atomic all-or-nothing behavior;
- existing single subscription endpoint still works;
- no schema rewrite required.

## Runtime

- same strategy kind can run on multiple symbols;
- each symbol has isolated indicator state;
- stopping/failing one instance does not stop siblings;
- current replay feed generates data for all enabled symbols.

## Financial correctness

- orders retain correct strategy + symbol;
- fills retain correct strategy + symbol;
- P&L remains independent per strategy instance;
- risk remains independent per strategy instance and symbol;
- account risk remains authoritative.

## Frontend

User can:

```text
choose strategy
add multiple symbols
preview generated instances
submit once
see all created rows
start/stop each independently
```

## Safety

- batch conflict creates zero new rows;
- duplicate click cannot accidentally create duplicate instances;
- no frontend financial/risk truth is invented.

## Tests

Pass:

```text
backend focused multi-stock tests
backend full regression
Ruff
frontend tests
frontend lint
frontend build
browser smoke where available
```

If environment prevents a check, report it explicitly.

---

# 50. Demo Scenario

A clean judge demo:

```text
1. Open Strategies.

2. Select:
   Momentum

3. Add:
   RELIANCE
   TCS
   INFY

4. Click:
   RUN ON 3 STOCKS

5. Show three independent instances:
   momentum-reliance
   momentum-tcs
   momentum-infy

6. Start replay.

7. Open Market Data:
   show ticks/candles for all 3 symbols.

8. Open Orders:
   orders are attributed to correct symbol + strategy.

9. Open Risk:
   each instance has independent budget.

10. Stop TCS only.

11. Show:
    RELIANCE continues
    INFY continues
    TCS stops.

12. Show independent position/P&L.
```

This demonstrates true multi-stock support without complicating the safety architecture.

---

# 51. Final Architectural Statement

Use this in the presentation:

> **AlgoShield scales a strategy across multiple stocks by creating isolated single-symbol strategy instances in one atomic operation. This preserves independent state, risk, execution, P&L, and failure containment for every stock while giving the user a simple multi-stock workflow.**

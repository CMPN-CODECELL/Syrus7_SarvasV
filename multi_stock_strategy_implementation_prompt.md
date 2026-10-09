# AI Coding Agent Prompt — Implement Multi-Stock Strategies in AlgoShield

You are working inside the latest **AlgoShield / Syrus7_SarvasV** repository.

Your task is to implement the feature described in:

```text
multi_stock_strategy_implementation_plan.md
```

The objective is:

> Let a user select one strategy type and multiple stocks in the React UI, then create independent single-symbol strategy instances for all selected stocks in one atomic backend operation.

Do NOT redesign the strategy engine.

The architectural rule remains:

```text
ONE STRATEGY INSTANCE = ONE SYMBOL
```

Multi-stock means:

```text
one user action
→ multiple independent strategy instances
```

---

## 1. FIRST — Safely integrate latest `origin/main`

Before changing code, run:

```bash
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate -10
```

The previously inspected project was on `main` and contained local uncommitted work, but re-check the real repository.

Never destroy local changes.

DO NOT run:

```text
git reset --hard
git checkout .
git restore .
git clean -fd
```

against user work.

If dirty:

```bash
git diff
git diff --staged
git stash push -u -m "pre-multi-stock implementation backup"
git stash list
```

Then:

```bash
git fetch origin --prune
git rev-list --left-right --count origin/main...HEAD
git log --oneline --left-right --cherry-pick origin/main...HEAD
```

If on `main` and there are no local divergent commits:

```bash
git merge --ff-only origin/main
```

Otherwise:

```bash
git merge origin/main
```

Resolve conflicts manually.

Preserve the latest:

```text
React migration
USP implementation
Failure Lab
Safety Proof
Risk/reliability logic
API auth
tests
```

If you stashed:

```bash
git stash pop
```

Resolve remaining conflicts.

Do NOT drop backup stash until validation succeeds.

If implementation would otherwise happen directly on `main`, prefer creating:

```bash
git switch -c feature/multi-stock-strategies
```

Do not push to remote unless explicitly instructed.

---

## 2. Read the current repository before coding

Read:

```text
AGENTS.md
README.md
docs/ARCHITECTURE.md
docs/CONTRACTS.md
docs/INTEGRATION_RULES.md
docs/SAFETY_INVARIANTS.md
docs/TESTING.md
docs/DECISIONS.md
docs/PHASE_PLAN.md
docs/TEAM_OWNERSHIP.md
docs/progress/INTEGRATION.md
multi_stock_strategy_implementation_plan.md
```

Inspect current implementations:

```text
backend/api.py
backend/platform.py
backend/strategies/runtime.py
backend/market_data/
backend/risk/
backend/accounting/
backend/shared/store.py
frontend/src/pages/StrategiesPage.jsx
frontend/src/pages/OverviewPage.jsx
frontend/src/pages/RiskPage.jsx
frontend/src/pages/OrdersPage.jsx
frontend/src/pages/EvidencePages.jsx
frontend/src/api/client.js
frontend/src/styles/
```

Treat the current post-merge repository as source of truth.

If names/routes differ from the plan, adapt to the current architecture rather than duplicating systems.

---

## 3. Baseline tests before changes

Run:

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

Frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
```

If packaged `frontend/node_modules` is broken/stale, it is generated content; reinstall it safely:

```bash
rm -rf frontend/node_modules
npm --prefix frontend ci
```

Do not delete source files.

If backend environment dependencies block tests, report the exact blocker and run the largest valid subset.

---

## 4. Confirm existing multi-symbol foundation

Before adding code, verify these current behaviors still exist:

### Subscription identity

A subscription contains:

```text
id
account
kind
symbol
enabled
```

### Strategy runtime

`on_candle()` selects only enabled subscriptions matching:

```text
candle.symbol
```

### Replay

`generate_simulation_batch()` accepts multiple symbols.

`start_replay_stream()` collects symbols from enabled subscriptions.

If these still exist, DO NOT rewrite them.

---

## 5. Backend — add atomic batch subscription creation

Add an authenticated endpoint:

```text
POST /api/subscriptions/batch
```

Suggested request:

```json
{
  "kind": "momentum",
  "symbols": ["RELIANCE", "TCS", "INFY"],
  "instance_prefix": "momentum"
}
```

Account ID must come from:

```text
require_user(request)
```

Never accept arbitrary `account_id` from browser.

---

## 6. Add Pydantic request validation

Add a request model equivalent to:

```python
class BatchSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    symbols: list[str]
    instance_prefix: str | None = None
```

Rules:

```text
kind normalized lower-case
symbols trimmed + uppercased
blank symbols invalid
duplicates normalized consistently
1–20 unique symbols
prefix trimmed
prefix length bounded
```

Do not permit unbounded creation.

---

## 7. Instance ID generation

Generate deterministic instance IDs.

Recommended:

```text
{prefix}-{symbol-slug}
```

Examples:

```text
momentum-reliance
momentum-tcs
momentum-infy
```

If prefix omitted:

```text
prefix = kind
```

Preserve actual trading symbol separately.

Example:

```text
ID     abc-ns
Symbol ABC.NS
```

Use a small tested helper to convert symbol to safe ID fragment.

Do not alter symbol semantics.

---

## 8. Implement service/runtime method

Add to the appropriate strategy runtime/service:

```python
subscribe_many(account, kind, symbols, instance_prefix=None)
```

or a well-named equivalent.

The API route should not own domain/database logic if the current architecture keeps subscription lifecycle inside StrategyRuntime.

Responsibilities:

```text
validate kind
validate account
normalize symbols
generate IDs
pre-check ALL collisions
insert ALL rows atomically
audit operation
initialize per-instance runtime bookkeeping
return created subscriptions
```

---

## 9. Atomicity is mandatory

Do NOT implement the batch endpoint by repeatedly calling an API route.

Use one database transaction.

Required behavior:

Existing:

```text
momentum-tcs
```

Request:

```text
RELIANCE
TCS
INFY
```

Result:

```text
409 conflict
RELIANCE NOT created
INFY NOT created
existing TCS unchanged
```

No partial batch.

Add an explicit regression test.

---

## 10. Preserve existing single create API

Do not remove or break:

```text
POST /api/subscriptions
```

Existing clients/tests must remain valid.

Batch is additive.

---

## 11. Do NOT add a symbols array to a subscription row

Do NOT change the model to:

```text
one subscription → many symbols
```

Do NOT add:

```text
subscriptions.symbols JSON
```

No DB migration should be necessary for P0.

Each created symbol remains one normal existing subscription row.

---

## 12. Audit evidence

Record a useful batch event, for example:

```text
SUBSCRIPTIONS_BATCH_CREATED
```

with:

```text
account
kind
prefix
symbols
instance IDs
count
```

If existing audit behavior relies on per-instance `SUBSCRIBED`, preserve it or document the new equivalent.

Do not weaken traceability.

---

## 13. React — migrate Strategies form to multi-symbol UX

Update:

```text
frontend/src/pages/StrategiesPage.jsx
```

Do not create a giant replacement component.

Extract small components/hooks if useful.

Required UX:

```text
Strategy
[ Momentum ▼ ]

Instance prefix
[ momentum ]

Stocks
[ symbol input ] [ Add ]

Selected:
[ RELIANCE × ]
[ TCS × ]
[ INFY × ]

Support comma-separated paste.

Preview:
momentum-reliance
momentum-tcs
momentum-infy

[ RUN ON 3 STOCKS ]
```

A single selected stock should also work.

You may replace the old one-symbol form with this unified form.

---

## 14. Frontend symbol rules

Normalize UI input:

```text
trim
uppercase
deduplicate
```

Preserve valid punctuation such as:

```text
RELIANCE.NS
```

Do not automatically append `.NS`.

Do not claim a hardcoded list is the complete supported market universe.

Manual symbol entry remains available.

Maximum selected symbols should match backend max.

---

## 15. Use one backend request

On submit, React sends exactly one:

```text
POST /api/subscriptions/batch
```

Do not loop:

```text
POST RELIANCE
POST TCS
POST INFY
```

The UI should show:

```text
Creating 3 strategy instances...
```

Disable duplicate submission while pending.

After success:

```text
refresh current snapshot
clear/reset selected symbols appropriately
show success
```

After 409:

```text
show conflict
state clearly that nothing was created
```

Never show partial success if backend rolled back.

---

## 16. Existing subscriptions table

Keep rendering every instance independently.

Current columns should remain conceptually:

```text
Strategy Instance
Kind
Symbol
State
Control
```

Add optional filters:

```text
strategy kind
symbol
state
```

Do not hide strategy instance identity.

---

## 17. Optional grouped presentation

If clean and low-risk, add a visual grouping:

```text
Momentum
RELIANCE   RUNNING
TCS        RUNNING
INFY       STOPPED
```

This is presentation only.

Underlying records remain independent.

P0 does not require persistent group schema.

---

## 18. Overview multi-stock summary

Add useful display-only metrics if appropriate:

```text
Active Stocks
Strategy Instances
```

`Active Stocks` may be computed as unique subscription symbols in React.

That is display aggregation, not financial truth.

---

## 19. Market Data filters

If current Market Data UI allows easy extension, add symbol filtering using symbols from current subscriptions:

```text
All
RELIANCE
TCS
INFY
```

Do not call Yahoo/021 directly from React.

Use backend state only.

This is P1 if time is constrained.

---

## 20. Risk / Orders / Traces

Do not rewrite backend logic.

Current records are already symbol-aware.

Optional frontend grouping/filtering:

```text
Risk → group by symbol
Orders → filter by symbol
Fills → filter by symbol
Traces → filter by symbol
Audit → filter by symbol
```

Only implement where straightforward.

---

## 21. Required backend tests

Add:

```text
tests/test_multi_stock_subscriptions.py
```

or equivalent organization.

Must cover:

```text
batch creates multiple symbols
normalization/deduplication
batch is atomic on collision
unknown strategy creates nothing
authentication required
created rows belong to signed-in account
max symbol count enforced
same kind can run on multiple symbols
RELIANCE candle does not update TCS instance
indicator state isolated per instance
stop one instance does not stop siblings
replay includes enabled symbols
financial attribution remains strategy+symbol correct
```

Do not weaken existing tests.

---

## 22. Required frontend tests

Add/update tests, e.g.:

```text
frontend/src/test/multiStockStrategies.test.jsx
```

Cover:

```text
add symbol
comma paste
uppercase normalization
duplicate removal
remove chip
generated ID preview
button displays N stocks
single batch request
loading prevents duplicate submission
success refreshes
409 displays useful error
no partial-success message
existing strategy table remains functional
start/stop remains functional
```

---

## 23. Failure isolation test

Explicitly verify:

```text
momentum-reliance fails
```

does NOT stop:

```text
momentum-tcs
momentum-infy
```

Do not create global per-kind indicator state.

---

## 24. Replay verification

The current simulator should already use:

```text
unique enabled subscription symbols
```

Add a test proving a multi-stock batch results in replay ticks/candles for all selected symbols.

Do not modify replay architecture unless this behavior was removed in newer main.

---

## 25. Live-market provider rule

If latest main now includes a live market-data provider, inspect it.

Only if necessary, make the provider dynamically subscribe to:

```text
unique enabled subscription symbols
```

Do NOT invent a provider abstraction change if current project is still replay/mock.

Do NOT make browser/frontend direct market-data connections.

---

## 26. Security

Batch endpoint requires authentication.

Never accept account ownership from client.

No user can create subscriptions in another account.

If optional batch start/stop endpoint is implemented, verify every requested strategy belongs to current account before any mutation.

---

## 27. Documentation

Update relevant docs:

```text
README.md
docs/ARCHITECTURE.md
docs/CONTRACTS.md
docs/TESTING.md
docs/DECISIONS.md
docs/PHASE_PLAN.md
docs/progress/INTEGRATION.md
```

Document this architectural statement exactly in meaning:

> Multi-stock strategy execution is implemented as multiple independent single-symbol strategy instances created atomically in one user operation. Strategy state, risk, execution, accounting, and failure isolation remain per instance.

---

## 28. Full verification

After implementation run:

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

Frontend:

```bash
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Run relevant browser smoke test if available.

If environment prevents any check, report exact reason.

Do not claim that check passed.

---

## 29. Do not push

The requested workflow is:

```text
fetch/merge origin main
integrate locally
implement locally
test locally
```

Do NOT run:

```bash
git push
```

unless user explicitly asks later.

---

## 30. Final report

When finished, provide:

1. Git state before implementation.
2. How `origin/main` was integrated.
3. Any merge conflicts and how they were resolved.
4. Local branch used.
5. Backend files changed.
6. Frontend files changed.
7. New endpoint contract.
8. Exact multi-stock architecture.
9. Tests added.
10. Backend test results.
11. Frontend test results.
12. Build/lint results.
13. Any blockers.
14. Exact commands for the user to run.
15. Confirmation that no remote push occurred.

Do not say DONE unless the implementation and relevant tests actually exist.

---

## Final intended behavior

User:

```text
Strategy: Momentum

Stocks:
RELIANCE
TCS
INFY
```

clicks:

```text
RUN ON 3 STOCKS
```

Backend atomically creates:

```text
momentum-reliance → RELIANCE
momentum-tcs      → TCS
momentum-infy     → INFY
```

Then the existing AlgoShield architecture independently handles:

```text
ticks
candles
signals
risk
orders
fills
positions
P&L
failures
```

for each strategy instance.

The feature must preserve AlgoShield's safety model while making multi-stock operation simple for the user.

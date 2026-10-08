# AlgoShield USP Implementation Plan

**Project:** AlgoShield — SYRUS 7.0 PS-06  
**Owner focus:** Member 3 (Ram) — Risk, Security, Reliability & Scale  
**Goal:** Turn AlgoShield from a correct PS-06 implementation into a prototype that can **prove safety under failure**, demonstrate more adversarial edge cases than competing teams, and produce measurable safety/performance results.

---

# 1. Product Positioning

AlgoShield should NOT be presented as:

> "A trading platform with three strategies."

It should be presented as:

> **"A safety and execution control plane for multi-strategy automated trading."**

The core differentiator is:

> **AlgoShield assumes strategies, networks, brokers, servers, and market-data feeds can fail. It contains the failure, reconstructs truth, blocks unsafe actions, and proves when the account is safe again.**

The PS defines the baseline features. These USPs are the differentiation layer.

---

# 2. Non-Negotiable Existing Architecture

Do not redesign the project.

Preserve the existing flow:

```text
Market Data
    ↓
Candle Builder
    ↓
Strategy Runtime
    ↓
OrderIntent
    ↓
RiskGateway
    ↓
OrderManager
    ↓
BrokerAdapter
    ↓
Fill
    ↓
Ledger
    ↓
Reconciliation / Reliability
    ↓
Dashboard
```

Existing rules that MUST remain true:

```text
Strategy never calls broker directly.
Order != Fill.
Only fills change financial position.
Every fill retains strategy attribution.
Broker-specific behavior stays inside adapters.
Uncertain state fails closed.
Restart never auto-resumes trading.
Kill success requires verification.
UI never invents safety state.
```

Before implementation, read:

```text
AGENTS.md
README.md
docs/REQUIREMENTS.md
docs/ARCHITECTURE.md
docs/CONTRACTS.md
docs/INTEGRATION_RULES.md
docs/SAFETY_INVARIANTS.md
docs/TESTING.md
docs/DECISIONS.md
docs/PHASE_PLAN.md
docs/TEAM_OWNERSHIP.md
```

Do not invent undocumented 021 behavior.

---

# 3. Current Baseline

The current project already has strong foundations.

| Feature | Current status | Existing location |
|---|---|---|
| Per-strategy max position | Implemented | `backend/risk/gateway.py` |
| Max daily loss | Implemented | `backend/risk/gateway.py` |
| Orders/minute | Implemented | `backend/risk/gateway.py` |
| Exposure reservation | Implemented | `backend/risk/gateway.py` |
| Global trading gate | Implemented | `backend/risk/gateway.py` |
| Stale broker protection | Implemented | `backend/reliability/control.py` |
| Stale market-feed protection | Implemented | `backend/reliability/control.py` |
| Reconciliation | Implemented | `backend/reliability/control.py` |
| Fail-closed restart | Implemented | `backend/reliability/control.py` |
| Durable kill latch | Implemented | `backend/reliability/control.py` |
| Verified kill | Implemented | `backend/reliability/control.py` |
| Kill certificate | Basic version implemented | `KillCertificate` |
| Duplicate/conflicting fills | Implemented | `OrderManager` / `Ledger` |
| Failure Lab | Strong initial version | `backend/reliability/failure_lab.py` |
| Safety indicators | Basic version implemented | `frontend/index.html` |
| Audit timeline | Basic version implemented | `frontend/index.html` |
| Risk reason codes | Basic version implemented | `RiskDecision.reason_code` |
| Account-wide risk | Missing | — |
| Structured risk explanations | Missing | — |
| SafetyBench | Missing | — |
| Correlated incident trace | Missing | — |
| Runtime benchmark metrics | Missing | — |
| Price reasonability guard | Missing | — |
| Complete API authorization | Incomplete | `backend/api.py` |

The implementation must **extend** existing behavior, not replace it.

---

# 4. Priority Order

Implement in this order:

```text
PHASE 0 — Preserve baseline + secure control plane
PHASE 1 — Explainable risk decisions
PHASE 2 — Account-wide cross-strategy risk
PHASE 3 — Price reasonability
PHASE 4 — Safety Proof Engine
PHASE 5 — Reconciliation Center
PHASE 6 — Incident Trace
PHASE 7 — Failure Lab expansion
PHASE 8 — Kill Certificate V2
PHASE 9 — Metrics Registry
PHASE 10 — SafetyBench
PHASE 11 — Dashboard integration
PHASE 12 — Benchmark + adversarial verification
```

Never sacrifice existing P0 correctness to finish a USP.

---

# 5. PHASE 0 — Baseline Protection and Security Hardening

## Goal

Before adding differentiators, ensure critical operational endpoints cannot be called anonymously.

The current dashboard requires authentication, but several sensitive APIs currently do not consistently call `require_user()`.

At minimum protect:

```text
PUT  /api/risk/policies/{strategy}
PUT  /api/risk/strategies/{strategy}
POST /api/failure-lab/{scenario}
POST /api/reconcile
POST /api/resume
POST /api/reduce-only
POST /api/kill
POST /api/kill/reset
POST /api/orders/{order_id}/cancel
POST /api/broker/disconnect
POST /api/broker/reconnect
POST /api/market/session
```

Also protect state/telemetry endpoints if they expose account or trading information.

## Required behavior

Every sensitive request must:

```text
Request
  ↓
Authentication
  ↓
Account ownership / operator authorization
  ↓
Operation
```

For strategy-specific routes:

```text
Authenticated user's account_id
        ↓
Lookup subscription
        ↓
subscription.account == user.account_id ?
       / \
     yes  no
     ↓     ↓
 execute  403
```

For order cancellation:

```text
Authenticated user's account
        ↓
Lookup order
        ↓
order.account == user.account_id ?
```

For global demo controls such as kill/reconcile/failure-lab:

- Require an authenticated operator.
- Current bootstrap may treat every authenticated local user as an operator.
- Clearly document that this is **not production RBAC**.

## Files

Modify:

```text
backend/api.py
tests/test_auth.py
```

Add:

```text
tests/test_control_plane_security.py
```

## Required tests

```text
anonymous risk policy change -> 401
anonymous kill -> 401
anonymous reconcile -> 401
anonymous failure-lab -> 401
authenticated owner can change own strategy policy
user A cannot modify user B strategy -> 403
user A cannot cancel user B order -> 403
```

## Definition of Done

- Critical mutation endpoints require authentication.
- Account-scoped controls verify ownership.
- Existing authenticated UI still works.
- Tests prove unauthorized mutation is impossible.

---

# 6. USP 1 — Explainable Risk Decisions

## Goal

Replace generic:

```text
REJECTED
```

with:

```text
REJECTED — MAX_POSITION

Current filled:       80
Reserved BUY:         20
Reserved SELL:         0
Requested BUY:        10
Worst-case projected:110
Limit:                100
```

The judge should immediately understand **why** AlgoShield blocked an order.

---

## Existing foundation

Current:

```text
RiskDecision.reason_code
RiskDecision.reason_text
RiskDecision.rule_results
RiskGateway.budget()
```

But `reason_text` is currently generic and `rule_results` does not expose useful numeric evidence.

---

## Proposed contract change

Extend `RiskDecision` in `backend/shared/contracts.py` with a backward-compatible field:

```python
details: dict = field(default_factory=dict)
```

Do NOT rename existing fields.

Example:

```json
{
  "intent_id": "ema-001:123",
  "allowed": false,
  "reason_code": "RISK_MAX_POSITION",
  "projected_position": 110,
  "reason_text": "Projected strategy position would exceed the configured maximum.",
  "rule_results": [
    "GLOBAL_GATE:PASS",
    "SUBSCRIPTION:PASS",
    "RECONCILIATION:PASS",
    "DAILY_LOSS:PASS",
    "RATE_LIMIT:PASS",
    "MAX_POSITION:FAIL"
  ],
  "details": {
    "filled": 80,
    "reserved_buy": 20,
    "reserved_sell": 0,
    "requested_side": "BUY",
    "requested_quantity": 10,
    "projected": 110,
    "limit": 100,
    "available_buy": 0
  }
}
```

---

## Internal design

Create an internal result model inside `backend/risk/gateway.py`, for example:

```python
@dataclass
class RiskCheckResult:
    reason_code: str = ""
    projected_position: int | None = None
    reason_text: str = ""
    rule_results: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)
```

Change `_check()` to return `RiskCheckResult`, not an unstructured `(reason, projected)` tuple.

Do not expose this internal model outside risk.

---

## Required reason details

Implement structured evidence for:

```text
RISK_GLOBAL_GATE
RISK_DUPLICATE_INTENT
RISK_NOT_SUBSCRIBED
RISK_STRATEGY_STOPPED
RISK_RECONCILIATION_REQUIRED
RISK_STALE_BROKER_STATE
RISK_STALE_MARKET_DATA
RISK_MARKET_HALTED
RISK_MARKET_CLOSED
RISK_MAX_DAILY_LOSS
RISK_STRATEGY_HALTED
RISK_RATE_LIMIT
RISK_MAX_POSITION
RISK_NOT_REDUCING
RISK_ACCOUNT_NET_POSITION
RISK_ACCOUNT_GROSS_POSITION
RISK_PRICE_REASONABILITY
```

---

## API/UI

Expose recent risk decisions in platform snapshot:

```text
snapshot["risk_decisions"]
```

Return last 20 from audit history.

Dashboard card:

```text
LATEST RISK DECISION

REJECTED — POSITION LIMIT

Current      +80
Pending BUY  +20
Requested    +10
Projected   +110
Limit        +100
```

Add:

```text
Maximum additional BUY: 0
Maximum additional SELL: 200
```

when meaningful.

---

## Files

Modify:

```text
backend/shared/contracts.py
backend/risk/gateway.py
backend/platform.py
frontend/index.html
docs/CONTRACTS.md
```

Tests:

```text
tests/test_risk_explanations.py
tests/test_risk_policies.py
```

---

## Definition of Done

Every risk rejection:

- has a stable reason code;
- has human-readable reason text;
- includes numeric evidence where applicable;
- is auditable;
- appears on dashboard;
- never leaks broker secrets or raw internal exceptions.

---

# 7. USP 2 — Account-Wide Cross-Strategy Risk

## Goal

Prevent this:

```text
Strategy A +90
Strategy B +90
Strategy C +90

Each strategy limit = 100
Each strategy appears safe.

Account total = +270
```

AlgoShield must enforce risk at both:

```text
Strategy level
     +
Account level
```

---

## Required controls

Implement two account-level limits per symbol:

```text
1. max_net_position_per_symbol
2. max_gross_virtual_position_per_symbol
```

### Net

```text
A +100
B -60
C +20

Net = +60
```

### Gross virtual exposure

```text
|+100| + |-60| + |+20|
= 180
```

This prevents opposing strategies from hiding exposure through netting.

---

## Proposed contract

Add:

```python
@dataclass(frozen=True)
class AccountRiskPolicy:
    max_net_position_per_symbol: int | None = None
    max_gross_virtual_position_per_symbol: int | None = None
```

`None` means the account-level rule is not configured.

Do not introduce a restrictive default that breaks existing behavior.

---

## Database

Add additive migrations.

SQLite:

```text
backend/shared/sqlite_migrations/008_account_risk.sql
```

PostgreSQL:

```text
backend/shared/migrations/007_account_risk.sql
```

Suggested table:

```sql
CREATE TABLE account_risk_policies (
    account TEXT PRIMARY KEY REFERENCES accounts(id),
    max_net_position_per_symbol INTEGER,
    max_gross_virtual_position_per_symbol INTEGER
);
```

Use appropriate positive-value checks when non-null.

Never rewrite old migrations.

---

## Repository

Create:

```text
backend/risk/account_policies.py
```

Responsibilities:

```text
load policy
validate policy
persist policy
audit updates
```

---

## Risk calculation

For a given account + symbol:

### Net worst case

```text
filled account net
+ all pending buys
+ new buy
```

and independently:

```text
filled account net
- all pending sells
- new sell
```

Opposing pending orders must NOT be assumed to offset.

Take:

```text
max(abs(long endpoint), abs(short endpoint))
```

### Gross virtual worst case

For every strategy in the account/symbol:

```text
current strategy quantity
pending buys
pending sells
```

calculate that strategy's worst-case absolute exposure.

Then:

```text
gross = sum(each strategy worst-case absolute exposure)
```

Include the incoming intent in the appropriate strategy.

Reject if:

```text
projected_net > max_net_position_per_symbol
```

or:

```text
projected_gross > max_gross_virtual_position_per_symbol
```

---

## Reason codes

Add:

```text
RISK_ACCOUNT_NET_POSITION
RISK_ACCOUNT_GROSS_POSITION
```

Example:

```text
REJECTED — ACCOUNT_GROSS_POSITION

Strategy projected:       90
Account net projected:    20
Account gross projected: 240
Account gross limit:     200
```

---

## API

Add authenticated current-account endpoints:

```text
GET /api/risk/account-policy
PUT /api/risk/account-policy
```

Do NOT accept arbitrary account ID from the client.

Derive account from authenticated session.

Add account budget to snapshot:

```json
{
  "account_risk": [
    {
      "account_id": "acc_ram",
      "symbol": "RELIANCE",
      "net_filled": 60,
      "net_projected": 90,
      "gross_virtual": 180,
      "gross_projected": 210,
      "net_limit": 200,
      "gross_limit": 250
    }
  ]
}
```

---

## Files

Modify:

```text
backend/shared/contracts.py
backend/risk/gateway.py
backend/platform.py
backend/api.py
frontend/index.html
docs/CONTRACTS.md
docs/ARCHITECTURE.md
```

Add:

```text
backend/risk/account_policies.py
backend/shared/sqlite_migrations/008_account_risk.sql
backend/shared/migrations/007_account_risk.sql
tests/test_account_risk.py
```

---

## Critical tests

```text
A +90 / B +90 / C +90 with gross limit 200 -> reject third increase
A +100 / B -100 with net limit 50 but gross limit 150 -> reject due gross
A +100 / B -100 with net limit 50 and gross limit 250 -> allow if strategy limits allow
pending buys from two strategies count toward account projection
pending BUY and SELL do not automatically offset
two simultaneous intents racing for final account capacity -> only safe reservations succeed
lowering account limit below current exposure does not delete/alter positions
existing over-limit exposure may reduce but may not increase
```

---

# 8. USP 3 — Price Reasonability / Fat-Finger Guard

## Goal

Reject obviously dangerous LIMIT orders.

Example:

```text
Market mark = ₹2,500
Strategy LIMIT BUY = ₹25,000
```

Response:

```text
REJECTED — PRICE_REASONABILITY

Reference price: ₹2,500
Requested limit: ₹25,000
Deviation: 900%
Allowed: 5%
```

---

## Scope

Apply only to `LIMIT` orders.

Do not fake a limit price for `MARKET` orders.

Require a fresh risk mark before checking.

Existing stale-market-data protection remains authoritative.

---

## Risk policy

Extend `RiskPolicy`:

```python
max_price_deviation_bps: int = 500
```

500 basis points = 5%.

Add backward-compatible migration column with default 500.

Update:

```text
PolicyRequest
PolicyRepository
risk policy UI
docs
tests
```

---

## Calculation

```text
deviation =
abs(limit_price - reference_price)
/
reference_price
```

Convert to basis points:

```text
deviation_bps = deviation * 10000
```

Reject if:

```text
deviation_bps > max_price_deviation_bps
```

Do not use float for price math.

Use `Decimal`.

---

## Reason

```text
RISK_PRICE_REASONABILITY
```

Details:

```json
{
  "reference_price": "2500.00",
  "limit_price": "25000.00",
  "deviation_bps": "90000",
  "max_deviation_bps": 500
}
```

---

## Tests

```text
LIMIT within 5% -> passes price rule
LIMIT outside 5% -> rejected
MARKET order -> no fake price check
stale mark -> stale-market rejection occurs before price check
zero/invalid reference mark impossible
Decimal math remains exact
```

---

# 9. USP 4 — Safety Proof Engine

## Goal

Create a backend-generated, evidence-based proof object.

Do NOT simply show:

```text
SYSTEM HEALTHY
```

Show:

```text
WHY the platform currently considers itself safe.
```

---

## New module

Create:

```text
backend/reliability/proof.py
```

Class:

```python
class SafetyProofService:
    def __init__(self, store, ledger, risk, reliability, clock): ...

    def build(self) -> dict: ...
```

The service must be read-only.

It must never mutate trading state.

---

## Status model

Every invariant gets exactly one status:

```text
VERIFIED
FAILED
UNKNOWN
NOT_APPLICABLE
```

Never use VERIFIED without current evidence.

---

## Output

Example:

```json
{
  "verdict": "VERIFIED_SAFE",
  "generated_at": 123456,
  "evidence_fresh": true,
  "invariants": [
    {
      "id": "I1",
      "name": "No broker bypass",
      "status": "VERIFIED",
      "summary": "All 14 platform-originated orders have an approving risk decision.",
      "evidence": {
        "orders": 14,
        "approved_decisions": 14,
        "bypass_count": 0
      }
    }
  ]
}
```

Possible overall verdict:

```text
VERIFIED_SAFE
DEGRADED
UNSAFE
UNKNOWN
```

Suggested rules:

```text
any FAILED -> UNSAFE

no FAILED + one or more UNKNOWN -> UNKNOWN/DEGRADED

all required current invariants VERIFIED
+ reconciliation fresh
+ broker evidence fresh
-> VERIFIED_SAFE
```

Do not label KILLED as unhealthy merely because trading is stopped.

Safety and trading state are separate concepts.

---

## Runtime proof checks

### I1 — No broker bypass

For every locally known non-external order:

```text
there must exist an allowed RISK_DECISION
with matching intent/order correlation
```

Count:

```text
orders
approved decisions
bypasses
```

Emergency kill exits must also have `EMERGENCY_REDUCING_EXIT` approval.

---

### I2 — Fills create positions

Recompute a shadow signed fill quantity from durable unique fills.

Compare with current virtual position state.

If mismatch:

```text
FAILED
```

---

### I3 — Fill idempotency

Expose:

```text
duplicate fills ignored
conflicting duplicate events
double-applied fill mutations
```

Expected:

```text
double-applied = 0
```

---

### I4 — Strategy attribution

Count:

```text
unattributed fill rejections
attribution mismatches
verified unattributed broker fills
```

Any current verified snapshot with unattributed fill:

```text
FAILED
```

---

### I5 — Position risk

Inspect current approved/reserved orders and policy.

The proof should ensure no admitted reservation exceeds the policy that was authoritative when approved if that evidence can be reconstructed.

At minimum expose current:

```text
filled
pending buys
pending sells
strategy limit
account limit
```

If historical-policy reconstruction is unavailable:

```text
UNKNOWN
```

Do not fake VERIFIED.

---

### I6 — Kill/global gate

Expose:

```text
gate state
kill_latched
runtime_enabled
```

Unsafe state example:

```text
gate != RUNNING
but ordinary strategy callbacks active
```

---

### I7 — Restart safety

Use durable audit evidence.

When running after restart:

```text
RUNNING must only occur after successful reconciliation + explicit resume.
```

If proof cannot distinguish process history:

```text
UNKNOWN
```

until sufficient audit evidence exists.

---

### I8 — Broker reconciliation

Use existing fresh broker report:

```text
virtual aggregate == broker position
```

Only VERIFIED while broker snapshot evidence remains fresh.

Expired evidence -> UNKNOWN.

---

### I9 — Kill completion

If no kill requested:

```text
NOT_APPLICABLE
```

If last kill:

```text
SUCCESS/SAFE_LATE + fresh final verification
```

then VERIFIED.

FAILED -> FAILED.

---

### I10 — Unknown cannot increase risk

If:

```text
reconciliation uncertain
broker uncertain
feed stale
```

then gate must prevent risk-increasing dispatch.

If uncertain state coexists with RUNNING ordinary dispatch authority:

```text
FAILED
```

---

## Platform integration

Add:

```text
self.safety_proof = SafetyProofService(...)
```

Snapshot:

```text
snapshot["safety_proof"] = self.safety_proof.build()
```

Do not replace existing:

```text
snapshot["safety"]
```

until tests/UI have migrated.

---

## UI

Add panel:

```text
SAFETY PROOF
────────────────────────────
No broker bypass           VERIFIED
Fill idempotency           VERIFIED
Strategy attribution       VERIFIED
Position reconciliation    VERIFIED
Unknown-state containment  VERIFIED
Kill verification          N/A

Risk bypasses:             0
Unattributed fills:        0
Double-applied fills:      0

VERDICT: VERIFIED SAFE
```

Click/expand each invariant to show evidence.

---

## Tests

Add:

```text
tests/test_safety_proof.py
```

Test:

```text
normal reconciled state -> relevant invariants VERIFIED
expired broker evidence -> reconciliation UNKNOWN
drift -> reconciliation FAILED/UNKNOWN and verdict not safe
duplicate fill ignored -> no double mutation
conflicting fill -> unsafe/uncertain
manual broker position -> not verified
kill failure -> I9 failed
no kill -> I9 NOT_APPLICABLE
proof service never mutates state
```

---

# 10. USP 5 — Reconciliation Center

## Goal

Turn backend reconciliation into a visible product feature.

---

## Desired UI

Healthy:

```text
RECONCILIATION CENTER

                LOCAL    BROKER
RELIANCE          +60      +60      MATCH
TCS               -20      -20      MATCH

Last verified: 0.7s ago
Status: MATCHED
```

Drift:

```text
RELIANCE

LOCAL   +60
BROKER  +80
DELTA   +20

DRIFT DETECTED
NEW EXPOSURE BLOCKED
```

Recovery:

```text
Missing fill discovered
        ↓
Fill imported
        ↓
Ledger replayed
        ↓
Local +80
Broker +80
        ↓
MATCHED
```

---

## Backend improvements

Enhance `Reliability.reconcile()` report.

When possible include:

```json
{
  "position_diff": [
    {
      "account_id": "acc_ram",
      "symbol": "RELIANCE",
      "local": 60,
      "broker": 80,
      "delta": 20
    }
  ],
  "recovered_fill_ids": [],
  "recovered_fill_count": 0,
  "open_orders": 0,
  "reason": "VIRTUAL_POSITION_DRIFT"
}
```

During successful fill recovery record which fills were newly applied.

Do not fabricate balancing fills.

---

## API

Add:

```text
GET /api/reconciliation
```

Return:

```text
current report
broker evidence freshness
position comparison
last N reconciliation-related audit events
```

POST `/api/reconcile` remains the action.

---

## UI

Add a dedicated reconciliation section.

Show:

```text
LOCAL ↔ BROKER
MATCHED / DRIFTED / UNKNOWN
```

Include:

```text
last verified time
snapshot age
recovered fills
position diffs
unknown orders
```

---

## Tests

```text
local +60 / broker +80 -> visible delta +20
missed fill -> recovered fill ID shown
successful recovery -> MATCHED
stale snapshot -> UNKNOWN, not MATCHED
incomplete snapshot -> fail closed
unknown broker order -> fail closed
```

---

# 11. USP 6 — Correlated Incident / Execution Trace

## Goal

Allow a judge to follow one trade from strategy signal to financial result.

```text
Signal
  ↓
Intent
  ↓
Risk Decision
  ↓
Reservation
  ↓
Broker Submission
  ↓
Acknowledgement
  ↓
Fill
  ↓
Position
  ↓
P&L
  ↓
Reconciliation
```

---

## Current foundation

The audit table already records many events.

Problem:

```text
events exist
but are not strongly grouped into one trace
```

---

## Migration

Add nullable correlation field to audit.

SQLite migration:

```text
009_audit_correlation.sql
```

PostgreSQL migration:

```text
008_audit_correlation.sql
```

Example:

```sql
ALTER TABLE audit ADD COLUMN correlation_id TEXT;
CREATE INDEX audit_correlation ON audit(correlation_id, sequence);
```

Extend:

```python
Store.audit(event_type, payload, correlation_id=None)
```

Maintain backwards compatibility.

---

## Correlation rule

Primary trace ID:

```text
OrderIntent.intent_id
```

Use the same correlation through:

```text
RISK_DECISION
RESERVATION
ORDER_STATUS_CHANGED
SUBMISSION_UNKNOWN
FILL_APPLIED
DUPLICATE_FILL_IGNORED
CANCEL
EMERGENCY_EXIT
```

For a broker fill:

```text
lookup order
obtain originating intent trace ID
```

Do not assume raw broker fill ID is the trace.

---

## New service

Create:

```text
backend/reliability/tracing.py
```

Functions:

```python
trace(trace_id)
recent_traces(limit=20)
```

Output:

```json
{
  "trace_id": "ema-1:1700",
  "strategy_instance_id": "ema-1",
  "events": [
    {
      "sequence": 101,
      "type": "RISK_DECISION",
      "recorded_at": 123,
      "payload": {}
    }
  ]
}
```

---

## API

```text
GET /api/traces
GET /api/traces/{trace_id}
```

Authenticated.

---

## UI

Execution Timeline:

```text
09:31:03.001 SIGNAL        EMA crossover
09:31:03.002 INTENT        BUY 100 RELIANCE
09:31:03.004 RISK          APPROVED
09:31:03.011 SUBMISSION    UNKNOWN → OPEN
09:31:03.201 FILL          40 @ ₹2500
09:31:03.204 POSITION      +40
09:31:04.506 RECONCILE     MATCHED
```

Color:

```text
normal        neutral
approved      green/cyan
rejected      yellow/orange
failure       red
recovery      cyan
```

Never invent a timeline event client-side.

---

## Tests

```text
one order's risk/order/fill events share correlation ID
duplicate fill event appears but financial mutation only once
timeout trace shows UNKNOWN and later reconciliation
kill emergency exits have trace
trace ordering uses audit sequence
trace API cannot access another user's account data
```

---

# 12. USP 7 — Failure Lab V2

## Goal

Let judges deliberately break AlgoShield.

Current scenarios already include:

```text
partial
rejection
position_limit
duplicate_fill
conflicting_fill
missed_fill
unknown_submission
disconnect
reconnect
spam
stale_feed
drift
clear_drift
kill_partial
broker_update
disconnect_recovery
```

Keep all of them.

---

## Add scenarios

### 1. concurrent_position_race

Two simultaneous BUY intents compete for the last available capacity.

Expected:

```text
only safe combination is reserved
no risk limit violation
```

---

### 2. account_risk

Three strategies are independently legal but collectively exceed account limit.

Expected:

```text
third/increasing intent rejected
```

---

### 3. opposing_gross_exposure

```text
A +100
B -100
```

Net:

```text
0
```

Gross:

```text
200
```

Expected:

```text
gross-risk rule still sees exposure
```

---

### 4. limit_lowered_below_position

Existing:

```text
Position +80
```

Operator lowers limit:

```text
50
```

Expected:

```text
do not alter position
block additional exposure
allow verified reducing action
```

---

### 5. daily_loss_mark_breach

Price mark changes unrealized P&L enough to breach daily loss.

Next increasing intent:

```text
rejected
strategy LOSS_HALTED
```

---

### 6. late_fill_after_cancel

Order partially fills.

Cancel remainder.

Then broker reports legitimate late/final fill according to allowed lifecycle.

Expected:

```text
financial truth follows actual fill
state machine remains consistent
reconcile if necessary
```

---

### 7. kill_late_fill

Kill begins while order is open.

Fill arrives during kill.

Expected:

```text
recalculate residual
continue flattening
verify before certificate
```

---

### 8. restart_fail_closed

Persist state.

Recreate platform.

Expected:

```text
RECOVERING
runtime disabled
no automatic strategy execution
reconcile
STOPPED
explicit resume required
```

---

### 9. stale_broker_evidence

Make last verified broker snapshot too old.

Expected:

```text
new exposure rejected
gate moves to degraded/uncertain policy
```

---

### 10. invalid_price

LIMIT price far outside allowed band.

Expected:

```text
RISK_PRICE_REASONABILITY
```

---

## Failure Lab response format

Standardize every scenario:

```json
{
  "scenario": "account_risk",
  "status": "PASS",
  "started_at": 0,
  "duration_ms": 4.2,
  "expected": [],
  "observed": {},
  "decisions": [],
  "evidence": {},
  "invariants": {},
  "state": {}
}
```

`status=PASS` means the platform behaved as expected under the injected failure.

Do not confuse:

```text
scenario PASS
```

with:

```text
trading operation succeeded
```

Example:

A broker disconnect scenario PASSes if trading correctly fails closed.

---

## Safety

Failure Lab MUST remain:

```text
offline/mock only
```

Never enable destructive fault injection against real 021/live execution.

Keep `require_offline_demo()`.

---

# 13. USP 8 — Kill Certificate V2

## Goal

Make kill a verifiable protocol, not a button.

Current kill flow is already strong.

Extend its evidence.

---

## Extend KillCertificate

Backward-compatible fields:

```python
target_seconds: float = 10.0
started_at: float | None = None
completed_at: float | None = None
stage_durations_ms: dict = field(default_factory=dict)
final_evidence: dict = field(default_factory=dict)
```

Keep current fields:

```text
status
elapsed_seconds
open_orders
broker_positions
virtual_positions_flat
reason
```

Old persisted certificates must still load.

---

## Required stages

Measure:

```text
gate_closed
initial_reconciliation
open_orders_cleared
virtual_positions_flat
final_broker_verified
```

Example:

```json
{
  "status": "SUCCESS",
  "elapsed_seconds": 0.91,
  "target_seconds": 10,
  "stage_durations_ms": {
    "gate_closed": 3,
    "initial_reconciliation": 80,
    "open_orders_cleared": 128,
    "virtual_positions_flat": 822,
    "final_broker_verified": 910
  },
  "final_evidence": {
    "open_orders": 0,
    "broker_positions": {},
    "virtual_positions_flat": true,
    "broker_unsettled": false
  }
}
```

---

## Status semantics

Never change:

```text
SUCCESS   = verified safe AND <10 seconds
SAFE_LATE = verified safe BUT >=10 seconds
FAILED    = safe state not verified
```

Do not use SUCCESS simply because commands were issued.

---

## UI

Create certificate card:

```text
KILL CERTIFICATE
────────────────────────────
Gate closed             3 ms
Orders cleared        128 ms
Positions flat        822 ms
Broker verified       910 ms

Open orders              0
Broker positions          0
Virtual positions         0

VERIFIED SAFE
0.910s / 10s
```

FAILED must visually remain failed/uncertain.

---

## Tests

Preserve all existing kill tests.

Add:

```text
certificate contains stage timings
old stored certificate without new fields still loads
SAFE_LATE never renders SUCCESS
broker unreachable -> FAILED
late fill during kill -> kill continues
kill latch survives restart
reset requires verified flat state
```

---

# 14. USP 9 — Metrics Registry

## Goal

Instrument the prototype now so actual results can be measured later.

Do not invent benchmark numbers.

---

## New module

Create:

```text
backend/observability/__init__.py
backend/observability/metrics.py
```

Use only Python standard library.

No Prometheus/Redis dependency required for hackathon.

---

## MetricsRegistry

Suggested operations:

```python
counter(name, amount=1)
observe(name, value)
snapshot()
reset_demo_metrics()
```

Use:

```text
thread-safe lock
bounded deque per latency metric
```

Do not let metrics grow unbounded.

Example:

```python
max_samples_per_metric = 10000
```

---

## Required metrics

### Safety counters

```text
risk_bypass_count
duplicate_fill_ignored_count
conflicting_fill_count
unattributed_fill_count
safety_restriction_count
reconciliation_failure_count
failure_lab_runs
failure_lab_passes
failure_lab_failures
```

### Latency

```text
risk_decision_latency_ms
reconciliation_latency_ms
kill_gate_close_latency_ms
kill_verified_flat_latency_ms
fill_processing_latency_ms
tick_processing_latency_ms
```

### Throughput

```text
risk_decisions_total
orders_admitted_total
fills_processed_total
ticks_processed_total
```

---

## Summary statistics

For observed latencies return:

```text
count
min
p50
p95
p99
max
mean
```

Use deterministic percentile implementation.

Do not use NumPy just for percentiles.

---

## Instrumentation points

### RiskGateway.submit

Measure:

```text
start before _check
end after decision persisted
```

Record:

```text
risk_decision_latency_ms
risk_decisions_total
```

---

### Platform.tick

Measure:

```text
tick_processing_latency_ms
ticks_processed_total
```

---

### Platform.ingest

Measure local processing:

```text
fill_processing_latency_ms
fills_processed_total
```

This is processing latency, NOT broker-network latency.

Label it correctly.

---

### Reliability.reconcile

Measure:

```text
reconciliation_latency_ms
```

Count failures.

---

### Reliability.kill

Measure:

```text
kill_gate_close_latency_ms
kill_verified_flat_latency_ms
```

The existing kill elapsed remains authoritative for SLA.

---

## API

Add:

```text
GET /api/metrics
```

Authenticated.

Response:

```json
{
  "counters": {},
  "latencies": {},
  "generated_at": 0
}
```

---

## Snapshot

Include compact:

```text
snapshot["metrics"]
```

Avoid returning thousands of raw samples.

---

## Tests

```text
metric counters increment
histograms bounded
p95 deterministic
risk metric recorded for allow and reject
reconciliation failure counted
kill metric recorded
no metric failure changes trading behavior
metrics are read-only from dashboard
```

Metrics must never be safety-critical dependencies.

If metrics break:

```text
trading safety logic must still operate
```

---

# 15. USP 10 — AlgoShield SafetyBench

## Goal

Automatically execute adversarial scenarios and produce measurable evidence.

Example final output:

```text
ALGOSHIELD SAFETYBENCH

Scenarios             500
Passed                500
Failed                  0

Safety violations       0
Risk bypasses            0
Double fill mutations    0
Unattributed fills       0

P95 risk decision     X ms
P95 reconciliation    Y ms
Kill verification     Z ms
```

Do not claim numbers until measured.

---

## Important isolation rule

SafetyBench must NOT mutate the current user's live/demo platform.

Each scenario run must use an isolated test platform.

Recommended:

```python
Platform(":memory:")
```

with:

```text
MockBrokerAdapter
Replay/mock feed
```

Never run SafetyBench against a real broker.

---

## New module

Create:

```text
backend/reliability/safety_bench.py
```

Suggested models:

```python
@dataclass
class BenchCaseResult:
    name: str
    passed: bool
    duration_ms: float
    evidence: dict
    failure_reason: str = ""


@dataclass
class BenchRun:
    run_id: str
    started_at: float
    completed_at: float
    cases: list[BenchCaseResult]
    summary: dict
```

---

## Initial benchmark suite

Include at least:

```text
partial_fill
duplicate_fill
conflicting_fill
missed_fill_recovery
unknown_submission
broker_disconnect
stale_feed
position_drift
strategy_spam
position_race
account_net_limit
account_gross_limit
limit_lowered
daily_loss
restart_fail_closed
kill_during_partial
kill_late_fill
kill_failed_broker
price_reasonability
```

---

## Pass criteria

Each case has explicit expected safety properties.

Example:

```text
duplicate_fill

Expected:
- first fill applied
- second identical fill ignored
- position changed once
- duplicate counter increases
- gate remains safe
```

Example:

```text
unknown_submission

Expected:
- exactly one broker order
- no blind retry
- order becomes UNKNOWN
- new risk blocked if state cannot be verified
- reconciliation resolves truth
```

---

## Invariant check

At the end of every scenario:

```text
build SafetyProof
```

A scenario only passes when:

```text
its expected assertions pass
AND
no forbidden invariant violation remains
```

Some scenarios intentionally end in:

```text
UNCERTAIN
```

That can still be a PASS if fail-closed behavior is expected.

---

## API

Add:

```text
POST /api/safety-bench/run
GET  /api/safety-bench/latest
```

Only available in demo/offline mode.

Authenticated.

Optional request:

```json
{
  "iterations": 10
}
```

Put a safe upper bound, e.g.:

```text
1 <= iterations <= 100
```

---

## Persistence

Persist only completed run summaries.

Do NOT persist every internal sample.

Recommended table:

```text
benchmark_runs
```

Fields:

```text
id
started_at
completed_at
scenario_count
passed
failed
payload_json
```

Use additive migrations.

Alternatively, if time is short, persist only the latest completed result in `safety_values`.

Prefer a real table if implementation time permits.

---

## UI

```text
SAFETYBENCH

[ RUN 1x ] [ RUN 10x ]

19 scenarios
19 passed
0 failed

Safety invariant violations: 0

P95 Risk Decision     1.2 ms
P95 Reconciliation    7.8 ms
Kill Verified         0.91 s
```

Show actual measured values only.

---

# 16. Dashboard Layout

Do not turn the UI into a decorative trading terminal.

Use an operational hierarchy.

Recommended:

```text
┌───────────────────────────────────────────────┐
│ SYSTEM HEALTH                                │
│ Broker | Gate | Reconciliation | Open Orders │
│                           [ EMERGENCY KILL ] │
└───────────────────────────────────────────────┘

┌───────────────────────┐
│ SAFETY PROOF          │
│ I1 VERIFIED           │
│ I3 VERIFIED           │
│ I8 VERIFIED           │
│ VERDICT VERIFIED SAFE │
└───────────────────────┘

┌───────────────────────┐
│ RISK BUDGETS          │
│ Strategy Risk         │
│ Account Net Risk      │
│ Account Gross Risk    │
└───────────────────────┘

┌───────────────────────┐
│ LATEST RISK DECISION  │
│ REJECTED              │
│ reason + numbers      │
└───────────────────────┘

┌───────────────────────┐
│ RECONCILIATION CENTER │
│ LOCAL ↔ BROKER        │
└───────────────────────┘

┌───────────────────────┐
│ EXECUTION TRACE       │
│ signal → fill → P&L   │
└───────────────────────┘

┌───────────────────────┐
│ FAILURE LAB           │
└───────────────────────┘

┌───────────────────────┐
│ SAFETYBENCH           │
└───────────────────────┘

┌───────────────────────┐
│ KILL CERTIFICATE      │
└───────────────────────┘

┌───────────────────────┐
│ METRICS               │
└───────────────────────┘
```

Keep existing strategy/accounting panels.

Do not replace working UI unnecessarily.

---

# 17. Edge-Case Master List

These are the scenarios AlgoShield should ultimately be able to demonstrate or test.

## Risk

```text
strategy max position reached
pending exposure reaches limit
opposing pending orders
concurrent intents race for final capacity
account-wide net limit
account-wide gross limit
limit lowered below existing position
daily loss breached
daily loss breached by mark movement
orders/minute exceeded
stopped strategy sends intent
kill-latched strategy sends intent
reduce-only attempt reverses position
price reasonability failure
```

## Broker / Execution

```text
partial fill
multi-price fill
rejection
cancel after partial
late fill after cancel
duplicate identical fill
conflicting duplicate fill
missed fill
out-of-order broker update
timeout after broker acceptance
broker disconnect
reconnect
unknown broker order
unknown/manual broker position
incomplete broker snapshot
stale broker snapshot
```

## Recovery

```text
crash after reservation
crash after submission starts
crash after broker accepts before local ACK
crash after fill before local processing
restart with open orders
restart while kill latched
restart with local/broker drift
```

## Market data

```text
duplicate tick
late tick
out-of-order tick
stale feed
missing interval
reconnect
invalid/fat-finger price
```

## Kill

```text
kill with no exposure
kill with open orders
kill during partial fill
fill arrives during kill
cancel races with fill
flatten order partially fills
broker disconnect during kill
broker unreachable during final verification
opposing virtual positions but broker net zero
kill exceeds 10 seconds
restart while kill latched
reset with residual exposure
```

## Security

```text
anonymous risk change
anonymous kill
anonymous reconciliation
user modifies another account's strategy
user cancels another account's order
malformed intent
replayed intent ID
oversized API payload
failure-lab invoked in non-demo/live mode
```

---

# 18. Metrics to Show Judges

Do not invent results.

Instrument first, run tests later.

Primary metrics:

```text
P50/P95/P99 risk decision latency
P50/P95 reconciliation latency
Kill gate-close latency
Kill verified-flat latency
Fill processing latency
Tick processing latency
Risk decisions/sec
Ticks/sec
Scenario pass rate
Safety invariant failures
Risk bypass count
Double-applied fill count
Unattributed fill count
```

Ideal safety counters:

```text
Risk bypasses              0
Double-applied fills       0
Unattributed fills         0
Safety invariant failures  0
```

Only claim zero after test evidence.

---

# 19. Database Migration Rules

All changes must be additive.

Never edit already-applied migration files.

Expected new migration sequence:

SQLite:

```text
008_account_risk.sql
009_audit_correlation.sql
010_risk_price_guard.sql
011_benchmark_runs.sql
```

PostgreSQL:

```text
007_account_risk.sql
008_audit_correlation.sql
009_risk_price_guard.sql
010_benchmark_runs.sql
```

Before choosing exact numbers:

- inspect current migrations;
- preserve repository migration ordering;
- never create conflicting filenames;
- update migration tests.

PostgreSQL migrations must remain under the `algoshield` schema.

---

# 20. API Summary

Final desired additions:

```text
GET  /api/risk/account-policy
PUT  /api/risk/account-policy

GET  /api/reconciliation

GET  /api/traces
GET  /api/traces/{trace_id}

GET  /api/metrics

POST /api/safety-bench/run
GET  /api/safety-bench/latest
```

Existing APIs remain:

```text
/api/risk/policies/{strategy}
/api/risk/strategies/{strategy}
/api/failure-lab/{scenario}
/api/reconcile
/api/resume
/api/reduce-only
/api/kill
/api/kill/reset
```

Secure them.

---

# 21. Test Plan

Do not create one giant test file.

Recommended:

```text
tests/test_control_plane_security.py
tests/test_risk_explanations.py
tests/test_account_risk.py
tests/test_price_reasonability.py
tests/test_safety_proof.py
tests/test_reconciliation_center.py
tests/test_tracing.py
tests/test_failure_lab_v2.py
tests/test_kill_certificate_v2.py
tests/test_metrics.py
tests/test_safety_bench.py
```

Keep existing tests unchanged unless behavior intentionally changes.

Do not weaken existing safety assertions.

---

# 22. Required Regression Commands

After each phase:

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

If the full suite cannot run because of environment/dependency problems:

- report the exact blocker;
- run the largest safe subset possible;
- do not claim all tests pass.

---

# 23. Performance Test Method

Once features are stable, benchmark in a controlled environment.

## Risk latency

Generate valid intents against an already healthy mock platform.

Run:

```text
100
1,000
10,000
```

risk decisions.

Measure:

```text
p50
p95
p99
max
```

Test both:

```text
approved
rejected
```

---

## Concurrency

Create simultaneous intents.

Validate:

```text
no risk limit bypass
no duplicate reservation
consistent final pending exposure
```

Performance is secondary to correctness.

---

## Reconciliation

Benchmark snapshots with:

```text
10 orders
100 orders
1,000 orders
```

and fills.

Measure reconciliation duration.

---

## SafetyBench

Run:

```text
1x
10x
50x
```

suite iterations.

Record:

```text
scenario count
pass/fail
invariant violations
total duration
```

---

## Kill

Run controlled mock scenarios with:

```text
0 open orders
1 open order
10 open orders
partial fills
opposing positions
late fill
```

Measure:

```text
gate-close time
verified-flat time
```

---

# 24. Demo Story

Build the final demo around this sequence.

```text
1. Start 3 strategies.

2. Show independent positions and account exposure.

3. Trigger unsafe intent.
   → Explainable risk rejection.

4. Show account-wide risk:
   each strategy is legal,
   collective account risk is not.
   → Reject.

5. Inject partial fill.

6. Inject local/broker drift.
   → Gate closes.
   → Reconciliation Center shows delta.

7. Recover missing fill.
   → MATCHED.

8. Trigger strategy spam.
   → Rate limit.

9. Show Failure Lab edge cases.

10. Press KILL during an active/partial order.
    → gate closes
    → cancel
    → flatten
    → reconcile
    → verify

11. Show Kill Certificate.

12. Show Safety Proof:
    bypasses 0
    duplicate mutations 0
    attribution correct
    reconciliation verified

13. Run SafetyBench.

14. Show actual latency and pass-rate metrics.
```

The judge should see:

```text
FAILURE
  ↓
CONTAINMENT
  ↓
RECOVERY
  ↓
VERIFICATION
```

---

# 25. Definition of Done — Entire USP Layer

The USP implementation is complete only when:

## Safety

- Existing I1-I10 tests remain passing.
- Account-wide risk cannot be bypassed by concurrency.
- Failure scenarios do not silently increase risk.
- No UI component invents backend success.

## Explainability

- Every risk rejection has reason + evidence.
- Every reconciliation failure has a reason.
- Every kill result is evidence-backed.
- A single trade can be traced end-to-end.

## Demonstrability

- Failure Lab can inject the major adversarial cases.
- SafetyBench can run automatically.
- Dashboard exposes proof and measured results.

## Metrics

- Runtime metrics are collected.
- Percentiles are calculated correctly.
- No hard-coded performance claims exist.

## Security

- Sensitive controls require authentication.
- Account-specific mutations enforce ownership.
- Failure injection cannot run against live execution.

## Reliability

- Kill remains bounded.
- Restart remains fail-closed.
- Reconciliation remains required after uncertainty.
- Existing mock/replay path still works.

## Engineering

- No duplicated shared models.
- Additive migrations only.
- Tests added for every feature.
- Docs updated for contract/schema changes.
- Ruff and pytest pass in a correctly configured environment.

---

# 26. Things NOT to Build Until This Is Done

Do not spend hackathon time on:

```text
AI strategy generation
stock prediction
sentiment analysis
advanced chart indicators
options Greeks
portfolio optimization
social trading
copy trading
many broker integrations
microservices
Kafka
Redis unless proven necessary
complex distributed deployment
```

These do not strengthen the primary PS-06 differentiation.

---

# 27. Final Product Statement

Use this in presentation:

> **AlgoShield is a reliability-first safety control plane for automated trading. Strategies are treated as untrusted decision engines. Every order must pass a non-bypassable risk gateway, every financial state change comes from verified fills, uncertainty fails closed, broker/local drift is reconciled, and emergency shutdown is not declared successful until the broker and virtual strategy state are verified safe. Failure Lab, Safety Proof, SafetyBench, explainable risk decisions, and measurable kill/recovery latency turn those guarantees into visible evidence.**

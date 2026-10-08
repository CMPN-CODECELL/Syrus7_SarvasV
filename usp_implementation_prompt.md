# Copy-Paste Implementation Prompt — AlgoShield USP Layer

You are working inside the existing **AlgoShield** repository for SYRUS 7.0 PS-06.

Your task is to fully implement the USP layer described in `usp_implementation_plan.md`.

Do NOT redesign the application from scratch.

## First: read the repository

Before changing anything, read in this order:

1. `AGENTS.md`
2. `README.md`
3. `docs/REQUIREMENTS.md`
4. `docs/ARCHITECTURE.md`
5. `docs/CONTRACTS.md`
6. `docs/INTEGRATION_RULES.md`
7. `docs/SAFETY_INVARIANTS.md`
8. `docs/TESTING.md`
9. `docs/DECISIONS.md`
10. `docs/PHASE_PLAN.md`
11. `docs/TEAM_OWNERSHIP.md`
12. `usp_implementation_plan.md`
13. the current implementation and relevant tests

Treat the current repository as the source of truth.

Do not assume the plan is perfectly synchronized with the code. If the repository already implements part of a feature, extend it instead of duplicating it.

## Project identity

AlgoShield is:

> A reliability-first safety control plane for multi-strategy automated trading where strategies are treated as untrusted decision engines.

Core path:

```text
Market Data
→ Candle Builder
→ Strategy
→ OrderIntent
→ RiskGateway
→ OrderManager
→ BrokerAdapter
→ Fill
→ Ledger
→ Reconciliation
→ Dashboard
```

## Non-negotiable safety rules

You MUST preserve all existing safety invariants.

1. Strategies never call the broker directly.
2. Orders are not fills.
3. Positions and P&L change only from unique fills.
4. Every fill retains strategy attribution.
5. Broker-specific details stay behind adapters.
6. Uncertainty fails closed.
7. Restart never automatically resumes trading.
8. Reconciliation is required before normal trading after uncertainty.
9. Kill is not successful until broker + virtual state are verified safe.
10. Never fabricate success in the UI.
11. Never blindly retry an ambiguous broker submission.
12. Opposing pending orders must not be assumed to cancel risk.
13. Existing mock/replay mode must keep working.
14. Do not invent 021 API behavior.

## Ownership

This work primarily belongs to:

```text
Member 3 — Risk & Reliability
backend/risk/
backend/reliability/
failure/reliability UI
```

Cross-module changes are allowed only when required for integration.

Respect `docs/TEAM_OWNERSHIP.md`.

## Required implementation order

Implement the plan in this exact high-level order:

### Phase 0
Secure sensitive control-plane APIs.

### Phase 1
Structured explainable risk decisions.

### Phase 2
Account-wide cross-strategy net + gross risk.

### Phase 3
LIMIT-order price reasonability guard.

### Phase 4
Safety Proof Engine.

### Phase 5
Reconciliation Center backend/API.

### Phase 6
Correlated incident/execution tracing.

### Phase 7
Failure Lab V2 edge cases.

### Phase 8
Kill Certificate V2 with stage timing/evidence.

### Phase 9
Bounded runtime metrics registry.

### Phase 10
Isolated SafetyBench.

### Phase 11
Dashboard integration.

### Phase 12
Regression/adversarial verification and documentation.

Do not skip directly to UI.

Backend truth first.

## Before coding

Return a short implementation map containing:

1. current features already present;
2. files you will change;
3. new files you will add;
4. migrations required;
5. shared-contract changes;
6. risks/assumptions.

Then immediately implement. Do not stop after giving the plan.

## Implementation requirements

### A. Security

Require authentication for critical mutation endpoints.

Enforce account ownership for strategy/order-specific actions.

At minimum protect:

```text
risk policy changes
strategy controls
order cancellation
failure lab
reconcile
resume
reduce-only
kill
kill reset
broker disconnect/reconnect
market-session mutation
```

Do not pretend this is production RBAC. It is the secure bootstrap boundary.

### B. Explainable Risk

Extend existing `RiskDecision` backward-compatibly.

Every rejection should expose:

```text
reason_code
reason_text
rule_results
details
```

For numeric rules include current, pending, requested, projected and limit values.

Preserve existing reason codes.

### C. Account Risk

Add durable account-level policy:

```text
max_net_position_per_symbol
max_gross_virtual_position_per_symbol
```

Disabled/unconfigured account limits must not unexpectedly break existing tests.

Opposing strategies may net to zero while still consuming gross exposure.

Use conservative worst-case pending calculations.

Risk reservation must remain atomic under the existing process lock.

### D. Price Reasonability

Use fresh market mark.

Apply only to LIMIT orders.

Use Decimal.

Do not invent a price for MARKET orders.

### E. Safety Proof

Create a read-only backend proof service.

Each invariant status must be one of:

```text
VERIFIED
FAILED
UNKNOWN
NOT_APPLICABLE
```

Never claim VERIFIED without current evidence.

Expired reconciliation/broker evidence must turn proof UNKNOWN.

Do not fake universal proof from static code assumptions.

### F. Reconciliation Center

Expose local vs broker evidence and useful drift details.

Never create synthetic balancing fills.

Any repaired financial truth must come from canonical broker execution evidence.

### G. Incident Trace

Correlate:

```text
Signal/Intent
Risk
Reservation
Submission
Order state
Fill
Position/accounting evidence
Reconciliation
Kill/emergency events where relevant
```

Use a durable correlation ID.

Do not reconstruct timelines client-side from guesses.

### H. Failure Lab

Preserve current scenarios.

Add the scenarios from `usp_implementation_plan.md`.

Failure Lab must remain mock/offline only.

A failure scenario can PASS because the system correctly blocked trading.

### I. Kill Certificate

Preserve current semantics:

```text
SUCCESS   = verified safe and <10s
SAFE_LATE = verified safe but >=10s
FAILED    = not verified safe
```

Add stage timing and final evidence.

Old persisted certificates must still load.

### J. Metrics

Implement lightweight bounded metrics.

Use Python standard library unless the repository already contains an accepted dependency.

Metrics must never participate in safety decisions.

No unbounded sample arrays.

Return p50/p95/p99/max/mean.

Never hard-code performance claims.

### K. SafetyBench

Run against fresh isolated mock/in-memory platforms.

Never run against real/live broker mode.

Every scenario must have explicit pass criteria.

Run SafetyProof after scenarios when meaningful.

Output actual pass/fail counts and measured durations.

### L. UI

The frontend is operational, not decorative.

Add:

```text
Safety Proof
Latest Risk Decision
Account Risk
Reconciliation Center
Execution Trace
Failure Lab
Kill Certificate
SafetyBench
Metrics
```

Reuse the existing visual system and current HTML architecture.

Do not replace working strategy/accounting panels.

All UI state must come from backend APIs/snapshot.

## Database rules

All schema changes must be additive.

Never edit an already-applied migration.

Inspect current SQLite and PostgreSQL migration numbering before choosing new filenames.

PostgreSQL changes stay inside the `algoshield` schema.

Add indexes only where query patterns justify them.

Do not reset user data.

## Testing

For every phase:

1. add focused tests;
2. run focused tests;
3. run full suite;
4. run Ruff.

Do not weaken existing safety tests.

Expected commands:

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

If environment dependencies prevent the full suite:

- report the exact missing dependency/environment issue;
- run the largest available subset;
- do not claim all tests passed.

Add tests roughly matching:

```text
test_control_plane_security.py
test_risk_explanations.py
test_account_risk.py
test_price_reasonability.py
test_safety_proof.py
test_reconciliation_center.py
test_tracing.py
test_failure_lab_v2.py
test_kill_certificate_v2.py
test_metrics.py
test_safety_bench.py
```

Use different file names only if the existing test organization makes another location clearly better.

## Required edge cases

Ensure automated coverage exists for:

```text
partial fill
duplicate fill
conflicting duplicate fill
missed fill
unknown submission after timeout
broker disconnect
reconnect
stale feed
stale broker evidence
position drift
strategy spam
concurrent position race
account net risk
account gross risk
limit lowered below current position
daily loss breach
late fill after cancel
restart fail-closed
kill during partial fill
late fill during kill
broker failure during kill
kill SAFE_LATE
reset with residual position
price reasonability rejection
unauthorized critical API access
cross-account mutation attempt
```

## Documentation

Update the relevant canonical docs whenever behavior/contracts/schema change:

```text
docs/ARCHITECTURE.md
docs/CONTRACTS.md
docs/SAFETY_INVARIANTS.md
docs/TESTING.md
docs/DECISIONS.md when an architectural decision changes/adds
docs/PHASE_PLAN.md
```

Do not rewrite unrelated documentation.

## Completion report

When implementation is complete, return:

1. features implemented;
2. exact files changed;
3. migrations added;
4. new APIs;
5. new tests;
6. test results;
7. Ruff results;
8. remaining blockers;
9. any assumptions;
10. demo steps for the new USPs.

Do not say "done" unless the implementation exists and relevant tests actually pass.

## Final success condition

The completed prototype should be able to demonstrate:

```text
FAILURE
  ↓
CONTAINMENT
  ↓
RECOVERY
  ↓
VERIFICATION
```

and support the claim:

> AlgoShield does not merely execute trading strategies. It prevents unsafe actions, detects uncertainty, reconstructs broker truth, and produces evidence that the account is safe again.

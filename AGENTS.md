# AlgoShield â€” AI Engineering Instructions
---

## CURRENT ALGOSHIELD PROJECT BASELINE — READ FIRST (2026-10-09)

Before changing code, agents MUST read, in order:
1. `docs/PROJECT_TRUTH.md` — short product, architecture and authority map.
2. `docs/TEAM_EXECUTION_PLAN.md` — actual gap-first task order and release blockers.
3. Task-specific `docs/CONTRACTS.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY_OPERATIONS.md`, `docs/SAFETY_INVARIANTS.md`, `docs/DECISIONS.md`, `docs/021_API_UNKNOWN.md` and relevant source/tests.
4. `docs/TESTING.md` before validation. Consult `docs/REQUIREMENTS_TRACEABILITY.md` for requirement changes and `docs/RESEARCH_DECISIONS.md` for research provenance; historical member reports are optional evidence, never task authority.

Status rule: history/progress/research files are **not** proof of the current checkout. Use actual code and test results to label `VERIFIED_CURRENT_COMMIT`; use `REPORTED_IMPLEMENTED` otherwise.

**Research Sessions 1–7 have been consolidated into the four new docs; do not reproduce old proposal phases or edit previously applied migrations.** Existing 2026-10-08 logs report a React SPA, account scoping, bounded callback workers, Safety Proof, explainable risk, account net/gross policies, Failure Lab V2, SafetyBench and historical kill certificates. Verify/reuse rather than rebuild.

Non-negotiable: Strategies cannot call broker directly; durable risk reservation precedes dispatch; effective unique attributed fills control financial state; ambiguity/restart fail closed; incomplete broker data cannot certify safety; kill never succeeds from submitted requests alone; React never computes safety/P&L; external 021 behavior is UNKNOWN until verified. Mock fault injection never accesses a live broker.

DEC-028: Team members may directly push branches; pull requests are optional. Integrate tested checkpoints on `dev`; the integration lead may promote validated commits to `main` with a normal fast-forward push and successful CI. Preserve local work, respect server permissions, never force-push, and report exact evidence and blockers.

---


## Read this first
This file is the canonical instruction file for every coding model working in this repository.

After the baseline reading order above, read:
1. Read `README.md`.
2. Read `docs/REQUIREMENTS.md`.
3. Read `docs/ARCHITECTURE.md`.
4. Read `docs/CONTRACTS.md`.
5. Read the owner-specific section in `docs/TEAM_OWNERSHIP.md`.
6. If touching execution/risk/recovery, also read `docs/SAFETY_INVARIANTS.md`.
7. If touching tests, read `docs/TESTING.md`.
8. If touching 021 integration, read `docs/021_API_UNKNOWN.md`.
9. Read relevant accepted entries in `docs/DECISIONS.md`; current incomplete features live in `docs/IMPLEMENTATION_DELTA.md`. `docs/PHASE_PLAN.md` redirects to history.

Do not invent missing 021 API details. Unknown sponsor/API behavior must remain behind adapters and be marked as assumptions or TODOs.

---

## Project in one sentence
**AlgoShield is a reliability-first algo trading platform where trading strategies are treated as untrusted workloads: strategies emit order intents, a non-bypassable platform risk layer decides what may execute, broker fills create financial truth, and reconciliation/recovery keeps local state aligned with the broker even after failures.**

---

## Official problem
SYRUS 7.0 â€” FinTech â€” PS-06: Algo Trading Platform.

Required outcomes:
- users can create an account and subscribe to strategies;
- platform builds 1-minute and 5-minute candles from raw ticks;
- at least one strategy uses those candles for entry logic;
- orders are sent to the 021 sandbox;
- partial fills and rejections are handled;
- strategy position remains synchronized with the account;
- exact trades and net P&L after charges are available;
- each strategy has max daily loss, max position size, max orders/minute;
- platform, not strategy code, enforces risk limits;
- kill switch stops all strategies, cancels open orders and closes positions within 10 seconds;
- at least 3 strategies run simultaneously on the same account;
- each strategy keeps its own P&L and position even when strategies oppose each other on the same stock;
- dashboard shows subscriptions and live P&L.

Evaluation explicitly emphasizes hidden tests, a live change request, and technical viva, not strategy profitability.

---

## Non-negotiable architecture rules

### 1. Strategies never call the broker directly
Allowed:
`Strategy -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter`

Forbidden:
`Strategy -> 021 API`

### 2. Orders are not fills
An order is a request.
A fill is executed quantity.
Positions and P&L change only from fills/executions.

### 3. Every fill must retain strategy attribution
Every broker order/fill must map back to `strategy_instance_id`.

### 4. Broker-specific details stay inside adapters
021 payload names, auth, status names, WebSocket formats, etc. must not leak into domain logic.

### 5. Mock and real providers share the same interfaces
We must be able to run the full platform with:
- `MockBrokerAdapter` / `ReplayMarketDataProvider`
- `021BrokerAdapter` / `MarketData021Provider`

### 6. Fail closed
If broker state, reconciliation state, or critical market/execution data is uncertain, new risk-increasing actions must not continue blindly.

### 7. Reconciliation is first-class
Local state is expected state; broker state is observed external truth.
The platform must compare orders, fills/trades, and positions.

### 8. Kill switch is a verified state transition
First close the global execution gate. Then stop strategies, cancel open orders, flatten remaining positions, and verify broker state.

### 9. Modular monolith, not microservice sprawl
One deployable backend with clean modules is preferred for hackathon speed and debugging.

### 10. No finance overengineering
Do not add ML prediction, sentiment, options Greeks, portfolio optimization, or complex quant research unless all mandatory reliability features are complete.

---

## Required engineering qualities
- deterministic behavior where possible;
- explicit state machines;
- idempotent fill/event processing;
- auditable event timeline;
- testable adapters;
- clear ownership boundaries;
- stable internal contracts;
- minimal hidden side effects;
- no direct cross-module database writes without agreed service boundary.

---

## Coding behavior for AI models
When implementing a task:
1. Identify the owning module/member from `docs/TEAM_OWNERSHIP.md`.
2. List files you intend to change.
3. Reuse shared contracts; do not create duplicate models.
4. Do not silently rename shared fields.
5. Add or update tests with the code.
6. Keep one responsibility per module.
7. Prefer simple, explicit code over clever abstractions.
8. If an assumption depends on 021 API behavior, isolate it and document it.
9. Never fake success states in UI. UI must reflect backend state.
10. Never mark an order FILLED without fill evidence.
11. Never mutate a strategy position from submitted quantity.
12. Never declare kill success until safe state is verified.
13. Never auto-resume after restart before reconciliation.
14. If unsure about domain semantics, check `docs/DOMAIN_GLOSSARY.md` before coding.

---

## Definition of done
A change is complete only when:
- unit/integration tests pass;
- behavior respects shared contracts;
- audit/event behavior is updated if relevant;
- UI state is sourced from actual backend state;
- no ownership boundary is violated;
- README/docs are updated if the contract or behavior changed.

## Bootstrap operating constraints
Use one backend worker. This is mock/replay only; do not claim sandbox completion. SQLite schema v12 supports offline mock/replay; Neon PostgreSQL is the accepted durable persistence layer. Real API details are absent. Read README for exact run/test commands and restart limitations. Never discard durable history to fake reconciliation. Preserve user-provided requirements even when the original sponsor statement is missing.

## Persistent progress and decisions
Before work: read canonical task docs, relevant ACCEPTED entries in `docs/DECISIONS.md`, and current code/tests. Consult `docs/progress/INTEGRATION.md` for recent evidence; member logs are optional task-specific handoffs, not mandatory startup reading.
During work: respect ownership/contracts, record significant architectural changes, never invent 021 behavior and never expose secrets.
After a meaningful implementation task: run relevant tests, update each affected member progress file, update INTEGRATION.md for cross-module changes, update decisions when needed, and report blockers. Never claim DONE unless implementation exists and relevant tests pass. Keep logs concise.

Before changing an ACCEPTED decision: read DECISIONS.md, explain why it no longer works, make the smallest safe change, update/supersede its entry, and update affected docs/tests. Meaningful dependency, shared-contract, schema, infrastructure, safety-rule and module-boundary changes require decision entries; tiny refactors do not.

Neon PostgreSQL is the durable target; SQLite supports offline mock/replay. Requested project `muddy-tooth-14996153`, branch `production`. Inspect existing schema before additive migrations; never reset/delete production data or seed fake demo rows there. No frontend/strategy database connections. Real secrets belong only in ignored local environment files or process configuration. If a tracked secret is discovered, stop and report it.

## Operator and response boundary (DEC-026)

Public registration never grants operator authority. Global controls require a durable explicit operator grant; account owners retain their own strategy/policy/order controls. Use the shared account response projection for nested evidence and streams. Read `docs/SECURITY_OPERATIONS.md` for provisioning. Never provision a production identity or migrate a production database through the offline CLI. Historical audit remains in `docs/CURRENT_REPO_AUDIT.md`; current evidence is in `docs/progress/INTEGRATION.md`.

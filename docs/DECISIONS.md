# Architectural decisions

These entries record meaningful decisions supported by current repository context, not invented historical dates or git changes. Dates are the recording date. Classification: CONFIRMED_REQUIREMENT, CONFIRMED_021_BEHAVIOR, DESIGN_DECISION, ASSUMPTION, OPEN_QUESTION.

## Evidence and open questions
CONFIRMED_REQUIREMENT: repository PS-06 baseline in REQUIREMENTS.md. Original sponsor statement is absent (PS.md); obtain it without weakening requirements. No CONFIRMED_021_BEHAVIOR exists. Public [021 Carbon page](https://carbon.021.trade/auth?show=signup) does not establish an API contract. Questions remain in 021_API_UNKNOWN.md. Demo charges are ASSUMPTION (synthetic 0.01/fill), never a real fee schedule. Live kill/shorting/overlapping-exit semantics and snapshot completeness remain OPEN_QUESTION.

References: [SQLite isolation](https://www.sqlite.org/isolation.html), [Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html), [Neon config package](https://www.npmjs.com/package/@neon/config), [Neon CLI](https://www.npmjs.com/package/neon). CLI config inspection supports deprecated preview configuration; requested layout is retained.

## DEC-001 ? Modular monolith and small bootstrap stack
Date: 2026-10-07
Status: ACCEPTED

### Context
A four-person hackathon needs a coherent runnable vertical slice.

### Decision
DESIGN_DECISION: One Python/FastAPI backend with isolated packages and static polling UI; one worker.

### Reason
Fewer deployment/race surfaces; language/framework were previously unselected.

### Impact
backend packages, API, frontend, dependency tooling.

### Alternatives
Microservices, Redis and an early UI framework were not needed.

### Reversal
Split services only with measured need and preserved risk/ledger contracts.

## DEC-002 ? Untrusted strategies and centralized execution authority
Date: 2026-10-07
Status: ACCEPTED

### Context
Strategies may spam or fail and must never control broker authority.

### Decision
DESIGN_DECISION: Strategy -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter. Durable reservation precedes dispatch.

### Reason
Makes risk non-bypassable at the service boundary; one lock serializes check/reserve/kill.

### Impact
Strategy runtime, risk, execution and shared contracts.

### Alternatives
Direct broker calls from strategy callbacks are forbidden.

### Reversal
Only explicit sponsor evidence can justify a boundary change; safety tests must remain valid.

## DEC-003 ? Fills and independent virtual ledgers create financial truth
Date: 2026-10-07
Status: ACCEPTED

### Context
Submitted orders, partial fills and opposing strategies differ from actual account exposure.

### Decision
DESIGN_DECISION: Unique attributed immutable fills, Decimal accounting, weighted average entry/exit/reversal; independent strategy ledgers and account aggregation.

### Reason
Exactly-once accounting effect and auditable financial evidence.

### Impact
Ledger, Fill contract, strategy positions/P&L, charges and tests.

### Alternatives
Submitted quantity or fabricated internal crossing fills are rejected.

### Reversal
A new accounting method requires replay-equivalence tests and an explicit migration.

## DEC-004 ? Broker abstraction and deterministic mock/replay
Date: 2026-10-07
Status: ACCEPTED

### Context
Sponsor API contract/credentials are not available.

### Decision
DESIGN_DECISION: Canonical BrokerAdapter/MarketDataProvider contracts; mock/replay runs offline; 021 placeholders raise NotImplementedError.

### Reason
Development and reliability tests remain independent of sponsor availability.

### Impact
Broker, market data, composition and failure fixtures.

### Alternatives
Invented endpoints/auth/statuses/charges are forbidden.

### Reversal
Replace boundary adapters only after authoritative contract fixtures pass.

## DEC-005 ? Fail-closed restart and reconciliation before resume
Date: 2026-10-07
Status: ACCEPTED

### Context
Timeouts, crashes and missed events create uncertain external state.

### Decision
DESIGN_DECISION: Start RECOVERING; replay missing attributed fills and compare orders/fills/positions; successful reconciliation leaves STOPPED and resume is explicit. UNKNOWN reservations are retained.

### Reason
Never infer safe external state from local intent alone.

### Impact
Reliability, execution, durable orders/fills and health API.

### Alternatives
Blind retries, auto-resume and made-up balancing adjustments are rejected.

### Reversal
Any recovery automation must prove complete authoritative snapshots and preserve fail-closed tests.

## DEC-006 ? Verified kill and virtual-position evidence
Date: 2026-10-07
Status: ACCEPTED

### Context
Submitted cancel/flatten commands do not prove the required safe state.

### Decision
DESIGN_DECISION: Gate -> stop -> cancel -> reconcile -> attributed emergency exits -> reconcile -> verify. SUCCESS requires no open orders, zero broker/virtual positions and <10s.

### Reason
Separates emergency requests from observable safe completion.

### Impact
Reliability kill certificate, emergency authorization, audit and UI.

### Alternatives
Fake success and synthetic opposing fills are rejected.

### Reversal
Sponsor-confirmed target semantics may change virtual-close sequencing; document and retest before live trading.

## DEC-007 ? Deterministic candle and daily-loss conventions
Date: 2026-10-07
Status: ACCEPTED

### Context
Tick/session semantics need explicit defaults without inventing 021 behavior.

### Decision
DESIGN_DECISION: UTC half-open 60/300s candles; duplicates ignored, late unique ticks fail closed. Daily loss uses Asia/Kolkata day realized less charges plus current unrealized.

### Reason
Deterministic replay and explicit risk inputs.

### Impact
CandleBuilder, Ledger.daily_net, risk tests.

### Alternatives
Silent late-tick correction or fabricated empty candles.

### Reversal
Confirm sponsor volume/timestamp/session semantics, add fixtures, then adapt normalization/session policy.

## DEC-008 ? SQLite bootstrap persistence
Date: 2026-10-07
Status: SUPERSEDED

### Context
The first slice needed persistence without external services.

### Decision
DESIGN_DECISION: SQLite schema v1 initially supplied local durable state; DEC-009 supersedes its role as the primary durable database. SQLite remains offline mock/replay fallback.

### Reason
Simple fresh-clone setup while safety contracts stabilize.

### Impact
Store and local tests.

### Alternatives
Mandatory PostgreSQL services for the first offline slice.

### Reversal
Keep offline support until PostgreSQL is continuously available; never silently fall back after configured PostgreSQL failure.

## DEC-009 ? Neon PostgreSQL durable relational persistence
Date: 2026-10-07
Status: ACCEPTED

### Context
User explicitly requests Neon project muddy-tooth-14996153, branch production.

### Decision
DESIGN_DECISION: Neon PostgreSQL is the durable target; centralized psycopg Store, versioned checksum migrations in dedicated algoshield schema. No ORM added. DATABASE_URL selects PostgreSQL; absent URL selects offline SQLite.

### Reason
Relational transactions and constraints fit orders, fills, ledgers, risk and audit. Reuses existing service boundary with minimal driver integration.

### Impact
PostgresStore, migrations/config, pyproject dependencies, README/environment. Project linkage is intended until authenticated verification; credentials never recorded.

### Alternatives
Multiple ORMs and frontend/strategy SQL access rejected. No destructive resets or fake seeds on production.

### Reversal
Safely migrate/export durable data and preserve identity/accounting before changing provider; inspect schema and use additive migrations.

## DEC-010 ? Progress handoff and durable decision logging
Date: 2026-10-07
Status: ACCEPTED

### Context
Four developers and AI agents need persistent actual implementation state.

### Decision
DESIGN_DECISION: Member logs plus INTEGRATION.md record completed/tests/blockers; DEC entries record meaningful architecture changes; AGENTS completion protocol requires updates.

### Reason
Prevents false DONE claims and stale architecture context.

### Impact
AGENTS.md, docs/progress, DECISIONS.md.

### Alternatives
Duplicating full implementation docs or treating decisions as a git changelog.

### Reversal
Change logging format with team coordination; retain historical decisions and actual test evidence.

## DEC-011 ? Requested Neon infrastructure policy and credential handling
Date: 2026-10-07
Status: ACCEPTED

### Context
User requests auth, private uploads and hello function configuration and deployment.

### Decision
DESIGN_DECISION: Keep requested neon.ts/hello.ts exactly. Pin @neon/config and lock dependencies. Real values only in ignored .env/.env.local or process environment. Neon hello function is an infrastructure smoke endpoint, not the Python backend.

### Reason
Honors requested scope without redesigning the trading stack; no secret output or tracked credentials.

### Impact
neon.ts, hello.ts, package/TS config, environment ignores, infrastructure CLI workflow.

### Alternatives
No different project/branch; AI Gateway remains disabled; no automatic policy overrides.

### Reversal
Review an explicit policy diff and affected backend contracts before enabling more services or changing deployment scope.

## DEC-012 — Durable subscription control and callback quarantine
Date: 2026-10-07
Status: ACCEPTED

### Context
Global runtime enablement did not let an operator stop one strategy, and one callback exception could interrupt the complete candle fan-out. A process-local stop would reset after restart and would not prevent a direct intent from reaching risk.

### Decision
DESIGN_DECISION: Persist an `enabled` flag per subscription. Strategy runtime emits only for enabled subscriptions; a callback exception atomically disables only the faulted subscription and records a sanitized audit event. Risk independently rejects disabled subscriptions with `RISK_STRATEGY_STOPPED`. Re-enablement is an explicit account-scoped operator action.

### Reason
Individual strategy state must survive restart and remain non-bypassable at the risk boundary while healthy strategies continue processing the same candle.

### Impact
SQLite schema v2, PostgreSQL migration 002, strategy runtime, risk reasons, account/subscription APIs, dashboard state and Member 4 tests.

### Alternatives
Process-local halted sets and UI-only stop controls were rejected because they reset on restart and could be bypassed by direct intent submission.

### Reversal
A future subscription state machine may replace the boolean only through an additive migration and coordinated contract tests preserving stopped-strategy risk rejection.

## DEC-013 — Isolated local PostgreSQL development databases
Date: 2026-10-07
Status: ACCEPTED

### Context
PostgreSQL persistence and migrations were only locally unit-tested because an isolated Neon database was unavailable. Production data must never be used for integration tests, while SQLite alone cannot validate psycopg behavior, advisory ownership or PostgreSQL migration application.

### Decision
DESIGN_DECISION: Support peer-authenticated local PostgreSQL with separate `algoshield_local` application and `algoshield_test` rollback-only test databases. `scripts/setup_local_postgres.sh` creates missing databases and applies the same reviewed additive migrations without dropping, resetting or seeding data. Machine-specific URLs remain in ignored `.env.local`; Neon PostgreSQL remains the durable deployment target.

### Reason
Developers can validate the real PostgreSQL store and migrations safely without production access or stored local credentials.

### Impact
Local setup documentation, environment template, migration validation and PostgreSQL integration testing.

### Alternatives
Using production/Neon data for tests, silently falling back to SQLite, or maintaining a second PostgreSQL schema path were rejected.

### Reversal
Replace the local launcher when the team adopts a different isolated development environment, while preserving separate application/test databases and the existing migration history.

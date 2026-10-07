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

## DEC-012 — Durable offline mock and P0 failure evidence
Date: 2026-10-07
Status: ACCEPTED

### Context
In-memory external mock state prevented teammates from restarting the runnable demo. Partial fills and rejections existed in code but were not observable through the frontend.

### Decision
Persist canonical mock orders/fills independently of the platform DB via atomic JSON replacement; load it only for offline SQLite mode. Add risk-routed deterministic Failure Lab scenarios, real order/candle displays and CI. Refuse all demo seeding against PostgreSQL.

### Reason
Restart reconciliation now compares independently retained external evidence; P0 is testable from API and dashboard without 021 or Neon authentication.

### Impact
Minimal cross-owner changes: mock persistence (Member 2), platform/API/frontend wiring (Members 3/4), P0 integration tests and ignores. Shared financial models/formulas are unchanged. `design.md` remains removed per user instruction.

### Alternatives
Reconstructing broker truth from the platform ledger would hide drift and was rejected.

### Reversal
Replace the mock fixture with an independently hosted simulator or a documented adapter, retaining recovery and drift tests.

## DEC-013 — Durable validated policies and risk budgets
Date: 2026-10-07
Status: ACCEPTED

### Context
Restart reset configurable risk policies and individual halt state. There was no authoritative API to inspect pending exposure or change limits.

### Decision
Add risk-owned risk_policies/strategy_controls via additive PostgreSQL and versioned SQLite migrations. Validate finite positive loss limits and strict positive integer quantities/limits. Preserve existing policy mapping access. Derive loss/rate consumption from durable fills/orders; persist loss halts. Extend RiskDecision additively with reason/time/reservation details and introduce enums retaining existing state values. Expose budgets and policy/state APIs. Normalize migration SQL line endings before hashing.

### Reason
Restarts cannot erase configured limits or loss evidence; pending exposure survives policy changes. Canonical hashes stay stable across Windows/Linux checkouts.

### Impact
Member 3 risk service/API/tests, shared contracts/store/migration packaging and documentation. No accounting formula changes. PostgreSQL migration execution remains unverified until isolated DB access is available.

### Alternatives
Mutable process dictionaries and UI-authoritative limits were rejected.

### Reversal
Migrate policy/control history through a versioned schema change and retain restart, validation and concurrent-reservation tests.

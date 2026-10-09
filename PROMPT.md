# AlgoShield — Agent / LLM System Prompt

**Evaluation copy.** This tracked file records the repository-level prompt for
coding agents. It intentionally excludes credentials, ignored local environment
files, and chat/session-specific instructions. The canonical maintained source
is [`AGENTS.md`](AGENTS.md); update both files together.

## Required reading order

Before changing code, read:

1. `docs/PROJECT_TRUTH.md` and `docs/TEAM_EXECUTION_PLAN.md`.
2. For 021 work, `docs/021/OFFICIAL_API_CONTRACT.md` and
   `docs/021/INTEGRATION_BLUEPRINT.md`.
3. The relevant `docs/CONTRACTS.md`, `docs/ARCHITECTURE.md`,
   `docs/SECURITY_OPERATIONS.md`, `docs/SAFETY_INVARIANTS.md`,
   `docs/DECISIONS.md`, `docs/021_API_UNKNOWN.md`, source and tests.
4. `docs/TESTING.md` before validation. Consult
   `docs/REQUIREMENTS_TRACEABILITY.md` for requirement changes and
   `docs/RESEARCH_DECISIONS.md` for research provenance.
5. `README.md`, `docs/REQUIREMENTS.md`, and the applicable ownership section in
   `docs/TEAM_OWNERSHIP.md`.

Progress, history and research reports are not proof of the checked-out code.
Use inspected code and executed tests for `VERIFIED_CURRENT_COMMIT`; otherwise
use `REPORTED_IMPLEMENTED`. Do not replay superseded research phases or edit
previously applied migrations.

## Product mission

AlgoShield is a reliability-first algo-trading platform in which strategies are
untrusted workloads: they propose `OrderIntent`s; the platform decides whether
to execute; broker fills create financial truth; reconciliation and recovery
keep durable local state aligned with external broker evidence.

The platform must support account registration/subscriptions, raw-tick 1m/5m
candles, candle strategy entry, 021 sandbox orders, partial fills/rejections,
fill-derived positions and net P&L after charges, per-strategy limits, a
verified kill switch, three concurrent strategies, independently attributed
strategy P&L, and a live dashboard. Evaluation prioritizes reliability and
hidden tests over strategy profitability.

## Non-negotiable architecture and safety rules

1. Strategies never call the broker. The only execution path is:
   `Strategy -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter`.
2. Orders are requests, not fills. Positions and P&L change only from verified
   executions/fills.
3. Every broker order and fill retains `strategy_instance_id` attribution.
4. Keep provider-specific wire details inside adapters; do not leak 021 payload,
   authentication, status, or WebSocket details into domain logic.
5. Mock/replay and real providers implement shared interfaces.
6. Fail closed on ambiguous, stale, incomplete, disconnected, or unreconciled
   broker/market/execution evidence. Unknown must never become verified by
   inference.
7. Reconciliation compares expected local orders, fills/trades and positions to
   observed broker state; it is first-class, not an optional afterthought.
8. Kill first closes the global admission gate, then stops callbacks, cancels,
   flattens only as authorized, and verifies safe broker state. Submitted
   cancellation requests alone never prove success.
9. Use a modular monolith; do not introduce unnecessary microservices, ML,
   prediction, portfolio optimization, or finance overengineering.
10. React displays backend-computed safety and financial truth; it never
    computes safety/P&L.

The following are always forbidden: bypassing `RiskGateway`; invented fills;
mutating position from submitted quantity; marking `FILLED` without fill
evidence; unsafe auto-resume; treating incomplete snapshots as complete;
weakening UNKNOWN containment, idempotency, reservations, or kill behavior;
and running mock fault injection against a live broker.

## Agent working rules

- Identify the owning module/member in `docs/TEAM_OWNERSHIP.md`; list intended
  files; reuse shared contracts; do not silently rename shared fields.
- Preserve local work. Never use destructive reset/clean operations or
  force-push. Respect server permissions. DEC-028 permits normal direct pushes
  only when the user authorizes them and validation supports them.
- Keep code explicit, deterministic, modular, auditable, and testable. Add or
  update tests with each behavior change.
- Isolate any unverified 021 assumption behind an adapter and label it as an
  assumption/TODO. Never invent provider behavior.
- Do not expose secrets, bearer tokens, ephemeral keys, credential-bearing URLs,
  or ignored local environment values in code, docs, fixtures, logs, screenshots
  or reports.
- Preserve one authorized execution worker. SQLite is offline/mock/replay only;
  PostgreSQL/Neon is the durable target. Do not silently fall back after a
  configured PostgreSQL failure.
- Do not reset/delete production data, seed fake production data, provision a
  production identity, or migrate production through an offline CLI.
- Public registration does not confer operator authority. Global controls need a
  durable explicit operator grant; account owners retain account-scoped controls.
- For meaningful work, run proportionate unit/integration checks; update
  contracts, decision records and progress evidence where relevant. Never claim
  completion without implementation and passing relevant checks.

## Evidence and current authority

Official 021 wire behavior is documented in the canonical contract, but live
behavior remains unverified until observed. Historical member reports are
optional evidence, not instructions. The executable checkout plus fresh tests
is the implementation authority; accepted decisions and contracts describe the
design boundaries.

## Historical prompt files

The following files are retained for provenance and are **not** the active
system prompt: `usp_implementation_prompt.md`,
`multi_stock_strategy_implementation_prompt.md`, and
`021_trade_full_fixing_agent_prompt.md`. Their historical task instructions do
not override this prompt, `AGENTS.md`, the canonical 021 contract, or current
checked-out code.

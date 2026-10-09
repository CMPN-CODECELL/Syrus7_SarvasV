# Team execution plan

## Official 021-03 update (2026-10-09)

The supplied official contract supersedes the earlier claim that all endpoint and packet schemas were unavailable. DEC-031 adds a first gap-only checkpoint: strict fixture normalization and isolated mandatory strategy policies are implemented, while live transport, runtime composition, durable broker mapping, trade association, charges, complete history, opposing close semantics and sandbox/PG evidence remain release blockers. Continue with `docs/021/INTEGRATION_BLUEPRINT.md`; do not rebuild the existing risk/ledger/React modules.

2026-10-09 (Asia/Calcutta). Sole operational phase plan under DEC-028.
Product facts: PROJECT_TRUTH. Gap/evidence matrix: REQUIREMENTS_TRACEABILITY.
Current blockers: IMPLEMENTATION_DELTA. Contracts and invariants remain normative.
Historical research and member progress are optional provenance, not task authority.

## Baseline and promotion gate

Reviewed baseline: 4782ca17ddc209e4543707375d18e5c28f80ff46.
Direct-push CI prerequisite commit: 63266eb3aab1dfaa0c3934bae744d459df2184c4.
Local candidate validation: 372 Python passed / 1 isolated PG skipped; 30 React
tests, seven rehearsals, Ruff, ESLint, build and root TypeScript passed. Exact
environment/remote confirmation is in progress/INTEGRATION. No 021 or deployed
readiness claim. Phase 0 completes only after main publication is confirmed.

User authorization supersedes earlier dev-only and mandatory-PR workflow rules.
Team members may directly push their branches; pull requests are optional.
Normal fast-forward/non-force pushes and validation remain required. GitHub
collaborator access/branch rules are server administration, not granted by docs.
Do not change protections or bypass required server checks. PR #1 was closed
without merging at the owner's request. No future feature branches are pre-created.

## Current gaps and adjudication

| Priority | Gap | Decision and dependency |
|---|---|---|
| P0 release | Old CI lacked SPA prerequisite before pytest | Fixed in 63266eb; require actual push CI success before promotion |
| P0 external | No authenticated 021 orders/feed/history/charges | BLOCKED_EXTERNAL; obtain schemas, scoped identifiers, credentials and fixtures |
| P0 durability | Actual PG financial parity/controller exclusion unverified | IMPLEMENTED_UNVERIFIED; authorized isolated pre-migrated database required |
| P0 live safety | Snapshot consistency/completeness and opposing virtual exits | BLOCKED_EXTERNAL; sponsor capability/timing/product rules required |
| P1 product verification | scripts/browser_smoke.py uses legacy selectors and port 8011 outside default Origins | PARTIAL; adapt to canonical React and explicit test Origin, run isolated desktop/mobile |
| P1 deployment | TLS/secure cookie, identity/operator governance, proxy peer policy and audit retention | PARTIAL local-only; authorize a deployment environment and policy before live exposure |
| P1 runtime entrypoint | scripts/run_app.sh omits --no-proxy-headers unlike Docker/README | Documentation/config mismatch; Member 3 owns correction/validation |
| P2 performance | Ledger full-history replay has no measured regression | DEFERRED; benchmark before cache, never introduce a second financial authority |
| Conditional economics | Corrections/busts/independent late fees lack normalized source semantics | DEFERRED until verified contract; preserve conflicting-evidence fail-closed behavior |
| Rejected | Ledger/risk/React/runtime/proof rebuild, timestamp sequence, alternate candles, Redis/Kafka/ML | NOT_REQUIRED; existing suites work, no reproduced need |

## Ownership and one-writer rule

| Owner | Exclusive workstream | Shared-file assignment and reviewers |
|---|---|---|
| Member 1 | backend/accounting; financial parity and persistence tests | store.py/postgres.py and new migrations: M1 writes, M2/M3 review; M3 lock work follows M1 handoff |
| Member 2 | backend/broker and backend/execution; provider/event identity | contracts.py broker fields: M2 writes only in coordinated slot, M1/M3/M4 review |
| Member 3 (integration lead) | backend/risk, backend/reliability; security/release | api.py, platform.py, auth/browser security, AGENTS/canonical docs/CI: M3 writes; affected owners review |
| Member 4 | backend/market_data, backend/strategies, frontend/src; browser/demo | Consumer changes follow frozen contract; API composition through M3, financial semantics through M1 |

No simultaneous writers to shared files. Reserve the file/change set and base SHA
in integration evidence before work. Schema changes must be necessary, new,
forward-only and tested for existing rows; preserve all applied SQL/checksums.

## Task packets

All packets require a focused failing/missing acceptance case first, relevant
cross-owner regressions, docs/evidence with SHA and command results, and a clean
artifact/secret/lock review. Handoff = commit SHA, exact diff, fixture provenance,
executed commands/skips and remaining blockers. No estimated hours are implied.

### M1-PG01 — P0, financial persistence parity (M)

Objective: PS06/07/14 financial truth on the durable target. Existing Ledger.apply/
_calculate is Decimal/fill-derived; PostgreSQL code exists but its test is skipped.
Targets: backend/accounting/ledger.py (validation only), backend/shared/postgres.py
PostgresStore, backend/shared/migrate.py migrations/apply; tests/test_postgres_integration.py,
test_database.py, test_member1.py and test_charges.py. Input: explicitly isolated
authorized URL and applied checksum ledger. Fixtures: duplicate concurrent fills,
opposing strategies, reversals/fees, rollback, restart and SQLite-vs-PG equality.
Forbidden: production URLs, formula rewrites, old migration edits, hidden SQLite
fallback. Done: exact Decimal parity and rollback/restart evidence on PG; publish
sanitized fixture/results. Checkpoint G1; BLOCKED until environment authorized.

### M1-FIN02 — conditional P1, correction/fee specification (M)

Objective: PS07 exact final economics. Existing attached charges work; independent
adjustments/corrections are unsupported. Targets: docs/CONTRACTS.md capability
table and ledger.py projection tests, coordinated contracts.py only if accepted.
Input: M2-CAP01 authenticated execution/fee examples and reference/order guarantees.
Specify delta vs replacement, bust target, units, session attribution, ordering,
duplicate/restart replay and quarantine. No fill overwrite or guessed taxes.
Done: accepted model and fixtures before implementation; handoff to M2/M3.
Checkpoint G2; BLOCKED_EXTERNAL until source semantics are authenticated.

### M2-CAP01 — P0, provider capability and fixture dossier (S)

Objective: PS05/06/12. Existing Broker021Adapter methods raise NotImplementedError;
mock interfaces and scoped identity contract are working. Targets:
backend/broker/adapters.py BrokerAdapter/Broker021Adapter (inspect),
docs/021_API_UNKNOWN.md, docs/CONTRACTS.md; tests/test_broker_adapter_contract.py.
Inputs: request sponsor specification; record unavailable capabilities explicitly.
Acceptance: authenticated endpoint/auth/ID uniqueness, status/cancel/timeout,
pagination/coverage/freshness, fee, shorting/netting and kill evidence fields.
No invented fields or compatibility claims. Done: immutable sanitized raw fixtures,
provenance/version and normalized expected results. G1 dossier may retain blockers;
G2 implementation cannot start until required provider capabilities are confirmed.

### M2-ADAPTER02 — P0, real identity/event adapter (L)

Objective: PS05/06, canonical stable attribution. Targets: Broker021Adapter.submit/
cancel/snapshot/parse_update/drain_updates; OrderManager.submit_reserved/ingest/
process_broker_update; snapshots.verify_snapshot; mock_persistence.py reference
only; contracts.py shared slot M2. Input: CAP01 and M1 financial fixture approval.
Acceptance: ord-123 vs brk-999 compound (provider, account, raw ID), collisions,
partial/reject, duplicate/conflict, cancellation, persisted mapping across restart,
UNKNOWN timeout without retry, unknown identity fail closed, complete snapshots.
No arbitrary alternate-ID lookup, raw fields in domain, unneeded schema column.
Done: adapter contract suite and controlled sandbox round trip with measured
evidence; preserve mock compatibility. Handoff G2 → G3a. BLOCKED_EXTERNAL today.

### M3-SEC01 — P1, deployment transport/security policy (M)

Objective: PS01/15 access boundary. Existing DEC-026/027 works locally; secure=False
cookies and local operator CLI are not production identity. Targets: api.py
set_session_cookie/create_app/browser_boundary, auth.py, browser_security.py,
scripts/run_app.sh, Dockerfile, SECURITY_OPERATIONS; test_round2_security.py,
test_operator_authority.py and test_control_plane_security.py. Inputs: isolated
deployment URL/TLS/identity/proxy/operator governance agreed by owner.
Acceptance: trusted/missing/evil Origin and bearer, TLS cookie flags, 401/403
mutation-free, revoked operator/session, two-account nested HTTP/WS, spoofed
forwarded IP, documented shared-peer capacity. Forbidden: auto-grants, production
provisioning, weaker projection or live fault injection. Done: runbook plus
isolated deployment evidence, no claimed production coverage. G1; policy-dependent
parts BLOCKED until approved. Align run_app flags without changing DB defaults blindly.

### M3-PG02 — P0, exclusive controller and crash gate (M)

Objective: I1/I7/I10 durable authority. Targets: PostgresStore.__init__, migrate.apply,
RiskGateway.submit/authorize_dispatch, Reliability.reconcile/resume; test_postgres_integration.py,
test_recovery.py and test_state_machine.py. Input: M1-PG01 DB/transaction handoff;
M3 receives exclusive postgres.py slot. Fixtures: second process denied before
dispatch, lock release/reacquire, failed reservation commit → no submit, crash after
UNKNOWN → retained reservation/no retry, failed PG connection → no fallback.
No multiworker trading or production writes. Done: process/transaction fixtures
pass on isolated PG; sanitized evidence. G1/G3c; BLOCKED on isolated DB.

### M3-SAFE03 — P0, real recovery and kill capability gate (L)

Objective: PS12 and I8/I9/I10. Targets: snapshots.verify_snapshot,
Reliability.reconcile/kill/reset_kill, Deadline/BrokerSession in broker_calls.py, risk gateway;
test_recovery.py, test_kill.py, test_kill_certificate_v2.py. Inputs: ADAPTER02,
financial G3b and sponsor coverage/netting/exit/SLA definitions. Fixtures: matching
net but omitted offset fills, incomplete/aged history, in-flight submit, hung
call, partial cancel/late fill, net-flat opposing virtual positions and rejected exit.
Done: no green from requests alone; truthful SUCCESS/SAFE_LATE/FAILED, gate latch,
separate net/virtual evidence and authorized reset after restart. Keep current
mock fixtures; live latency must be measured separately. G3c/d; BLOCKED_EXTERNAL.

### M4-WEB01 — P1, canonical browser smoke (M)

Objective: PS01/02/15 and evaluation readiness. Targets: scripts/browser_smoke.py,
frontend/src/pages/AuthPages.jsx, StrategiesPage.jsx, OrdersPage.jsx,
components/AppShell.jsx, auth/AuthContext.jsx and telemetry/TelemetryContext.jsx.
Inputs: built SPA, isolated mock process, configured exact browser Origin (8011
is not a default trusted port), test ordinary/operator identities provisioned offline.
Replace legacy Confirm Password/#subscription-form/#strategy-rows/Signed in as
assertions only after checking actual React labels/routes. Fixtures: login,
subscription, KILLED/RECOVERING/UNKNOWN, 40/100 execution, missing money ≠ zero,
signal candle/time, account switch/logout/401/1008, desktop/mobile overflow.
No financial recomputation or duplicate providers. Done: reproducible Playwright
run, screenshots and console checks, HTTP/WS two-account regressions. G1/G4;
browser installation/process access may block execution, report it explicitly.

### M4-FEED02 — P0, verified raw feed normalization (L)

Objective: PS03/04/13. Targets: candles.py MarketDataProvider/CandleBuilder/
ReplayMarketDataProvider, session.py MarketSession, runtime.py on_candle,
platform.py tick; test_candle_correctness.py, test_mock_feed.py, test_replay_stream.py,
test_market_session.py. There is no implemented MarketData021Provider file to copy.
Input: sponsor tick identity/timestamp/volume/reconnect/backfill/session contract;
ADAPTER02 and G3 risk prerequisites before enabling live strategy entry.
Acceptance: 60/300 boundaries, duplicate IDs vs simultaneous distinct ticks,
late/gap handling, volume units, stale event/receive, reconnect warmup and three
opposing strategies. No alternate aggregator, fictitious bars or timestamp-as-sequence.
Done: raw-to-canonical fixtures plus controlled feed evidence; offline replay stays
compatible. Shared provider creation via M3 integration slot. G2/G3e; BLOCKED_EXTERNAL.

### M4-DEMO03 — P1, release/viva rehearsal (S)

Objective: PS16 readiness, not proof of hidden-test completion. Targets:
backend/demo_scenarios.py RehearsalRunner, scripts/rehearsal_runner.py,
docs/DEMO_AND_DEBUG.md, frontend evidence pages; test_demo_scenarios.py.
Input: G3f and WEB01. Acceptance: seven deterministic mocks, opposing P&L,
partial/reject, risk denial, UNKNOWN/restart/recovery, verified mock kill and
truthful failed/incomplete evidence. Sandbox demonstration is separate and conditional.
Done: fixed-SHA walkthrough, extension/live-change exercise and evidence bundle.
No injected fault against live/PG. G4; do not wait for sponsor to rehearse mock cases.

## Sequential phases and integration checkpoints

| Phase | Entry / tasks / allowed parallel work | Ordered exit and owner |
|---|---|---|
| 0 Baseline freeze | Main promotion confirmed; full requirement matrix and DEC-028. Integration lead owns shared slots and CI. No future features. | G0: validated common main SHA, direct-push workflow, fixture/deployment/DB blockers recorded. M3 lead |
| 1 Foundations | G0. M1-PG01, M2-CAP01, M3-SEC01 audit, M4-WEB01/feed dossier independently, without shared interface changes. M3-PG02 follows M1 shared-slot release. | G1: independent evidence + precise blockers. Mock browser work may finish while external tasks remain blocked. Live Phase 2 requires sponsor fixtures and approved shared contract. M3 lead |
| 2 Provider/data interfaces | CAP01 source verified; one coordinated contracts/schema slot. M2-ADAPTER02 first; M4 raw fixture normalization after contract freeze; M1 validates identity/economics, M3 verifies evidence capability. | G2: complete adapter/feed contract tests, PG/backward compatibility if schema changed, sandbox facts recorded; no hidden mock substitution. M2 leads, M3 integrates |
| 3 Safety chain | G2; no six independent merges. Sequential G3a mapping/events → G3b M1 fills/financial projection → G3c M3 risk/reconciliation → G3d M3 kill/restart → G3e M4 runtime/feed → G3f M3 API + M4 React. | Each checkpoint: focused + cross-owner + seven mocks before downstream starts. Full suite at G3f. Unknown evidence blocks downstream live exposure. M3 integration owner |
| 4 Adversarial demo/deployment | G3f, WEB01 and authorized isolated deployment/DB. M4-DEMO03 and all-owner fixtures. | G4: PS matrix re-evaluated, desktop/mobile and PG evidence, TLS/cookie/Origin/ingress, three strategies, exact mock and separately verified live outcomes. External blockers remain explicit. M3/M4 |
| 5 Release | G4 for claimed scope; no unreviewed shared-interface change, exact remote head and clean diff/secret/artifact review. | Full checks and push CI green, normal promotion into main with owner authorization; sync dev before next phase. M3 lead; no forced refs |

Containment in every phase: retain the last verified baseline, close trading gate
for uncertain runtime/provider evidence, pause downstream work on failure, correct
on an isolated branch and revalidate. Use additive fix/revert commits for code;
never reset published history or revert applied DB migrations destructively.
No phase rollback may discard fills, UNKNOWN reservations or kill latch history.

## Direct branch pushes and exact integration order

All members fetch and base from the same published G0 main SHA (or the explicitly
designated current dev checkpoint). No automatic future branch creation.

1. Member 1: `member1/pg-financial-parity`; Member 2: `member2/provider-capabilities`;
   Member 3: `member3/deployment-security`; Member 4: `member4/react-browser-smoke`.
   Direct pushes to these branches are allowed. Lead integrates independent diffs
   into dev only after respective acceptance; no all-four edit of shared files.
2. Reserve one `integration/provider-contract` slot before `member2/021-adapter`;
   then `member1/verified-financial-events` only when economics input exists.
3. Integrate `member3/021-recovery-kill`, then `member4/021-feed-runtime`, then
   `integration/scoped-live-api-ui`. Each uses the preceding verified dev SHA.
4. `integration/release-validation` captures phase-wide CI/demo/DB/browser evidence;
   lead normally fast-forwards main when ancestry permits, otherwise validates a
   non-rewriting merge candidate. Direct pushes never imply force updates.

PRs are optional and there is no mandatory PR merge order; the branch integration
order above replaces it. Before every integration: fetch, inspect exact source
SHA/diff, agree shared contracts with affected owners, run focused/cross-owner
tests + seven rehearsals. Before main: full tests, published push CI and expected
remote head. If main moves independently, re-audit ancestry and revalidate the
updated candidate. Do not auto-merge feature/multi-stock-strategies: its scope is
unreviewed and outside this release. GitHub team users need repository write access;
server permissions/rules may still reject a direct push, which must be reported.

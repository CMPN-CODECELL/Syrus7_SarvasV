# Current repository audit and proposed changes

Recorded 2026-10-09 (Asia/Calcutta). Review checkpoint requested by the owner;
no implementation changes, commits, or pushes have been made by this audit.

## Checkout and preservation

- Original local `main`: `8e5ee505d1785ee82caa36ea66c1b73517395da7`.
- Fetched `origin/main`: `b0930c52056f175539e8fe9be7a1fabd2cd075eb`.
- Current local `dev`: `b0930c52056f175539e8fe9be7a1fabd2cd075eb`.
- Remote head inspection returned `main` only; no remote `dev` existed.
  Local `dev` was created from the fetched main history, incorporating its
  recent frontend fixes without modifying the local main branch.
- Checksum-verified copies of the modified AGENTS.md and four untracked research
  documents are outside the repository at
  `C:\Users\ASUS\AppData\Local\Temp\AlgoShield-backup-613e238ad9fc402f80dbae4c52df7c9f`.
  A tracked diff is included. Git reported no ignored files before validation;
  no secret contents were printed or copied into tracked files.
- Local `dev` initially tracks `origin/main` because that was its start point.
  Change its upstream to `origin/dev` only after a reviewed, successful normal
  push to `HEAD:dev`; never use an unqualified push with the current upstream.
- The named MASTER_REPO_UPDATE_PROMPT.md and AGENTS_ENTRYPOINT_PATCH.md were
  not found in this checkout. The attached master prompt and user-supplied
  entrypoint instructions supplied their contents. The baseline section is
  already present in the user's modified AGENTS.md.

## Verified gap matrix

`VERIFIED_CURRENT_COMMIT` below refers to inspected code and executed evidence
at b0930c5, with no tracked source modifications. It is scoped evidence, not
certification of all behavior or live readiness.

| Requirement/rule | Source | Current behavior and evidence | Status | Missing/failing evidence | Proposed action | Priority |
|---|---|---|---|---|---|---|
| Authenticated account controls | backend/api.py:181,187,200; tests/test_control_plane_security.py | Anonymous critical controls rejected; strategy and order ownership checked; existing tests pass in full run | VERIFIED_CURRENT_COMMIT | Operator vs ordinary-user authority is not represented | Reuse auth/ownership; review explicit operator or local-demo authorization policy | P0 |
| Cross-account telemetry | backend/api.py:584,594,600,606 | Two-account mock probe: GET /api/state hides other subscription; POST /api/reconcile returns that subscription in state, HTTP 200 | VERIFIED_CURRENT_COMMIT gap | Existing isolation tests do not exercise these mutation responses | Scope reconcile/resume/reduce-only/reset responses; audit reconciliation-center, proof, broker and kill response payloads; add two-account adversarial regressions | P0 |
| Global mutation authority | backend/api.py:415,421,426,431,448,579,584,594,600,606,612 | Global actions call require_user, allowing any registered session; stronger function authorization absent by inspection | VERIFIED_CURRENT_COMMIT gap | Negative ordinary-user 403/mutation-free tests | Resolve operator provisioning and deployment restriction before permission design changes | P0 / review |
| Integrated Python suite | tests/test_member4_workflow.py:551,561 | 312 passed, 1 failed, 1 skipped after frontend build; failing assertion requires old setSnapshot(null) name | VERIFIED_CURRENT_COMMIT gap | Source-string assertion diverges from current telemetry implementation | Preserve backend lifecycle checks; replace stale frontend source assertion with behavioral session/logout/1008 coverage already exercised in Vitest, rather than weakening safety behavior | P0 |
| Tick/candles/three opposing strategies | backend/market_data/candles.py; backend/strategies/runtime.py; backend/demo_scenarios.py | Seven rehearsals pass; opposing positions +1/-6/+1, broker net -4; 1m/5m strategy evidence | VERIFIED_CURRENT_COMMIT mock | Real feed semantics unavailable | Reuse; document scope | P1 docs |
| Fill-derived accounting and reservations | backend/accounting/ledger.py:11; backend/risk/gateway.py:193; backend/execution/orders.py:200,234 | Full run passes accounting, partial/reject, duplicate/conflict, account exposure and race tests | VERIFIED_CURRENT_COMMIT mock | Provider correction/charge semantics unknown | Reuse; do not invent correction economics | P1 / 021 blocked |
| Kill/dispatch/restart/freshness | backend/reliability/control.py:117,435; tests/test_kill.py; tests/test_recovery.py | Existing gate/dispatch, hung-call, cancel/fill, SAFE_LATE, incomplete/zero-net history, UNKNOWN and persisted-latch tests pass; rehearsal kill SUCCESS 0.19s | VERIFIED_CURRENT_COMMIT mock | Provider snapshot consistency/coverage and live exit semantics require contract | Reuse deterministic tests; identify a specific missing fixture before any change | P0 live blocker |
| Bounded callback workers | backend/strategies/runtime.py:456; tests/test_strategy_execution_safety.py | Timeout, kill, invalidation, bounded shutdown and post-close storage isolation tests pass | VERIFIED_CURRENT_COMMIT | Threads do not isolate malicious Python | Reuse; retain upload exclusion | P1 docs |
| React and evidence layer | frontend/src; backend/reliability/proof.py, tracing.py, safety_bench.py, failure_lab.py | 28 Vitest tests / 6 files pass; React build and lint pass; Python USP suites pass | VERIFIED_CURRENT_COMMIT mock | Node 23.6.0 outside several installed packages' declared engines | Document reproducible build prerequisite and supported runtime; do not rewrite React | P1 |
| Mock-only injection | backend/platform.py:454; backend/reliability/failure_lab.py:49; backend/api.py:560 | Guard refuses PostgreSQL or non-MockBrokerAdapter; SafetyBench creates fresh in-memory platforms per case; tests pass | VERIFIED_CURRENT_COMMIT | Deployment/operator authority still unresolved | Keep guard; add negative boundary tests only if audit finds absent coverage | P0 authority / P1 docs |
| Persistence and migrations | backend/shared/migrate.py:13; backend/shared/postgres.py:36; tests/test_database.py | Packaged PG through 010, SQLite through 011; PG has two distinct 002 files; migration checksum and SQLite upgrade tests pass | VERIFIED_CURRENT_COMMIT files/SQLite | Actual PG transactions/ownership not tested here; isolated URL absent, psql absent, Docker daemon unavailable | Preserve all migration files; test isolated PG once provided; no production access | BLOCKED P0 |
| 021 orders/feed/fees/kill | backend/broker/adapters.py:232; docs/021_API_UNKNOWN.md | Broker021Adapter raises NotImplementedError | UNKNOWN / BLOCKED | Authenticated sponsor schemas, credentials and execution evidence absent | Obtain verified sponsor contract; no fabricated adapter | P0 external |
| Documentation precedence | docs/PS.md; docs/PHASE_PLAN.md; docs/CONTRACTS.md; usp_implementation_plan.md | PS.md contains supplied PS-06 text, rather than placeholder; old phase opening says schema v2 while actual SQLite is v11; contracts say MARKET-only although executable accepts LIMIT | VERIFIED_CURRENT_COMMIT doc gaps | Provenance authentication still pending; historic logs remain historical | Correct current summaries, preserve decision history, label USP proposal historical and point to delta; append next decision DEC-026 | P1 |

## Exact validation

Environment: Windows PowerShell, Python 3.13.1, Node v23.6.0, npm 10.9.2.
All trading validation used isolated SQLite and mock/replay; no production
database, live 021, or remote Neon test was attempted.

| Command | Result |
|---|---|
| python -m pytest -q -p no:cacheprovider --basetemp=data/research-audit-20261009 | 291 passed, 6 failed, 1 skipped, 16 errors; errors caused by audit-selected missing data parent; five failures require unbuilt SPA, one stale source assertion |
| Same command with --basetemp=data/research-audit-20261009-retry --tb=short, after creating data | 307 passed, 6 failed, 1 skipped; no setup errors |
| Same command with --basetemp=data/research-audit-20261009-built --tb=short, after build | **312 passed, 1 failed, 1 skipped**, 53.17s; stale assertion tests/test_member4_workflow.py:561; isolated PG test skipped |
| python -m ruff check . | Passed |
| python -m ruff format --check . | Passed; 89 files already formatted |
| npm.cmd --prefix frontend ci --ignore-scripts --fetch-retries=0 --fetch-timeout=15000 | Installed 217 packages; engine warnings for Node 23.6.0; audit reported 0 vulnerabilities |
| npm.cmd --prefix frontend run test | **28 passed, 6 test files passed**, 61.32s |
| npm.cmd --prefix frontend run lint | Passed |
| npm.cmd --prefix frontend run build | Passed; generated ignored dist assets |
| npm.cmd ci --ignore-scripts --fetch-retries=0 --fetch-timeout=15000 | Installed 151 packages; audit reported 1 low / 2 moderate vulnerabilities; no audit fix or lock changes |
| npm.cmd run check | Passed (root TypeScript infrastructure); no standalone frontend typecheck script exists |
| python scripts/rehearsal_runner.py | Failed with ModuleNotFoundError: backend on this uninstalled checkout |
| python -m scripts.rehearsal_runner (PYTHONPATH=repo root, PYTHONIOENCODING=utf-8) | **7 scenarios passed**; no source changes |
| Two-account FastAPI TestClient probe on in-memory Platform | Reconcile response leak reproduced; scoped GET excludes other subscription, reconcile includes it |
| docker info --format '{{.ServerVersion}}' | Daemon unavailable; no database container created |
| git diff --check | Passed |

Initial frontend/TypeScript checks failed because dependencies were absent;
the table records actual checks after installing unchanged lockfiles. Browser
driver smoke and an external mock-broker process smoke have not been run;
existing HTTP mock tests passed in the Python suite. No historical test count
has been substituted for a fresh result.

## Proposed reviewable change set

1. P0 account isolation: modify backend/api.py and
   tests/test_control_plane_security.py/tests/test_member4_workflow.py to scope
   privileged-action responses to the authenticated account and prevent nested
   financial data leakage. Preserve backend global outcome truth. Audit all
   related evidence responses before selecting the exact patch.
2. P0 integration: update the stale source-string test in
   tests/test_member4_workflow.py using existing behavioral frontend tests as
   evidence; extend frontend/src/test/telemetry.test.jsx if an uncovered
   invalidation race is identified. No safety assertions removed for a green run.
3. Documentation: reconcile AGENTS.md reading orders while preserving mandatory
   rules; add README start links; update PROJECT_TRUTH, IMPLEMENTATION_DELTA,
   REQUIREMENTS_TRACEABILITY, RESEARCH_DECISIONS, ARCHITECTURE, CONTRACTS,
   PHASE_PLAN, TESTING, DEMO_AND_DEBUG, 021_API_UNKNOWN and the USP historical
   plan with concise current facts and links. Append DEC-026 and dated
   integration/affected-member evidence; retain historical decisions/logs.

Owners: API/shared integration across Members 3/4; test telemetry Member 4;
financial projection boundaries Members 1/3. No migrations or accounting
formula changes proposed.

Permission design remains a product review item: identify who may perform
global kill/resume/reconcile and broker controls, how that operator identity is
provisioned, and whether deployment is explicitly restricted to local demo.
Authentication alone does not resolve that choice. Neon project identities
remain unresolved and require no database action during this work.

After review: implement small regressions, repeat affected/full validation,
review staged paths for secrets/generated artifacts, commit logically on dev,
recheck remote refs and push only `git push origin HEAD:dev` when safe.
This is the pre-remediation audit. DEC-026 and
`docs/progress/INTEGRATION.md` record the implemented resolution and current
validation. The earlier failures and review items remain historical evidence.

## Next three tasks

1. Review the isolation/test/doc proposal and resolve global operator authority.
2. Apply the approved P0 response-isolation and integration regressions, then
   synchronize documentation against passing current evidence.
3. Run final full checks and isolated PG/browser validation where available;
   record remaining blockers, review the diff, and push only origin/dev.

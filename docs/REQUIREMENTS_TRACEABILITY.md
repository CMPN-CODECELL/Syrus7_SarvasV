# Requirements and current-repository audit

Audited 2026-10-09 (Asia/Calcutta). Source: supplied PS-06 in PS.md/REQUIREMENTS.md;
sponsor-authenticated provenance remains pending. Operational sequencing lives
only in TEAM_EXECUTION_PLAN. This file maps evidence, not future feature phases.

Evidence E1: candidate 4782ca17ddc209e4543707375d18e5c28f80ff46 in an isolated
worktree; 372 Python passed / 1 PG skipped, 30 React passed, seven rehearsals,
lint/build/type checks. Windows/Python 3.13.1/Node 23.6.0/npm 10.9.2. E2:
63266eb3aab1dfaa0c3934bae744d459df2184c4 changes only push CI, same domain code;
GitHub Linux safety-tests succeeds after building SPA before pytest. Main was
promoted to E2 by normal fast-forward. Full command/error/skip provenance is in
progress/INTEGRATION. No isolated PG, actual 021 or deployed browser claim.

Status: VERIFIED_CURRENT_COMMIT = scoped executable mock/replay evidence;
IMPLEMENTED_UNVERIFIED = code exists but target environment not exercised;
PARTIAL = mandatory external/acceptance evidence missing; BLOCKED_EXTERNAL =
required sponsor/environment input missing; NOT_IMPLEMENTED/DEFERRED/NOT_REQUIRED
retain their ordinary meaning. E1/E2 are evidence references for all rows below.

## PS-06 completion matrix

| ID | Feature | Code/function | Test/evidence | Status and gap/severity | Owner / next |
|---|---|---|---|---|---|
| PS01 | Account/session/operator access | api.create_app; auth.AuthService; browser_security.origin_allowed | test_auth, test_round2_security, test_operator_authority; E1/E2 | VERIFIED_CURRENT_COMMIT local; deployment identity/TLS unverified P1 | M3 SEC01 |
| PS02 | Subscribe and start/stop own strategy | runtime.StrategyRuntime; Platform snapshot; api subscription routes | test_member4, test_strategy_lifecycle; E1/E2 | VERIFIED_CURRENT_COMMIT mock; no arbitrary uploads | M4 preserve |
| PS03 | Raw ticks → 60/300-second candles | candles.CandleBuilder.ingest_event; official021.parse_market_frame | test_candle_correctness, test_member4, test_mock_feed, test_official021 | VERIFIED_CURRENT_COMMIT canonical mock; MOCK_VERIFIED 021 sampled-snapshot decoding, not a live raw-trade feed | M4 FEED02 |
| PS04 | Candle-based strategy entry | runtime.on_candle; built-in handlers | test_member4, test_demo_scenarios; rehearsal 1; E1/E2 | VERIFIED_CURRENT_COMMIT mock; real feed dependent | M4 FEED02 |
| PS05 | Actual 021 sandbox orders | adapters.Broker021Adapter; broker.official021 | test_broker_adapter_contract, test_official021 | OFFICIAL_DOCUMENTED + MOCK_VERIFIED normalization; live transport/credentials/round trip BLOCKED_EXTERNAL | M2 ADAPTER02 |
| PS06 | Fills/partial/reject/cancel lifecycle | OrderManager.submit_reserved/ingest/process_broker_update | test_broker_updates, test_execution_state_machine, test_cancellation; E1/E2 | PARTIAL: mock verified, real events/identity unverified P0 | M2 ADAPTER02 |
| PS07 | Exact attributed trades/net P&L after charges | Ledger.apply/_calculate; Platform.history | test_member1, test_charges, test_safety; E1/E2 | PARTIAL: Decimal mock verified; real charges/corrections/final economics unknown P0 | M1 PG01/FIN02 |
| PS08 | Max strategy position | RiskGateway.submit/budget | test_risk_policies, test_safety; E1/E2 | VERIFIED_CURRENT_COMMIT mock directional reservations | M3 preserve |
| PS09 | Max daily loss | Ledger.daily_net; RiskGateway.submit | test_risk_policies, test_price_reasonability, test_recovery; E1/E2 | VERIFIED_CURRENT_COMMIT accepted IST formula; sponsor definition open | M1/M3 CAP01 clarification |
| PS10 | Max orders/minute | RiskGateway.budget/submit | test_safety, test_risk_policies; E1/E2 | VERIFIED_CURRENT_COMMIT rolling (now-60,now] admissions | M3 preserve |
| PS11 | Platform-owned risk, no bypass | RiskGateway.authorize_dispatch; OrderManager._start_reserved | test_safety, test_hardening, test_strategy_execution_safety; E1/E2 | VERIFIED_CURRENT_COMMIT mock; one worker | M3 PG02 |
| PS12 | Stop/cancel/flatten/verify within 10 seconds | Platform.kill; Reliability.kill/reset_kill | test_kill, test_kill_certificate_v2; rehearsal 6; E1/E2 | PARTIAL: mock measured SUCCESS; real exit/netting/coverage/SLA unknown P0 | M3 SAFE03 |
| PS13 | At least three simultaneous strategies | StrategyRuntime.on_candle; RehearsalRunner | test_member4, test_demo_scenarios; rehearsal 1; E1/E2 | VERIFIED_CURRENT_COMMIT shared event loop/bounded callbacks; not three processes | M4 preserve |
| PS14 | Opposing strategies independent position/P&L | Ledger.positions/aggregate; RiskGateway.account_budget | test_member1, test_account_risk, test_kill; rehearsal 1; E1/E2 | PARTIAL: mock attribution verified; live shorting/netting/exit policy unknown P0 | M1/M2/M3 CAP01 |
| PS15 | Live subscriptions/P&L dashboard | Platform.snapshot; API WS; React telemetry/domain/pages | test_control_plane_security, test_member4_workflow; Vitest telemetry/integrationGaps/round2Evidence; E1/E2 | VERIFIED_CURRENT_COMMIT mocked transport/rendering; deployed browser unverified P1 | M4 WEB01 |
| PS16 | Hidden tests/change request/viva readiness | tests; demo_scenarios; rehearsal_runner | E1 seven mocks and module regressions | PARTIAL; actual hidden tests cannot be certified; browser smoke stale P1 | M4 DEMO03 |

Scope count: 16 rows = 10 VERIFIED_CURRENT_COMMIT (mock/local), 5 PARTIAL,
1 BLOCKED_EXTERNAL. This is not 10/16 live PS compliance. PS05 is not implemented;
PS06/07/12/14 and feed/deployment evidence need external acceptance. No test count
substitutes for sponsor sandbox proof.

## Safety invariant matrix

| ID | Invariant | Code/function | Test at E1/E2 | Status / gap | Owner / next |
|---|---|---|---|---|---|
| I1 | Broker dispatch requires approved durable reservation | RiskGateway.submit/authorize_dispatch; OrderManager._start_reserved | test_hardening, test_state_machine | VERIFIED_CURRENT_COMMIT mock; PG commit/exclusivity unverified | M3 PG02 |
| I2 | Fills alone create positions | Ledger.apply/_calculate | test_member1, test_execution_state_machine | VERIFIED_CURRENT_COMMIT mock | M1 preserve |
| I3 | Unique financial application | Ledger.apply; OrderManager.ingest | test_member1, test_broker_updates, test_recovery | VERIFIED_CURRENT_COMMIT canonical IDs; real identity scoped mapping blocked | M2 ADAPTER02/M1 FIN02 |
| I4 | Account/strategy/symbol/side attribution | OrderManager.ingest; verify_snapshot | test_execution_state_machine, test_operator_authority | VERIFIED_CURRENT_COMMIT mock; foreign/unknown fails closed | M2/M1 preserve |
| I5 | Pending directional position capacity | RiskGateway.submit/account_budget | test_account_risk, test_risk_policies | VERIFIED_CURRENT_COMMIT serialized mock; PG verification pending | M3 PG02 |
| I6 | Closed gate/stopped strategy cannot increase risk | RiskGateway.authorize_dispatch; Platform.kill | test_kill, test_strategy_execution_safety | VERIFIED_CURRENT_COMMIT mock; authorized reductions separate | M3 preserve |
| I7 | Restart never auto-resumes | Platform.__init__; Reliability.resume | test_recovery, test_state_machine, test_p0 | VERIFIED_CURRENT_COMMIT SQLite/mock; PG crash coverage pending | M1 PG01/M3 PG02 |
| I8 | Broker health requires sufficient orders/fills/positions | snapshots.verify_snapshot; Reliability.reconcile | test_recovery incl net0/missing offset fills | VERIFIED_CURRENT_COMMIT mock completeness; provider consistency unknown | M3 SAFE03 |
| I9 | Kill success requires actual timed end-state evidence | Reliability.kill; KillCertificate | test_kill, test_kill_certificate_v2 | VERIFIED_CURRENT_COMMIT mock; net and virtual flatness separate, live blocked | M3 SAFE03 |
| I10 | UNKNOWN cannot increase risk or trigger blind retry | OrderManager.submit_reserved; Reliability.reconcile | test_execution_state_machine, test_recovery, test_state_machine | VERIFIED_CURRENT_COMMIT mock; live identity/history contract pending | M2/M3 CAP01 |

## Module/environment adjudication

| Area | Inspected implementation and tests | Status / actual remaining work |
|---|---|---|
| Auth/account security | auth.py, browser_security.py, api.py; operator/Origin/hash suites | Local verified; secure=False cookie, offline-only operator CLI, basic identity → deployment SEC01 |
| Runtime/candles | runtime.py bounded generation workers; candles.py direct intervals/session.py; execution-safety/candle/replay suites | Mock verified; threads are not hostile-code isolation; real feed absent |
| Broker/order IDs | adapters.py, http_adapter.py, orders.py; contract/cancellation/recovery suites | Mock canonical IDs verified; actual scoped provider mapping NOT_IMPLEMENTED, no premature column |
| Financial truth | ledger.py immutable executions/Decimal/reversal; member1/charges/recovery | Mock verified; independent late-fee/correction events unsupported; profile before cache |
| Risk/recovery/kill | gateway.py, control.py, snapshots.py, broker_calls.py | Existing suites verified; external history/close capability and PG failures remain unknown |
| React/evidence | frontend/src; presentation.py, tracing.py, proof.py | Scope and exact strings verified; scripts/browser_smoke.py uses legacy selectors, port needs trusted Origin |
| Failure Lab/SafetyBench | platform.fail-scenario guard; failure_lab.py/safety_bench.py | SQLite/mock-only verified; never use live/PG faults; no benchmark-as-live-safety claim |
| SQLite migration/restart | store.py v12; test_database upgrades; mock_persistence.py | VERIFIED_CURRENT_COMMIT; old applied files unchanged in promotion |
| PostgreSQL | PostgresStore advisory lock/checksum validation; opt-in rollback test | IMPLEMENTED_UNVERIFIED real transactions/controller parity; isolated test skipped; packaged through migration011 (two distinct historical002 names) |
| CI/packaging | tests.yml, Dockerfile, pyproject package-data | Prior CI pytest prerequisite missing, reproduced cloud failure; fixed push-only workflow succeeds at E2. Docker image not built here |
| Deployment scripts | run_app.sh; SECURITY_OPERATIONS | run_app lacks --no-proxy-headers; mark mismatch for SEC01, do not silently pick a Neon project |
| 021/feed | Strict fixture normalizer plus live-disabled Broker021Adapter; no composed 021 transport/provider | PARTIAL; sandbox identity/history/fees/kill remain BLOCKED_EXTERNAL |
| Hidden/change tests | tests and seven isolated rehearsals | PARTIAL readiness; actual hidden harness/change request unknown |

Unresolved human inputs: isolated DB authorization, which Neon identity/environment,
deployment domain/TLS/identity/operator governance, sponsor-authenticated statement
and API/fee/netting/SLA semantics. GitHub collaborator access is separate server
administration; main direct push acceptance does not grant every teammate write access.

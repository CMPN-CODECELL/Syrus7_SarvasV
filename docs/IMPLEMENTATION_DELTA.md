# AlgoShield — Research-to-Repository Implementation Delta

> Version: 2026-10-09. This is a **gap-driven integration plan**, not an instruction to reimplement all research. Current branch/commit must be audited first. Work on `dev`, never `main`.

## How to interpret status

- `REPORTED_IMPLEMENTED`: file/progress decision describes completed work, but current checkout unverified.
- `VERIFY`: inspect real source and rerun tests; change only upon demonstrated gap.
- `P0`: PS-critical or security/integration blocker. `P1`: correctness hardening or measured differentiator. `P2`: optional polish.
- `021-BLOCKED`: cannot finalize without authentic sponsor material.

## Baseline differences: old plans vs research Sessions 1–7

| Area | Earlier docs/plans may say | Latest recorded evidence / accepted target | Required action |
|---|---|---|---|
| Frontend | Vanilla `frontend/index.html` source | DEC-025 React/Vite `frontend/src` canonical, legacy preserved as static demo | VERIFY build/routes; update old docs to link React, do not revert |
| USP implementations | `usp_implementation_plan.md` says missing | DEC-024 + integration log report account risk, Safety Proof, traces, benchmarks, Failure Lab V2, certificates | VERIFY modules and behavior; mark old plan historical |
| Strategy callbacks | Hung callback blocks lock | DEC-019–022 report pure bounded workers, epoch invalidation, nonblocking teardown | VERIFY timeout and late completion race tests |
| Access control | Entire app anonymous | DEC-026 adds durable operator grants and a shared scoped response boundary, with adversarial tests | Reuse verified boundary; isolated PG and production identity remain blockers |
| Reconciliation | Compare net and self-heal | Complete/attributed history and freshness already reported; cross-endpoint consistency may remain weak | Add adversarial incomplete/inconsistent snapshot tests; no synthetic economics |
| Broker integration | Full 021 adapter perhaps implied | Adapter stubs, external HTTP mock and mock/replay are reported | Preserve honesty; BLOCK until real contract/credentials |
| Kill | Request cancel = success | Bounded multi-round, durable latch, V2 certificate reported; real opposing exit unknown | Test dispatch/late-fill/hung-call; sponsor close semantics |
| Accounting | Immutable unique fills sufficient for every event | Duplicate handling reported; corrected/busted trades not defined | Define unsupported-correction fail-closed now; 021-specific processing later |
| Database | One definitive Neon project | Project IDs differ across decisions/logs; isolated local PG reported | Audit environment and migration ledger; never seed production |
| Testing | One reported suite count = complete | Historical 311/1 skip + 14 frontend + 7 rehearsals; branch uncertain | Run full tests at one dev SHA; record real results |

## Work in exact dependency order

### B01 — Preserve and verify integrated `dev` (P0)

- `git status`, branch, remotes, diff, untracked; back up all non-secret changes, securely preserve secrets; fetch `main` and `dev`.
- Integrate latest `origin/main` into `dev` without overwriting local features; resolve semantically (never wholesale `ours/theirs`). Do not push unless authorized and checks finish.
- Record current commit, Python/frontend/rehearsal test results, skips and live startup. Treat failing checks as blockers rather than weakening assertions.
- **Done:** one current `dev` commit has reproducible test report; no uncommitted work accidentally lost.

### B02 — Audit authoritative contracts, migration history and health states (P0)

- Compare `backend/shared/contracts.py`, `docs/CONTRACTS.md`, adapters, Store and frontend API callers.
- Check fields for identity, account scoping, Decimal string encoding, `is_complete=False` default, historical certificate immutability, UNKNOWN vs confirmed zero, and state transitions.
- Check actual SQLite and PG migration ledgers/checksums (USP plan's 007–010 may already be applied). Never reuse numbers or edit applied files.
- **Done:** mismatch inventory and focused backward-compatibility tests; update docs only after code is consistent.

### B03 — Close privileged API authorization gaps (P0)

- Inspect all mutations in `backend/api.py`: risk policies and strategy controls, `/api/reconcile`, `/api/resume`, `/api/reduce-only`, `/api/kill`, `/api/kill/reset`, order cancel, failure lab, broker disconnect/reconnect/sync, market session, demo, accounts, account-level risk policy and benchmark run.
- Classify global operator authority vs user's own-account operation; apply server-side account scope, explicit operator role or explicit local-demo restriction; deny anonymous, cross-account and unauthorized actions. Do not assume every registered account can globally kill all users in a public deployment.
- Failure injection/benchmark must refuse non-mock or non-isolated environments even if caller authenticated.
- **Done:** negative 401/403 tests and mutation-free failures, including WS/SSE logout eviction and nested payload isolation.

### B04 — Audit dispatch, reservation, kill and restart (P0)

- Test paused broker dispatch concurrent with kill latch, partial fill→cancel→late fill, timeout-after-accept→restart, broker-call hang and DB failure before admission commit.
- Verify every pre-gate-close potential dispatch remains tracked; no ordinary dispatch authorization is granted after gate closure. No external I/O under a long DB lock; timeout never implies rejection.
- Measure end-to-end kill using monotonic time from trigger to broker-verified conditions; verify `SUCCESS`/`SAFE_LATE`/`FAILED` truth and persisted latch.
- **Done:** deterministic race fixtures exercise real production paths via isolated mock with event trace.

### B05 — Verify financial math, account risk and evidence quality (P0/P1)

- Independently test partial fill, cancel/reversal, multi-price average, charges, exact Decimal outputs, strategy attribution, net vs gross virtual exposure, concurrent policies, stale mark/day boundary.
- Add provider-scoped correction/bust capability and quarantine behavior **only if missing**; do not silently change existing ledger replay order without causal-model migration and reference-model tests.
- Verify order/fill/position snapshot *scope, freshness, coverage and consistency*; matching broker net is insufficient for `HEALTHY`. Absent incomplete-history evidence must remain UNKNOWN.
- **Done:** no false-green reconciliation, no double economic mutation, no fabricated ownership or fills.

### B06 — Test actual PostgreSQL and environment configuration (P0)

- Use dedicated local/isolated test PG. Check transactions, advisory controller ownership, migration checksums, restart, rollback and auth storage.
- Reconcile documented Neon IDs and intended environments; do not assume project/branch, connect to production, or run migrations without explicit authorization.
- **Done:** PG test result recorded (not skipped unless lack of isolated access is documented); no destructive operations.

### B07 — Verify official 021 capability and build adapter (P0, 021-BLOCKED)

- Request authentic sponsor docs, creds and test account; map supported order lifecycle, cancel, fill IDs, history, charges, market timestamps/volume, netting/shorting and kill semantics to existing canonical interfaces.
- Develop provider fixtures and contract tests; disable any unsupported live feature rather than simulating provider assurances.
- **Done:** real sandbox order/partial/reject/reconcile evidence and explicit results for all capabilities. Never claim this before real execution.

### B08 — Prove existing differentiators, do not rebuild (P1)

- Inspect and re-run Explainable Execution Authority, Evidence-Gated Recovery, Dual-Scope Exposure, Verified Emergency Shutdown, Failure Lab V2 and SafetyBench; verify same backend paths, not duplicated business logic.
- Confirm Safety Proof status is evidence scoped (`VERIFIED/FAILED/UNKNOWN/NOT_APPLICABLE`), historical certificates are immutable, mock runs isolated, and metrics show only actual measurements.
- **Done:** one reproducible 3-strategy incident demonstration and linked test evidence.

### B09 — Documentation and final demo freeze (P1)

- Update docs following `RESEARCH_DECISIONS.md`; update README/AGENTS, architecture, contracts, testing, demo, decision log, progress and 021 unknowns without erasing historical entries.
- Practice full demo under fixed commit and isolated environment; preserve actual timing and skip information.
- **Done:** a new coding agent can read `AGENTS.md` → `PROJECT_TRUTH.md` → delta and know what is implemented, unverified, blocked and next.

## Adversarial tests required at minimum

| Fixture | Expected invariant |
|---|---|
| Two intents race for capacity while limit changes | Serialized correct policy version, no oversubscription |
| Kill while ordinary submit is poised/in-flight | No post-gate unauthorized dispatch; pre-existing uncertainty tracked |
| BUY100 fill40 cancel-request fill20 cancel-remainder40 | Final filled+60, reservation zero only on terminal confirmation |
| Timeout after broker accept + crash + incomplete history | No duplicate retry, gate closed, reservation retained |
| Broker local+60 vs external+80 without fill price/owner | No fabricated BUY20; UNKNOWN |
| Matching net positions but missing offsetting executions | Not globally `VERIFIED` |
| A+100, B-100, broker net0 on kill | Account flat != virtual flat |
| Fill correction after partial close | Reproject when supported; otherwise quarantine/halt |
| Stale loss mark and pending order | Cannot enable risk increase on stale evidence |
| Second controller starts; PG failure during admission | No dual dispatch or undurable external order |
| Authenticated user A mutates/reads B | Denied with no leakage/mutation |
| Hung callback + kill | Control path responsive; stale callback has no effect |

## Required coding-agent output

Produce a gap inventory with `current code location | doc expectation | proof/test | decision | change | result`. Make the smallest targeted patches, run tests and record exact counts. Update `docs/progress/INTEGRATION.md` with commit/environment. New decisions append to `docs/DECISIONS.md`. Never report `VERIFIED_CURRENT_COMMIT` from historical member logs.

## Current disposition after approved remediation (2026-10-09)

- B01/B03: IMPLEMENTED_VERIFIED in offline/mock validation; see `progress/INTEGRATION.md` for the exact implementation SHA and checks. Global operator authorization, response leakage and stale telemetry test are repaired.
- B02/B04/B05/B08: existing executable mock suites pass; no migrations were rewritten and no accounting/kill/runtime feature was rebuilt. Provider-specific corrections and consistency require sponsor evidence.
- B06: BLOCKED; no isolated PostgreSQL URL/server is available. Migration 011/provisioning on PostgreSQL is IMPLEMENTED_UNVERIFIED.
- B07: BLOCKED/UNKNOWN; authentic 021 contract/credentials absent.
- B09: current summaries synchronized, historical decisions/phases retained. Active next work is isolated PG verification, sponsor fixtures, and deployment identity/TLS hardening. The original B01-B09 checklist remains acceptance guidance, not an instruction to repeat completed work.

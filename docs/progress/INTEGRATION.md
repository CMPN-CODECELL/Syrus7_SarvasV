# Integration Progress

## Current Status
- Phase: integrated mock/replay hardening with Member 4 strategy/runtime and local PostgreSQL verification
- Status: BLOCKED
- Last updated: 2026-10-08 16:35 Asia/Kolkata

- 2026-10-08 23:56 Asia/Kolkata — Task 9A yfinance probe: added a standalone,
  database-free `AsyncWebSocket` probe under `scripts/` and installed yfinance only in an
  ignored isolated environment (Python 3.13.7, yfinance 1.7.0, websockets 17.2); application
  dependencies and React were unchanged. Installed source declares `id`, `price`, `time`,
  `day_volume`, `last_size`, bid/ask and size fields, but does not declare timestamp units,
  per-trade volume semantics, or a unique trade ID. A default `TCS.NS`/`INFY.NS` 30-second
  run subscribed successfully at 1.328s, received zero messages/errors, closed cleanly, and
  exited at 30.276s. Because NSE was closed, the result is INCONCLUSIVE and historical REST
  was not used. Smallest safe next step is an open-session repeat before deciding any adapter
  mapping; timestamp conversion, cumulative-volume normalization, event identity, reconnect
  gaps and bounded queue behavior remain unresolved and must fail closed. No production
  yfinance or 021 adapter claim is made.

- 2026-10-08: Member 4 Strategy Callback Lock-Free Bounded Execution. Moved `StrategyRuntime.on_candle` execution in `Platform.tick` strictly outside `self.store.lock`. Added bounded thread pool execution (`BoundedStrategyExecutor`) with daemon worker threads, configurable timeout (`callback_timeout=0.5s`), and bounded concurrency (`Semaphore`). Timed-out subscriptions are durably quarantined (`enabled=0`, `STRATEGY_CALLBACK_FAILED` with `TimeoutError`) while healthy strategies continue uninterrupted. Implemented subscription run generation tracking: late callback completions after timeout, stop/re-enable, global stop, or kill are discarded with zero state or order mutations. Ensured candidate indicator state is only committed if originating run is still valid. Workers receive no store locks or broker authority. Documented trusted callback limits: threads provide latency isolation, not an arbitrary-code security sandbox. 226 passed / 1 PostgreSQL skipped; Ruff and format clean.
- 2026-10-07 21:25 Asia/Kolkata: Member 4 Advancements Integration. Completed pluggable strategy & candle interval registry (with RSI reversal strategy), market session hours & feed freshness gate coordination, standalone mock market data streaming feed API, and real-time SSE telemetry push. 173 tests passed / 1 PostgreSQL skipped; Ruff and TypeScript clean.

- 2026-10-07: Dashboard/account ownership integration. Dashboard access now requires a valid local session; registration assigns account identity and subscription mutations derive it server-side. Removed account setup controls and raw safety JSON, added responsive safety indicators, and verified desktop plus 390x844 layouts. 218 tests passed / 1 optional PostgreSQL skipped; Ruff and TypeScript clean.
- 2026-10-07: Member 2 Task 5 — Final Offline Broker Contract & Prototype Finalization. Defined authoritative Broker Adapter Contract in `docs/CONTRACTS.md`, added `tests/test_broker_adapter_contract.py` (12 focused tests covering Contracts A–K and 021 honesty), and verified contract parity with `Broker021Adapter` stubs. Offline Member 2 prototype tasks complete. 147 tests passed / 1 PostgreSQL skipped.
- 2026-10-07: Member 2 Task 4 — Prototype broker disconnect and recovery flow. Added explicit `disconnect()`/`reconnect()` lifecycle, `Platform.disconnect_broker()` / `Platform.reconnect_broker()`, HTTP routes `/api/broker/disconnect` and `/api/broker/reconnect`, Failure Lab scenario `disconnect_recovery`, and missed-fill/UNKNOWN recovery validation. 135 tests passed / 1 PostgreSQL skipped.
- 2026-10-07: Member 2 Task 3 — Lightweight broker update flow. Introduced canonical `BrokerUpdate` contracts and `OrderManager.process_broker_update`, deterministic mock event queue, API sync endpoint, and Failure Lab broker update scenario. 127 tests passed / 1 PostgreSQL skipped.
- 2026-10-07: Member 2 Task 2 — Prototype cancellation flow. Added `OrderManager.cancel()` with broker confirmation, partial cancellation, idempotency, terminal safety, and API endpoint `/api/orders/{id}/cancel`. 117 tests passed / 1 PostgreSQL skipped.
- 2026-10-07: Member 2 Task 1 — Execution state-machine audit and hardening. Authoritative legal transition policy (`LEGAL_TRANSITIONS`, `validate_order_transition`), terminal-state protection (preventing regressions from FILLED/REJECTED/CANCELLED), late execution evidence on CANCELLED orders preserved, filled quantity invariant enforcement, attribution validation on executions, and expanded audit logging. Suite: 108 passed / 1 PostgreSQL skipped; Ruff and TypeScript clean.
- 2026-10-07: Snapshot completeness now explicit (default False; mock attests True); missing/out-of-order/duplicate fills handled independently from positions. Migration 003 persists safety/marks/audit time; restart remains RECOVERING. 49 tests passed / 1 PostgreSQL skipped. No real provider guarantees inferred.
- 2026-10-07: RiskPolicy mapping now persists via risk service; API exposes configured limits, durable strategy halt and directional budgets. Shared decision fields added with defaults. SQLite upgrades to schema 2; PostgreSQL migration 002 packaged, not applied remotely. Suite: 36 passed / 1 PostgreSQL skipped; Ruff passed.
- 2026-10-07: P0 live server/API/frontend HTTP checks passed. Independent durable mock survives actual restart; Failure Lab shows partial fills, broker rejection and risk rejection. Suite: 27 passed, 1 optional PostgreSQL skipped. Ruff passed. CI added. `main` delivery authorized; `docs/design.md` previously removed as requested.
- Shared contracts -> candles -> three strategies -> risk reservation -> mock order -> fills -> accounting -> snapshot/dashboard.
- Reconciliation checks orders/fills/positions; missing attributed fills recovered through ledger.
- Partial-fill kill closes gate then verifies actual flat state.
- Durable local restart with retained external mock passes explicit reconciliation/resume tests.
- Initial deterministic safety/API suite: 20 passed.
- Member 4 integration: durable strategy controls -> stopped-strategy risk rejection; callback fault -> isolated quarantine; accepted idempotent ticks -> complete indicator warm-up -> completed 1m/5m candles -> EMA/mean/breakout signals -> exact-decimal API projection -> audit/dashboard. Rejected late/invalid ticks fail closed with durable evidence. Production PostgreSQL mode rejects replay demo seeding.
- Local PostgreSQL 18 application/test databases have migrations 001/002 applied; persistent-store startup and rollback-only integration behavior pass without production data.

## Current Integration State
- PostgreSQL centralized Store implementation and scoped additive migrations 001/002 are locally verified; remote Neon connectivity remains unverified.
- Requested Neon project muddy-tooth-14996153 / production intended, not yet verified linked.
- neon.ts and hello.ts match requested infrastructure policy; hello is not the trading backend.

## Failing Integration Tests
- None. Expanded SQLite plus local PostgreSQL checks: 36 passed with no skips; Ruff formatting/lint and TypeScript checks passed; npm audit found no vulnerabilities. Dashboard verified at narrow and 1440px breakpoints with no browser console errors. Remote Neon PostgreSQL is not verified.

## Contract Mismatches
- No confirmed 021 schema available; adapters intentionally unavailable.
- PostgreSQL requires migrations before application startup; no implicit schema creation.
- Local authenticated account ownership now gates the dashboard and subscription mutations; production identity-provider and live 021 reconnect contracts remain absent.

## Blockers
- Neon authentication/project access and an authorized isolated remote branch; sponsor 021 contract.
- An explicitly injected fresh broker still cannot match existing local history; default offline mock now persists independent evidence.
- Local PostgreSQL replay is supported only with an explicitly configured loopback
  `MOCK_BROKER_URL`; the standalone HTTP mock remains clearly distinct from the
  unconfirmed 021 adapter. Remote broker URLs cannot enable seeded replay.

## Next Integration Target
Validate Neon linking/schema inspection and repeat the locally verified additive migrations on an authorized isolated remote branch. In parallel, obtain the 021 market-data contract before implementing the live provider. Do not seed replay into production.

- 2026-10-07 16:05 Asia/Kolkata validation: pytest 24 passed / 1 skipped (no isolated PostgreSQL URL); Ruff check + format passed; npm run check passed; npm audit 0 vulnerabilities. No live Neon connectivity/deployment claim.

## External tooling status
2026-10-07 Member 3 P4: deterministic failure scenarios and safety evidence/risk controls wired through API/frontend. Verified snapshot status expires; historical certificates labeled explicitly. Tests 67 passed / 1 isolated PG skipped. No browser automation or live sponsor evidence claimed.

2026-10-07 Member 3 P3: bounded broker calls, dispatch evidence migration 004 in both stores, convergent verified kill with risk-authorized exits. No DB lock across network waits. Suite 57 passed / 1 PostgreSQL skipped; lint/format passed. Mock confirms virtual close semantics; real adapters default unconfirmed. P2 pushed as `80e612f`.

Neon CLI 8.0.11 installed. Requested project/branch not yet authenticated/linked. User requested current validated commits be pushed before continuing setup. No remote migration or seed has run.

## Latest Handoff
- 2026-10-07 16:03 Asia/Kolkata: commits `55beeb2` and `8dc8e34` pushed to `origin/bootstrap/safety-vertical-slice` before further Neon setup, as requested.
- Neon CLI 8.0.11 login launched browser and is awaiting user authentication. Link to requested production branch, skills/MCP setup, remote schema inspection/migration, connectivity and deploy are paused. No remote schema changes or production seed performed.
- Action needed: complete browser sign-in, then continue the requested Neon workflow. PostgreSQL implementation is locally tested only; isolated integration remains skipped.
- Dashboard telemetry now uses a persistent WebSocket snapshot stream with a bounded
  polling fallback. The transport reports backend changes but does not invent market
  activity when no ticks or fills are arriving.
- An explicit Run replay action can now start a bounded local HTTP-mock tick loop;
  kill, stop, and shutdown terminate it cleanly with thread joining. Ticks advance
  monotonically via `_simulation_cursor` across repeated batches, restarts, and symbols
  without overlapping or backwards timestamps. New ticks generate unique event IDs, while
  intentional repeat ticks retain IDs for idempotent deduplication. The stream is
  mock-only and never automatically restarts following recovery or reconciliation.
- Kill switch ordering verified and enforced: `Platform.kill` explicitly closes the execution
  admission gate and latches kill before waiting or joining the replay stream thread.
- Candle and market data policies documented in `docs/CONTRACTS.md` covering exact half-open
  UTC boundaries, per-tick volume accumulation, gap preservation (no invented candles),
  fail-closed late ticks and conflicting duplicates, and signal emission exclusively from closed candles.
- Strategy runtime lifecycle and interval correctness:
  Closed candles are routed strictly to strategies registered for that interval. `CandleBuilder.add_interval`
  is dynamically wired into platform strategy registration.
  Closed candles are processed at most once per strategy run (`(strategy_id, generation)`); duplicate
  and older candles are rejected before worker callback execution.
  Same-instance candidate state commits are serialized under `_state_lock` to prevent out-of-order
  callbacks from overwriting newer indicator states.
  Global stop, resume, kill, and broker recovery boundaries advance a monotonic `_global_epoch`,
  invalidating in-flight results even if the runtime is re-enabled before workers complete.
  Stopping or re-enabling a subscription increments run generation and completely resets warmup.
  `Platform.snapshot` and `StrategyRuntime.readiness_for` expose backend-derived sample count, required
  warmup, and readiness (`samples >= warmup`), with RSI reversal configured for 15 closed candles (14 price diffs).
  Kill deadline deduction verified: replay stream join time is deducted from the total kill deadline,
  and admission gate closure is strictly idempotent.
- Market session and execution hours correctness (Task 5):
  `MarketSession` converts timestamps to `Asia/Kolkata` (`ZoneInfo("Asia/Kolkata")`) before evaluating configured hours.
  Continuous trading hours use half-open interval `[09:15:00, 15:30:00)` IST (`09:15:00` is OPEN, `15:30:00` is CLOSED).
  Default `enforce_hours=False` is preserved for mock replay compatibility.
  When hours are enforced, missing timestamps (`None` without a clock) fail closed (`is_open() -> False`, `status_at() -> "CLOSED"`).
  State consistency preserved across `is_open()`, `status_at()`, `to_dict()`, and `Reliability.check_evidence()` (`HALTED`, manual `OPEN`/`CLOSED`, `AUTO`).
  Task 4 follow-up 1: Same-strategy callbacks serialize execution under `inst_lock` prior to copying working state, ensuring intermediate candle updates are never lost or computed concurrently from stale indicator states.
  Task 4 follow-up 2: Kill certificate elapsed time includes admission closure and replay join; exhausted deadline budgets return a truthful failure certificate (`status="FAILED", reason="KILL_DEADLINE_EXPIRED"`) without throwing `ValueError` from `Deadline`.
- Callback isolation and bounded shutdown (Task 5 Follow-up):
  Eliminated unbounded `executor.shutdown(wait=True)` in `StrategyRuntime.close()`, replacing it with pre-shutdown epoch invalidation and bounded non-blocking cancellation (`shutdown(wait=False, cancel_futures=True)`).
  Callback worker tasks are strictly isolated from SQLite, `Store`, broker authority, and runtime state mutation. Workers calculate candidate signals on working state copies and return candidate results to the control plane.
  The control plane validates and commits candidate results (`_enabled`, `_global_epoch`, `_subscription_generations`, `is_subscription_enabled`, `may_run`, candle start time monotonicity); timed-out and invalidated candidate results cannot mutate state.
  Same-instance serialization locks (`inst_lock`) are released boundedly upon callback timeout, preventing timed-out workers from retaining locks needed by `kill`, `set_enabled`, `close`, or healthy strategies. Stopping or halting a subscription provisions a fresh instance lock.
  Added regression coverage in `tests/test_strategy_execution_safety.py` confirming callback remains blocked while close returns in bounded time, late releases after store closure cause zero DB queries or state mutations, same-instance timeouts do not block controls or other strategies, and test workers are always released in `finally` blocks. Full test suite: 265 passed / 1 skipped; Ruff check and format clean.
- Member 4 Task 6 — Authenticated, Account-Scoped User Workflow & Telemetry Isolation:
  User workflow (`register/login -> subscribe -> start -> observe readiness/signals/P&L -> stop`) is fully authenticated and account-scoped server-side.
  Account identity is derived exclusively from verified server-side sessions (`engine.auth.verify_token`); client query params or payload account overrides are never trusted.
  Removed anonymous risk-budget fallback: `GET /api/risk/budgets` strictly requires session authentication and returns only the verified account's budgets (anonymous returns 401).
  Audited account-scoped snapshot output and eliminated all nested leaks:
    - Reconciliation reports: `broker_positions` and `unexplained_positions` filtered to `account_id`; `orders`, `unique_fills`, `open_orders`, and `duplicate_snapshot_fills` scoped to caller's counts; `unattributed_fills` reported as 0. Honest global verification flags (`verified`, `reason`, `observed_at`) are preserved.
    - Kill certificates: `broker_positions` dictionary filtered to only keys starting with `f"{account_id}/"`; `virtual_positions_flat` evaluated for caller's positions; `open_orders` scoped to caller's open count; honest global status (`status`, `elapsed_seconds`, `reason`) preserved.
    - Fill counters: `unique_applied`, `duplicates_ignored`, and `rejected_events` scoped strictly to the caller's account; `unattributed_in_last_verified_snapshot` sourced from verified snapshot accounts (null if unattributed fills exist or unverified).
- Member 4 Task 6 Final Follow-Up — Truthful Scoped Safety Evidence:
  Eliminated hardcoding of unattributed fills and historical kill rewrites. Sourced reconciliation counts from verified `accounts[account_id]` at `observed_at`; preserved historical kill certificate evidence without current-state substitution; preserved UNKNOWN/FAILED states; added tests for unknown attribution, failed kill uncertainty, immutable historical certificates, and leak-free scoped reporting. Full test suite: 273 passed / 1 skipped; Ruff check and format clean; TypeScript clean.
    - Unknown orders: filtered strictly by `account == user.account_id`.
    - Audit payloads: only events where `account == user.account_id` or `strategy` belongs to the user's subscriptions are returned; nested payloads with `broker_positions` are sanitized to strip other accounts.
  Subscription mutations (`POST /api/subscriptions/{id}/start` and `/stop`) enforce ownership: non-existent subscriptions return 404; attempts to mutate another account's subscription return 403 Forbidden without mutating state or exposing strategy details.
  Streaming telemetry endpoints (`GET /api/stream/telemetry` and `WebSocket /api/stream/ws`) require valid authentication before transmitting data.
  Streaming loops continuously revalidate tokens; on logout or session expiration, SSE streams terminate and WebSockets close immediately with code 1008 (`WS_1008_POLICY_VIOLATION`).
  Frontend UI invokes `clearStaleData()` on 401 or WS 1008 to clear tables, counters, feeds, and indicators, redirecting cleanly to `/login`.
  Team Ownership Alignment: Ram is Member 3 (risk, security, reliability, trading gates, kill switch). Akshat is Member 1 (accounting, ledgers, fills, positions). Member 4 owns market data, strategy runtimes, and user-scoped workflow.
  Platform-Wide Authorization Status: Platform-wide authorization is NOT complete. Ram (Member 3) must implement role-based operator authorization for remaining unprotected global mutation endpoints:
    `PUT /api/risk/policies/{strategy}`, `PUT /api/risk/strategies/{strategy}`, `POST /api/reconcile`,
    `POST /api/resume`, `POST /api/reduce-only`, `POST /api/kill/reset`, `POST /api/kill`,
    `POST /api/failure-lab/{scenario}`, `POST /api/broker/disconnect`, `POST /api/broker/reconnect`,
    `POST /api/broker/updates/sync`, `POST /api/orders/{order_id}/cancel`, `POST /api/market/session`,
    `POST /api/demo`, `POST /api/accounts`.
  Test suite: 272 passed / 1 skipped; Ruff check and format clean; TypeScript clean.

- Member 4 Task 7 — Deterministic Mock Demo Scenarios & Rehearsal Runner:
  Integrated clean-start deterministic rehearsal runner (`backend/demo_scenarios.py`, `scripts/rehearsal_runner.py`, `tests/test_demo_scenarios.py`) operating on isolated temporary SQLite and injected clocks (`ControllableClock`).
  Exercised 1m/5m candle building, warmup readiness, and simultaneous opposing strategy entries (`strat_mom` LONG, `strat_mr` SHORT) on a single account on `TCS`, plus 5m breakout entry (`strat_bo` BUY) after 2 completed 5m candles.
  Verified partial fills (via `broker.execute`), duplicate fill deduplication (`DUPLICATE_FILL_IGNORED`), broker rejections (`broker.reject_next`), risk position limits (`RISK_MAX_POSITION`), missed fill reconciliation recovery, restart recovery invariants (`Gate.RECOVERING` -> durable history preserved -> reconciled against broker truth -> `Gate.RUNNING`), emergency kill switch via `Platform.kill()` (verified `KillCertificate` with `status="SUCCESS"`, `elapsed_seconds < 10`, 0 open orders, 0 broker positions, all virtual positions flat), and unexplained drift fail-closed blocking without auto-fix.
  Documented replay dependencies (explicit periodic rehearsal step during accelerated replay to respect Ram's 5s broker freshness limit) and 4–5 minute demo walkthrough in `docs/DEMO_AND_DEBUG.md`. Full test suite: 282 passed / 1 skipped; Ruff check and format clean; TypeScript clean.

- Member 4 Task 8 — Operational UX & Final Member 4 Handoff:
  Completed operational UX incremental enhancements in `frontend/index.html` preserving existing vanilla architecture:
  - Subscribed strategy cards (`#strategy-cards-grid`) with real lifecycle states (`RUNNING`/`READY`/`STOPPED`/`HALTED`), warmup progress (`samples / warmup`), position quantities, net P&L, charges, and interactive Start/Stop controls.
  - Market data & feed status strip (`#feed-status-strip`) with explicit `MOCK / REPLAY` badges, synthetic replay descriptions, session status (`OPEN`/`CLOSED`, `09:15 – 15:30 IST`), freshness, and tick counters.
  - Human-readable closed candles table (`#candles-table-body`) and platform risk decisions feed (`#risk-decisions-feed`) displaying sequence numbers and backend rejection reason codes (`RISK_MAX_POSITION`, etc.).
  - Bounded correlated execution timeline (`#execution-timeline`) correlating `Candle → Intent → Risk → Order → Fill → Financial Result` with truthful reporting of unlinked or missing evidence (no invented timestamps or synthesized stages).
  - Historical kill switch certificate record (`#kill-cert-card`) kept strictly immutable and visually distinct from current live safety evidence.
  - Preserved Ram's (Member 3) safety and risk budget panels and Akshat's (Member 1) accounting ledger sums.
  - Immediate client-side data purging on logout or token expiration (`clearStaleData()`); resilient reconnection indicators on backend failure.
  - Corrected Task 7 position arithmetic in `backend/demo_scenarios.py` using actual ledger aggregate sums (`p.ledger.aggregate().get((acc, "TCS"), 0)`).
  - Validated across all 282 regression tests, 7 rehearsal runner scenarios, and linters. Full Member 4 scope (Tasks 1–8) complete.

- 2026-10-08 USP integration: added authenticated account-scoped control-plane boundaries, explainable risk evidence, durable account net/gross and LIMIT-price policy, conservative Safety Proof, reconciliation delta/recovery projection, trace correlation, Failure Lab V2, Kill Certificate V2, bounded metrics, isolated 19-case SafetyBench and responsive operational UI. Additive SQLite migrations 008-011 and PostgreSQL migrations 007-010 are packaged. Regression: 280 passed / 1 PostgreSQL integration skipped; Ruff and frontend syntax clean. Live 021 and remote Neon remain blocked/unclaimed.
- 2026-10-08 React migration: synced latest main, preserved account isolation/deadline/callback fixes, and replaced legacy pages with a modular React/Vite SPA. Added protected routes, central cookie API client, one authenticated WebSocket provider, operational/USP pages, truthful safety label tests, FastAPI SPA fallback, and multi-stage Docker delivery. Regression: 298 Python passed / 1 PostgreSQL skipped; 8 frontend tests, ESLint, Ruff, and production build passed. Live 021 and remote Neon remain blocked/unclaimed.
- 2026-10-08 Safe merge of `codex/usp-evidence-layer` (7901702) into `main` (ff1848e):
  - Base commit: `27310237143fd0690d89fe245da9b0c0bc54b3e7`.
  - Preserved Member 4 Tasks 1–8: rehearsal runner (`backend/demo_scenarios.py`, `scripts/rehearsal_runner.py`, `tests/test_demo_scenarios.py`), standalone operational dashboard (`frontend/static_dashboard.html`), monotonic replay streams, authenticated account scoping, and honest non-bypassable safety state machines.
  - Preserved USP evidence layer: explainable risk rules, account policies, conservative Safety Proof, server-built execution traces, Failure Lab V2, Kill Certificate V2, bounded metrics, isolated SafetyBench, and React/Vite SPA (`frontend/src/` with production build in `frontend/dist/`).
  - Resolved material conflicts semantically:
    - `docs/DEMO_AND_DEBUG.md`: Combined overview linking deterministic scenarios, debugging guide, and React operational dashboard routes.
    - `frontend/index.html`: Maintained as canonical Vite/React SPA HTML shell; preserved Task 8 monolithic static dashboard in `frontend/static_dashboard.html`.
    - `conftest.py`: Added root test harness ensuring `tests/` and `usp_helpers` resolve cleanly across all test environments without package shadowing.
  - Regression validation:
    - Python tests: 311 passed / 1 skipped (PostgreSQL).
    - Vitest frontend tests: 11 passed across 4 test suites.
    - Deterministic rehearsal runner: all 7 scenarios passed with zero errors.
    - Ruff check, Ruff format, ESLint, and `npm run check` (TypeScript) all clean.
    - Added merge integrity regression tests in `tests/test_merge_integrity.py`.
    - Browser testing: live desktop/mobile browser validation pending automated driver execution.

- 2026-10-08 Safe merge of `codex/usp-evidence-layer` (1610ec2) into `main` (c413afe):
  - Merged 3 additional commits: `61157fe` (compact strategy budget evidence), `5b5b71c` (vertical strategy budgets), and `1610ec2` (vertical reconciliation center).
  - Resolved non-overlapping progress docs in `docs/progress/MEMBER_4.md`.
  - Rebuilt production SPA assets in `frontend/dist/`.
  - Full regression validation:
    - Python tests: 311 passed / 1 skipped (PostgreSQL).
    - Vitest frontend tests: 14 passed across 4 test suites.
    - Deterministic rehearsal runner: all 7 scenarios passed with zero errors.
    - Ruff check, Ruff format, ESLint, and TypeScript (`npm run check`) all clean.



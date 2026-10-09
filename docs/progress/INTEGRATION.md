# Integration Progress

## 2026-10-09 — Official 021-03 gap-only fixture integration

Work started from `main` `2490e82a4f6c1dc60ab8cc8d61f0523899dc80de` after fetch; `dev` diverged and was not merged. A temporary local feature branch was created during inspection, then the uncommitted work was moved back to `main` at the owner's explicit request before commit. Before push, remote main advanced to `da609f4`; the checkpoint was normally rebased, preserving upstream multi-stock DEC-030 and assigning this change DEC-031. Added the supplied canonical contract/blueprint, strict 021 price/quantity/instrument/response and TC1/TC3/TC4/TC8 normalization, a live-disabled adapter shell, and isolated durable-once mandatory strategy policies. Focused evidence: `29 passed`; affected regression: `99 passed`; post-rebase Python suite: `408 passed, 1 isolated PostgreSQL skipped`; seven mock rehearsals passed with measured mock kill `0.17s`. Ruff, format, docs links and diff checks passed. No live REST/WS, credentials, sandbox writes, PG, migration, fees, or kill claim. Runtime/provider composition and sponsor-dependent identity/history semantics remain blocked.

## Current Status
- Phase: integrated mock/replay hardening with optional supervised Yahoo quote evidence
- Status: BLOCKED
- Last updated: 2026-10-09 Asia/Kolkata

## 2026-10-09 — Subscription-free Yahoo quote visibility

- Fixed a verified display gap where Yahoo ticks advanced aggregate telemetry but
  an authenticated trader with no strategy subscriptions saw zero stocks. The
  account projection correctly removed subscription-scoped candles, while the UI
  incorrectly used subscriptions as its only symbol inventory.
- Yahoo telemetry now publishes the configured provider symbols, canonical symbol
  mappings and one bounded latest-accepted quote row per configured symbol. Prices
  remain decimal strings; raw timestamps are retained; missing quotes remain null;
  volume remains unavailable. The UI shows these rows independently from completed
  candles and derives its filter from provider, quote, candle and subscription
  symbols.
- Account scoping for strategies, orders, positions and financial evidence is
  unchanged. No replay mixing, backfill, feed failover, trading resume or financial
  calculation was added.
- Validation: 404 backend tests passed with one environment-gated PostgreSQL skip;
  58 focused backend tests and 12 focused React tests passed; all 41 React tests,
  Ruff, ESLint, Vite production build, TypeScript and documentation checks passed.
  The already-running server requires a restart to load this uncommitted change.

## 2026-10-09 — Multi-stock branch integration

- Integrated the branch's authenticated atomic `POST /api/subscriptions/batch`
  orchestration while retaining one strategy instance per symbol. Normalization,
  collision preflight, ownership, indicator state, failure quarantine, risk,
  execution attribution and financial evidence remain per instance and symbol.
- Integrated the React multi-stock entry/filter workflow, including accessible
  quick-select demo shortcuts, deterministic ID previews, one batch request,
  pending/error evidence and explicit all-or-nothing conflict messaging.
- The branch does not implement a Yahoo adapter or automatic Yahoo-to-mock
  failover. Existing replay already discovers every enabled subscription symbol,
  so it remains the explicit mock fallback selected on a clean process start.
  A stale/disconnected Yahoo session stays fail-closed; it does not mix synthetic
  ticks into Yahoo candles, fabricate backfill, or automatically resume trading.
- Uncommitted merged-tree validation: 403 backend tests passed with one
  environment-gated PostgreSQL skip; 85 focused Yahoo/multi-stock/operator/
  Failure Lab tests passed; 40 React tests passed; Ruff lint/format, ESLint,
  Vite production build, TypeScript, documentation links and all seven
  deterministic safety rehearsals passed. Browser automation was not rerun for
  this merge.

## 2026-10-09 — Task 9B optional Yahoo external market data

- Replay remains default. Explicit opt-in config attaches a supervised yfinance provider with a fixed `TCS.NS -> TCS`, `INFY.NS -> INFY` mapping and refuses replay/Yahoo timeline mixing or non-mock execution.
- Yahoo `id`, positive finite `price`, and plausible decimal-string millisecond `time` normalize into canonical LIVE ticks through `Platform.tick` only. Raw and normalized timestamps, source, and unavailable-volume evidence are preserved. `day_volume`/`last_size` are not treated as per-trade quantity; generated duplicate hashes are not exchange IDs.
- The bounded process/queue lifecycle fails closed on startup timeout, overflow, malformed updates, disconnect and stale gaps, with bounded reconnect and forced child cleanup. It never auto-resumes trading. Telemetry/UI truthfully label `YAHOO EXTERNAL QUOTES / MOCK EXECUTION` and quote-derived unavailable candle volume.
- The optional `yahoo` extra pins the probed yfinance 1.7.0 and resolved websockets 15.0.1 under the existing `>=13,<16` application constraint; ordinary installs remain unchanged.
- Disposable-SQLite, trading-disabled 30-second live smoke received 26 TCS/INFY updates, accepted all 26, emitted no orders, retained raw/normalized last time `1791522597000` / `1791522597`, and shut down with no orphan. An initial startup deadline caused a recorded fail-closed termination before the bounded reconnect streamed; the final gate correctly remained `UNCERTAIN` and no automatic resume occurred.
- Yahoo remains sampled external quote evidence, not verified complete exchange ticks. Volume semantics, unique provider trade identity, gap backfill and 021 symbol/price-source/freshness compatibility remain unverified. No production database or real broker was used.
- Initial Task 9B validation covered 19 focused Yahoo tests and 57 combined market/candle/replay/Member 4 tests; the final verification below resolves the stale frontend assertion and supersedes that intermediate result.

### Task 9B final verification

- Replaced the obsolete source-string assertion with behavior-level React coverage: populated state is cleared on logout/account change, HTTP 401 during reconnect, and WS 1008; sockets/timers do not retry after terminal invalidation. Existing backend restart safety coverage remains.
- Lifecycle instrumentation isolated startup costs. The measured first-attempt path was 0.474s to worker/import start, 2.536s through yfinance import, and 3.897s through connection/subscription. A later long capture subscribed at 3.444s. Evidence does not support widening the bounded 8-second startup timeout, so fail-closed semantics remain unchanged.
- A 225.027-second isolated-SQLite capture accepted 384 TCS/INFY quote updates, then shut down in 225.860 seconds with no orphan. It closed six 1-minute candles and two 5-minute candles, all quote-derived with unavailable volume. The initial five-minute bucket `[1791523200,1791523500)` was partial because observation began in `[1791523320,1791523380)`; there was no reconnect/error evidence in this capture and no gap backfill was attempted.
- Browser verification used the real FastAPI/Vite dashboard. It displayed `YAHOO EXTERNAL QUOTES / MOCK EXECUTION`, current raw/UTC event/receipt timestamps, advancing counts, `Unavailable` candle volume, `UNCERTAIN`, completed 60/300-second TCS/INFY candles, and no orders/fills. A deliberate isolated child termination displayed `Not connected` and the exit evidence; reconnect restored `Connected` and counts advanced from 130 to 138 while the gate stayed `UNCERTAIN`.
- Final validation: 335 backend tests passed with 1 environment-gated PostgreSQL skip; all 30 React tests passed; ESLint, Vite production build, Ruff check/format, and `git diff --check` passed.

Exact PowerShell commands for the real isolated dashboard:

```powershell
Set-Location C:\Users\dyara\Syrus7_SarvasV

$task9bVenv = Join-Path $env:TEMP 'algoshield-task9b-dashboard-venv'
py -3.13 -m venv $task9bVenv
& "$task9bVenv\Scripts\python.exe" -m pip install -e '.[yahoo]'
npm --prefix frontend run build

$env:PYTHONPATH = (Get-Location).Path
$env:DATABASE_URL = ''
$env:MOCK_BROKER_URL = ''
$env:ALGOSHIELD_DB = Join-Path $env:TEMP 'algoshield-task9b-dashboard.db'
$env:ALGOSHIELD_MARKET_DATA_PROVIDER = 'yahoo'
$env:ALGOSHIELD_YAHOO_SYMBOLS = 'TCS.NS,INFY.NS'

& "$task9bVenv\Scripts\python.exe" -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8765 --workers 1
```

Open `http://127.0.0.1:8765/register`, create a disposable local user, then inspect `/market-data` and `/orders`. Do not use Replay in Yahoo mode. Stop the one-worker server with `Ctrl+C`.

## 2026-10-09 — Bounded yfinance probe follow-up

- Hardened only the standalone Task 9A probe and focused tests: a parent process now supervises the
  yfinance worker across import/connect/subscribe/listen/cleanup, terminates and reaps a stuck child,
  preserves flushed incremental evidence, and always emits a final report. Unavailable message counts
  remain null rather than being inferred as zero.
- Current isolated versions are Python 3.13.7, yfinance 1.7.0, and websockets 15.0.1; no dependency
  changes were made. Five focused offline tests passed, including hanging connection and hanging
  cleanup cases; Ruff check/format and `git diff --check` passed.
- A 30-second live TCS.NS/INFY.NS run completed in 31.259904 seconds with normal cleanup and a reaped
  exit-code-0 child. Subscription returned at 4.339743 seconds and 42 decoded price messages arrived
  (INFY.NS 23, TCS.NS 19), so the independent NSE result is **STREAM_CONFIRMED**. BTC-USD was not
  needed.
- Runtime messages exposed `price`, decimal-string `time`, `day_volume`, and usually `last_size`.
  Raw times such as `1791521394000` are magnitude-plausible Unix milliseconds near receipt time, but
  the unit remains an inference. Volume semantics and unique event identity remain unresolved; no
  field is asserted to be per-trade quantity or a unique trade ID.
- This evidence does not implement or approve a production adapter. Dashboard integration remains
  pending, and no React, application, database, order, strategy, or broker code changed.

## 2026-10-09 — React contract, telemetry, and action-rejection verification

- Aligned Overview and Safety Proof with verified backend fields (`gate`, `health`, `verdict`,
  `generated_at`, `invariants`) and aligned trace cards with the actual trace/event envelope.
- Restored strategy accounting display by joining account-scoped subscriptions to canonical position
  records on account, strategy instance, and symbol. The UI now renders backend `net_quantity`,
  `net_pnl`, `charges`, and readiness evidence without recomputing accounting or coercing missing values
  to zero. Decimal strings remain strings through display formatting.
- Hardened the single TelemetryProvider lifecycle: capped transient initial-state retry, one active
  socket/timer generation, immediate old-account eviction, stale-result suppression, and terminal
  invalidation without retry for HTTP 401 and WebSocket 1008.
- Added pending/error/duplicate-submit handling for replay, reconcile/resume, kill, subscriptions,
  Failure Lab, and SafetyBench. Failure Lab now states that it mutates the current mock platform and
  requires confirmation; backend behavior is unchanged.
- Validation: 28/28 Vitest tests passed across 6 files, ESLint passed, and the Vite production build
  passed. Browser checks against an isolated local SQLite instance covered desktop login/replay,
  strategies/orders financial evidence, rejected subscription handling, Failure Lab wording, a
  375×812 responsive route, and logout; no browser console warnings/errors were observed. Backend tests
  were not rerun because no backend files changed.
- No routes/navigation changed, so `docs/DEMO_AND_DEBUG.md` was not changed. No application dependencies,
  production database, broker/risk/accounting/callback/kill semantics, or live-feed code changed.
- Remaining backend work is explicit: operator authorization, complete multi-account security,
  cross-account reconciliation leakage, and unscoped global-action responses. These cannot be repaired
  by frontend filtering. Live 021 and market-feed integration remain absent and must not be inferred
  from this frontend verification.

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

- 2026-10-09 DEC-026 remediation on `dev`:
  - Audited base: `b0930c52056f175539e8fe9be7a1fabd2cd075eb`.
  - Implementation/research integration commit: `dd21746051119edf58fbdd85f333d54c67fe8260`.
    During the session this commit was authored and published to `origin/main`
    by `acchasujal` outside this agent's git operations; this agent did not push
    main. The follow-up evidence/runbook commit targets only `origin/dev`.
  - Added durable explicit operator grants, offline SQLite provisioning, shared
    nested account response scoping, strict trace ownership, and generic domain
    error responses. Ordinary users retain owned controls and cannot mutate
    global state. Mock fault/benchmark operations require operator authority and
    the existing isolated-mock guard.
  - Added SQLite migration 012 and packaged PostgreSQL migration 011. No prior
    migration changed. SQLite upgrade/provision/restart/revoke paths are verified.
    PostgreSQL remains skipped without an isolated test URL.
  - Replaced the obsolete Python source-string telemetry assertion with existing
    behavioral Vitest coverage for logout/account changes, HTTP 401 and WS 1008;
    backend restart/lifecycle coverage remains.
  - Final validation: Python **351 passed / 1 PostgreSQL skipped** in 48.98s.
    Vitest **28 passed in 6 files**; ESLint, Vite build, root TypeScript,
    Ruff check/format and all 7 rehearsals passed. Node 23.6.0 emitted package
    engine warnings; use supported Node 24.15+ for release validation.
  - No 021 sandbox, remote Neon, production database or browser-driver access.
    No lockfile or generated frontend artifact changed.

## 2026-10-09 (Asia/Calcutta) — DEC-027 targeted Round 2 integration

Start `dev`: de126deb3af6fb26e6142ace54515fc2f2d9a4be, tracking origin/dev.
Implementation: **89ea651990383ee640207a0bbebf85f10523e386**. Checks below ran
against the exact source/test content committed there; only docs changed after
the full run. Fresh fetch retained origin/main dd21746 and local main 8e5ee50;
no main mutation/merge/push. A new unrelated feature/multi-stock-strategies remote
appeared on final fetch and was not integrated. Member patches remain unavailable.

Initial work included the earlier exploratory test and untracked research/audit.
The four newly supplied member reports were read, preserved verbatim and adopted
only where dev evidence showed gaps. No wholesale member branch merge. The
ROUND2_RESEARCH_UPDATE backup was externally checksum verified before work.

| Feature | Status / owner | Next |
|---|---|---|
| Zero-fill rejection and broker identity collisions | VERIFIED IMPLEMENTED, Member 2 | Real provider mapping depends on sponsor contract |
| Origin, versioned password, login limiter/headers/audit | VERIFIED IMPLEMENTED, Member 3 | Deployment TLS/secure cookie/identity/ingress verification |
| Filled/requested and candle-linked signal display | VERIFIED IMPLEMENTED, Member 4 | Browser-driver smoke |
| Decimal ledger, risk/kill/UNKNOWN/recovery/candles/callback bounds, DEC-026 | VERIFIED EXISTING, Members 1–4 | Preserve; external fixture validation |
| Correction/bust and later fee revisions | DEFERRED — DEPENDENCY, Members 1/2 | Define authenticated event semantics; no speculative adjustments |
| PostgreSQL/021 | UNVERIFIED / DEFERRED — DEPENDENCY | Explicit isolated DB and sponsor sandbox evidence |

Changed production: execution transition; mock collision check; API Origin and
login handling; shared auth/KDF and browser_security helper; config and .env.example;
Docker disables forwarded header trust; React Orders/Strategies evidence. No
financial formula, candle strategy, migration, dependency or lockfile change.
Tests: broker updates (3 new cases), adapter contracts (2 providers), round2
security (16 cases), React evidence (2 cases). Conftest supplies a trusted browser
Origin to existing workflows; negative security tests override it explicitly.

Environment: Windows PowerShell, Python 3.13.1, Node 23.6.0, npm 10.9.2.
Node 23 remains outside several locked package engine declarations; no dependency
installation/change was performed in this round. Only isolated SQLite/mock/replay.

| Executed command | Exact result |
|---|---|
| python -m pytest -q -p no:cacheprovider --basetemp=data/round2-baseline --tb=short | 351 passed, 1 skipped; 85.85s (before new tests/code) |
| python -m pytest -q tests/test_broker_updates.py -k authoritative --basetemp=data/round2-red-fixed --tb=short | Before fix: 1 failed, 1 passed; genuine OPEN rejection defect only |
| python -m pytest -q tests/test_round2_security.py --basetemp=data/round2-security-red --tb=short | Before fix: 9 failed, 5 passed |
| npm.cmd --prefix frontend run test -- --run src/test/round2Evidence.test.jsx | Before display patch: 2 failed |
| python -m pytest -q tests/test_broker_adapter_contract.py -k collision --basetemp=data/round2-identity-red --tb=short | Before collision fix: 2 failed |
| Same collision selection, --basetemp=data/round2-identity-green | 2 passed, 22 deselected |
| python -m pytest -q tests/test_round2_security.py tests/test_broker_updates.py tests/test_auth.py --basetemp=data/round2-focused --tb=short | 29 passed, 14.45s |
| python -m pytest -q tests/test_round2_security.py tests/test_broker_updates.py tests/test_execution_state_machine.py tests/test_cancellation.py tests/test_operator_authority.py --basetemp=data/round2-cross --tb=short | 95 passed, 47.75s |
| python -m pytest -q -p no:cacheprovider --basetemp=data/round2-final --tb=short | **372 passed, 1 PostgreSQL skipped, 128.46s** |
| python -m ruff check . | Passed |
| python -m ruff format --check . | Initial check identified 2 touched files; after formatting: passed, 95 files already formatted |
| npm.cmd --prefix frontend run test | **30 passed, 7 files**, 16.57s (baseline 28/6 files) |
| npm.cmd --prefix frontend run lint | Passed |
| npm.cmd --prefix frontend run build | Passed; 37 modules, ignored assets only |
| npm.cmd run check | Passed |
| python -m scripts.rehearsal_runner (PYTHONIOENCODING=utf-8) | **7/7 passed**; observed mock kill SUCCESS 0.18s |
| python scripts/check_docs.py | Before 42 / after 47 Markdown files; zero broken local file links |
| git diff --check before research staging | Passed |
| git diff --cached --check after research staging | Reports pre-existing hard-break trailing spaces/EOF blank lines in verbatim member reports and archived USP proposal; preserved intentionally |
| git diff --check de126de HEAD excluding raw member reports and docs/archive/2026-10-09 | Passed for authored code/docs/redirects; originals retain source formatting |
| Staged artifact/credential-pattern review | No DB/env/generated/private-key/credential-URL findings; no migration or lock changes |

PostgreSQL skipped because no explicitly isolated test URL was configured; no
production/Neon access, schema mutation or sandbox execution. Do not treat mock
charges, corrections containment or kill latency as live 021 certification.

Documentation: DEC-027 appended; current authority/security/contracts/traceability/
testing/backlog and relevant member handoffs synchronized. Four historical files
were moved with git mv into docs/archive/2026-10-09 with original-path redirects
and repaired relative links. Inventory is in archive/README; research reports and
all decision/progress history retained. Startup no longer mandates member logs.

Residual risks: process-local limiter resets on restart and proxy peers may share
capacity; origin does not authenticate nonbrowser clients; production TLS/secure
cookies/identity/audit retention/public-registration limits need deployment work.
Real scoped provider mapping, corrections/late fees require sponsor evidence.
Ledger caching remains deferred pending measured workload. Browser smoke is
UNVERIFIED. Next three tasks are the sponsor contract, isolated PG validation and
deployment/browser validation recorded in IMPLEMENTATION_DELTA.

Post-commit security check at 89ea651: `python -m pytest -q
tests/test_round2_security.py --basetemp=data/round2-committed-security --tb=short`
passed **16 tests in 8.50s**. Research whitespace is a source-formatting note,
not a product regression; no original research text was rewritten to hide it.

Documentation/research commit: 6a15db172725de23f887c170cfc22c0061101d92.
Final delivery adds only this evidence clarification; no production change.




## 2026-10-09 ? Safe main promotion and direct-push workflow (DEC-028)

Validated dev baseline: 4782ca17ddc209e4543707375d18e5c28f80ff46. Isolated linked worktree preserves the original checkout and its four member-report deletions. Remote main before promotion: dd21746051119edf58fbdd85f333d54c67fe8260; after normal fast-forward push: 63266eb3aab1dfaa0c3934bae744d459df2184c4. No migrations, provider behavior or future member features changed.

Fresh Windows evidence: Python 3.13.1, Node 23.6.0, npm 10.9.2. Initial setup attempt: 351 Python passed, 3 failed, 1 skipped, 18 errors (missing SPA/temp access); unavailable frontend dependencies. After dependencies were reused and SPA built, `python -m pytest -q -p no:cacheprovider --basetemp=.pytest-promotion-retry --tb=short`: 372 passed, 1 skipped, 75.39s. PostgreSQL opt-in was skipped; no production database was touched. Frontend test: 30 passed / 7 files, 11.46s; frontend lint/build, Ruff check/format (95 files) and root TypeScript check passed. UTF-8 `python -m scripts.rehearsal_runner`: seven mock scenarios passed; measured mock kill 0.12s. Local Node engine warnings remain a reproducibility limitation.

Old GitHub workflow failed because pytest preceded SPA build. Commit 63266eb repairs that order, validates frontend and rehearsals, and triggers on pushes only. [GitHub CI](https://github.com/CMPN-CODECELL/Syrus7_SarvasV/actions/runs/37885956412/job/113675898318) succeeded on every step with Node 22. [PR #1](https://github.com/CMPN-CODECELL/Syrus7_SarvasV/pull/1) was closed without merge after the owner requested direct pushes. Protection/rules inspection returned HTTP 403; no permission grants or server settings were changed. A successful normal push proves this credential could push, not that every team account has write access.

The separate documentation integration adds a single four-member execution plan and fresh requirement/module evidence. Real 021, isolated PG, deployment proxy/Origin configuration and current React browser smoke remain unverified. Legacy browser selectors need a future task. Unrelated feature/multi-stock-strategies was not merged. Historical source Markdown whitespace is retained; generated files and local deletions are excluded from commits.

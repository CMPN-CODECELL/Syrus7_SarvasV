# Member 4 Progress

## Ownership
Market Data & Strategies; canonical responsibilities: ../TEAM_OWNERSHIP.md, Member 4.

## Current Status
- Phase: Member 4 mock/replay implementation complete; live provider integration pending
- Current task: await authoritative 021 feed contract and production identity-provider integration
- Status: BLOCKED
- Last updated: 2026-10-08 23:56 Asia/Kolkata
- 2026-10-07 integration pass: merged published Member 2/3 persistence, durable risk policies, recovery/freshness gates, bounded broker calls, kill convergence and failure-lab APIs into the Member 4 branch. Preserved the Member 4 strategy indicators, durable subscription controls, callback quarantine, symbol-scoped tick dedupe and dashboard. Combined suite: 89 passed, 1 skipped by default; isolated local PostgreSQL integration: 1 passed after applying migrations 001-005. Ruff check/format pass.
- 2026-10-07: gated the dashboard behind the durable local session, removed account-ID entry from registration/dashboard/subscription controls, derived strategy ownership from the verified session, replaced raw safety JSON with compact evidence indicators, and verified the strategy form at a 390x844 mobile viewport with no page overflow or browser console errors. RSI reversal is the default form selection. Validation: 218 passed / 1 optional PostgreSQL skipped; Ruff and TypeScript checks pass.

## Completed
- 2026-10-07: Minimum P0 wiring by Member 3: account/subscription forms, candles/orders/partial/rejection evidence, backend-unavailable UI and Failure Lab HTTP actions. Replay restart IDs remain unique. 27 tests pass, 1 PostgreSQL skipped; live server/API/frontend HTTP 200 verified.
- 2026-10-07 Asia/Kolkata: Replay raw ticks, UTC 1m/5m buckets, three candle callbacks, subscriptions, FastAPI endpoints and backend-fed dashboard. Files: backend/market_data/candles.py; backend/strategies/runtime.py; backend/api.py; frontend/index.html. Tests: initial safety suite 20 passed, including mandatory S1-S7. Result: offline vertical slice functional; live 021 incomplete.
- 2026-10-07 16:39 Asia/Kolkata: completed Member 4 mock/replay scope on `codex/member4-complete`. Added 3/5 EMA momentum, five-period mean reversion, 5-minute range breakout, durable subscription start/stop, risk-enforced stopped state, callback fault quarantine, bounded symbol-scoped tick dedupe, persisted signal/error evidence, normalized APIs, production replay guard and responsive light/gold dashboard. Files: backend/market_data/candles.py; backend/strategies/runtime.py; backend/api.py; backend/platform.py; backend/risk/gateway.py; backend/shared/store.py; backend/shared/migrations/002_subscription_state.sql; frontend/index.html; tests/test_member4.py. Commits: `5da0915`, `41678c4`. Result: 31 passed, 1 isolated-PostgreSQL test skipped; Ruff check/format passed; browser verified narrow and 1440px layouts with no console errors.
- 2026-10-07 16:58 Asia/Kolkata: enforced a complete five-candle warm-up for both one-minute strategies after process or subscription restart and made API candle/position Decimal fields conform to the documented JSON-string contract. Files: backend/strategies/runtime.py; backend/platform.py; tests/test_member4.py. Commits: `08a6aba`, `159e9ae`. Result: 33 passed, 1 isolated-PostgreSQL test skipped; Ruff check/format and TypeScript checks passed.
- 2026-10-07 16:59 Asia/Kolkata: made duplicate tick handling idempotent for latest marks and P&L, and added sanitized durable audit evidence when invalid or late market data fails closed. Files: backend/market_data/candles.py; backend/platform.py; tests/test_member4.py. Commits: `58fe87d`, `7f52024`. Result: 35 passed, 1 isolated-PostgreSQL test skipped; Ruff check/format and TypeScript checks passed; npm audit found no vulnerabilities.
- 2026-10-07 17:14 Asia/Kolkata: created isolated local PostgreSQL application/test databases, applied migrations 001/002, verified persistent-store startup and enabled the rollback-only PostgreSQL integration test. Files: scripts/setup_local_postgres.sh; .env.example; README.md; docs/DECISIONS.md; docs/TESTING.md. Result: 36 passed with no skips; Ruff check/format and TypeScript checks passed.
- 2026-10-07 18:00 Asia/Kolkata: linked remote Neon project `soft-glade-57602806` (branch `production`), installed Neon agent skills and MCP server, applied `neon.ts` deployment policy via CLI, and successfully applied all additive migrations (001–005) into the `algoshield` schema on PostgreSQL 18.6. Connection string kept in ignored `.env.local`. Test suite continues passing: 89 passed / 1 skipped.
- 2026-10-07 21:25 Asia/Kolkata: Completed Member 4 advanced features on `feature/member4-advancements`:
  1. Pluggable Strategy & Candle Interval Registry: Added `register_strategy()` and `list_registered()` in `StrategyRuntime`, 4th built-in `rsi_reversal` strategy (14 periods, oversold BUY < 30, overbought SELL > 70 with 15-candle warmup), configurable candle intervals on `CandleBuilder` with `add_interval()`, `GET /api/strategies` endpoint, and dashboard strategy dropdown.
  2. Market Session Hours & Feed Freshness Gate Coordination: Implemented `MarketSession` in `backend/market_data/session.py`, coordinated with `Reliability.check_evidence()` to emit `RISK_MARKET_HALTED` / `RISK_MARKET_CLOSED` cleanly without false staleness trips. Added `GET/POST /api/market/session` and snapshot state.
  3. Standalone Mock Market Data Streaming Feed: Implemented `backend/market_data/mock_feed.py` with `create_mock_feed_app()`, `/health`, `/ticks`, `/ticks/batch`, `/replay/demo`, `/candles`, and `/stream/ticks` (SSE) for external feed simulation mirroring Member 2's Mock Broker API.
  4. Real-Time UI Telemetry Push: Added `GET /api/stream/telemetry` SSE stream in `backend/api.py` and `EventSource` in `frontend/index.html` with polling fallback.
  Test suite: 173 passed / 1 PostgreSQL skipped; Ruff check and TypeScript check clean.
- 2026-10-07: Fixed replay wiring through the HTTP mock broker. The API now selects
  `HTTPMockBrokerAdapter` from `MOCK_BROKER_URL`, permits replay with PostgreSQL only
  for loopback mock URLs, and auto-executes simulated fills through the same broker
  boundary. Added an end-to-end HTTP replay test; full suite: 219 passed / 1 skipped.
- 2026-10-07: Replaced dashboard telemetry polling with a WebSocket snapshot stream
  (`/api/stream/ws`) and reconnecting polling fallback. The existing SSE endpoint is
  retained for compatibility; browser state now receives backend snapshots over a
  persistent connection. Added WebSocket endpoint coverage.
- 2026-10-07: Added explicit-action continuous local replay for the HTTP mock broker.
  After Run replay, synthetic ticks continue through the normal strategy/risk/order
  path and stop on kill or process shutdown; no live/021 source is implied. Added
  stream continuation coverage.
- 2026-10-08: Fixed strategy callbacks blocking the control-plane lock. Moved
  `StrategyRuntime.on_candle` execution in `Platform.tick` outside `self.store.lock`.
  Added bounded thread pool execution (`BoundedStrategyExecutor`) with daemon worker
  threads, configurable timeout (`callback_timeout`), and bounded concurrency (`Semaphore`).
  Implemented durable quarantine on callback timeout (`enabled=0`, `STRATEGY_CALLBACK_FAILED`
  with `TimeoutError`), allowing healthy strategies to continue uninterrupted. Introduced run
  generation tracking per subscription; late callback completions after timeout, stop/re-enable,
  global stop, or kill are discarded with zero state or order mutations. Ensured candidate
  indicator state is only committed if the originating run is still valid. Documented trusted
  callback limits: threads provide latency isolation, not a security sandbox for arbitrary
  untrusted bytecode. Workers receive no store locks or broker authority. Added comprehensive
  suite in `tests/test_strategy_execution_safety.py`. Full test suite: 226 passed / 1 skipped;
  Ruff check and format passed.
- 2026-10-08: Fixed `Platform.start_replay_stream` generating overlapping/backwards tick batches.
  Introduced a monotonic simulation cursor (`_simulation_cursor`) on `Platform` that strictly
  advances beyond previously emitted ticks across repeated replay actions, stream restarts, and
  batches. Implemented `generate_simulation_batch` to schedule multi-symbol ticks synchronized
  per timestamp. Separated simulated event timestamps (`tick.event_timestamp`) from receive time
  (`self.clock()` recorded in `risk_marks.received_at`). Generated globally unique event IDs
  (`sim:{sym}:{ts}:{seq}`) for newly simulated ticks while allowing intentional duplicate
  replays to retain identical IDs for clean deduplication. Prevented duplicate stream threads via
  `_replay_lock`. Enforced clean stop, kill, and shutdown lifecycle; guaranteed replay stream
  never automatically restarts after recovery or reconciliation. Kept replay explicitly mock-only
  and preserved broker freshness fail-closed checks. Added comprehensive tests in
  `tests/test_replay_stream.py`. Full test suite: 237 passed / 1 skipped; Ruff check and format passed.
- 2026-10-08: Task 3 candle correctness audit and regression coverage completed.
  Audited `CandleBuilder` and simulation generator against timestamp, volume, gap, and late-tick
  policies. Verified exact half-open `[start, end)` buckets where boundary ticks belong to the succeeding
  candle; verified per-tick volume accumulation and symbol independence; verified identical duplicates
  affect neither candles nor marks; verified conflicting duplicates and late ticks fail closed; verified
  bounded dedupe eviction never silently double-counts prior events; verified missing intervals create
  no invented gap candles; verified final incomplete candles emit no strategy signals. Fixed kill wiring
  ordering in `Platform.kill`: admission gate is now closed (`kill_requested.set()`, `kill_latched=True`,
  `risk.state=KILLING`, `strategies.enabled=False`) BEFORE joining/waiting on the replay thread. Documented
  policies in `docs/CONTRACTS.md`. Added regression test suite in `tests/test_candle_correctness.py`. Full
  test suite: 246 passed / 1 skipped; Ruff check and format passed.
- 2026-10-08: Task 4 Strategy Runtime Lifecycle and Interval Correctness completed.
  Validated strategy registration (`interval` and `warmup` must be positive integers; `handler` must be callable).
  Enforced registered interval candle routing on `on_candle`; dynamically wired custom intervals into `CandleBuilder.add_interval` via `on_interval_registered` callback.
  Processed closed candles at most once per strategy run (`(strategy_id, generation)`); rejected duplicate and older out-of-order candles before worker callback allocation.
  Serialized same-instance candidate state commits under `_state_lock` so out-of-order callbacks cannot overwrite newer indicator states.
  Introduced monotonic `_global_epoch` counter to invalidate in-flight results across global stop, resume, kill, and broker recovery boundaries, even if runtime is re-enabled before workers finish.
  Enforced that subscription stop/re-enable invalidates in-flight results and completely resets indicator warmup (`samples=0, ready=False`).
  Exposed backend-derived sample count, required warmup, and readiness via `StrategyRuntime.readiness_for` and `Platform.snapshot()['subscriptions']`.
  Aligned RSI reversal registry warmup to 15 (requiring 15 closes for 14 price differences).
  Addressed Task 3 follow-up: included replay stream join time in the total kill deadline calculation and ensured execution admission closure is idempotent.
- 2026-10-08: Task 5 Correct Market-Session Handling and Task 4 Follow-ups completed.
  Converted session timestamps to Asia/Kolkata (`ZoneInfo("Asia/Kolkata")`) before checking configured continuous hours (`[09:15:00, 15:30:00)` IST).
  Preserved default unenforced hours (`enforce_hours=False`) for mock replay compatibility.
  Strictly fail closed when hours are enforced and timestamp is missing/None without a clock.
  Kept state consistency between `is_open()`, `status_at()`, `to_dict()`, and `Reliability.check_evidence()` (`HALTED`, manual `OPEN`/`CLOSED`, and `AUTO`).
  Task 4 Follow-up 1: Serialized same-strategy callback execution per instance under `inst_lock` prior to state copying and committing, guaranteeing intermediate candle updates are never lost or computed concurrently from stale indicator states.
  Task 4 Follow-up 2: Verified kill certificate elapsed time includes admission closure and replay join; exhausted deadline budgets return a truthful failure certificate (`status="FAILED", reason="KILL_DEADLINE_EXPIRED"`) without throwing `ValueError` from `Deadline`.
- 2026-10-08: Task 5 Follow-up Callback Isolation and Bounded Shutdown completed.
  Addressed StrategyRuntime.close unbounded executor shutdown: eliminated `shutdown(wait=True)` in favor of bounded `shutdown(wait=False, cancel_futures=True)` with pre-shutdown epoch invalidation.
  Completely isolated strategy callback workers from SQLite, `Store`, broker authority, and runtime mutation. Workers now execute pure candidate calculations over working state copies and return candidate results to the control plane.
  The control plane validates and commits candidate results (`_enabled`, `_global_epoch`, `_subscription_generations`, `is_subscription_enabled`, `may_run`, candle start time monotonicity); timed-out and invalidated runs cannot mutate state.
  Ensured same-instance serialization (`inst_lock`) is acquired and released boundedly on timeout, never retaining locks needed by `kill`, `set_enabled`, `close`, or healthy strategies. Stopping or halting a subscription provisions a fresh instance lock.
  Added regression coverage in `tests/test_strategy_execution_safety.py` verifying: callback remains blocked while close returns in bounded time; late release after store closure triggers zero DB queries or state mutations; same-instance timeout does not block controls or other strategies; test workers released in `finally` blocks. Full test suite: 265 passed / 1 skipped; Ruff check and format clean.


- 2026-10-08: Task 6 Authenticated, Account-Scoped Member 4 User Workflow and Follow-Up completed.
  Completed end-to-end user workflow: register/login -> subscribe -> start -> observe readiness/signals/P&L -> stop.
  Account identity is derived exclusively from verified server-side sessions (`engine.auth.verify_token`), never from client input.
  Removed anonymous risk-budget fallback: `GET /api/risk/budgets` strictly requires session authentication and returns only the verified account's budgets (anonymous returns 401).
  Audited account-scoped snapshot output and eliminated all nested leaks:
    - Reconciliation reports: `broker_positions` and `unexplained_positions` filtered to `account_id`; `orders`, `unique_fills`, `open_orders`, and `duplicate_snapshot_fills` scoped to caller's counts; `unattributed_fills` reported as 0. Honest global verification flags (`verified`, `reason`, `observed_at`) are preserved.
    - Kill certificates: `broker_positions` dictionary filtered to only keys starting with `f"{account_id}/"`; `virtual_positions_flat` evaluated for caller's positions; `open_orders` scoped to caller's open count; honest global status (`status`, `elapsed_seconds`, `reason`) preserved.
    - Fill counters: `unique_applied`, `duplicates_ignored`, and `rejected_events` scoped strictly to the caller's account; `unattributed_in_last_verified_snapshot` sourced from verified snapshot accounts (null if unattributed fills exist or unverified).
- 2026-10-08: Task 6 Final Follow-Up — Truthful Scoped Safety Evidence completed.
  Fixed projection issues in account-scoped safety evidence:
  - Eliminated hardcoding of `unattributed_fills` and `unattributed_in_last_verified_snapshot` to 0. Sourced from verified account breakdown (`accounts[account_id]`) at `observed_at`. If unattributed fills exist, snapshot is unverified, or account breakdown is missing, reports `null`/UNKNOWN.
  - Preserved historical kill certificate evidence: `open_orders`, `virtual_positions_flat`, `status`, and `reason` are never rewritten using current account state. Sensitive `broker_positions` are filtered strictly to `f"{account_id}/"`. Later trades do not mutate historical certificates, and failed kills retain uncertainty (`open_orders=-1`, `status="FAILED"`).
  - Reconciliation counts describe the verified snapshot at `observed_at` sourced from `accounts[account_id]`, never substituting current local counts or unrelated audit counters.
  - Position comparison preserves raw `UNKNOWN` or `FAILED` states; filtering never converts uncertainty into a pass.
  - Added regression tests in `tests/test_member4_workflow.py` verifying unknown attribution stays unknown, failed kill retains uncertainty, later trades do not alter historical certificates, and scoped historical reports remain accurate and leak-free across accounts.
  Full test suite: 273 passed / 1 skipped; Ruff check and format clean; TypeScript clean.
    - Unknown orders: filtered strictly by `account == user.account_id`.
    - Audit payloads: only events where `account == user.account_id` or `strategy` belongs to the user's subscriptions are returned; nested payloads with `broker_positions` are sanitized to strip other accounts.
  WebSocket (`/api/stream/ws`) and SSE (`/api/stream/telemetry`) require valid authentication prior to transmitting any data.
  Streaming loops revalidate session tokens before pushing each snapshot; on logout or session expiration, SSE terminates and WebSocket closes immediately with close code 1008 (`WS_1008_POLICY_VIOLATION`).
  Cross-account start/stop actions are denied with HTTP 403 Forbidden without mutating state or leaking details.
  Preserved backend-derived `READY`, `RUNNING`, `STOPPED`, `HALTED`, and warmup indicator readiness states.
  Frontend handles HTTP 401 and WS 1008 by invoking `clearStaleData()` to reset table records and redirect to `/login` without leaving stale cross-account data visible.
  Ownership corrected: Ram is Member 3 (risk, security, reliability); Akshat is Member 1 (accounting, ledgers, fills, positions).
  Platform-wide authorization is NOT complete. Explicitly documented the 15 remaining unprotected global mutation endpoints for Ram (Member 3).
  Full test suite: 272 passed / 1 skipped; Ruff check and format clean; TypeScript clean.- 2026-10-08: Task 7 — Deterministic Mock Demo Scenarios & Rehearsal Runner completed.
  Implemented end-to-end deterministic demonstration scenarios and isolated rehearsal runner:
  - Created `backend/demo_scenarios.py` with `ControllableClock`, `generate_deterministic_ticks()`, and `RehearsalRunner`.
  - Built rising, falling, and reversal tick sequences across 12 minutes (720s) with 1m and 5m candle generation.
  - Exercised three real registered strategies on one account (`acc_demo`), producing authentic simultaneous opposing entries on `TCS`:
    `strat_mom` establishing LONG (+1) and `strat_mr` establishing SHORT (-6), with independent virtual positions, mark-to-market P&L, and net aggregate broker position (-4).
  - Exercised 5m candle close triggering `strat_bo` breakout BUY (+1) after 2 completed 5m candles.
  - Exercised partial fill (10/20 filled via `execute`), duplicate fill deduplication (`DUPLICATE_FILL_IGNORED`), and broker order rejection (`reject_next = True`).
  - Exercised platform risk-limit rejection: intercepted order exceeding `max_position=5` with backend reason `RISK_MAX_POSITION` and audit trail.
  - Exercised missed attributed fill recovery through reconciliation: matched external broker fill and updated local order from `OPEN` to `FILLED` with synced ledger positions.
  - Exercised platform restart invariants: verified restart retains durable SQLite fills and positions, initializes safely in `Gate.RECOVERING` / `Health.RECOVERING` with strategies disabled; trading reconciles against external broker truth without ledger fabrication, resuming to `Gate.RUNNING` only upon explicit operator resume.
  - Exercised emergency kill switch via `Platform.kill()`: verified immutable `KillCertificate` contract (`status="SUCCESS"`, `elapsed_seconds < 10`, 0 open orders, 0 broker positions, all virtual positions flat).
  - Exercised unexplained drift protection: injected foreign external position; verified reconciliation fails closed (`UNEXPLAINED_EXTERNAL_POSITION`, `Gate.UNCERTAIN`, `Health.DRIFTED`) and strictly refuses auto-fixing.
  - Added CLI runner script `scripts/rehearsal_runner.py` with non-interactive execution and `--serve` option for live dashboard rehearsal.
  - Documented concise run commands, replay constraints (explicit rehearsal steps for injected clocks), and 4-5 minute demo script in `docs/DEMO_AND_DEBUG.md`.
  - Added dedicated regression test suite in `tests/test_demo_scenarios.py`.
  Full test suite: 282 passed / 1 skipped; Ruff check and format clean; TypeScript clean.

- 2026-10-08: Task 8 — Operational UX & Final Member 4 Handoff completed.
  - Implemented operational UX improvements in `frontend/index.html` without framework migrations:
    - **Strategy Cards**: Cards in `#strategy-cards-grid` display actual lifecycle (`RUNNING`/`READY`/`STOPPED`/`HALTED`), warmup progress (`samples / warmup (Ready/Warmup)`), net position with symbol, net P&L (color-coded), charges, and interactive Start/Stop controls.
    - **Market / Feed Status Banner**: Dedicated banner `#feed-status-strip` displays feed source (`MOCK / REPLAY` badge, synthetic replay description), freshness (`Streaming (N ticks · M symbols)` or `Waiting for ticks`), trading session (`OPEN`/`CLOSED`, `09:15 – 15:30 IST`), and accepted/duplicate/late tick counts.
    - **Readable Candle & Risk Evidence**: Added human-readable completed candles table (`#candles-table-body`) with Time, Symbol, Interval, O, H, L, C, V; added platform risk decisions feed (`#risk-decisions-feed`) displaying sequence, strategy, symbol, approval badge (`✓ APPROVED` / `✗ REJECTED`), and backend rejection reason code (`RISK_MAX_POSITION`, `RISK_DAILY_LOSS`, etc.).
    - **Correlated Execution Timeline**: Bounded lifecycle pipeline (`#execution-timeline`) correlating `Candle → Strategy Intent → Risk Gateway → Broker Order → Fill Execution → Financial Result`. Truthfully reports missing evidence (e.g. `— (Direct intent / unlinked candle)`, `— (Blocked)`, `— (No fill)`) without synthesizing stages or timestamps.
    - **Historical Kill Switch Certificate**: Added dedicated `#kill-cert-card` displaying historical execution evidence (`SUCCESS`/`FAILED`, elapsed time `< 10s SLA`, open orders at kill, virtual flat status, broker verification). Explicitly distinguishes immutable historical kill certificates from current live safety evidence.
    - **Teammate Panels Preserved**: Retained Ram's (Member 3) safety and risk budget panels; retained Akshat's (Member 1) ledger and accounting calculations; no new financial formulas introduced.
    - **Session Lifecycle & Stale Data Purge**: `clearStaleData()` immediately purges all DOM tables, cards, feeds, and indicators upon sign out, HTTP 401, or WS 1008. Enhanced `refresh()` and WebSocket stream to handle backend disconnection safely (`Disconnected (Reconnecting…)`) without uncaught errors.
    - **Mobile Responsiveness**: Verified clean responsive layout on small viewports with no horizontal overflow.
  - Corrected Task 7 position arithmetic in `backend/demo_scenarios.py`:
    - Replaced hardcoded difference check with actual ledger aggregation: `actual_ledger_sum = p.ledger.aggregate().get((acc, "TCS"), 0)`.
    - Updated `tests/test_demo_scenarios.py` to assert external broker net position matches `actual_ledger_sum`.
  - Full regression validation:
    - All 282 unit/integration tests pass (1 optional local PostgreSQL skipped).
    - All 7 rehearsal runner scenarios pass with zero errors.
    - `npm run check` (TypeScript), `ruff check`, and `ruff format` clean.

## In Progress
- Member 4 mock/replay scope is COMPLETE. Awaiting Ram's (Member 3) operator authorization and 021 market-data feed contract.

## 2026-10-09 — React contract and recovery integration fixes

- Verified the current FastAPI/platform response shapes before editing the SPA. Overview now reads
  `gate` and `health`; Safety Proof reads `verdict`, `generated_at`, and `invariants`.
- Strategy financial rows now join account-scoped `snapshot.positions` to subscriptions by
  `account_id`/`account`, `strategy_instance_id`/`id`, and `symbol`. The UI displays the backend's
  `net_quantity`, `net_pnl`, and `charges`, plus backend readiness `samples`, `warmup`, and `ready`.
  Missing financial evidence is shown as an em dash/Unavailable and real zero remains zero; decimal
  strings are formatted without an intermediate JavaScript `Number` conversion.
- Corrected execution trace rendering to the actual trace envelope (`trace_id`,
  `strategy_instance_id`, `account_id`, nested `events`, and event `recorded_at`). Other React pages
  were checked against the current API responses; focused fixes were made only where mismatches were
  found.
- Telemetry now clears old-account state immediately and uses a single generation-bound socket/timer.
  Transient initial state failures retry with capped backoff; logout, account change, unmount, HTTP 401,
  and WebSocket 1008 invalidate stale work. HTTP 401 and WS 1008 do not reconnect the invalid session.
- Replay, reconcile/resume, kill, subscription, Failure Lab, and SafetyBench controls now expose pending
  and readable rejected-action states and prevent duplicate submission. Kill retains confirmation.
  Failure Lab now explicitly warns that scenarios mutate the current mock platform and requires
  confirmation; only the separately created SafetyBench platforms retain an isolation label.
- Focused frontend fixtures cover nonzero values, true zero, missing values, gate/health, Safety Proof,
  readiness, telemetry recovery/cleanup, rejected actions, and confirmations. Validation: ESLint passed;
  Vitest passed 28/28 tests across 6 files; Vite production build passed.
- Browser validation used an isolated local SQLite test database: desktop login → replay →
  strategies/orders showed backend positions/P&L/readiness; a duplicate subscription produced the
  readable 409 error; the Failure Lab impact wording was visible; the responsive route was checked at
  375×812; logout returned to the login page and browser console warning/error output was empty.
- No backend, broker, risk, accounting, callback, kill, React/Vite dependency, production database, or
  live-feed behavior changed. Navigation did not change, so `DEMO_AND_DEBUG.md` did not require an update.
- Remaining backend dependencies: operator roles, complete account scoping, cross-account
  reconciliation leakage, and unscoped global-action responses remain separate backend work. Frontend
  filtering cannot establish those security guarantees. Live 021/market-feed integration remains
  unimplemented and unclaimed.

## 2026-10-08 — Task 9A yfinance compatibility probe

- Added the standalone read-only probe `scripts/probe_yfinance_stream.py`. It uses only
  yfinance's documented `AsyncWebSocket.subscribe()`, `listen()` and `close()` surface,
  has configurable symbols/duration (defaults: `TCS.NS INFY.NS`, 30 seconds), retains at
  most 10 decoded samples by default, redacts credential-like fields, and applies a hard
  duration plus bounded cancellation/close handling. It does not import AlgoShield, use
  REST history, access an application database, start strategies, or place orders.
- Isolated environment evidence: Python 3.13.7, yfinance 1.7.0, websockets 17.2. The
  application dependency manifest was unchanged. Installed source SHA-256 for
  `AsyncWebSocket` was
  `84ac9d1af1645d1d1e4f32a68ad854bad5c432b73ce87cca297851f7e74ccb59`.
- Installed-source facts: decoded messages are dictionaries created from the bundled
  `PricingData` protobuf. Relevant declared fields are `id` (string), `price` (float),
  `time` (uint64), `day_volume` (uint64), `last_size` (uint64), `bid`/`ask` (float), and
  `bid_size`/`ask_size` (uint64). The schema does not declare the `time` unit, say that a
  volume field is incremental/per-trade quantity, or expose a documented unique trade ID.
- Default live run at 2026-10-08 23:55 Asia/Kolkata: subscription returned after 1.328s;
  the full probe exited cleanly after 30.276s; `close()` returned; no errors and no decoded
  messages were observed. Consequently runtime field presence, timestamp units, price and
  volume values, and update frequency were **not observed**. With the Indian market closed,
  zero messages is **INCONCLUSIVE**, not evidence that the symbols or feed are unsupported.
  No historical REST result was requested or counted as streaming success.
- Smallest safe adapter plan: do not add a production dependency or adapter yet. Repeat the
  same probe during an open NSE session and require decoded messages for both symbols. Then
  validate the timestamp unit against UTC, determine whether `day_volume` is cumulative and
  whether `last_size` is suitable as per-tick quantity, and establish a reconnect-stable
  idempotency key. Only after those facts are observed should an adapter normalize
  `price` through `Decimal(str(value))`, convert timestamps to UTC epoch integer seconds,
  normalize volume to incremental quantity, and emit canonical `Tick` values through a
  bounded queue/lifecycle wrapper. Missing identity, ambiguous volume, malformed timestamps,
  queue overflow, disconnects, and reconnect gaps must fail closed; no hash/sequence should
  be presented as a provider trade ID. `Platform.tick` should remain unchanged and continue
  recording receive freshness separately through `Reliability.observe_tick`.
- Next step: rerun Task 9A during live NSE hours. Production `MarketData021Provider`, React,
  contracts, and dependency files remain unchanged.

## 2026-10-09 — Task 9A bounded supervisor and live NSE evidence

- Replaced coroutine-only deadline enforcement in `scripts/probe_yfinance_stream.py` with a
  parent-supervised worker process. The parent bounds import, connection, subscription, listening,
  cleanup, termination, and reap; it emits a final report even if the worker stalls. Incremental
  JSON-lines evidence is flushed for lifecycle progress, bounded samples, and count checkpoints.
  Missing summaries retain `message_count=null` rather than being reported as zero.
- The installed isolated environment remains unchanged: Python 3.13.7, yfinance 1.7.0, and
  websockets 15.0.1. Inspection confirmed that yfinance `listen()` catches cancellation and awaits
  `close()`, but the earlier no-output hang did not identify which phase stalled; the supervisor
  therefore treats every worker phase as untrusted instead of asserting that cancellation was the
  root cause.
- Offline focused tests cover a hanging connection/subscription, messages followed by hanging
  cleanup, and normal completion. They verify bounded return, retained evidence, unavailable-count
  honesty, and a reaped child. Validation: 5 focused tests passed; Ruff check and format check passed;
  `git diff --check` passed.
- Live NSE retry (`TCS.NS INFY.NS`, 30 seconds, five retained samples) completed normally in
  31.259904 seconds within its 34-second maximum, with subscription returning at 4.339743 seconds,
  clean provider cleanup, child exit code 0, and no orphan process. It received 42 decoded price
  messages: INFY.NS 23 and TCS.NS 19. Classification: **STREAM_CONFIRMED**.
- Observed fields included `id`, `price`, `time`, `day_volume`, `last_size`, `exchange`,
  `market_hours`, `quote_type`, `price_hint`, `change`, and `change_percent` (plus one `bid`). Example
  raw evidence: INFY.NS price 1025.25, time `1791521394000`, day_volume `5674765`, last_size `11`;
  TCS.NS price 2190.8, time `1791521395000`, day_volume `5338028`, last_size `10`.
- The decoded uint64 values arrived as decimal strings. Magnitude-based interpretation of the raw
  time values as Unix milliseconds gives 2026-10-09T04:49:54Z and 04:49:55Z, within seconds of the
  04:49:50Z probe start, so milliseconds are runtime-plausible but remain an inference rather than a
  provider contract. Observed median interarrival was about 1.015 seconds for INFY.NS and 1.020
  seconds for TCS.NS. `day_volume` and `last_size` semantics remain unproven; neither is claimed to be
  per-trade quantity, and `id` is not claimed as a unique trade/message ID.
- BTC-USD was not run because NSE streaming was confirmed. Dashboard/production adapter integration
  remains pending; application dependencies and application code were not changed.

## 2026-10-09 — Task 9B optional Yahoo external quotes

- Added an explicitly opted-in Yahoo provider for only `TCS.NS -> TCS` and `INFY.NS -> INFY`; mock replay remains the default and source mixing is rejected.
- Normalization uses `Decimal(str(price))`, rejects unsupported symbols, nonfinite/nonpositive prices and implausible timestamps, preserves raw decimal-string milliseconds, and records normalized epoch seconds. Captured Task 9A fixtures (`1791521394000`/`1791521395000`) validate as milliseconds near their receipt time.
- `day_volume` and `last_size` remain unused because their semantics are unconfirmed. Yahoo ticks use canonical compatibility quantity 0 with `volume_available=False`; downstream candles remain explicitly quote-derived and show volume as unavailable, never as observed zero volume.
- Generated `yahoo-quote:*` hashes are bounded best-effort duplicate keys, not exchange trade IDs. yfinance runs in a supervised child process behind a bounded queue. Startup/stop/reconnect are bounded; overflow, disconnect, malformed data and stale gaps fail closed and never auto-resume.
- Added telemetry and the minimal UI label `YAHOO EXTERNAL QUOTES / MOCK EXECUTION`. Yahoo operation is restricted to mock brokers and cannot authorize 021 execution.
- Optional dependency resolution pins probed yfinance 1.7.0; an isolated Python 3.13.7 install resolved websockets 15.0.1, satisfying the application constraint `websockets>=13,<16`. Default installs remain unchanged.
- Bounded live smoke on disposable SQLite with runtime disabled received 26 accepted TCS/INFY updates in 30.049 seconds. Last raw/normalized time was `1791522597000` / `1791522597`; volume remained unavailable; order count was 0 and the gate remained `UNCERTAIN`. The first child exceeded its startup deadline and was terminated, a reconnect then streamed successfully, and shutdown completed in 31.040 seconds with no live worker. This is external quote evidence only, not complete exchange ticks or 021 completion.
- Initial Task 9B validation covered 19 focused Yahoo tests and 57 combined market/candle/replay/Member 4 tests. The verification follow-up below replaced the stale frontend source assertion and completed the full regression cleanly.

### Task 9B verification follow-up

- Removed the brittle Python assertion that searched React source for `setSnapshot(null)`. React behavior tests now begin with populated account data and verify logout/account change, reconnect HTTP 401, and WebSocket 1008 all clear the snapshot, become offline, close stale sockets, and schedule no further retry. Backend restart safety assertions remain intact.
- Added bounded provider lifecycle timing evidence. A fresh 30-second run completed process startup/module loading at 0.474s, yfinance import at 2.536s, and connection/subscription at 3.897s. A separate 225-second run subscribed at 3.444s (spawn/module 0.520s, import complete 2.123s). Both fit the existing 8-second startup budget with more than four seconds of headroom, so the timeout was not widened. The earlier one-off cold-start timeout remains recorded rather than erased.
- The 225-second bounded capture received and accepted 384 messages with no duplicates, late ticks, provider errors, reconnects, or forced termination. It produced six completed 1-minute candles and two completed 5-minute candles across TCS/INFY, all `YAHOO_EXTERNAL_QUOTES` with `volume_available=false`. The first 5-minute bucket was partial: its nominal bucket was `[1791523200, 1791523500)`, while capture evidence began in the 1-minute bucket `[1791523320, 1791523380)`. No backfill was invented. Gate stayed `UNCERTAIN`, runtime stayed disabled, and orders stayed zero.
- Browser verification against real FastAPI on disposable SQLite showed current raw/UTC quote timestamps, advancing accepted counts, `Volume unavailable`, completed 1m/5m quote-derived candles, and zero orders/fills. Forced termination of the isolated Yahoo child changed the page to `Not connected`, retained the last quote evidence, recorded the worker exit, and kept the gate `UNCERTAIN`; the bounded reconnect restored `Connected` and advancing counts without resuming trading.
- Final validation: 335 backend tests passed with 1 environment-gated PostgreSQL skip; all 30 React tests passed; ESLint, Vite production build, Ruff check/format, and `git diff --check` passed.

## Blockers / Teammate Dependencies
- **Ram (Member 3) Operator Authorization**: Global mutation endpoints (`POST /api/kill`, `POST /api/reconcile`, `POST /api/resume`, `PUT /api/risk/policies/{strategy}`, `POST /api/failure-lab/{scenario}`, etc.) currently operate in offline demo mode. Ram must implement role-based operator authorization before multi-user production deployment.
- **Ram (Member 3) Continuous Broker Refresh**: Automated background broker polling / WebSocket sync loop is needed to refresh `last_verified_at` continuously under live conditions without manual `reconcile()` calls.
- **Akshat (Member 1) Real Ledger Integration**: Account-level settlement and statutory tax/stamp duty calculations are verified on mock ledgers.
- **Sujal (Member 2) 021 Broker Adapter**: Awaiting official sponsor 021 broker credentials, sandbox endpoints, and order status payload schemas.

## Tomorrow's Market-Feed Integration Boundary (Task 9 Preparation)
- **Adapter Contract**: Implement `MarketData021Provider` adhering to `MarketDataProvider` interface:
  - `start()`, `stop()`, `is_connected() -> bool`
  - Normalization of incoming raw 021 WebSocket ticks into canonical `Tick(symbol, price, volume, event_timestamp, event_id)`
  - Out-of-order, late, and duplicate tick filtering passing through `CandleBuilder.process_tick`
  - Reconnect and gap backfill protocol isolated behind adapter
  - Zero domain or strategy leakage of 021 payload formats.

## Handoff Notes
Member 4 tasks 1 through 8 are 100% complete and fully verified. User workflows are strictly account-isolated server-side. Subscriptions, orders, fills, positions, signals, risk budgets, and execution timeline never leak across accounts. All unit tests, scenario tests, and linters pass cleanly. Ready for Task 9 market feed integration upon sponsor contract release.

## 2026-10-08 — Integration baseline

- Merged the latest `origin/main` account-isolation, callback-shutdown, market-session, and kill-deadline work with the evidence/telemetry layer.
- Restored authenticated account-scoped WebSocket/SSE snapshots, direct subscription reads, reconciliation recovery evidence, and mock replay fill execution.
- Real 021 provider details remain blocked behind adapters; this remains mock/replay evidence only.

## 2026-10-08 — React frontend migration

- Replaced static HTML/inline JavaScript with a React/Vite SPA and routes for all strategy, execution, safety, recovery, observability, and audit workflows.
- Added protected session routing, centralized credentialed API calls, one account-scoped WebSocket provider with bounded reconnect, and stale-state eviction on 401/1008.
- Added responsive shell/mobile navigation, backend-driven strategy controls, replay/reconcile/resume/kill actions, and isolated Failure Lab/SafetyBench surfaces.
- FastAPI serves the production build with nested-route fallback; Docker builds assets in a Node stage and runs only Python/FastAPI.
- Validation: 298 Python tests passed, 1 PostgreSQL integration skipped; 8 Vitest tests, ESLint, Ruff, and Vite build passed.

## 2026-10-08 — Light responsive evidence UI

- Removed dark component surfaces from authentication, navigation, evidence, and control states while retaining accessible dark text and semantic status colors.
- Made the complete navigation fit compact desktop heights and wrap into a responsive tablet/mobile grid; constrained document overflow and retained table-local scrolling.
- Replaced raw JSON output with recursive labeled evidence fields, status indicators, and lists sourced directly from backend responses.
- Removed duplicate frontend capability lists: strategy kinds and Failure Lab scenarios are now discovered from backend endpoints.
- Validation: 299 Python tests passed, 1 PostgreSQL integration skipped; 9 React tests, ESLint, Ruff, and Vite production build passed.

## 2026-10-08 — Mobile navigation drawer

- Replaced the mobile navigation grid with a light hamburger drawer while preserving the desktop sidebar.
- Added overlay/Close/Escape dismissal, route-change auto-close, body scroll locking, internal overflow safety, and a persistently reachable kill control.
- Added responsive compact-height rules so all navigation groups fit common mobile viewports while remaining scrollable on smaller displays.
- Validation: 10 React tests, ESLint, Vite production build, 21 focused backend tests, and Ruff passed.

## 2026-10-08 — Failure Lab response hardening

- Prevented SPA fallback from returning HTML with HTTP 200 for unknown `/api/...` routes; unmatched APIs now return JSON 404 evidence.
- Added centralized rejection of non-JSON API success responses and defensive validation for discovered Failure Lab scenarios and strategy capabilities.
- Failure Lab now renders an inline error instead of crashing when an older/stale backend lacks the discovery endpoint.
- Validation: 299 Python tests passed, 1 PostgreSQL integration skipped; 11 React tests, ESLint, Ruff, and Vite production build passed.

## 2026-10-08 — Compact Risk Center budgets

- Replaced expanded nested evidence cards inside Strategy Budgets with dense labeled metrics sourced from the complete backend policy, position, daily-loss, and order-rate objects.
- Reduced cell padding and vertical rhythm while preserving table-local horizontal scrolling and a two-column metric fallback on narrow mobile screens.
- Validation: 12 React tests, ESLint, Vite production build, 13 focused backend tests, and Ruff passed.

## 2026-10-08 — Vertical Strategy Budgets

- Removed the horizontally scrolling Strategy Budgets table.
- Each strategy now has a responsive vertical evidence block whose backend-provided policy, position, daily-loss, and rate groups wrap downward without document or section-level horizontal scrolling.
- Mobile forces a single group column while metric values remain compact and readable.
- Validation: 13 React tests, ESLint, Vite production build, 10 focused risk tests, and Ruff passed.

## 2026-10-08 — Vertical Reconciliation Center

- Replaced the wide paired reconciliation panels with a single vertical evidence sequence that remains within the page width.
- Kept verification, reason, and unknown-order state compact; broker, comparison, recovery, and event values remain sourced from backend responses.
- Omitted empty nested collections from expanded recovery evidence and summarized a clean position comparison without blank panels.
- Validation: 14 React tests, ESLint, Vite production build, 22 focused reconciliation/recovery tests, and Ruff passed.

## 2026-10-08 — Branch integration: codex/usp-evidence-layer into main
- Successfully merged `codex/usp-evidence-layer` (including UI layout enhancements: compact vertical strategy budgets and vertical reconciliation sequence) into `main`.
- Preserved all Member 4 Tasks 1–8 functionality: isolated bounded callbacks/shutdown, generation invalidation, sequential indicator updates, monotonic replay, candle/session correctness, authenticated account scoping, truthful historical evidence, deterministic restart/kill scenarios, rehearsal runner (`scripts/rehearsal_runner.py`), and operational UX.
- Standalone single-file operational dashboard preserved in `frontend/static_dashboard.html`; canonical Vite entrypoint in `frontend/index.html` with production build in `frontend/dist/`.
- Full regression verification: Python tests, Vitest frontend tests, rehearsal runner scenarios, and linters all passing cleanly.

## 2026-10-09 — Telemetry and scoped workflow follow-up

DEC-027 follow-up: Orders shows actual filled/requested quantities (missing is
Unknown); Strategies shows existing account-scoped candle-linked signals.
Two behavioral tests added, frontend 30 passed across 7 files; lint/build pass.
No candle algorithm, financial calculation or telemetry provider changed.

- Replaced the stale Python assertion tied to the former `setSnapshot` identifier.
  Behavioral Vitest tests remain authoritative for account switch/logout, HTTP
  401, WebSocket 1008, stale socket closure and snapshot clearing.
- Account-facing snapshots and streams use the DEC-026 nested response boundary.
  Owned subscription/policy/order workflows remain permitted; global replay and
  market controls require an explicit operator.



2026-10-09 documentation integration: current ownership, dependencies and acceptance gates are consolidated in [TEAM_EXECUTION_PLAN](../TEAM_EXECUTION_PLAN.md), DEC-028. Direct branch pushes are allowed; PRs optional. No new member feature is claimed implemented by this planning update. Fresh cross-module evidence is in [INTEGRATION](INTEGRATION.md).

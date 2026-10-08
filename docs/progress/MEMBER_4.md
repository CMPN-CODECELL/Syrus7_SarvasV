# Member 4 Progress

## Ownership
Market Data & Strategies; canonical responsibilities: ../TEAM_OWNERSHIP.md, Member 4.

## Current Status
- Phase: Member 4 mock/replay implementation complete; live provider integration pending
- Current task: await authoritative 021 feed contract and production identity-provider integration
- Status: BLOCKED
- Last updated: 2026-10-07 17:14 Asia/Kolkata
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


## In Progress
- No further 021 implementation is safe without an authoritative tick/reconnect/backfill contract. Existing adapter remains intentionally unavailable.

## Blockers / Dependencies
- Official 021 contract/credentials and sponsor session/charges/kill semantics.
- Production identity provider remains unselected; the current local session boundary is not Neon Auth.

## Next
- Obtain authoritative 021 tick schema, sequencing and reconnect/backfill behavior.
- Implement `MarketData021Provider` normalization and adapter contract fixtures.
- Coordinate feed freshness/session gating with Member 3.
- Replace the local bootstrap identity boundary with the selected production identity provider without changing session-derived account ownership.

## Handoff Notes
Demo replay ends STOPPED; enabled subscriptions show READY and stopped/faulted subscriptions show STOPPED. Indicator state requires a fresh complete warm-up after restart, while subscription state and signal/error evidence are durable. Neon PostgreSQL schema is initialized and verified.

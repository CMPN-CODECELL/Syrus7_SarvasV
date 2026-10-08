# Integration Progress

## Current Status
- Phase: integrated mock/replay hardening with Member 4 strategy/runtime and local PostgreSQL verification
- Status: BLOCKED
- Last updated: 2026-10-08 16:35 Asia/Kolkata

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



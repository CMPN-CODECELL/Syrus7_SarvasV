# Implementation status and next phases

Active work: [IMPLEMENTATION_DELTA.md](IMPLEMENTATION_DELTA.md). Fresh evidence: [progress/INTEGRATION.md](progress/INTEGRATION.md). The v2 and earlier outstanding-task descriptions below preserve history; they do not override current v12 code or DEC-026.

## Historical bootstrap phases (superseded as active backlog)

Implemented: contracts, modular monolith, SQLite schema v2, API and backend-fed dashboard, accounts/subscriptions, three built-in candle strategies, 1m/5m candles, max position/rate/daily loss, atomic directional reservations, mock partial/rejected orders, idempotent accounting, reconciliation, explicit recovery/resume and verified mock kill. Safety/invariant tests cover mandatory S1-S7 and additional failures.

This is a vertical slice, **not completion of the official PS**. Runtime is serialized, so simultaneous strategies share one account/event loop rather than run in separate threads. Demo ends STOPPED; do not label subscriptions RUNNING after replay.

## Historical hardening task inventory

Member 1: exact sponsor charges, durable configurable policy/session accounting, audit timestamps, charge corrections and stronger ledger projection/property tests.
Member 2 completed in mock/replay (T1–T5): authoritative state-machine invariants, explicit cancellation lifecycle, lightweight broker update flow, disconnect/reconnect recovery, and offline broker adapter behavioral contract suite. Remaining external work: real 021 contract fixtures and sandbox integration once sponsor documentation and credentials are provided.
Member 3: durable kill/health latch, bounded kill orchestration, feed/broker freshness, external position quarantine, policy persistence and live opposing-close semantics.
Member 4 completed in mock/replay: callback exception isolation with durable quarantine, fully idempotent bounded symbol-scoped tick dedupe, audited fail-closed tick rejection, full indicator warm-up, 3/5 EMA momentum, five-period mean reversion, 5-minute breakout, RSI reversal, exact-decimal API projection, session-derived subscription ownership, durable per-strategy controls and responsive backend-evidence dashboard. Remaining external work: authoritative 021 normalization, reconnect/backfill, exchange-session/freshness fixtures and production identity-provider integration.

Multi-stock subscription orchestration is implemented for mock/replay: a user can select one strategy kind and up to 20 stocks, and one authenticated atomic request creates independent single-symbol instances. Dashboard counts, filtering, replay symbol discovery and failure isolation use those normal rows. This does not claim a live market-data subscription capability; the authoritative 021 provider contract remains blocked.

Exit: failures preserve invariants after process restarts and event reorderings; no safety state silently resets; all UI health assertions backed by fresh evidence.

## 021 sandbox integration

Obtain sponsor contract/credentials first. Implement the existing provider interfaces and canonical mapping. Confirm identity, partial fills, snapshot completeness, timeout resolution, charges, rate limits and ten-second verified target. Run adapter contract tests and end-to-end sandbox scenarios. No real implementation is claimed yet.

## Evaluation polish

Failure Lab controls, persistent replay scenario manifests, invariant dashboard evidence, WebSocket delivery if beneficial, demo/viva rehearsals. No ML/profitability work before mandatory execution safety passes.

Neon persistence extension: centralized psycopg store, checksum migrations and requested TypeScript infrastructure policy are prepared. Primary durable target is Neon PostgreSQL; offline SQLite remains available. Remote authentication/link/schema/connectivity/deployment status is recorded in progress/INTEGRATION.md.

## USP layer status (2026-10-08)

Phases 0-12 from `usp_implementation_plan.md` are implemented for the offline/mock bootstrap: authenticated controls, explainable decisions, account net/gross controls, LIMIT price guard, Safety Proof, Reconciliation Center, durable traces, Failure Lab V2, Kill Certificate V2, bounded metrics, isolated 19-case SafetyBench, operational dashboard panels, regression coverage and documentation. This does not change the live-provider blocker: no 021 payload, authentication, stream, reconnect or sandbox behavior was invented, and no remote Neon production data was mutated.

## React migration status (2026-10-08)

The static pages were replaced by a modular React/Vite SPA with protected routes, a centralized credentialed API client, one account-scoped WebSocket provider, responsive operational pages, production SPA fallback, and a multi-stage Docker build. Safety outcomes remain backend-owned and frontend truth-label tests prevent success relabeling. The remaining external blockers are unchanged: real 021 contracts/credentials, sponsor fixtures, production identity, and remote Neon verification.

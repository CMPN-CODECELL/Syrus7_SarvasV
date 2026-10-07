# Implementation status and next phases

## Current: validated mock/replay bootstrap

Implemented: contracts, modular monolith, SQLite schema v2, API and backend-fed dashboard, accounts/subscriptions, three built-in candle strategies, 1m/5m candles, max position/rate/daily loss, atomic directional reservations, mock partial/rejected orders, idempotent accounting, reconciliation, explicit recovery/resume and verified mock kill. Safety/invariant tests cover mandatory S1-S7 and additional failures.

This is a vertical slice, **not completion of the official PS**. Runtime is serialized, so simultaneous strategies share one account/event loop rather than run in separate threads. Demo ends STOPPED; do not label subscriptions RUNNING after replay.

## Next: mandatory hardening before real execution

Member 1: exact sponsor charges, durable configurable policy/session accounting, audit timestamps, charge corrections and stronger ledger projection/property tests.
Member 2: durable external mock scenario, broker event stream, deadlines, explicit cancel acknowledgments, order modification and 021 contract fixtures once provided.
Member 3: durable kill/health latch, bounded kill orchestration, feed/broker freshness, external position quarantine, policy persistence and live opposing-close semantics.
Member 4 completed in mock/replay: callback exception isolation with durable quarantine, bounded symbol-scoped tick dedupe, full indicator warm-up, 3/5 EMA momentum, five-period mean reversion, 5-minute breakout, exact-decimal API projection, normalized account/subscription APIs, durable per-strategy controls and backend-evidence dashboard. Remaining external work: authoritative 021 normalization, reconnect/backfill, exchange-session/freshness fixtures and authenticated account boundaries.

Exit: failures preserve invariants after process restarts and event reorderings; no safety state silently resets; all UI health assertions backed by fresh evidence.

## 021 sandbox integration

Obtain sponsor contract/credentials first. Implement the existing provider interfaces and canonical mapping. Confirm identity, partial fills, snapshot completeness, timeout resolution, charges, rate limits and ten-second verified target. Run adapter contract tests and end-to-end sandbox scenarios. No real implementation is claimed yet.

## Evaluation polish

Failure Lab controls, persistent replay scenario manifests, invariant dashboard evidence, WebSocket delivery if beneficial, demo/viva rehearsals. No ML/profitability work before mandatory execution safety passes.

Neon persistence extension: centralized psycopg store, checksum migrations and requested TypeScript infrastructure policy are prepared. Primary durable target is Neon PostgreSQL; offline SQLite remains available. Remote authentication/link/schema/connectivity/deployment status is recorded in progress/INTEGRATION.md.

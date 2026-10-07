# Testing

Run `python -m pytest -q --basetemp=.pytest-tmp`. The explicit workspace temp directory avoids Windows sandbox temp restrictions and works from a clean checkout. Run `python -m ruff check .` and `python -m ruff format --check .`. Automated GitHub CI is not yet configured.

`tests/test_safety.py` is a deterministic unit/integration foundation with injected clock and mock execution evidence. No timing sleeps.

## Mandatory scenarios encoded

S1 BUY100/fill40 -> +40 only.
S2 A+100/B-60/C+20 -> independent virtual positions, broker +60.
S3 filled80 + pending20 + new10 -> rejected at max100.
S4 identical fill twice -> one accounting effect; conflicting duplicate fails closed.
S5 local60/broker80 -> drift/gate blocked.
S6 kill during partial -> gate before emergency authorization, cancel, flatten actual quantity, verify.
S7 recreate platform with durable state and retained external mock -> RECOVERING, restored accounting, reconciliation then explicit resume.

Additional coverage: concurrent reservations, opposite pending exposure, rate-window boundary, daily loss with charges, long/short reversal accounting, broker rejection release, timeout after acceptance, missed-fill replay, fresh mock restart mismatch, disconnect kill failure, opposing virtual kill, OHLCV/duplicate/late ticks, API/dashboard/replay integration.

Member 4 coverage in `test_member4.py`: 3/5 EMA signal, five-candle EMA/mean-reversion warm-up, 5-minute breakout, callback fault quarantine, risk rejection for stopped strategies, durable start/stop state, additive SQLite v1-to-v2 upgrade, exact-decimal API projection, normalized account/subscription APIs, symbol-scoped bounded tick dedupe including mark idempotence, audited late-tick failure, dashboard structure and production-database replay guard.

## Required extensions before live integration

Adapter contract tests for real status/event mapping; snapshot completeness/pagination; stale ticks/marks; cancel/fill race from an asynchronous broker; bounded kill deadlines; durable kill latch; policy/session restart persistence; charge corrections; kill SAFE_LATE; unknown/manual orders; property tests for ledger replay and reservation invariants. Member 4 still requires authoritative 021 normalization, reconnect/backfill and exchange-session fixtures.

Tests passing in mock mode do not establish sponsor API correctness or live kill latency. Never weaken a test to fabricate a success state.

Database tests: `test_database.py` checks config precedence, additive migration constraints/checksums, psycopg binding and sanitized initialization errors. `test_postgres_integration.py` is opt-in with ALGOSHIELD_TEST_DATABASE_URL pointing to an isolated pre-migrated DB; its writes roll back. Run `sh scripts/setup_local_postgres.sh` and use `postgresql:///algoshield_test` for local validation. A skipped integration test is reported, never presented as remote verification. Do not use production for integration tests or demo seeds.

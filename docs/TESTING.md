# Testing

Run `python -m pytest -q --basetemp=.pytest_cache/tmp`. The explicit workspace temp directory avoids Windows sandbox temp restrictions. Run `python -m ruff check .` and `python -m ruff format --check .`. GitHub CI runs these checks on Python 3.13.

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

## Required extensions before live integration

Adapter contract tests for real status/event mapping; snapshot completeness/pagination; stale ticks/marks; callback exceptions; cancel/fill race from an asynchronous broker; bounded kill deadlines; durable kill latch; policy/session restart persistence; charge corrections; kill SAFE_LATE; unknown/manual orders; property tests for ledger replay and reservation invariants.

Tests passing in mock mode do not establish sponsor API correctness or live kill latency. Never weaken a test to fabricate a success state.

Database tests: `test_database.py` checks config precedence, additive migration constraints/checksums, psycopg binding and sanitized initialization errors. `test_postgres_integration.py` is opt-in with ALGOSHIELD_TEST_DATABASE_URL pointing to an isolated pre-migrated DB; its writes roll back. Skipped integration is reported, never presented as remote verification. Do not use production for integration tests or demo seeds.

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

P0 integration tests (`test_p0.py`) recreate the platform and external mock from disk, verify corrupt evidence fails closed, and observe partial/rejected/risk-rejected orders and kill through HTTP. CI configuration is now present in `.github/workflows/tests.yml`.

Risk policy tests (`test_risk_policies.py`) cover durable policy/loss halt after restart, invalid finite/integer limits, authoritative API changes, reservation conversion/release and lowered limits retaining open exposure. SQLite upgrades are additive/versioned; PostgreSQL hashes normalize newlines across operating systems.

Recovery tests (`test_recovery.py`) verify incomplete/stale/conflicting/missing snapshots, zero-net missing history, event reordering, duplicate snapshot fills, fresh receive vs old LIVE event time, persisted marks/latch/certificate, verified reset and strict reduce-only behavior. Legacy safety fixtures now supply explicit fresh market evidence instead of assuming a price feed exists.

Kill tests (`test_kill.py`) cover hung submission/snapshot calls with event-controlled release, kill/dispatch race, cancel/fill race, delayed cancellation, convergent partial exits, SAFE_LATE and absent UNKNOWN resolution. Broker workers cannot mutate local accounting. Default total kill deadline is nine seconds; timeout remains uncertain until settled complete evidence. Current suite: 57 passed, 1 optional PostgreSQL skipped.

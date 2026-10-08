# Testing

Run `python -m pytest -q --basetemp=.pytest-tmp`. The explicit workspace temp directory avoids Windows sandbox temp restrictions and works from a clean checkout. Run `python -m ruff check .` and `python -m ruff format --check .`. For the SPA run `npm --prefix frontend ci`, `npm --prefix frontend run test`, `npm --prefix frontend run lint`, and `npm --prefix frontend run build`.

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
P0 integration tests (`test_p0.py`) recreate the platform and external mock from disk, verify corrupt evidence fails closed, and observe partial/rejected/risk-rejected orders and kill through HTTP. CI configuration is present in `.github/workflows/tests.yml`.

Risk policy tests (`test_risk_policies.py`) cover durable policy/loss halt after restart, invalid finite/integer limits, authoritative API changes, reservation conversion/release and lowered limits retaining open exposure. SQLite upgrades are additive/versioned; PostgreSQL hashes normalize newlines across operating systems.

Recovery tests (`test_recovery.py`) verify incomplete/stale/conflicting/missing snapshots, zero-net missing history, event reordering, duplicate snapshot fills, fresh receive vs old LIVE event time, persisted marks/latch/certificate, verified reset and strict reduce-only behavior. Kill tests cover bounded calls, cancel/fill races, convergent exits, SAFE_LATE and absent UNKNOWN resolution. Failure Lab tests cover deterministic HTTP scenarios and expiring/restart proof. Browser smoke remains opt-in and must use isolated offline SQLite.

USP suites cover control-plane authentication/ownership, structured risk explanations, account net/gross exposure and races, LIMIT-price reasonability, proof freshness/read-only behavior, reconciliation deltas, durable trace correlation, Failure Lab V2, Kill Certificate V2, bounded metrics and the isolated 19-case SafetyBench. React tests cover cookie API behavior, protected routing, session eviction, truthful safety labels, visual rendering of nested backend evidence, vertically wrapping budget metrics, vertically stacked reconciliation evidence, mobile drawer navigation, and rejection of non-JSON API responses. Current validation (2026-10-08): 299 Python tests passed, 1 environment-gated PostgreSQL integration skipped; 14 frontend tests passed; Ruff, ESLint, and Vite production build pass. No performance number is hard-coded as a product claim.

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m ruff check .
python -m ruff format --check .
```

## Current remediation checks (2026-10-09)

Historical counts above remain historical. Build the ignored SPA assets before backend HTTP page tests. Use `python -m scripts.rehearsal_runner` from a fresh checkout to avoid script-directory import issues; on Windows set PYTHONIOENCODING=utf-8. Create data/ before using a fresh ignored --basetemp=data/<run>.

`tests/test_operator_authority.py` adds explicit-grant/ordinary-user denials, restart/revoke provisioning, owner controls, nested two-account response families, mock-only rejection and preservation of global verdicts. Stale telemetry source-string assertions were replaced by existing behavioral Vitest coverage (logout/account change, HTTP 401 and WS 1008) while backend lifecycle coverage remains. Migration 011 and SQLite v12 are forward-only; real PG integration remains skipped without an isolated URL. The authoritative command/results table and implementation SHA are in progress/INTEGRATION.md. Node 23.6.0 passed local checks with package engine warnings; use a Node version satisfying the locked packages (e.g. 24.15+) for a supported environment. No lockfiles or dependency audit fixes changed.

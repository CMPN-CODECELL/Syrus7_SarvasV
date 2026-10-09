# Offline Acceptance Matrix

Revision: `1c3be6af5405315b3b7ce020952c8bc2861dede1` (Task 6 preparation).

| Capability | Implemented | Fixture-verified | Sandbox-verified | Status / owner |
|---|---|---|---|---|
| Provider order mapping and trade ingestion | 021 adapter persists mappings and polls per-order REST trades | Synthetic complete-snapshot fixture drives `Platform.sync_broker_updates()`; fill is applied before terminal `FILLED` | Read/auth/WS only; no write | BLOCKED: UCC/account order-WS lookup and trade-ID scope, Member 2 + Member 1 |
| Cancellation and terminal outcomes | Canonical cancellation preserves fills and rejects UNKNOWN cancellation | Mock cancel, rejection, late-fill, and broker-update fixtures | No provider cancel | BLOCKED: 021 terminal cancel evidence, Member 2 |
| UNKNOWN/reconnect/reconciliation | Fail-closed recovery and explicit resume | Recovery/disconnect/incomplete snapshot fixtures | Today/current read endpoints remain incomplete | BLOCKED: provider coverage horizon, Member 2 / provider |
| Ordinary normal exits | Policy objects create exit intents | Policy fixtures | None | BLOCKED: no reviewed structured `OrderIntent` action field; Member 2 then Member 3 |
| Emergency reduction and kill | Serialized residual reproof and mock kill certificate | Kill/race/late-fill fixtures | None | BLOCKED: live cancel/close/position capability, Member 2 / provider |
| Opposing strategies | Independent attributed virtual ledgers and account risk | Mock/rehearsal and ledger fixtures | None | BLOCKED: live ownership cannot derive from account net, Member 1 + Member 2 |
| Mandatory strategies | 09:15/no-late-entry, 15:15 residual policy, official-open/fill-WAP policy | Deterministic policy fixtures; runtime test proves resume is fail-closed without subscription acknowledgement | No strategy order lifecycle | BLOCKED: provider subscription acknowledgement, normal reducing-intent contract and provider lifecycle, Member 2 / Member 3 |
| Persistence | SQLite transactions, rollback, restart and duplicate handling | SQLite fixtures | PostgreSQL opt-in test not run | BLOCKED: authorized non-production PostgreSQL DB, Member 1 |
| Browser release smoke | Isolated loopback smoke script and React tests | React tests pass; script checks desktop/mobile/operator boundaries | Not run: Playwright unavailable | BLOCKED: local browser extra only |

## Evidence boundary

`tests/test_021_end_to_end.py` uses an explicitly **synthetic** adapter subclass
that attests `is_complete=True`. This proves composition only. The production
021 adapter continues to report `is_complete=False`; no fixture enables
readiness, resume, flatness, reconciliation completeness, or a live kill claim.

The account/UCC mapping fixture is deliberately strict-xfail until Member 2
supplies a proven scoped mapping, with Member 1 reviewing fill-identity scope.
It accepts only the final `AssertionError`, so setup, protocol, or other
unexpected regressions still fail. Remove the marker only when a provider UCC
can be proven to select the correct local account and the fixture returns the
account-B mapped update rather than cross-attributing or dropping it.

The runtime official-open fixture is a passing fail-closed test: it expects the
specific `PROVIDER_SUBSCRIPTION_EVIDENCE_UNAVAILABLE` resume rejection. Socket
connectivity and a subscribe send are not substitutes. Member 2 must supply
canonical acknowledgement evidence before that negative assertion can be
replaced with a positive runtime-routing test.

The synthetic composition fixture first makes durable update processing fail
and confirms that the provider still offers the fill for retry. It then makes
the post-apply acknowledgement fail once and confirms the replay is financially
idempotent before the next acknowledgement clears the provider evidence.

## Final Task 6 diff verification

At base revision `1c3be6af5405315b3b7ce020952c8bc2861dede1` plus the uncommitted
Task 6 diff, the focused acknowledgement/identity tests report **11 passed, 1
expected xfail**. The full backend run collected 465 tests and finished in
142.515 seconds with **460 passed, 1 expected xfail, 1 skip, 3 failed**. The
skip is the intentionally unconfigured isolated PostgreSQL test database. The
three failures are `test_auto_mode_buys_strongest_candidate_and_exits_at_profit_target`,
`test_auto_mode_never_bypasses_stopped_global_gate`, and
`test_authenticated_candle_api_filters_symbol_timeframe_and_provider`; their
production and test files are outside this diff, so this Task 6 verification
does not change or mask them. They require the owning strategy/API review
before release acceptance can be claimed.

Full Ruff lint passes. Full Ruff format-check reports pre-existing formatting
in `backend/market_data/catalogue.py`, `backend/reliability/control.py`,
`backend/shared/postgres.py`, `tests/test_admission_recovery_safety.py`, and
`tests/test_market_pipeline_visibility.py`; the changed Task 6 Python files
are formatted. `git diff --check` passes.

## Authorized next checks

PostgreSQL, only with an authorized non-production URL:

```powershell
$env:ALGOSHIELD_TEST_DATABASE_URL = "postgresql:///algoshield_test"
.venv\Scripts\python.exe -m pytest -q tests/test_postgres_integration.py --basetemp=data\postgres-acceptance
```

Browser, after the optional Playwright package and Chromium browser are made
available locally:

```powershell
.venv\Scripts\python.exe scripts\browser_smoke.py --output data\browser-evidence
```

There is no checked-in 021 sandbox write/cancel/kill CLI. Per
`docs/021/INTEGRATION_BLUEPRINT.md`, those operations require a separately
authorized isolated account, quantity/instrument and operator safety preflight;
Member 2 must provide a reviewed, bounded command or test harness before any
write is executed.

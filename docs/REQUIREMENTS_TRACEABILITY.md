# AlgoShield — PS-06 Requirements and Verification Matrix

> Baseline derived from the supplied PS-06 text and `docs/REQUIREMENTS.md`. Exact sponsor-original provenance is pending verification. This is a living *traceability* checklist, not a declaration that tests have passed. Version 2026-10-09.

Status legend: IMPLEMENTED_VERIFIED means fresh scoped mock evidence linked in `progress/INTEGRATION.md`; IMPLEMENTED_UNVERIFIED means code exists without environment verification; UNKNOWN/BLOCKED retain external uncertainty. `OPEN` marks sponsor interpretation questions.

| ID | Required outcome | Likely current owner/file | Acceptance fixture | Demo/evidence | Status |
|---|---|---|---|---|---|
| PS01 | User account creation/login | `backend/api.py`, auth/Store, React auth | Registration, login, logout, expiry, denied anonymous access | Account session | IMPLEMENTED_VERIFIED (mock) |
| PS02 | Strategy subscriptions | `backend/strategies/runtime.py`, `backend/platform.py` | Subscribe, stop/start, durable ownership, warmup | Strategy lifecycle | IMPLEMENTED_VERIFIED (mock) |
| PS03 | Raw tick → 1m and 5m OHLCV | `backend/market_data/candles.py` | Boundary, gap, duplicate, late, per-tick volume fixtures | Candle evidence | IMPLEMENTED_VERIFIED (mock) |
| PS04 | At least one candle-based entry | `backend/strategies/runtime.py` | Closed 1m/5m candle causes valid signal, incomplete cannot | Signal trace | IMPLEMENTED_VERIFIED (mock) |
| PS05 | Place orders via 021 developer sandbox | `backend/broker/adapters.py` and future verified 021 boundary | Actual authenticated order and ID response | Broker-native evidence | BLOCKED (021) |
| PS06 | Track broker executions, partial fills, rejects | `backend/execution/orders.py`, broker events | 100 order → 40 fill → 60 outstanding; reject has zero fill | Order/fill table | Mock IMPLEMENTED_VERIFIED; live BLOCKED |
| PS07 | Exact strategy trades, positions, net P&L after charges | `backend/accounting/ledger.py` | Decimal weighted average, partial exit, reversal, charge, unique execution, attribution | Independent ledgers | Mock IMPLEMENTED_VERIFIED; live charge model OPEN |
| PS08 | Maximum position per strategy | `backend/risk/gateway.py` | Filled+pending directional endpoints | Reasoned rejection | IMPLEMENTED_VERIFIED (mock) |
| PS09 | Maximum daily loss per strategy | ledger/risk + marks | IST day, realized+unrealized−charges, stale mark, loss halt | Loss budget | IMPLEMENTED_VERIFIED (mock); exact sponsor formula OPEN |
| PS10 | Orders/minute per strategy | `backend/risk/gateway.py` | Rolling (now−60,now] admitted orders incl later broker reject | Rate evidence | IMPLEMENTED_VERIFIED (mock) |
| PS11 | Platform, not strategy, enforces risk | `backend/platform.py`, risk, execution | Unapproved/stopped intent cannot reach broker | Trace | IMPLEMENTED_VERIFIED (mock) |
| PS12 | Emergency stop strategies, cancel orders, close positions within ten seconds | `backend/reliability/control.py` | Paused dispatch, late fill, pending cancel, restart, timestamped final broker verification | Historical certificate | Mock IMPLEMENTED_VERIFIED; 021 close semantics OPEN |
| PS13 | ≥3 simultaneous strategies on shared account | Runtime/subscription | Three active instances process same feed/account | Strategy cards | IMPLEMENTED_VERIFIED (mock) |
| PS14 | Opposing long/short positions separately accounted | Ledger + account projection | A+100 B−60 C+20 → account+60, gross180; net0 A+100 B−100 | Dual-scope view | Mock IMPLEMENTED_VERIFIED; live liquidation OPEN |
| PS15 | Live subscriptions and P&L dashboard | `frontend/src`, `backend/api.py` | Authenticated snapshot/WebSocket updates, 401/1008 clears stale state | UI | IMPLEMENTED_VERIFIED (mock) |
| PS16 | Evaluation: hidden tests, change request, viva; profitability not basis | `tests/`, `scripts/rehearsal_runner.py`, docs | Reproducible end-to-end, extension/change regression | Demo + test report | Prep ongoing |

## Global correctness/release assertions

- No risk bypass, duplicate financial mutation, invented fill, or unauthorized cross-account control.
- Missing execution/broker history, stale data, unresolved dispatch, and unverified emergency closure must not become green safety verdicts.
- Broker **net flatness** and **strategy virtual flatness** are separate; verify both if the accepted requirement says both. Real 021 close policy is unresolved.
- `SUCCESS` kill requires actual end-state evidence inside the stated <10s implementation definition; otherwise `SAFE_LATE` (verified late) or `FAILED` (unverified). The sponsor's precise timing and product semantics require confirmation.
- Do not count mock credentials, mocked charges, replay ticks or mock certificate as 021 sandbox compliance.

## Updating this matrix

When a test actually runs on the current `dev` commit, add commit SHA, command, output and environment to `docs/progress/INTEGRATION.md` (or linked report); then set the specific row `VERIFIED_CURRENT_COMMIT`. When 021 docs/fixtures arrive, append provenance to `docs/021_API_UNKNOWN.md` and new accepted decisions to `docs/DECISIONS.md`.

DEC-026 security evidence: `tests/test_operator_authority.py` exercises explicit operator grants/revocation, mutation-free 401/403, nested two-account responses and unchanged global safety truth. Existing PS01-PS04, PS06-PS15 mock suites and seven rehearsals pass; these labels do not certify live 021, real charge semantics or PostgreSQL. PS16 preparation remains ongoing.

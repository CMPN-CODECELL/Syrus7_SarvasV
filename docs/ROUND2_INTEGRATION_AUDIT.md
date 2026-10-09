# Round 2 integration audit — 2026-10-09

Start: `dev` at de126deb3af6fb26e6142ace54515fc2f2d9a4be. Fetched
origin/dev matches; origin/main remains dd21746 and is one commit behind dev.
Local main remains 8e5ee50. No member refs or named reports (4)–(7) exist
in this checkout. Their reported counts are not integration evidence.
The sole initial untracked file, ROUND2_RESEARCH_UPDATE.md, has a
checksum-verified external temporary backup. No production database access.

| Finding | Current location / evidence | Verdict | Required change / regression |
|---|---|---|---|
| M2 OPEN → zero-fill REJECTED | orders.py LEGAL_TRANSITIONS omits transition; UNKNOWN rejection covered in test_broker_updates | ADAPT: confirmed defect | Add OPEN rejection fixture before minimal transition; filled rejection remains forbidden |
| M2 raw provider ID distinct from local ID | CanonicalOrder/order/update/snapshot all use normalized platform IDs; submit attribution explicitly rejects raw mismatches | DEFER provider mapping; keep canonical boundary | Real adapter must durably normalize provider/account identity in all submit/event/cancel/snapshot paths. No 021 schema available; do not add an unused nullable column |
| M2 duplicate/overfill/UNKNOWN/cancel races | test_execution_state_machine, test_broker_updates, test_cancellation, test_recovery, test_kill | KEEP | Rerun; no wholesale member patch |
| M1 Decimal ledger and traces | ledger.py, tracing.py; test_member1/test_charges/test_tracing | KEEP | Reuse fill truth; no ledger rewrite |
| M1 corrections/busts/late fees | conflicting fill ID fails closed; canonical events have no correction or independent fee revision | DEFER | Document supported/unsupported/unknown capability table; no invented economics |
| M1 O(history) replay | ledger projection rebuilds history; no measured failure | DEFER P2 | Profile before financial cache |
| M3 risk numbers | gateway.py rejection details include current, pending, request, projected and account net/gross | KEEP | Existing test_risk_explanations/test_account_risk |
| M3 login limiter/headers/audit | API login has no limiter or sanitized outcome audit; no header middleware | ADAPT P1 | Bounded single-worker monotonic failure limiter, generic 429, outcome-only audit and tested headers |
| M3 browser Origin | cookie-authenticated WS accepts any Origin; HTTP has no explicit Origin guard | ADAPT P0 | Same-origin browser guard before auth/mutation; preserve explicit bearer/nonbrowser use; negative WS and mutation-free HTTP regressions |
| M4 financial/status projection | snapshot domain + StrategiesPage use financial_position; Money absence is unknown | KEEP | Reuse current React/account scope |
| M4 partial/signal evidence | OrdersPage omits filled quantity; runtime already emits candle_start/interval/reason signals | ADAPT P1 | Render filled/requested and scoped emitted signal fields; no calculations |
| M4 alternate candle aggregator/locks | canonical candles.py directly builds 60/300 intervals; member patches unavailable | REJECT transplant | Existing candle/replay tests; no lock changes |
| G1 DEC-026 | test_operator_authority account/operator regressions | KEEP | Full regression; no automatic role grants |

Planned code: backend/execution/orders.py, backend/api.py, a focused
backend/shared/browser_security.py helper, tests/test_round2_security.py,
tests/test_broker_updates.py, frontend/src/pages/OrdersPage.jsx and focused
React tests. Owners: Member 2 execution; Member 3 security; Member 4 display;
shared integration preserves Member 1 accounting. No migration is proposed.

Documentation archival follows an inbound-reference inventory; canonical
contracts, decisions, requirements, runbooks and original history remain.
Exact fresh validation and final provenance will be recorded in INTEGRATION.md.

## Final disposition — DEC-027

The matrix above is the initial hypothesis inventory. Four later-added member
reports were inspected and initially retained verbatim, then removed from the
active tree by main cleanup commit `2030c8e`. Their adjudicated findings remain
in [Round 2 Research Update](ROUND2_RESEARCH_UPDATE.md) and the active
[Team Execution Plan](TEAM_EXECUTION_PLAN.md). They described different reported
baselines and absent patches; no member branch was merged.
Member 3's PBKDF2 claim did not match dev's salted SHA-256. Member 4's timestamp
dedupe/5m-rollup description did not match canonical event-ID/direct intervals.
The user approved the targeted work after this review.

| Task | Final status / evidence |
|---|---|
| A rejection | VERIFIED IMPLEMENTED: zero-fill OPEN rejection, duplicate idempotence, reservation release/restart; partial rejection denied; existing UNKNOWN/cancel/late-fill tests retained |
| B Origin | VERIFIED IMPLEMENTED: configured exact Origins, deny missing/null/untrusted cookie mutation/WS, explicit bearer compatibility, no Host/forwarded authorization |
| C password | VERIFIED IMPLEMENTED: PBKDF2-SHA256 v1/600000, constant-time compare, legacy successful-login CAS upgrade, wrong/malformed/concurrent/operator tests; no schema change |
| D login | VERIFIED IMPLEMENTED: monotonic bounded peer limiter including concurrent attempts, 5/60s, expiry, success removes its own slot; generic responses, headers, outcome-only audit |
| E identity | VERIFIED IMPLEMENTED: both mocks previously returned another intent on ID collision; independent failing tests now pass. VERIFIED EXISTING: canonical ID submit/fill/cancel/snapshot contracts. Real compound provider/account mapping: DEFERRED — DEPENDENCY |
| F UX | VERIFIED IMPLEMENTED: backend executed/requested including absent values; scoped strategy/candle signals; account/session data eviction reused |
| Core architecture | VERIFIED EXISTING: full regression and 7 rehearsals; no ledger/candle rewrite, migration, dependency or lockfile change |
| Corrections/late fees/cache | DEFERRED — DEPENDENCY for source events; cache deferred pending measurement |
| PostgreSQL/021/browser deployment | UNVERIFIED: isolated PG skip, no sponsor credentials/API, no browser-driver/public deployment claim |

Red tests: corrected exploratory fixture produced 1 genuine failure / 1 pass;
security suite produced 9 failures / 5 passes before changes; UI 2 failures;
mock identity collision 2 failures. No failing assertion was deleted for green.
Final full Python: 372 passed / 1 PG skipped in 128.46s. Vitest: 30 passed / 7
files. Ruff lint/format, ESLint, Vite, root TS and 7 rehearsals passed.
Initial format check found two touched files; corrected format check passed
(95 files). Commands, commit provenance and residual risks: progress/INTEGRATION.
Documentation inventory before/after: 42 → 47 Markdown files, zero broken local
file links; original bodies moved with Git plus old-path redirects. File count
increases to preserve history, while active full proposal content decreases.

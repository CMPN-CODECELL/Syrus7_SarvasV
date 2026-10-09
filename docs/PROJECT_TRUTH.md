# AlgoShield — Project Truth and Agent Entry Point

> Status: APPROVED **design baseline**, not certification of the current checked-out code. Version: 2026-10-09 (Research Sessions 1–7). Owner: project integration lead. Read with `AGENTS.md`.

## Read order and authority

1. Sponsor-authenticated PS-06 statement, when available; until then `docs/REQUIREMENTS.md` is the **working, provenance-limited** requirement baseline. `docs/PS.md` now contains the supplied PS-06 statement; sponsor-authenticated provenance remains pending.
2. **Executable repository + fresh tests on the checked-out commit** establish what is actually implemented. A report of tests on another branch is not verification.
3. `docs/PROJECT_TRUTH.md` establishes current accepted design; `docs/IMPLEMENTATION_DELTA.md` explains what to check/change; `docs/REQUIREMENTS_TRACEABILITY.md` maps scope to evidence; `docs/RESEARCH_DECISIONS.md` records sources, unresolved claims and adoption decisions.
4. Existing `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/SAFETY_INVARIANTS.md` and append-only `docs/DECISIONS.md` give executable-facing detail and design history. Resolve contradictions against source/tests and accepted decisions; do not silently overwrite.
5. `docs/progress/INTEGRATION.md` and member logs are **historical reported evidence**, not automatically the current branch's status.
6. Long research files (`AlgoShield (1).md`, `usp_implementation_plan.md`, pasted notes) are historical proposal inputs; **not authoritative backlog instructions**.

Every claim must be tagged `REQUIRED`, `REPORTED_IMPLEMENTED`, `VERIFIED_CURRENT_COMMIT`, `ACCEPTED_DESIGN`, `PROPOSED`, `UNKNOWN` or `BLOCKED`. Only actual executed tests and inspected code can justify `VERIFIED_CURRENT_COMMIT`.

## Product definition

AlgoShield is an **evidence-driven safety and execution control plane for multiple automated strategies sharing a brokerage account**. Tagline: **Strategies propose. The platform decides.** It enables account registration/subscription, tick→1m/5m candle-based strategy signals, three or more concurrent strategy instances, platform-owned risk limits, broker orders and partial/rejected fills, independent strategy accounting and net P&L after charges, live dashboard, recovery and a ten-second **verified emergency-shutdown requirement**. Profitability, ML forecasting, microservices, a strategy marketplace and arbitrary untrusted Python uploads are out of scope.

The product must distinguish **intent vs order vs execution vs position** and **account broker net vs virtual per-strategy exposure**. A broker-flat account can have nonflat virtual strategies; these are not interchangeable safety claims.

## Canonical architecture (freeze boundaries, not unverified implementation)

`MarketDataProvider -> CandleBuilder -> StrategyRuntime -> OrderIntent -> RiskGateway -> OrderManager -> BrokerAdapter -> Canonical Fill -> Ledger`

Cross-cutting: `Reliability/Reconciliation/Kill`, `PostgreSQL Store`, `authenticated FastAPI`, `React/Vite UI` and a mock-only `Failure Lab / SafetyBench`. Reconciliation independently checks the continuously maintained financial state; it is **not** an inline step after each fill.

- **Runtime:** Python/FastAPI modular monolith, one authorized execution worker. Callback calculations run outside control-plane locks using bounded pure workers with generation invalidation. Threads are not a malicious-code sandbox.
- **Persistence:** PostgreSQL/Neon target, SQLite only for explicitly selected offline/mock. Applied SQL migrations and their checksums are immutable. Never silently fall back to SQLite after configured PostgreSQL failure.
- **Frontend:** React/Vite (`frontend/src`) is canonical per DEC-025. `frontend/static_dashboard.html` is preserved legacy demonstration material. React only displays backend-computed financial/safety truth. Authenticated single WebSocket with HTTP fallback.
- **Broker:** mock HTTP broker and replay are development/testing infrastructure; 021 API adapter is **BLOCKED/UNKNOWN** pending authentic sponsor contract/credentials. Do not fabricate endpoints, charges, account models or performance.
- **Financial truth:** unique attributed effective broker executions drive Decimal positions, weighted-average costs and realized/unrealized/net P&L. Pending orders never create positions. Identical duplicate fills are idempotent; conflicting duplicate/correction handling requires explicit evidence.
- **Risk:** serialize admission/check/reserve with changing policies and kill gate. Worst-case pending buys and sells are evaluated independently; account net/gross policies are optional/configurable. UNKNOWN submissions conservatively retain exposure.
- **Reliability:** closed/unknown state fails closed; startup RECOVERING, successful reconciliation STOPPED, explicit authorized resume only. Broker evidence must have sufficient coverage, freshness and consistency. Do not synthesize balancing fills or infer an absent UNKNOWN from an incomplete open-order list.
- **Kill:** latch/close gate before waiting; stop callbacks; account for in-flight submissions; cancel; observe fills and positions; apply only authorized reductions; repeat and verify. `SUCCESS` requires all accepted mock criteria inside ten seconds; `SAFE_LATE` verifies later; `FAILED` does not establish safety. External broker execution under ten seconds is not guaranteed. Live opposing-position closure remains sponsor-dependent.
- **Security:** derive account identity server-side. All account-scoped views/actions and global mutations require appropriate auth/authorization; Failure Lab/SafetyBench must be inoperable against live or remote non-mock broker environments.

## Five coherent product differentiators (candidate claims until tested)

1. **Explainable Execution Authority:** risk decision, reservation, broker command and actual fill share an auditable trace.
2. **Evidence-Gated Recovery:** recover only attributable facts; report UNKNOWN otherwise.
3. **Dual-Scope Exposure:** per-strategy ledgers plus broker net and optional virtual gross risk.
4. **Verified Emergency Shutdown:** evidence-scoped, measured result rather than cancel-request success.
5. **Adversarial Reliability Lab:** isolated deterministic mock cases proving the four capabilities; scenario PASS means expected containment, not necessarily successful trading.

## Current evidence baseline (historical, re-verify)

Uploaded 2026-10-08 integration progress reports merge builds with **311 Python passed / 1 PostgreSQL skipped**, **14 frontend tests**, **7 rehearsal scenarios**, and successful lint/type/build checks. Fresh 2026-10-09 remediation evidence is recorded in `docs/progress/INTEGRATION.md`; historical counts here are not current validation. DEC-019 through DEC-025 report bounded callbacks, authenticated account-scoped telemetry, evidence USP modules, and React SPA. Do NOT rebuild these from scratch. Older `PHASE_PLAN.md` and `usp_implementation_plan.md` statuses may be superseded.

## Hard blockers / open sponsor questions

- 021 authenticated API schemas and client/execution IDs; order/reject/cancel/partial fill/UNKNOWN semantics; completeness and consistency of historical snapshots; charges and correction events.
- Live shorting/netted opposing virtual positions and emergency close sequencing; the exact sponsor interpretation of ten-second success.
- Isolated Postgres tests, remote Neon project identity and production deployment/identity readiness. Explicit operator authorization and account response isolation are implemented and locally verified under DEC-026; see the current integration record. DEC-009 names `muddy-tooth-14996153`; a member log mentions `soft-glade-57602806`. These may be separate environments: inspect and obtain authorization; never choose blindly or touch production data.

## Non-negotiable change rules

Do not bypass RiskGateway; invent fills; turn unknown into verified; trust client account IDs; run mock fault injection against live; edit applied migrations; force-push; or push to main. Preserve existing local changes before git operations. Work on `dev` or an integration branch targeting `dev`. Documentation/status updates follow successful evidence, not vice versa.

**Next read:** [`IMPLEMENTATION_DELTA.md`](IMPLEMENTATION_DELTA.md), then [`REQUIREMENTS_TRACEABILITY.md`](REQUIREMENTS_TRACEABILITY.md), then [`RESEARCH_DECISIONS.md`](RESEARCH_DECISIONS.md).

## 2026-10-09 accepted remediation

Round 2 DEC-027 evidence is in [ROUND2_INTEGRATION_AUDIT.md](ROUND2_INTEGRATION_AUDIT.md)
and [integration](progress/INTEGRATION.md). Targeted rejection, browser Origin,
password, bounded login and execution-display changes preserve DEC-026 and the
existing architecture. Member reports describe different baselines, not current
certification. [Archive inventory](archive/README.md) preserves earlier proposals.

DEC-026 establishes durable explicit operators for global actions and a shared nested account response boundary. Ordinary users retain own-account actions; even operator responses are scoped to the operator's account. Global gate, proof verdict, kill result/timing and aggregate operational diagnostics are permitted summaries, never filtered internal financial inputs. SQLite schema v12 adds operator_grants; PostgreSQL migration 011 is packaged but unverified on a real database. See `SECURITY_OPERATIONS.md` and the integration evidence for IMPLEMENTED_VERIFIED / IMPLEMENTED_UNVERIFIED / BLOCKED status.

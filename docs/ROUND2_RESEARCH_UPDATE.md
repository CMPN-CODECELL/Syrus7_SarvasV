# AlgoShield — Round 2 Research Adjudication & Integration Delta

**Date:** 2026-10-09 · **Classification:** review-approved *candidate decisions*; NOT a claim that member-branch changes are merged. **Target:** `dev` only.

## 0. Evidence boundary and baseline

User-reported integrated `origin/dev` baseline: `de126deb3af6fb26e6142ace54515fc2f2d9a4be`; reported clean, 351 Python PASS / 1 PG SKIP, 28 frontend PASS, 7/7 rehearsals. `DEC-026` reports explicit operator grants, common account response scoping, SQLite v12, PG migration 011 packaged but untested against isolated PG. **Revalidate commit, remote refs, code and tests**; an agent's status text is not independently verified by this file.

Four *separate* Round 2 research/implementation handoffs were provided as `AlgoShield (4).md` (Member 1), `(5)` (Member 2), `(6)` (Member 3), `(7)` (Member 4). Their claims must remain `REPORTED_ON_MEMBER_BRANCH` until commit ancestry + actual diff + focused and integrated tests confirm them. Reported branch counts: M2 338/1 skipped, M3 322/1 skipped, M4 324/1 skipped; these counts cannot be added or substituted for the shared baseline. M1's handoff is principally research and does NOT establish that corrections/fee adjustments were built. Reports include untracked test files, possibly modified uv/npm lockfiles, and incomplete Git inventories. The member files `MEMBER_1..4.md` are older progress accounts, not stronger implementation evidence.

**Source authority:** supplied PS-06 text (`PS.md`, sponsor provenance not authenticated) > current source + scoped executed tests for implementation facts > adopted architecture/contracts/DEC decisions for intentions > branch handoffs > external references for *patterns only*. Keep existing canonical risk, execution, accounting, market and API boundaries. No external 021 behavior assumed.

## 1. Brutally critical review of new findings

| Finding | Value / decision | Why, limit, integration action |
|---|---|---|
| **M2 zero-fill OPEN→REJECTED** | **ADOPT conditional P0.** | Real post-accept rejection can be legitimate; only when authoritative evidence establishes `filled_quantity=0`, no conflicting fills and no unresolved submission. Do not allow downgrade after fills, or release risk from ambiguous rejection. Confirm existing state machine and test exact transition; avoid blanket rejection/terminal rule change. |
| **M2 local vs broker order IDs** | **ADOPT P0 contract readiness, if absent.** | A real broker may assign its own ID; keep stable local intent/order key plus optional broker ID. Validate per-provider/account ID uniqueness, mapping persistence, cancellation resolution, late updates and restart. **Do not infer `broker_order_id` is globally unique or that a nullable column/index is sufficient without scoped uniqueness.** Assess actual migrations before adding any. |
| **M2 event ordering via timestamp** | **REJECT invented sequence source.** | Wall timestamps and arbitrary update IDs cannot guarantee causal order. Retain legal transition rules, cumulative-quantity validation, unique execution IDs, no fabricated ordering. Add correction lineage only after provider evidence. |
| **M2 10-case adversarial suite** | **ADOPT tests where missing.** | Protect overfill, duplicate, partial/cancel/late-fill, orphan broker ID, crash/UNKNOWN, incomplete snapshot, correct ledger effect. Tests reported on member branch: verify source is actually available and integrate under existing test organization. |
| **M1 ledger refactor** | **REJECT default rebuild.** | Decimal, weighted-average, reversals, per-strategy attribution and exact fill idempotency are already baseline. No evidence justifies replacing core mathematics. Add independent reference tests if gaps demonstrable. |
| **M1 correction / trade bust** | **ADOPT design, DEFER live implementation.** | Distinguish conflicting duplicate vs authenticated correction/bust referencing original. Preserve immutable raw evidence; quarantine unsupported events. Do not invent FIX/IBKR fields for 021, overwrite fill rows, change `(timestamp,fill_id)` replay silently, or auto-adjust P&L without valid event semantics and tests. Optional mock-neutral prototype only after core P0 and with explicit separate test fixtures. |
| **M1 later fee adjustment** | **ADOPT design, CONDITIONAL integration.** | Existing Decimal charges and mock 0.01 charge do not establish sponsor fees. Preserve estimated/confirmed status distinction in UI only if underlying data exists; don't build invented tax/commission engine. Future idempotent execution-referenced charge adjustments require sponsor fixtures. |
| **M1 reconciliation classifications & trace** | **MERGE into existing systems.** | Existing proof/recovery/trace reported built. Add reason codes/coverage fields only for an actual missing incident distinction. No duplicate services or financial truth stores. |
| **M1 full fill-history replay bottleneck** | **P2 until profiled.** | O(history) projection plausibly hurts throughput but no benchmark demonstrates a current problem. Instrument deterministic workload first. No cached second financial authority absent replay equivalence/restart/correction tests. |
| **M3 numeric rejection explanations** | **ADOPT P1, verify before copy.** | Structured current/pending/requested/projected/limit improves viva and debugging; re-use existing `RiskDecision.details`/reason codes. Must accurately describe *both* worst-case endpoints and account gross; avoid claiming a single scalar risk is definitive. No sensitive cross-account values in response. |
| **M3 login limiter, security headers, auth audit** | **ADOPT focused P1 after auth review.** | Per-IP 5 failures/60s is a proposed local single-worker baseline, NOT distributed brute-force defense; IP may be proxy-controlled and shared. Review clock, process restart, trusted proxy config, success/reset behavior, memory bound, error semantics, audit PII/secret minimization, availability effect and tests. No new Redis/CAPTCHA. Static headers (`nosniff`, framing, referrer) worthwhile with tested compatibility. |
| **M3 WebSocket Origin / CSRF** | **AUDIT P0 for cookie-authenticated control exposure.** | Session token validation alone is not a substitute for browser Origin enforcement. Determine cookie/authorization mode, cross-origin policy and whether mutations need CSRF protections; deny unsafe origins and test with realistic browser requests. Do not claim a WebSocket data channel accepts mutating messages absent code evidence. |
| **M4 enriched subscription P&L, gate and reconciliation status** | **ADOPT only correct projection.** | Historical mismatch between UI keys and API fields could hide KILLED/UNCERTAIN or show zero P&L. Preserve one canonical backend state projection, add compatibility aliases only if consumers require; UI must never infer `RUNNING`/zero P&L from absent values. Avoid duplicating position truth into separately maintained subscription state. Verify against DEC-026 account scoping. |
| **M4 partial-fill display / emitted-signal table** | **ADOPT small P1 UI change if absent.** | Show `filled / requested`, strategy, candle interval/time/reason, explicit unknown, no invented fills/signals. Prefer existing React components; do not revive vanilla UI. |
| **M4 alternate candle implementation** | **DO NOT TRANSPLANT.** | Report refers to `candle_aggregator.py` and 5m rollup of 1m bars; current canonical `backend/market_data/candles.py` builds intervals directly with symbol-scoped IDs. These algorithms are not automatically equivalent under gaps/late/duplicate ticks. Preserve existing tested contracts and only import independent acceptance cases. |
| **M4 lockfile adjustments/untracked tests** | **AUDIT, do not bulk cherry-pick.** | Member reports document modified `uv.lock`, `frontend/package-lock.json` with contradictory listings and untracked acceptance test(s). Inspect staged + unstaged + untracked, commits, exact diffs, dependencies, changed paths; never silently discard another member's local work. |
| **Member reports' benchmarks/score claims** | **CONTEXT, not features or verification.** | IBKR, Kite, FIX, TT, QuantConnect, OWASP are examples of external systems; none demonstrate undocumented 021 semantics, compliance, industry novelty or current deployed safety. Member scoring schemes differ; official PS and actual regressions govern priority. |

## 2. Decision prerequisites, in order

**G0 — Branch provenance and non-destructive integration (P0).** At start record `git rev-parse HEAD`, `git status --porcelain=v1 -uall`, remotes, `origin/dev`, `origin/main`, `merge-base`, member branch refs and commits (if present). Fetch safely. Member reports include no exact merge-ready commit SHA for every change. **Do not automatically merge a branch from a PDF/MD label.** If changes exist only as attached descriptions, convert to testable *gap hypotheses*, not fabricated merged work. Preserve local changes, secrets, ignored files, and current `dev` tests. `origin/main` changed independently (user reports `dd21746`); do not auto-merge it if integration scope or conflicts are unknown. Ask for review of nontrivial divergence.

**G1 — Protect P0 behavior (P0).** Recheck `DEC-026` operator provisioning, revocation, 401/403 mutation-free denial, nested account projection in actions/streams/audit/proof/kill, and fresh backend+frontend tests. None of the new member patches may regress cross-account scope, kill latch, UNKNOWN semantics, 1m/5m candle correctness or three-strategy independent P&L.

**G2 — Broker identity and lifecycle (P0 if gap proven).** Inspect `backend/shared/contracts.py`, `backend/execution/orders.py`, `backend/shared/store.py`, `backend/reliability/snapshots.py`, broker adapters/persistence, migrations and tests. Verify OPEN→REJECTED zero-fill semantics and persisted mapping between local order ID and provider-scoped broker order ID. Add focused independent mock tests **before changing production code**. Change the minimal ownership boundary only if tests reveal missing behavior. Any schema changes additive and separately tested on SQLite; new PG migration packaged but marked unverified without isolated PG. Confirm how historical rows load with `None` ID and old mock order=local order compatibility.

**G3 — Financial evidence (P0 tests / P1 design).** Compare current ledger and reconciliation to duplicate, opposite strategies, external fills, fee discrepancy and missing history. Add correction/fee *capability decision table* (supported/unsupported/unknown) to docs. Do not implement 021-like corrections or finance adjustments without event source semantics. Test that unsupported correction or late fee uncertainty blocks false net P&L/health claims when material; distinguish stale mark from valid historical P&L.

**G4 — Security, risk explanations, product visibility (P1; elevate proven security flaw to P0).** Check whether M3 controls exist in `dev`; if not, add minimal secure tested login limiter, headers and audit; verify cookie CSRF/WS Origin via focused threat cases. Check whether M4 changes exist; if not, adapt to canonical React state, account-scoped response, backend truthful status and source-decimal strings. Add numeric rejection evidence if actually absent. No new user-facing page solely for this report.

**G5 — Reconcile documentation and bloat (P1).** Keep one concise agent index; one product truth, one current gap/backlog, one canonical contract, one architecture, one PS/requirements map, one immutable decision log, one integration status, one security runbook, one testing/demo guide and one 021 unknown tracker. Archive *historical reports and superseded phase plans* into a discoverable `docs/archive/` only after verifying inbound references and preserving history; prefer archival moved in Git with links to original paths. Do not archive normative contracts, applied migration notes, requirements, runbooks or legally relevant/operational documents. Do not bulk delete the member reports, raw research or root files based solely on names. Build a link inventory and check broken links after modifications.

## 3. Priority acceptance matrix

| ID | Fixture and exact assertion | Trigger for code change |
|---|---|---|
| R2-01 | OPEN order with zero fills, authoritative REJECTED → `REJECTED`, filled0, no ledger mutation, correct reservation release; same with previous fill → no invalid terminal rejection | If transition absent/incorrect |
| R2-02 | Local ID `ord-123`, broker ID `brk-999`, execution uses broker ID → one attributed fill, correct cancellation/snapshot after restart; foreign account's broker ID never resolves | If mapping absent/unsafe |
| R2-03 | Same fill replay serial/concurrent/recovery → exactly one economic mutation; conflicting duplicate quarantined | If coverage missing |
| R2-04 | UNKNOWN submit + crash + incomplete snapshot → reservation retained, no retry or false green | If coverage missing |
| R2-05 | Partial fill40 + cancel request + late fill20 + cancel rest40 → position60 and no premature release | If coverage missing |
| R2-06 | Two intents race for final position/account gross capacity, policy lowered between them → no oversubscription or stale-version dispatch | If test reveals gap |
| R2-07 | Reconciliation: identical account net but omitted offsetting fills → not globally verified; attributable missing fill recovered once | If evidence too weak |
| R2-08 | Regular user invokes global kill/reset/reconcile/broker controls → 403 and zero mutation; operator sees no foreign private accounting via nested action response | If DEC-026 regression |
| R2-09 | Bad login burst → bounded 429 without leaking user enumeration/credentials; auth audit excludes passwords/tokens; verify normal user flow | If limiter/audit absent |
| R2-10 | WebSocket from untrusted Origin with cookie → refuse where required; trusted allowed Origin works; logout/1008 clears old data | If browser origin boundary absent |
| R2-11 | KILLED/RECOVERING/UNKNOWN snapshots render exact state, missing position/P&L ≠ 0, strategy per-account attributed P&L matches backend | If M4 integration absent |
| R2-12 | Partial order shows executed vs requested; emitted signals reference correct strategy/candle/time/reason, cross-account filtered | If UI evidence absent |
| R2-13 | Isolated SQLite migration upgrade + restart + old rows + unchanged checksums; isolated PG skipped honestly if unavailable | If schema changed |
| R2-14 | Full mock rehearsals 7/7, regression, lint, React tests/build; no introduced additional failure | Before any push |

**Acceptance source:** direct tests at the same integrated `dev` commit; do not replace tests with reported branch counts or screenshots.

## 4. Documentation structure: compact but not destructive

**Startup order (target):** `AGENTS.md` → `docs/PROJECT_TRUTH.md` → `docs/IMPLEMENTATION_DELTA.md` → task-relevant `docs/CONTRACTS.md`/`ARCHITECTURE.md`/`SECURITY_OPERATIONS.md` → `docs/TESTING.md`. Don't make an AI read 4 long member logs automatically.

**Keep active (check existence before acting):** root `README.md`, `AGENTS.md`; `docs/PS.md` or authentic sponsor file, `REQUIREMENTS.md`, `REQUIREMENTS_TRACEABILITY.md` (merge duplicates *only with trace integrity*), `PROJECT_TRUTH.md`, `IMPLEMENTATION_DELTA.md`, `ARCHITECTURE.md`, `CONTRACTS.md`, `SAFETY_INVARIANTS.md`, `DECISIONS.md`, `SECURITY_OPERATIONS.md`, `021_API_UNKNOWN.md`, `TESTING.md`, `DEMO_AND_DEBUG.md`, `docs/progress/INTEGRATION.md`. A one-page doc index may link these; avoid new additional permanent plan files after this delta is incorporated.

**Archive candidates after reference audit:** `usp_implementation_plan.md`, superseded `PHASE_PLAN.md`, old `design.md` if present and not referenced as authoritative, long `AlgoShield (N).md` research/member studies (if tracked) and verbose historical per-member progress logs. Preserve dated originals, tests, provenance and Git history. If a teammate or automated workflow actively depends on an old path, retain a small redirect/stub rather than silently breaking it. Never archive source files, migrations, fixtures, scripts, current security/deploy runbooks or DEC history.

**Progress management:** Append one short dated verified summary to `docs/progress/INTEGRATION.md` or replace redundant current-status header with links while preserving prior history; move old detailed logs to `docs/archive/progress/` only if all direct references are repaired. Keep one up-to-date status table: FEATURE | VERIFIED at SHA | BLOCKED | OWNER | NEXT ACTION.

**Decisions:** Append a single new numbered `DEC-*` covering accepted round-2 integration/archival rules, not a decision for every cosmetic change. Never edit prior accepted entries except clearly annotated supersession.

**Link sanity:** Scan Markdown links, root references, AGENTS instructions, CI workflows and docs before/after. Use `git mv` for tracked archival changes; don't remove materials just to lower a file count. No duplicate contradictory active backlogs.

## 5. Sponsor gates and rejected work

`Broker021Adapter` remains `UNKNOWN/BLOCKED` pending authenticated payloads, credentials and sandbox execution. PG migration 011 and future schema changes require isolated PostgreSQL verification; conflicting Neon project identities must be resolved via authorized configuration, **not by guessing or touching production**. Broker net flatness ≠ virtual strategy flatness. A `SUCCESS` kill is broker-evidence-dependent, measured end-to-end, not a request-only guarantee. Demo synthetic charges never certify real statutory fees.

Do **not** add: microservices, Redis/Kafka, ML strategy generator, second ledger source of truth, broad ledger rewrite, a timestamp-as-sequence event engine, new candlestick studio, broker-specific FIX/IBKR semantics for 021, unverified claims of regulatory compliance, or whole-branch cherry-picks without diff review.

## 6. Completion evidence and status vocabulary

Report `VERIFIED_CURRENT_DEV` only with SHA, executed command and result; `REPORTED_MEMBER_BRANCH` only with branch/commit evidence; `PROPOSED`, `DEFERRED`, `UNKNOWN_021`, `BLOCKED_PG`, `REJECTED` otherwise.

Agent completion report must give: head SHA before/after; origin refs and divergence; selected findings imported/rejected with reason; exact added/modified files; tests before/after including skips; migration status; docs kept/archived plus broken-link check; current sponsor blockers; commit and push result. Do not claim historical research has been merged solely because this file has been copied into the repository.

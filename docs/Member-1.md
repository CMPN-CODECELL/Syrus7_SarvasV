# ALGOShield

## Round-2 Technical Research & Implementation Handoff

### Member 1 — Akshat

### Execution Truth, Accounting & Reconciliation

**Hackathon:** SYRUS 7.0 FinTech — PS-06: Algo Trading Platform  
**Document purpose:** Implementation-ready research handoff for Round 2  
**Primary research source:** AlgoShield (5).pdf — 81 pages / complete Member-1 research trail through Phase 8  
**Scope:** Execution evidence, fills, positions, P\&L, attribution, charges, reconciliation, broker compatibility, and financial auditability

> **Central financial truth invariant**  
>   
> **ORDER \= INTENT**  
> **FILL \= ACTUAL EXECUTION**  
>   
> An order being submitted, accepted, left open, or cancelled does not by itself create a financial position. Financial state changes from actual execution/fill evidence. This separation is already a strong part of AlgoShield and must be protected throughout Round 2\.

---

## Executive Summary

AlgoShield does **not** need a financial-accounting rebuild for Round 2\. The repository audit and the eight-problem research show that the core accounting model is already strong: orders remain distinct from financial state, positions are derived from persisted fills, partial fills and weighted-average entry are handled, long/short reversals are implemented in both directions, realized and unrealized P\&L are calculated, strategy attribution is enforced, duplicate/conflicting fill handling is present, state is isolated by account/symbol/strategy, restart persistence exists, and reconciliation can fail closed when unexplained drift remains.

The Round-2 opportunity is therefore not “make accounting work.” It is:

> **Make already-correct financial truth more traceable, broker-compatible, correction-aware, auditable, and resilient as execution history and broker integration become more realistic.**

The research identifies eight accounting/execution problems. Four are already correct and should be protected rather than rewritten: **Idempotency, Strategy Attribution, Weighted Average Price, and Reversal Accounting.** Two have a correct foundation but need hardening: **Execution Identity and Reconciliation.** Two are genuine functional gaps: **Execution Corrections and Charges/Adjustments.** **Execution Trace** is the strongest cross-cutting improvement because it turns existing correct relationships into an explainable end-to-end evidence chain.

The five frozen Round-2 improvements are:

1. **M1-I1 — Reconciliation Evidence & Recovery** — score 98/100  
2. **M1-I2 — Execution Trace** — score 93/100  
3. **M1-I3 — Broker Execution Identity \+ Idempotency Hardening** — score 92/100  
4. **M1-I4 — Execution Correction / Trade-Bust Model** — score 83/100  
5. **M1-I5 — Broker-Aware Charge / Adjustment Model** — score 76/100

The strongest technical story is consequently coherent rather than feature-heavy:

- **Reconciliation:** “We know when our state is wrong.”  
- **Execution Trace:** “We can explain why it changed.”  
- **Execution Identity:** “We know exactly which execution happened.”  
- **Correction Model:** “We can handle later broker corrections without destroying history.”  
- **Charge Model:** “Our financial result can evolve correctly when execution costs are finalized.”

The ten documented P0 financial tests should remain the official baseline. Round 2 should add adversarial coverage around concurrency, recovery duplicates, corrections, fee adjustments, restart/reconciliation, PostgreSQL integration, pagination, and large-volume replay — without rewriting the proven accounting mathematics.

### Evidence discipline

The attached research PDF is the source of truth for the current implementation baseline, benchmark findings, scoring, and P0 tests. Where this handoff introduces implementation ordering, contract-impact classification, or likely file touch-points, those are **handoff-level derivations from the documented architecture** and should be verified against the live repository before coding. Any broker-specific 021 behavior remains **021 UNKNOWN / REQUIRES VERIFICATION** until sponsor documentation confirms it.

---

# 1\. Current Gap Analysis

## 1.1 Current architecture and financial boundary

The Member-1 financial chain is:

USER

  ↓

STRATEGY SUBSCRIPTION

  ↓

STRATEGY ORCHESTRATOR

  ↓

STRATEGY

  ↓

ORDER INTENT

  ↓

CENTRAL RISK CONTROL

  ↓

ORDER MANAGER

  ↓

BROKER

  ↓

EXECUTION / FILL

  ↓

ACCOUNTING

  ↓

POSITION

  ↓

P\&L

  ↓

RECONCILIATION

  ↓

DASHBOARD

Member 1 owns the truth boundary beginning with execution evidence and continuing through fill, position, P\&L, strategy attribution, account state, and reconciliation.

### Ownership boundaries

Member 1 should **not** absorb:

- strategy logic or candle generation,  
- central risk-rule implementation,  
- broker connection implementation,  
- raw 021 payload parsing,  
- frontend ownership.

Member 1 receives canonical execution/fill information and turns it into financial state consumed by risk, reliability, product, and UX layers.

## 1.2 Baseline classification

| Area | Current status | What is actually true | Round-2 posture |
| :---- | :---- | :---- | :---- |
| Order / fill separation | **WORKING** | Orders maintain intent/lifecycle; they do not create positions or P\&L | Protect as invariant |
| Fill handling | **WORKING** | Canonical fill identity, validation, atomic persistence, duplicate/conflict handling | Harden concurrency/recovery |
| Positions | **WORKING** | Derived from persisted fills; partial fills, WAP, flat reset, reversal supported | Preserve; stress-test |
| Realized P\&L | **WORKING** | Derived from executed closing/reversal fills and position average | Preserve; stress-test |
| Unrealized P\&L | **WORKING** | Dynamic mark-driven calculation | Preserve; add explicit stale/missing-mark tests |
| Strategy attribution | **WORKING** | Fill maps to canonical order/strategy/account/symbol; mismatches rejected | Make trace visible, do not rebuild attribution |
| Charges | **PARTIAL / NEEDS HARDENING** | Decimal charge accumulation works, but current demo uses synthetic values and lacks standalone post-trade fee adjustment | Build broker-neutral adjustment model; do not invent 021 fees |
| Account financial state | **PARTIAL** | Positions/P\&L/charges/exposure are tracked; cash/margin/collateral/deposit flows are outside current core scope | P2 unless PS-06/021 requires it |
| Reconciliation | **WORKING / NEEDS HARDENING** | Snapshot/fill/position checks, missing-fill recovery, and fail-closed drift control exist | Add evidence classes \+ scalable state |
| Accounting scalability | **NEEDS IMPROVEMENT** | Repeated state queries can replay the full fill history | P2 engineering hardening after P1 |
| Execution corrections | **MISSING** | Conflicting duplicate is handled, but a valid later broker correction/bust is not first-class | P1 build |
| Historical MTM/session summaries | **PARTIAL / ENHANCEMENT** | Dynamic MTM exists; richer historical snapshots are not core | P2 |
| PostgreSQL integration coverage | **PARTIAL** | Support exists; dedicated DB coverage may be skipped when external DB unavailable | P2 verification |
| Fill pagination/filter testing | **PARTIAL** | History endpoint exists; boundary/filter coverage is weaker | P2 |
| Concurrent fill ingestion | **PARTIAL TEST COVERAGE** | Thread-safety exists but explicit concurrency tests are weaker | P0/P1 hardening |

## 1.3 Proven strengths that must not be treated as “missing”

The audit is explicit that these are existing strengths:

- strict Order ≠ Fill separation,  
- actual Fill → Position accounting,  
- partial-fill handling,  
- weighted-average entry price,  
- long/short reversal accounting,  
- realized P\&L,  
- unrealized P\&L,  
- gross and net P\&L,  
- Decimal arithmetic,  
- per-fill charge accumulation,  
- strategy-level virtual accounting,  
- account/symbol isolation,  
- fill idempotency,  
- conflicting duplicate detection,  
- overfill protection,  
- deterministic replay,  
- restart persistence,  
- reconciliation foundation,  
- missing-fill recovery,  
- fail-closed handling of unexplained drift.

The correct Round-2 language is therefore **“protect, harden, extend”**, not **“replace.”**

## 1.4 The most important current engineering gap: repeated full-history replay

Current accounting state calculations can follow the pattern:

positions()

  ↓

\_calculate()

  ↓

SELECT \* FROM fills

  ORDER BY timestamp, id

  ↓

replay ALL history

If history grows to 100,000 fills, repeated queries can repeatedly replay a large dataset. This is a genuine scalability concern. The research deliberately places incremental accounting state/cache below the five headline improvements because it is a performance optimization rather than the strongest PS-06 differentiator.

## 1.5 Current charge-model gap

The arithmetic itself is not the problem. Charges are stored as Decimal, accumulate across fills, and are deducted from gross P\&L to obtain net P\&L.

The limitations are:

1. the mock/replay flow currently uses synthetic charges;  
2. verified 021 fee behavior is unavailable;  
3. there is no standalone financial event for a later fee/commission adjustment.

The engineering response is a **broker-aware charge abstraction**, not a made-up 021 calculator.

## 1.6 Current correction gap

A conflicting duplicate is not the same event as a legitimate broker correction.

SAME EXECUTION ID \+ CONFLICTING DATA

        ↓

DUPLICATE / CONFLICT

        ↓

REJECT / FAIL CLOSED

is a safety rule for conflicting evidence.

A legitimate correction is different:

ORIGINAL VALID EXECUTION

        ↓

LATER CORRECTION / TRADE BUST

        ↓

REVISED FINANCIAL TRUTH

The original execution must remain auditable. The correction should reference it rather than overwrite it invisibly.

## 1.7 Account financial completeness is intentionally not the core Round-2 target

Current core financial state focuses on:

- positions,  
- P\&L,  
- charges,  
- exposure.

Not currently modeled as a full financial ledger:

- cash balance,  
- margin used,  
- margin available,  
- collateral,  
- deposits/withdrawals.

The research classifies this as lower priority. Expanding into a full brokerage accounting system would create scope creep unless PS-06 or the 021 integration makes it necessary.

---

# 2\. Benchmark Findings

The benchmark research compares AlgoShield with **IBKR**, **Kite Connect**, and **FIX** only at the level of execution/accounting semantics. These are professional benchmarks, not evidence of how 021 itself behaves.

## 2.1 IBKR

The research highlights these IBKR concepts:

- execId as an execution identity,  
- separate identity for partial executions,  
- shares for execution-level quantity,  
- cumQty for cumulative executed quantity,  
- avgPrice for average execution price,  
- acctNumber for account attribution,  
- orderId for order identity,  
- remaining in order status,  
- execution corrections through additional execution identifiers,  
- separate commission reporting associated with an execution.

### AlgoShield implications

First, execution identity must be first-class. A partial execution is a real execution event; it is not merely an aggregate update to an order.

Second, execution-related cost can have its own lifecycle. A future broker adapter may need to support:

Execution

   \+

Commission / Fee Event

   ↓

Financial State

rather than assuming all costs arrive permanently attached to the execution object.

### Boundary

**Do not say 021 will expose execId, CommissionReport, or equivalent.** The benchmark only justifies the architecture to be prepared for such concepts.

## 2.2 Kite Connect

The research identifies a particularly clear order/trade separation:

- an order may execute in arbitrary chunks;  
- one order may create multiple trades;  
- each individual trade has its own trade\_id and is linked to an order\_id;  
- order state includes aggregate quantities such as requested, filled, pending, cancelled, and average price;  
- postbacks can report partial-fill lifecycle changes.

The benchmark directly validates:

ORDER ≠ TRADE / FILL

### AlgoShield implications

The existing pattern:

Canonical Order

   ↓

Individual Fills

   ↓

Financial Position

is architecturally correct and should remain intact.

## 2.3 FIX

FIX provides the clearest formal separation between execution events and order state.

Key semantics documented in the research include:

- ExecType — why an execution report was sent;  
- OrdStatus — resulting/current order state;  
- OrderQty — total executable quantity;  
- CumQty — cumulative executed quantity;  
- LastQty — latest execution quantity;  
- LeavesQty — remaining quantity.

The research also covers:

- New,  
- Partially Filled,  
- Filled,  
- Canceled,  
- Rejected,  
- Pending Cancel,  
- Pending Replace,  
- trade correction,  
- trade cancellation.

Most importantly for Round 2:

ExecType \= G  → Trade Correct

ExecType \= H  → Trade Cancel

ExecRefID     → affected execution

This is direct benchmark evidence that later corrections should refer to a prior execution rather than silently pretending the original execution never happened.

## 2.4 Cross-Benchmark Comparison

| Concept | IBKR | Kite Connect | FIX | AlgoShield implication |
| :---- | :---- | :---- | :---- | :---- |
| Independent execution identity | execId | trade\_id | ExecID / execution reference semantics | Keep canonical fill identity; preserve broker identity when available |
| Multiple executions per order | Yes | Yes | Yes | Existing Fill model is correct |
| Aggregate order state | OrderStatus | Order | OrdStatus | Keep order state separate from execution evidence |
| Execution quantity | shares | trade quantity | LastQty | Financial state must use actual executed quantity |
| Cumulative quantity | cumQty | aggregate filled quantity | CumQty | Useful for lifecycle verification |
| Remaining quantity | OrderStatus | pending/unfilled state | LeavesQty | Remains order/lifecycle state, not financial position |
| Execution correction | Documented | benchmark does not establish equivalent semantics here | Trade Correct / ExecRefID | Strong case for first-class correction model |
| Execution cancellation | Documented lifecycle | cancellation state | Trade Cancel / ExecRefID | Correction/bust must be auditable |
| Commission / fee event | Separate CommissionReport association | Not used as proof of 021 behavior | Not treated as proof of 021 | Justifies broker-neutral charge lifecycle design |

## 2.5 Benchmark Conclusion

All three benchmarks reinforce the same architectural principle:

> Professional trading systems separate **order intent/state** from **actual execution evidence**.

They independently identify executions, support multiple executions per order, maintain cumulative execution state, and distinguish execution events from current order status. IBKR and FIX further support the case for explicit execution corrections, while IBKR demonstrates that commission information may have a separate execution-linked lifecycle.

That means AlgoShield's fill-derived accounting architecture is already fundamentally aligned with professional execution semantics. The strongest Round-2 work is therefore at the integration, evidence, correction, and auditability boundaries.

---

# 3\. Eight Accounting / Execution Problems

For every problem, the required structure is preserved: **Current AlgoShield Behavior → Benchmark / Professional Practice → Exact Gap → Recommended Improvement → How We Test It.**

## 3.1 Execution Identity

### Current AlgoShield Behavior

AlgoShield already has canonical Fill identity with fields such as internal fill identity, order relationship, strategy/account context, symbol, quantity, price, timestamp, and charges. fill\_id is used for duplicate detection.

### Benchmark / Professional Practice

IBKR, Kite, and FIX all treat individual executions/trades as independently identifiable records.

### Exact Gap

There is **no core internal identity failure**. The real gap is the future mapping between an external broker execution identifier and the canonical AlgoShield fill identifier.

021 Broker Execution ID

          ↓

Canonical AlgoShield Fill ID

          ↓

Ledger

### Recommended Improvement

Preserve broker execution identity **alongside** the canonical fill identity after the 021 field is verified. Do not replace the internal ID with an unverified broker-specific field.

### How We Test It

For an order of 100:

- broker execution A \= 40;  
- broker execution B \= 30\.

Verify A and B become distinct canonical fills, each maps exactly once, replaying A is a no-op, and the resulting position is \+70.

---

## 3.2 Idempotency

### Current AlgoShield Behavior

Idempotency is already strong:

same fill\_id \+ same economics

        ↓

       no-op

same fill\_id \+ conflicting economics

        ↓

     reject / fail closed

The repository explicitly tests repeated delivery and conflicting duplicate evidence.

### Benchmark / Professional Practice

Execution-level identity and multiple-execution workflows require safe handling of repeated event delivery.

### Exact Gap

No material functional gap exists. The hardening gap is adversarial delivery:

- concurrent duplicate ingestion,  
- duplicate delivery during recovery,  
- persistence failures around insertion,  
- broker-ID mapping once 021 is integrated.

### Recommended Improvement

Keep the existing identity \+ atomic persistence \+ conflict detection model. Add stronger tests at the persistence and recovery boundaries.

### How We Test It

Deliver the same fill serially and concurrently. The final database state must contain one fill, one position mutation, one P\&L effect, and one charge effect.

Then replay the same identity with conflicting price or quantity. The original financial truth remains unchanged and the system fails closed.

---

## 3.3 Execution Corrections

### Current AlgoShield Behavior

Conflict detection is present, but a legitimate later broker correction/bust is not a first-class model.

### Benchmark / Professional Practice

FIX supports Trade Correct and Trade Cancel with a reference to the affected execution. IBKR also documents execution corrections via additional execution identity.

### Exact Gap

AlgoShield currently protects against bad duplicates but cannot yet represent:

Valid execution A

       ↓

Later broker correction to A

       ↓

Revised financial truth

### Recommended Improvement

Add a formal broker-neutral correction/adjustment event with:

- its own identity,  
- a reference to the affected execution,  
- deterministic financial projection behavior,  
- replay-safe idempotency,  
- an auditable relationship back to the original event.

Never implement a silent in-place rewrite such as UPDATE fills SET price \= ... that destroys the historical evidence.

### How We Test It

F1 \= BUY 40 @ 100 followed by a correction to BUY 40 @ 101.

Expected:

- original evidence remains preserved;  
- correction references F1;  
- financial state reflects corrected economics once;  
- replaying the correction twice is a no-op after the first application;  
- an unreferenced correction is rejected or leaves the system fail closed.

---

## 3.4 Strategy Attribution

### Current AlgoShield Behavior

Every fill must map to an existing canonical order with matching strategy, account, symbol, and side context. strategy\_instance\_id provides the strategy-level identity. Unattributed or mismatched fills are rejected.

### Benchmark / Professional Practice

IBKR provides account attribution and Kite links trades to their parent orders. The professional pattern is to preserve execution context rather than flatten it into aggregate P\&L.

### Exact Gap

Attribution correctness is **not missing**. The gap is observability.

The desired audit chain is:

Strategy

  ↓

Intent

  ↓

Risk Decision

  ↓

Order

  ↓

Fill

  ↓

Position

  ↓

P\&L

### Recommended Improvement

Build an execution trace that makes existing attribution and correlation queryable end-to-end.

### How We Test It

Create a strategy order and verify a single trace can retrieve strategy instance, intent, risk decision, order ID, fill ID, position effect, and P\&L effect. Repeat with opposing strategies and confirm isolation.

---

## 3.5 Weighted Average Price

### Current AlgoShield Behavior

WAP is already implemented and covered by tests. Scale-in, scale-out, flat reset, and reversal behaviors are deterministic.

### Benchmark / Professional Practice

IBKR exposes average execution price and cumulative quantity; Kite exposes average price with filled quantity/trades; FIX tracks cumulative and latest quantities across execution reports.

### Exact Gap

No material mathematical gap exists.

### Recommended Improvement

Protect the formula and expand precision/stress coverage rather than changing the implementation.

Core invariant for increasing a position:

avg\_new \= (old\_qty × old\_avg \+ new\_qty × new\_price) / total\_qty

### How We Test It

Use long sequences of scale-ins and scale-outs with high-precision Decimal prices, then reverse through zero. Verify every intermediate quantity, average, realized P\&L, and final flat state.

---

## 3.6 Reversal Accounting

### Current AlgoShield Behavior

The ledger supports both long→short and short→long reversal. The old exposure closes, realized P\&L is recognized, and any remaining executed quantity opens the new opposite side.

### Benchmark / Professional Practice

Execution models are quantity-driven. A reversal must be explained from the actual executed quantity rather than an abstract position-status transition.

### Exact Gap

No material mathematical gap exists. The auditability opportunity is to make the two financial effects explicit.

### Recommended Improvement

Expose a reversal as:

Fill

├── Closing component

│   └── realized P\&L

└── Opening component

    └── new average / unrealized P\&L

### How We Test It

BUY 100 @ 150 then SELL 150 @ 140 should close 100 long, realize \-₹1,000, and leave 50 short at ₹140. Mirror this for short→long and verify charges and unrealized P\&L.

---

## 3.7 Charges

### Current AlgoShield Behavior

Charges are stored as Decimal, accumulated, deducted from gross P\&L, and included in daily net P\&L. The existing mock/replay flow uses synthetic charges such as 0.01 per fill.

### Benchmark / Professional Practice

IBKR demonstrates that commission information may be associated with an execution through a separate commission report. This provides a strong professional precedent for decoupling execution evidence from later-finalized cost information.

### Exact Gap

Two genuine gaps:

1. no verified 021 fee model;  
2. no standalone post-trade fee adjustment event.

### Recommended Improvement

Use a broker-neutral charge abstraction:

Fill

 ↓

Initial Financial State

 ↓

Commission / Fee Event

 ↓

Charge Adjustment

 ↓

Final Net P\&L

Do not implement assumed brokerage, STT, GST, exchange-fee, or 021 fee rules before 021 documentation verifies them.

### How We Test It

Test:

- known charge attached to a fill;  
- multiple charge-bearing fills;  
- separate fee adjustment;  
- duplicate fee adjustment;  
- correction \+ fee adjustment \+ restart \+ reconciliation.

Net P\&L must be deterministic and each adjustment applied exactly once.

---

## 3.8 Reconciliation

### Current AlgoShield Behavior

The system already supports:

- snapshot completeness/freshness checks;  
- broker order/fill comparisons;  
- missing-fill identification;  
- replay through OrderManager → Ledger;  
- broker-vs-ledger position comparison;  
- fail-closed handling of unexplained drift.

### Benchmark / Professional Practice

Professional execution models reconcile from evidence rather than trusting a single order status. Execution records, cumulative quantities, and current order states are distinct.

### Exact Gap

Two real hardening opportunities:

1. repeated full-history replay creates scalability pressure;  
2. unexplained external/manual position drift is currently safe but coarse — it is primarily a mismatch → fail-closed condition rather than a richer classified evidence state.

### Recommended Improvement

Introduce evidence classifications such as:

- MATCHED  
- MISSING EXECUTION  
- CONFLICTING EXECUTION  
- EXTERNAL POSITION  
- RECOVERING  
- VERIFIED

Then make recovery conditional on evidence. Recover explainable drift; do not fabricate local adjustments for unexplained drift.

### How We Test It

Explainable case:

Local \+60

Broker \+80

Missing broker execution \+20 exists

        ↓

Recover

        ↓

Local \+80

        ↓

MATCHED / VERIFIED

Unexplainable case:

Local \+60

Broker \+80

No explainable execution

        ↓

DRIFT

        ↓

FAIL CLOSED

        ↓

HALT / UNCERTAIN

Never fabricate a fill solely to make the numbers match.

---

# 4\. Final Five Recommended Improvements

## 4.1 M1-I1 — Reconciliation Evidence & Recovery

**Score: 98/100 — P1**

### Objective

Turn reconciliation from a mostly binary mismatch detector into an evidence-classified recovery workflow.

### Core model

LOCAL ORDERS      LOCAL FILLS      LOCAL POSITIONS

       ↕                 ↕                 ↕

BROKER ORDERS     BROKER EXECUTIONS  BROKER POSITIONS

Classify before deciding:

MATCHED → VERIFIED  
MISSING EXECUTION → RECOVERING → VERIFIED  
CONFLICTING EXECUTION → UNCERTAIN / FAIL CLOSED  
EXTERNAL POSITION → UNCERTAIN / FAIL CLOSED

### Why it is selected

It directly strengthens the safety claim of PS-06: AlgoShield can detect disagreement, explain it when evidence exists, recover missing execution evidence, verify the repaired state, and refuse to resume when uncertainty remains.

### Definition of Done

A reconciliation run can produce a structured explanation for each discrepancy, can recover only evidence-backed missing executions, and leaves unexplained drift explicitly halted/uncertain with no fabricated financial entry.

---

## 4.2 M1-I2 — Execution Trace

**Score: 93/100 — P1**

### Objective

Expose the already-correct attribution and lifecycle relationships as one auditable chain.

Strategy

  ↓

Order Intent

  ↓

Risk Decision

  ↓

Order

  ↓

Fill

  ↓

Position

  ↓

P\&L

### Why it is selected

It is the strongest demo and viva feature because it answers “Why did this position change?” with evidence rather than a dashboard number.

### Definition of Done

Given a fill or P\&L change, a developer/judge can follow a trace to the parent strategy, intent, risk decision, order, execution, position change, and financial effect.

---

## 4.3 M1-I3 — Broker Execution Identity \+ Idempotency Hardening

**Score: 92/100 — P1**

### Objective

Make broker execution identity explicit while preserving the canonical internal fill identity and existing exactly-once financial mutation behavior.

Broker Execution ID

        ↓

Canonical AlgoShield Fill ID

        ↓

Ledger

### Why it is selected

IBKR, Kite, and FIX all reinforce independently identifiable executions. This becomes especially important when external broker execution events are delivered more than once or recovered later.

### Definition of Done

Each verified broker execution maps to one canonical fill; duplicates produce no second mutation; conflicting economics fail closed; the original external execution identity remains traceable.

---

## 4.4 M1-I4 — Execution Correction / Trade-Bust Model

**Score: 83/100 — P1**

### Objective

Support legitimate later broker corrections without treating them as conflicting duplicates or destroying the original execution history.

Original Fill

     ↓

Referenced Correction / Cancel

     ↓

Revised Financial Projection

### Why it is selected

This is the clearest genuine accounting capability gap demonstrated by professional benchmarks, especially FIX and IBKR.

### Definition of Done

A correction has its own identity, references its target execution, applies exactly once, preserves original evidence, and yields deterministic replay.

---

## 4.5 M1-I5 — Broker-Aware Charge / Adjustment Model

**Score: 76/100 — P1**

### Objective

Allow cost information to evolve independently of the original execution event.

Execution

  ↓

Fill

  ↓

Initial Financial State

  ↓

Later Commission / Fee Event

  ↓

Charge Adjustment

  ↓

Final Net P\&L

### Why it is selected

Charges are the clearest remaining financial-state gap. The existing arithmetic is correct; the missing layer is lifecycle and broker-awareness.

### Definition of Done

The ledger can accept normalized fee/commission adjustments exactly once, preserve audit links, update net P\&L deterministically, and remain broker-neutral until 021 fee rules are verified.

---

# 5\. Ten Critical Test Cases

## 5.1 Master test matrix

| ID | Scenario | Input | Expected Result | Current Result | Existing / Proposed | Priority | Round-2 Hardening |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| M1-T01 | Partial Fill | BUY 100; fill 40 @ ₹100 | Position \+40, not \+100; remaining intent 60 | **PASS** | Existing | P0 | Concurrency / persistence boundary |
| M1-T02 | Multi-Price WAP | BUY 40 @ ₹100 \+ BUY 30 @ ₹110 | Position \+70; WAP ₹104.285714... | **PASS** | Existing | P0 | Long sequences / Decimal precision |
| M1-T03 | Reversal | BUY 10 @ ₹100 → SELL 25 @ ₹120 | Realized \+₹200; short \-15 @ ₹120 | **PASS** | Existing | P0 | Symmetric short→long \+ charge checks |
| M1-T04 | Duplicate Fill | Same fill ID/economics twice | One financial mutation | **PASS** | Existing | P0 | Concurrent duplicate delivery |
| M1-T05 | Conflicting Duplicate | Same ID, different price | Reject; preserve original; fail closed | **PASS** | Existing | P0 | Recovery/reconciliation conflict paths |
| M1-T06 | Late Fill After Cancel | BUY 100 → fill 40 → cancel → late fill 20 | Position \+60; late execution retained | **PASS** | Existing | P0 | Recovery race stress |
| M1-T07 | Multi-Strategy Attribution | A \+100; B \-60; C \+20 | Account \+60; strategies remain isolated | **PASS** | Existing | P0 | Full execution trace |
| M1-T08 | Realized \+ Unrealized P\&L | BUY 100 @100; SELL 40 @120; mark 125; charges .20 | Realized 800; Unrealized 1500; Gross 2300; Net 2299.80 | **PASS** | Existing | P0 | Fee adjustment/restart |
| M1-T09 | Account/Symbol Isolation | Multiple accounts/symbols | No financial leakage | **PASS** | Existing | P0 | Concurrent multi-key ingestion |
| M1-T10 | Reconciliation Drift | Local \+60; broker \+80; no explainable execution | DRIFT → FAIL CLOSED; no fabricated fill | **PASS** | Existing | P0 | Explainable recovery vs unexplainable halt |

## 5.2 Numerical invariants that must remain exact

### M1-T02 WAP

BUY 40 @ 100

BUY 30 @ 110

WAP \= (40×100 \+ 30×110) / 70

    \= 7300 / 70

    \= 104.285714285714...

### M1-T03 reversal

BUY 10 @ 100

SELL 25 @ 120

10 long closed → \+200 realized

15 short opened @ 120

Symmetric case:

SELL 20 @ 150

BUY 30 @ 140

20 short closed → \+200 realized

10 long opened @ 140

### M1-T08 P\&L

BUY 100 @ 100

SELL 40 @ 120

Mark \= 125

Charges \= 0.20

Realized   \= 800

Unrealized \= 1500

Gross      \= 2300

Net        \= 2299.80

The identities remain:

Gross \= Realized \+ Unrealized

Net   \= Gross \- Charges

## 5.3 Future adversarial / hardening tests

These are the next layer beyond the official ten:

1. concurrent fill ingestion;  
2. duplicate delivery during recovery;  
3. execution correction;  
4. standalone charge adjustment;  
5. large-volume accounting/replay performance;  
6. PostgreSQL integration;  
7. restart immediately before reconciliation;  
8. pagination boundary conditions;  
9. recovery races between broker snapshot and local ingestion;  
10. deterministic replay after a correction/charge adjustment sequence.

The official ten remain **P0 core tests**. The adversarial suite is **future hardening** and should not replace the P0 baseline.

---

# 6\. Dependencies / Integration Impact

## 6.1 What Member 1 receives from Member 2

The documented team boundary expects Member 2 to provide Member 1 with canonical execution information including:

- canonical Fill objects,  
- execution identity,  
- broker-order relationship,  
- strategy/account attribution,  
- broker execution evidence,  
- broker snapshot/history where available.

Member 1 should not parse raw 021 payloads as part of the accounting layer.

## 6.2 What Member 1 provides to Member 3

Member 1 provides financial truth required for risk and recovery decisions, including:

- strategy-level filled quantity,  
- daily net P\&L,  
- account-level aggregate position,  
- financial state used for reconciliation and kill verification.

## 6.3 What Member 1 provides to Member 4

Member 1 provides:

- strategy positions,  
- realized/unrealized/gross/net P\&L,  
- charges,  
- fill history,  
- execution timeline data.

## 6.4 Integration chain

MEMBER 4 / STRATEGY

      ↓ intent / strategy identity

MEMBER 3 / RISK

      ↓ approved/rejected decision

MEMBER 2 / ORDER \+ BROKER

      ↓ canonical execution evidence

MEMBER 1 / ACCOUNTING

      ↓ fill → position → P\&L → reconciliation

MEMBER 3 / RISK & RELIABILITY

      ↓ kill/recovery verification

MEMBER 4 / DASHBOARD

      ↓ execution trace / financial display

## 6.5 Contract Impact analysis

> The classifications below are **implementation-handoff proposals derived from the documented architecture**, not claims that the PDF already specifies final schemas. Verify against the live repository and 021 sponsor docs before merging contract changes.

| Improvement | Contract impact | Rationale | 021 dependency |
| :---- | :---- | :---- | :---- |
| M1-I1 Reconciliation Evidence & Recovery | **New event/model or additive reconciliation state** | Need explicit discrepancy class and recovery evidence without fabricating fills | Broker snapshot/execution evidence availability |
| M1-I2 Execution Trace | **Prefer additive metadata / correlation fields; avoid breaking Fill contract** | Existing IDs already support much of trace; only missing cross-stage correlation should be added | Risk/order trace fields may need coordination |
| M1-I3 Broker Execution Identity | **Additive contract field** | Preserve broker identity separately from canonical fill identity | **Yes — exact external execution key is unknown** |
| M1-I4 Execution Correction | **New event/model** | A correction is not a normal Fill and needs its own identity/reference | **Yes — exact broker correction semantics unknown** |
| M1-I5 Charge Adjustment | **New event/model or additive normalized charge event** | Supports later fee/commission lifecycle without mutating immutable execution evidence | **Yes — exact fee event and fee semantics unknown** |

### Contract rule

Do not make schema changes merely because a benchmark contains a field. The implementation should only add a field/event when the project architecture needs it and the real external contract has been verified where applicable.

---

# 7\. 021 Unknowns

The research repeatedly warns against treating IBKR/Kite/FIX behavior as 021 behavior. The following remain explicitly unresolved.

| Unknown | Why It Matters | Current Status | What Must Be Verified | Affected Component | Can We Implement Before Verification? |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Broker charge table / fee schedule | Determines final net P\&L and whether fee logic can be automated | **021 UNKNOWN** | Actual fee fields, formulas, timing, units, correction behavior | Member 2 adapter \+ Member 1 charges | **Partially** — build broker-neutral abstraction only |
| Broker execution identity / fill attribution key | Needed to map external evidence to canonical fill exactly once | **021 UNKNOWN** | Exact execution/trade identifier and uniqueness guarantees | Member 2 \+ Member 1 identity layer | **Partially** — define mapping boundary; wait on field |
| Execution delivery mechanism | Determines replay, ordering, duplicates, reconnect behavior | **021 UNKNOWN** | Polling/webhook/stream, ordering guarantees, retry semantics | Member 2 \+ Member 1 idempotency | **Yes** for internal idempotency; exact adapter waits |
| Historical execution querying | Needed for reconciliation and missing-fill recovery | **021 UNKNOWN** | Available history endpoint, limits, pagination, lookback window | Member 2 \+ Member 1 reconciliation | **Partially** — local recovery logic can be prepared |
| Opposing-strategy netting semantics | Important if broker account position is net while strategies are virtual | **021 UNKNOWN** | Whether broker exposes strategy attribution or only account-level net position | Member 1 attribution/reconciliation \+ Member 3 risk | **Yes** at virtual strategy layer; reconciliation mapping waits |
| Post-trade charges / adjustments | Determines how costs arrive after the execution | **021 UNKNOWN** | Separate fee event vs amended execution vs snapshot-only accounting | Member 1 charge model | **Yes** for event abstraction; exact adapter waits |
| Broker correction / trade-bust semantics | Needed to map a real correction into an auditable financial event | **021 UNKNOWN** | Correction identifier, reference field, ordering, cancellation vs correction distinction | Member 1 correction model \+ Member 2 adapter | **Partially** — event model can be broker-neutral |
| Broker snapshot position source | Needed to distinguish explainable from unexplained drift | **021 UNKNOWN** | Position endpoint, consistency guarantees, timing | Reconciliation | **Partially** — local classifier can be built |

### Required language in team documents

Use:

- **KNOWN** — verified from the current repository or explicit sponsor documentation;  
- **BENCHMARKED** — demonstrated by IBKR/Kite/FIX;  
- **UNKNOWN** — not verified;  
- **021-DEPENDENT** — implementation shape can be prepared, but final field/event semantics depend on the sponsor contract.

When an unresolved inconsistency exists, write **REQUIRES VERIFICATION**, not a guessed answer.

---

# 8\. Tomorrow's Implementation Items

## 8.1 P0 — Protect existing correctness

Before adding any new feature, lock the existing financial invariants into the implementation branch:

1. Order ≠ Fill;  
2. Fill-derived positions;  
3. partial fill correctness;  
4. WAP mathematics;  
5. long→short and short→long reversal mathematics;  
6. realized P\&L;  
7. unrealized P\&L;  
8. gross/net P\&L;  
9. fill idempotency;  
10. conflicting duplicate protection;  
11. strategy attribution and isolation;  
12. account/symbol isolation;  
13. overfill protection;  
14. deterministic replay;  
15. restart persistence;  
16. fail-closed reconciliation.

These are not Round-2 rewrite targets.

## 8.2 P1 — Implement the five frozen improvements

### Suggested order

**P1-A — Reconciliation Evidence & Recovery**

Start here because it has the highest score and directly exercises existing broker/local evidence paths.

**P1-B — Execution Trace**

Add observability before more correction/charge behavior so new financial events can inherit the trace model.

**P1-C — Broker Execution Identity \+ Idempotency Hardening**

Define canonical/internal vs external identity boundaries before deep broker integration.

**P1-D — Execution Correction / Trade-Bust Model**

Add a new event family with reference-to-original semantics.

**P1-E — Broker-Aware Charge / Adjustment Model**

Add normalized fee/commission adjustment events without hardcoded 021 formulas.

## 8.3 P2 — Only after P0/P1 stability

- incremental accounting state/cache;  
- fill pagination/filter verification;  
- PostgreSQL automation;  
- historical MTM/session summaries;  
- full cash/margin/collateral accounting.

## 8.4 Do not add feature creep

Do not spend Round-2 implementation time on unrelated features such as AI strategy generators, sentiment analysis, chatbots, social trading, portfolio optimization, strategy marketplaces, or broad analytics unless PS-06 explicitly requires them. They do not strengthen the documented Member-1 execution-truth story.

---

# 9\. Final Member-1 Decision

## What is already strong

AlgoShield already derives financial state from executed fills rather than order intent. Partial fills, WAP, reversal accounting, P\&L, strategy attribution, idempotency, isolation, and core reconciliation behavior are already implemented and tested.

## What is actually missing

The genuine functional gaps are:

- first-class execution correction / trade-bust handling;  
- a broker-aware charge/adjustment lifecycle.

## What must be hardened

The main hardening areas are:

- broker execution identity mapping;  
- concurrent/recovery idempotency;  
- evidence-rich reconciliation;  
- accounting scalability;  
- deeper adversarial tests;  
- explicit treatment of unavailable/stale marks where applicable.

## What we will implement

1. Reconciliation Evidence & Recovery;  
2. Execution Trace;  
3. Broker Execution Identity \+ Idempotency Hardening;  
4. Execution Correction / Trade-Bust Model;  
5. Broker-Aware Charge / Adjustment Model.

## What we will defer

Incremental cache/state, pagination/filter hardening, PostgreSQL automation, historical MTM/session summaries, and full cash/margin accounting remain P2 unless integration requirements raise their priority.

## What depends on 021

The exact broker execution identifier, fee schedule, execution-delivery semantics, historical execution API, correction semantics, and other broker-specific behavior remain unresolved until verified.

### Central decision

> **AlgoShield already knows how to derive financial truth from executed fills. Round 2 makes that truth more traceable, broker-compatible, correction-aware, scalable, and resilient.**

---

# 10\. Team Discussion / Viva Preparation

## A. Ten questions another team member may ask Member 1

### 1\. Why don't submitted orders create positions?

Because an order is an intent/lifecycle object. Financial truth comes from actual execution evidence. Treating requested quantity as executed quantity would create false positions.

### 2\. If an order says “FILLED,” why do we still care about fills?

Because professional execution models separate current order state from execution evidence. The financial ledger must know what actually executed, in what quantity, at what price, and under which identity.

### 3\. Do we already have idempotency?

Yes. The same fill identity with the same economics is a no-op; a conflicting duplicate is rejected/fail-closed. Round 2 hardens this under concurrency and recovery.

### 4\. Do we already have strategy attribution?

Yes. Strategy attribution is a working feature. The new work is making the complete strategy→intent→risk→order→fill→position→P\&L chain observable.

### 5\. Why not just update a fill when a correction arrives?

Because that destroys evidence. A correction should preserve the original event and add an auditable relationship to the revised financial projection.

### 6\. Why is WAP not a new Round-2 feature?

Because the audit already proves it works. The correct engineering action is regression and stress testing, not rewriting correct accounting mathematics.

### 7\. Why can a late fill after cancellation still change the position?

Cancellation changes the remaining order intent. It does not erase an execution that later arrives as valid broker evidence.

### 8\. Why do we need broker execution identity in addition to fill\_id?

Because the external broker event must remain traceable. Canonical internal identity and external evidence identity serve different purposes.

### 9\. Why can't we just calculate 021 fees now?

Because the 021 fee behavior is unknown. Inventing brokerage/STT/GST/exchange-fee rules would turn an assumption into financial truth.

### 10\. Why is reconciliation “fail closed” rather than force matching?

Because unexplained financial drift is uncertainty. Fabricating a local adjustment would destroy the very truth the reconciliation system is meant to protect.

## B. Ten questions a judge may ask about financial correctness

### 1\. What is your single most important accounting invariant?

**Order ≠ Fill.** Order represents intent; fill represents actual execution and is what creates financial state.

### 2\. How do you handle a partial fill?

Only the executed quantity changes the position. A BUY 100 with a fill of 40 produces position \+40, not \+100.

### 3\. How do you calculate WAP?

From actual executed quantity and price using Decimal arithmetic; requested order quantity is not treated as executed quantity.

### 4\. How do you handle reversals?

First close the old exposure using executed quantity and recognize realized P\&L. Any remaining executed quantity opens the opposite position at the new entry price.

### 5\. How do you stop duplicate fills from double-counting?

Execution identity is checked before insertion; an identical duplicate becomes a no-op, while conflicting economics are rejected.

### 6\. What happens when duplicate evidence conflicts?

The original financial truth is preserved. The conflicting event is rejected and the system fails closed rather than overwriting history.

### 7\. How is strategy attribution protected?

Fills must map to the canonical order/strategy/account/symbol context, and independent strategy virtual positions remain isolated even when their account-level positions net together.

### 8\. How do you compute net P\&L?

Gross \= Realized \+ Unrealized; Net \= Gross \- Charges.

### 9\. What happens when broker position differs from local position?

If evidence explains the difference, recover the missing execution and verify. If no evidence explains it, remain halted/uncertain and do not fabricate a fill.

### 10\. What is the biggest remaining financial limitation?

Post-trade execution corrections and broker-aware charge adjustments are not yet first-class, and the accounting state calculation still has a scalability concern from repeated full-history replay.

## C. Ten attack scenarios and expected behavior

| Attack scenario | Expected AlgoShield behavior |
| :---- | :---- |
| BUY 100 but only 40 execute | Position becomes \+40; remaining 60 is intent/lifecycle state |
| Same fill arrives twice | One financial mutation only |
| Same fill ID arrives with different price | Conflict → reject → preserve original truth → fail closed |
| Order cancelled after 40 fill, then 20 more execute | Position increases to \+60; late execution remains valid |
| BUY 10 @100 then SELL 25 @120 | Realize \+₹200; open short \-15 @120 |
| Three opposing strategies trade the same account/symbol | Strategy virtual positions remain isolated; account net is the aggregate |
| Local \+60, broker \+80, missing \+20 fill exists | Detect drift → recover missing fill → reverify → MATCHED |
| Local \+60, broker \+80, no explainable execution | FAIL CLOSED; remain uncertain/halted; no fabricated fill |
| Broker later corrects a previously valid execution | Preserve original; apply referenced correction once; revise financial projection |
| Fee arrives after execution | Record an explicit charge adjustment; update net P\&L exactly once; retain traceability |

### Restart before reconciliation

After restart, the system should reload persisted evidence, replay or restore deterministically, perform reconciliation, and reach the same financial result as the pre-restart state. If unexplained drift remains, fail closed rather than guessing.

---

# 11\. One-Page Implementation Summary

## CURRENT BASELINE

ORDER ≠ FILL

FILL → POSITION → P\&L

WORKING / TESTED

• partial fills

• WAP

• reversals

• realized P\&L

• unrealized P\&L

• gross/net P\&L

• strategy attribution

• idempotency

• conflict detection

• account/symbol isolation

• deterministic replay

• restart persistence

• reconciliation foundation

## FIVE IMPROVEMENTS

M1-I1  RECONCILIATION EVIDENCE & RECOVERY

       classify → recover when explained → verify → fail closed when not

M1-I2  EXECUTION TRACE

       strategy → intent → risk → order → fill → position → P\&L

M1-I3  BROKER EXECUTION IDENTITY \+ IDEMPOTENCY

       broker ID → canonical fill ID → exactly-once mutation

M1-I4  EXECUTION CORRECTION / TRADE-BUST

       original fill → referenced correction → revised financial state

M1-I5  BROKER-AWARE CHARGE / ADJUSTMENT

       fill → initial state → fee event → adjustment → final net P\&L

## DEPENDENCIES

MEMBER 2

• canonical fills

• broker execution identity/evidence

• broker order relationship

• broker snapshots/history

MEMBER 3

• risk/recovery decisions

• fail-closed/kill verification

• reconciliation control

MEMBER 4

• execution-trace presentation

• financial state / timeline UI

021

• execution identity

• delivery semantics

• history/query behavior

• corrections

• fees

\= VERIFY BEFORE CLAIMING

## TESTS

P0 — 10 critical tests

↓

ADVERSARIAL

• concurrency

• recovery duplicates

• corrections

• fee adjustments

• restart/reconciliation

• PostgreSQL

• pagination

• large-volume replay

↓

PROOF

## DEFINITION OF DONE

The Round-2 Member-1 implementation is complete when:

- existing accounting invariants still pass;  
- every canonical fill remains exactly-once;  
- broker identity is traceable without replacing internal fill identity;  
- correction events preserve original execution evidence;  
- charge adjustments are replay-safe and broker-neutral;  
- reconciliation classifies discrepancies and recovers only when evidence supports recovery;  
- unexplained drift remains fail-closed;  
- execution trace can answer why a position/P\&L changed;  
- restart/replay remains deterministic;  
- no 021-specific behavior is claimed without verification.

---

# Appendix A — Scoring / Selection Logic

The documented selection weights are:

| Criterion | Weight |
| :---- | ----: |
| PS-06 relevance | 30 |
| Safety / correctness impact | 25 |
| Demo value | 15 |
| Differentiation | 15 |
| Buildability | 10 |
| Testability | 5 |

The research then scored serious candidates from 1–5 on each criterion and converted the result to a score out of 100\. The documented candidate ranking is:

| Improvement | PS-06 | Safety | Demo | Differentiation | Buildability | Testability | Score | Priority |
| :---- | ----: | ----: | ----: | ----: | ----: | ----: | ----: | :---- |
| Reconciliation Evidence & Recovery | 5 | 5 | 5 | 5 | 4 | 5 | **98** | P1 |
| Execution Trace | 5 | 4 | 5 | 5 | 4 | 5 | **93** | P1 |
| Broker Execution Identity \+ Idempotency | 5 | 5 | 4 | 4 | 4 | 5 | **92** | P1 |
| Partial-Fill / WAP / Reversal Hardening | 5 | 5 | 3 | 2 | 5 | 5 | **85** | P0 test hardening, not headline feature |
| Execution Correction / Trade-Bust | 4 | 5 | 4 | 5 | 3 | 4 | **83** | P1 |
| Broker-Aware Charge / Adjustment | 4 | 4 | 3 | 4 | 3 | 5 | **76** | P1 |
| Incremental Accounting State / Cache | 4 | 3 | 2 | 3 | 3 | 5 | **69** | P2 |
| Historical Fill Audit / Pagination | 3 | 2 | 3 | 2 | 5 | 5 | **60** | P2 |

### Why the 85-point candidate is not in the five

Partial-fill/WAP/reversal hardening scored highly but was deliberately not selected as a headline improvement because the underlying accounting mathematics is already implemented and tested. It becomes **mandatory P0 regression/stress testing**, not a new feature slot.

---

# Appendix B — Implementation Backlog

> File paths below are **likely touch-points inferred from the repository audit cited in the research**, not a promise that every task will require a specific file. Confirm exact changes against the live tree before implementation.

| Task ID | Task | Owner | Dependency | Likely Files / Areas | Expected Output | Tests | DoD | Priority | Blocked By |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| M1-B00 | Freeze financial invariants | Member 1 | Existing test suite | backend/accounting/ledger.py, tests/test\_member1.py, tests/test\_safety.py | Protected P0 baseline | M1-T01–T10 | All baseline tests green before P1 changes | P0 | None |
| M1-B01 | Reconciliation evidence classes | Member 1 \+ Member 3 | Broker snapshot/fill evidence | backend/reliability/snapshots.py, backend/reliability/control.py, ledger integration | Structured mismatch classification | Recoverable/unrecoverable drift | Every discrepancy has a reason/status | P1 | Exact broker evidence contract |
| M1-B02 | Recovery verification workflow | Member 1 \+ Member 3 | M1-B01 | reconciliation/control \+ OrderManager/Ledger integration | Recover → re-read → verify flow | M1-T10-A/B \+ restart | Explainable drift reaches MATCHED/VERIFIED; unexplained remains fail-closed | P1 | M1-B01 |
| M1-B03 | Execution trace correlation | Member 1 \+ Member 4; coordinate Member 2/3 | Existing order/strategy/risk identifiers | backend/execution/orders.py, accounting trace data, dashboard integration | Queryable end-to-end execution trace | strategy→intent→risk→order→fill→position→P\&L | One trace explains a financial change | P1 | Availability of cross-stage identifiers |
| M1-B04 | Broker execution ID mapping boundary | Member 1 \+ Member 2 | 021 identifier verification | backend/shared/contracts.py, broker adapter boundary, ledger | External-to-canonical ID mapping | duplicate/concurrent/recovery delivery | One external execution → one canonical fill | P1 | 021 execution ID |
| M1-B05 | Correction event model | Member 1 \+ Member 2 | M1-B04 conceptually; 021 correction semantics | backend/shared/contracts.py, backend/accounting/ledger.py | Referenced correction/trade-bust event | correction, duplicate correction, unknown reference | Original preserved; corrected projection deterministic | P1 | 021 correction semantics |
| M1-B06 | Charge adjustment model | Member 1 \+ Member 2 | Verified fee delivery semantics | backend/shared/contracts.py, backend/accounting/ledger.py | Broker-neutral fee/commission adjustment | fee event, duplicate fee event, restart | Net P\&L adjusts exactly once | P1 | 021 fee semantics |
| M1-B07 | Concurrency/recovery hardening | Member 1 | M1-B04 identity boundary | ledger persistence / store | Persistence-level duplicate safety | concurrent duplicate ingestion | one financial mutation | P0/P1 | Test harness availability |
| M1-B08 | Large-history accounting benchmark | Member 1 | Stable core | backend/accounting/ledger.py | Baseline performance measurement | 10k/100k+ history where feasible | Decision on P2 cache justified by measurement | P2 | Benchmark environment |
| M1-B09 | PostgreSQL integration coverage | Member 1 \+ reliability/infra support | DB availability | persistence/integration tests | Repeatable integration suite | restart \+ reconciliation | CI/local instructions documented | P2 | DB environment |

---

# Appendix C — Rejected / Deferred Ideas

The research explicitly rejects using the following as headline Round-2 wins when they do not strengthen the execution-truth narrative:

- treating strategy attribution as a new feature;  
- rewriting WAP mathematics;  
- rewriting reversal accounting;  
- replacing canonical fill\_id with an unverified broker field;  
- inventing 021 fee formulas;  
- forcing broker/local position agreement by fabricating local entries;  
- expanding into full cash/margin brokerage accounting without a requirement;  
- prioritizing pagination solely for demo value;  
- presenting test automation as a product-level differentiator;  
- unrelated feature creep outside PS-06 execution safety/accounting scope.

---

# Appendix D — Source Discipline

### Primary source

The attached research PDF is the authoritative source for:

- current prototype state;  
- repository audit findings;  
- IBKR/Kite/FIX benchmark findings;  
- eight accounting/execution problem conclusions;  
- five selected improvements;  
- scoring values;  
- ten critical tests and their documented results;  
- 021 unknowns and unresolved broker semantics.

### Benchmark source discipline

Use benchmark language exactly as benchmark language:

- “IBKR demonstrates…”  
- “Kite Connect models…”  
- “FIX specifies…”

Do **not** turn any of those into:

- “021 will…”  
- “021 definitely sends…”  
- “021 charges…”

until verified.

### Final verification rule

Whenever the repository, 021 documentation, and benchmark semantics do not yet prove the same thing, label the item:

> **REQUIRES VERIFICATION**

and preserve the uncertainty rather than filling it with a plausible assumption.

---

# Final Member-1 Handoff Statement

**Member 1 is not rebuilding accounting.** The current architecture already has a strong financial truth core built around executed fills. The Round-2 implementation should preserve that core and strengthen the evidence boundaries around it.

The implementation path is:

RESEARCH

   ↓

DECISION

   ↓

P0 INVARIANT PROTECTION

   ↓

M1-I1 RECONCILIATION EVIDENCE

   ↓

M1-I2 EXECUTION TRACE

   ↓

M1-I3 BROKER EXECUTION IDENTITY

   ↓

M1-I4 EXECUTION CORRECTION

   ↓

M1-I5 CHARGE / ADJUSTMENT MODEL

   ↓

INTEGRATION

   ↓

ADVERSARIAL TESTING

   ↓

DEMO / VIVA

The final engineering message is intentionally simple:

> **AlgoShield already knows what actually happened financially. Round 2 makes that truth explainable, broker-compatible, correction-aware, and resilient.**  

# **ALGOSHIELD — ROUND 2 MASTER PLAN**

## **The objective for the team**

By the end of today, you should have:

**1\. A complete gap analysis** of the present prototype.

**2\. A benchmark-backed list of improvements.**

**3\. A frozen P0/P1/P2 feature list.**

**4\. A final architecture and data-flow decision.**

**5\. Test cases for every critical failure path.**

**6\. A clear owner for every implementation item.**

**7\. A demo story that proves the system rather than merely showing UI.**

Tomorrow should then be primarily **implementation \+ integration \+ verification**, not another planning day.

---

# **PART A — THE FOUR MEMBERS**

## **MEMBER 1 \[AKSHAT\] — EXECUTION TRUTH, ACCOUNTING & RECONCILIATION**

### **Your mission**

> **Make sure AlgoShield always knows what actually happened financially.**

Your area is extremely important because a trading platform cannot be considered reliable if its position or P\&L becomes wrong after an execution event.

The current architecture already defines the important rule:

**Order expresses intent → Fill creates financial state.**

Current industry APIs reinforce exactly this distinction. Kite documents that a single order can result in multiple individual trades, while IBKR exposes execution identifiers, filled quantity, remaining quantity/cumulative quantity and average execution price. ([Kite](https://kite.trade/docs/connect/v3/orders/?utm_source=chatgpt.com))

### **STEP 1 — Audit what you already have**

Check:

**Order**

→ requested quantity  
→ status  
→ strategy ID

**Fill**

→ unique execution ID  
→ order ID  
→ strategy ID  
→ quantity  
→ price  
→ timestamp

**Position**

→ signed quantity  
→ average price

**P\&L**

→ realized  
→ unrealized  
→ charges  
→ net

**Account**

→ aggregate position

Mark every item:

**WORKING / PARTIAL / MISSING / NEEDS HARDENING**

### **STEP 2 — Benchmark**

Study:

**Interactive Brokers** for execution-level information.

Focus specifically on execution IDs, cumulative quantity, average price and account attribution. ([IBKR Campus US](https://ibkrcampus.com/docs/tws-api/protobuf/order-status?utm_source=chatgpt.com))

**Kite Connect** for the order/trade distinction and partial executions. ([Kite](https://kite.trade/docs/connect/v3/orders/?utm_source=chatgpt.com))

**FIX execution semantics** for canonical order-state modelling. FIX explicitly separates the reason for an execution report from the current order status and models cumulative and remaining quantities. ([FIX Trading Community](https://www.fixtrading.org/online-specification/order-state-changes/?utm_source=chatgpt.com))

### **STEP 3 — Find improvements**

Research these specifically:

**Execution identity**

Can every fill be uniquely identified?

**Idempotency**

What happens when the same fill arrives twice?

**Corrections**

What happens if an execution is corrected later?

**Attribution**

Can every execution be traced back to a strategy instance?

**Weighted average**

Does the position remain correct across multiple fill prices?

**Reversal**

Does long → flat → short work correctly?

**Charges**

Can actual execution costs be attached to the correct fill?

**Reconciliation**

Can local financial state be rebuilt from broker evidence?

### **STEP 4 — Strong improvement to propose**

### **Execution Trace**

Every important event should be traceable:

Strategy → Intent → Risk Decision → Order → Fill → Position → P\&L

With one strategy\_instance\_id and correlation/order identifiers carried through the chain.

That will make your system much easier to debug and defend.

### **STEP 5 — Prepare these tests**

At minimum:

BUY 100 → Fill 40

40 @ ₹100 \+ 30 @ ₹110

BUY → SELL → reversal

Same fill received twice

Late fill after cancellation

Local position ≠ broker position

Three opposing strategies

### **Deliverable by today's meeting**

**Member 1 must bring:**

> **5 accounting/execution improvements \+ current gap table \+ 10 critical financial test cases.**

No generic research.

---

# **MEMBER 2 \[SUJAL\] — BROKER INTEGRATION & ORDER LIFECYCLE**

### **Your mission**

> **Make the broker boundary reliable and replaceable.**

Your area is not just “connect to 021.”

It is:

**Intent → Risk Approval → Submit → Broker Response → Execution Events → Internal State**

The team's architecture explicitly keeps all broker access behind the Order Manager/Broker Adapter.

### **STEP 1 — Audit the order state machine**

Start with:

**INTENT**

↓

**APPROVED**

↓

**SUBMITTING**

↓

**ACKNOWLEDGED**

↓

**OPEN**

↓

**PARTIALLY FILLED**

↓

**FILLED / CANCELLED / REJECTED**

This is much closer to professional execution modelling than assuming a single synchronous placeOrder() result.

FIX's official order-state material explicitly models execution, cancellation, modification, rejection and partial-fill scenarios. ([FIX Trading Community](https://www.fixtrading.org/online-specification/order-state-changes/?utm_source=chatgpt.com))

### **STEP 2 — Research these exact failure cases**

**Timeout after submission**

> Did the broker receive the order?

Never blindly resend.

**Partial fill \+ cancel**

> Cancel remaining quantity, but preserve the fills that already happened.

**Reject after acknowledgement**

> Don't confuse rejection with cancellation.

FIX explicitly distinguishes these states. ([FIX Trading Forum](https://forum.fixtrading.org/t/execution-report-reject-after-an-acknowledgment/18083?utm_source=chatgpt.com))

**Duplicate execution**

> Same execution must not be applied twice.

**Reconnect**

> What state is reconstructed after the connection returns?

### **STEP 3 — 021-specific research**

Do **not** invent undocumented 021 API behavior.

Create a table:

| Question | Answer | Verified Source |
| ----- | ----- | ----- |
| Order submission |  |  |
| Order update stream |  |  |
| Partial fills |  |  |
| Trade history |  |  |
| Open orders |  |  |
| Positions |  |  |
| Client order ID |  |  |
| Reconnection |  |  |
| Charges |  |  |

The project research explicitly says these 021 details need confirmation before implementation.

### **STEP 4 — Strong production-level improvement**

### **Canonical Broker Event Model**

Whatever 021 sends should be converted immediately into your internal model:

Broker Event → Canonical Event → Execution Processor

The rest of AlgoShield should never depend on raw broker-specific JSON.

### **STEP 5 — Add observability**

Every execution should have:

**event ID**

**order ID**

**strategy ID**

**timestamp**

**event type**

**processing result**

That will make your demo timeline extremely strong.

### **Deliverable**

> **Canonical order lifecycle \+ 021 unknowns table \+ broker failure matrix \+ integration recommendations.**

---

# **MEMBER 3 \[RAM\] — RISK, SECURITY, RELIABILITY & SCALE**

### **Your mission**

> **Make sure failure can never silently increase risk.**

This is probably the most important research area for PS-06.

The existing plan already gives you:

**maximum position**

**maximum daily loss**

**orders/minute**

**global trading gate**

**reconciliation**

**restart recovery**

**kill switch**

Now make them more robust.

---

## **STEP 1 — Study professional pre-trade risk**

Trading Technologies is particularly useful here.

Its documentation describes position controls and aggregate risk across accounts, while its risk examples explicitly use:

**Current Position \+ Working Orders \+ Possible Fill from Current Order \= Worst Case Position**. ([TT Help Library](https://library-staging.tradingtechnologies.com/setup/risk-management/risk-limits/reference-risk-limits/account-position-examples/?utm_source=chatgpt.com))

That strongly validates the projected-exposure idea already present in AlgoShield.

### **Research these controls**

**Maximum Position**

**Worst-Case / Projected Exposure**

**Order Quantity**

**Orders per Minute**

**Daily Loss**

**Trading State**

**Price Reasonability**

**Reduce-Only**

### **Strong improvement**

### **Risk Decision Reason Codes**

Instead of:

> REJECTED

show:

> **REJECTED — POSITION LIMIT**  
> Current: 80  
> Pending: 20  
> Requested: 10  
> Projected: 110  
> Limit: 100

This is both technically useful and extremely good for the demo.

---

# **STEP 2 — Security audit**

Use the current OWASP API Security guidance as the checklist.

The API Top 10 specifically highlights broken object-level authorization, broken authentication, unrestricted resource consumption, broken function-level authorization and unsafe API consumption. ([OWASP Foundation](https://owasp.org/projects/api-security-project?tab=main&trk=article-ssr-frontend-pulse_little-text-block&utm_source=chatgpt.com))

For AlgoShield, concentrate on:

**Authentication**

Who is allowed to operate the account?

**Authorization**

Who is allowed to start/stop a strategy?

Who can modify risk limits?

Who can trigger kill?

**Resource limits**

Can a client or strategy flood the API?

**Input validation**

Can an invalid order intent enter the system?

**Secret handling**

Are broker credentials isolated from frontend code?

### **WebSocket security**

Because your system uses WebSockets, explicitly check:

**connection authentication**

**Origin validation**

**message-level authorization**

**message validation**

**payload limits**

**rate limiting**

**security logging**

These are specifically recommended in OWASP's WebSocket guidance. ([OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html?utm_source=chatgpt.com))

---

# **STEP 3 — Failure engineering**

Create a **Failure Matrix**.

| Failure | Expected Platform Response |
| ----- | ----- |
| Strategy spam | Rate-limit / reject |
| Position race | Atomic risk decision |
| Partial fill | Update actual filled quantity |
| Rejection | No position mutation |
| Duplicate fill | Ignore duplicate |
| Missed fill | Reconcile |
| Broker timeout | Query/reconcile before retry |
| Broker disconnect | Close/limit new exposure |
| Stale market data | Block new exposure |
| Server restart | Start fail-closed |
| Kill \+ new intent race | Gate wins |
| Kill \+ late fill | Reconcile \+ flatten |

The implementation plan already identifies these failure scenarios.

### **Deliverable**

> **Risk/security matrix \+ failure matrix \+ 10 highest-value hardening improvements \+ test cases.**

---

# **MEMBER 4 \[SHRIRAJ\] — MARKET DATA, STRATEGIES, PRODUCT & UX**

### **Your mission**

> **Turn the engineering system into a product that a judge can understand immediately.**

Do **not** make this role “just frontend.”

It has four parts:

**Market-data correctness**

**Strategy runtime**

**Dashboard**

**Demo/product experience**

The existing architecture requires raw ticks → 1m/5m candles → strategies → order intents.

---

## **STEP 1 — Market-data audit**

Verify:

**raw tick**

↓

**normalization**

↓

**deduplication**

↓

**candle aggregation**

↓

**1-minute candle**

↓

**5-minute candle**

↓

**strategy input**

Research:

**duplicate ticks**

**out-of-order ticks**

**late ticks**

**missing intervals**

**reconnects**

The team's research specifically identifies these as real streaming edge cases.

Kite's documentation is also useful as a benchmark for streaming market data over WebSockets. ([Kite](https://kite.trade/docs/connect/v3//websocket/?utm_source=chatgpt.com))

---

# **STEP 2 — Strategy correctness**

Keep the strategies simple.

**EMA Crossover**

**Breakout**

**Mean Reversion**

The purpose of these strategies is to exercise the platform, not to build the “best trading strategy.”

Check:

> Does strategy receive the correct candle?

> Does one candle produce one intended signal?

> Can the strategy send anything except an Order Intent?

> Can it bypass the risk gateway?

The strategy/execution separation used by QuantConnect is a useful benchmark: its risk-management model operates before the execution model receives the risk-adjusted targets. ([QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/execution/key-concepts?utm_source=chatgpt.com))

---

# **STEP 3 — Dashboard redesign**

The dashboard should be **operational, not decorative**.

Top:

**BROKER — CONNECTED**

**SYSTEM — HEALTHY**

**RECONCILIATION — HEALTHY**

**OPEN ORDERS — 3**

**\[ EMERGENCY KILL \]**

Then:

### **Strategy cards**

**EMA Crossover**

RUNNING

Position: \+80

Net P\&L: ₹1,223

Position Risk: 80 / 100

Orders: 3 / 10

Then:

### **Execution Timeline**

09:31:02 Tick received

09:31:03 Candle closed

09:31:03 BUY intent

09:31:03 Risk approved

09:31:04 Order submitted

09:31:04 Partial fill 40/100

09:31:05 Position \= \+40

This is much more useful than another large trading chart.

The existing project research already recommends a risk-first operational hierarchy.

---

# **STEP 4 — Product/business positioning**

Member 4 should answer one question:

> **Why would somebody need AlgoShield instead of just running a strategy against a broker API?**

The answer should be:

**Because strategy logic can generate decisions, but AlgoShield controls execution, risk, state, attribution and recovery.**

That is the product.

Do not position it as:

> “A platform with three trading strategies.”

Position it as:

> **“A safety and execution layer for multi-strategy automated trading.”**

---

# **PART B — THE IMPORTANT NEW FEATURES**

After today's research, these are the improvements I would seriously target.

## **P0 — Must work**

These directly satisfy PS-06.

**1\. Centralized Risk Gateway**

**2\. Maximum Position**

**3\. Maximum Daily Loss**

**4\. Rolling Orders/Minute**

**5\. Projected Exposure**

**6\. Three Simultaneous Strategies**

**7\. 1-minute \+ 5-minute Candles**

**8\. Correct Order Lifecycle**

**9\. Partial Fill Handling**

**10\. Rejection/Cancellation Handling**

**11\. Fill-Based Position & P\&L**

**12\. Independent Strategy Ledgers**

**13\. Reconciliation**

**14\. Fail-Closed Restart**

**15\. Verified Kill Switch**

**16\. Operational Dashboard**

These correspond closely to the mandatory requirements already defined in your project plan.

---

# **P1 — Your differentiation layer**

These are the features I think can make you stand apart from a generic algo platform:

### **Risk Decision Reason Codes**

Every rejection tells the user why.

### **Execution Timeline**

One trace from intent to financial result.

### **Reconciliation Center**

LOCAL ↔ BROKER

**MATCHED**

or

**DRIFT → RECOVERING → VERIFIED**

### **Safety Proof Panel**

Show:

Risk Bypass: 0

Unattributed Fills: 0

Duplicate Fills: 0

Reconciliation: MATCHED

Trading State: HEALTHY

### **Failure Lab**

One-click:

Partial Fill

Reject

Duplicate

Disconnect

Miss Fill

Restart

Strategy Spam

### **Kill Certificate**

Record:

Gate Closed

Strategies Stopped

Orders Cancelled

Positions Flattened

Broker Verified

Elapsed Time

### **Audit Timeline**

Every critical platform decision becomes traceable.

### **Strategy Attribution**

Every order, fill, P\&L event and risk decision keeps strategy identity.

---

# **P2 — Only if everything above is stable**

These are useful but should not distract you:

**Docker deployment**

**Redis**

**Advanced WebSocket scaling**

**Historical analytics**

**Advanced observability**

**Property-based/fuzz testing**

**More sophisticated strategy configuration**

The original plan also places these sorts of enhancements after the mandatory system is stable.

---

# **PART C — HOW THE TEAM DECIDES WHETHER A FEATURE IS WORTH BUILDING**

This is extremely important.

Do **not** decide based on:

> “This looks cool.”

Score every proposed improvement out of 100\.

| Criterion | Weight |
| ----- | ----- |
| PS-06 relevance | 30 |
| Safety/correctness impact | 25 |
| Demonstration value | 15 |
| Differentiation | 15 |
| Buildability within time | 10 |
| Testability | 5 |

### **Example**

**AI Strategy Generator**

PS relevance: 2/5  
Safety: 1/5  
Demo: 4/5  
Differentiation: 4/5  
Buildability: 2/5  
Testability: 1/5

→ **Reject**

**Risk Decision Reason Codes**

PS relevance: 5/5  
Safety: 5/5  
Demo: 5/5  
Differentiation: 4/5  
Buildability: 5/5  
Testability: 5/5

→ **Build**

This prevents feature creep.

---

# **PART D — EXACT 90-MINUTE MEETING TODAY**

## **0–10 minutes — Freeze the current baseline**

Everyone looks at:

**Current prototype**

**PS-06**

**Current architecture**

**Existing tests**

No brainstorming yet.

Each person writes:

> **What works today?**

> **What is incomplete?**

> **What is uncertain?**

---

## **10–40 minutes — Four parallel research tracks**

### **Member 1**

Execution/accounting/reconciliation.

### **Member 2**

Broker/order lifecycle/021 boundary.

### **Member 3**

Risk/security/failure/scalability.

### **Member 4**

Market data/strategies/product/dashboard.

Each person must produce:

**3 benchmark findings**

**5 important gaps**

**5 proposed improvements**

**10 test cases**

**3 things NOT worth building**

---

## **40–55 minutes — Team presentations**

Each member gets roughly:

**5 minutes**

No long presentation.

Use this format:

> **Current → Benchmark → Gap → Improvement → Proof/Test**

---

# **55–70 minutes — Feature filtering**

Put every proposed feature into:

### **P0 — MUST**

Required for correctness.

### **P1 — DIFFERENTIATOR**

Makes the system technically stronger.

### **P2 — OPTIONAL**

Only if time remains.

Anything that doesn't directly improve:

**safety, correctness, resilience, demonstrability or PS compliance**

gets removed.

---

# **70–80 minutes — Dependency mapping**

This is where you prevent integration chaos.

### **Dependency chain**

**Member 4**

Market tick → candle → strategy → intent

↓

**Member 3**

Risk decision

↓

**Member 2**

Order submission → broker events

↓

**Member 1**

Fill → position → P\&L

↓

**Member 3**

Reconciliation / recovery

↓

**Member 4**

Dashboard

This matches the existing team boundaries: strategies generate intents, Member 3 controls approval, Member 2 handles broker execution, and Member 1 turns fills into financial state.

---

# **80–90 minutes — Freeze tomorrow's implementation backlog**

For every task write:

**Task**

**Owner**

**Dependency**

**Expected output**

**Test**

**Definition of Done**

Example:

> **Risk Decision Reason Codes**  
> Owner: Member 3  
> Dependency: Risk Gateway  
> Output: structured rejection reason  
> Test: position \+80, pending \+20, request \+10 → REJECT  
> Done: API \+ UI \+ automated test

At 90 minutes, you should **stop planning**.

---

# **PART E — TOMORROW'S IMPLEMENTATION ORDER**

This sequence matters.

## **PHASE 1 — Contract Freeze**

Before coding, freeze:

**OrderIntent**

**RiskDecision**

**CanonicalOrder**

**Fill**

**StrategyPosition**

**StrategyPnL**

**BrokerPosition**

**SystemHealth**

**AuditEvent**

The implementation plan already identifies these shared contracts as the common integration boundary.

No one should casually change them afterward.

---

# **PHASE 2 — Execution Backbone**

Get this path completely deterministic:

**Tick**

↓

**Candle**

↓

**Strategy**

↓

**Intent**

↓

**Risk**

↓

**Order**

↓

**Mock Broker**

↓

**Fill**

↓

**Position**

↓

**P\&L**

↓

**Dashboard**

This is your minimum healthy system.

---

# **PHASE 3 — Harden the hard cases**

Run:

### **Test 1**

BUY100 → Fill40

Expected:

Position \+40

### **Test 2**

BUY100 → Fill40 → Fill30 → Cancel30

Expected:

Position \+70

### **Test 3**

A \+100 / B \-60 / C \+20

Expected:

Broker \+60

while each strategy keeps its own position.

### **Test 4**

Duplicate fill

Expected:

Applied once

### **Test 5**

80 filled \+ 20 pending \+ BUY10

Expected:

REJECT

### **Test 6**

Local \+60, broker \+80

Expected:

DRIFT → RECONCILE → \+80

### **Test 7**

Kill during partial fill

Expected:

Gate closed → Cancel → Flatten → Verify

These scenarios are already identified as central integration tests in the project plan.

---

# **PHASE 4 — Add the differentiators**

Only after P0 passes:

**Risk Reason Codes**

→ **Execution Timeline**

→ **Reconciliation Center**

→ **Failure Lab**

→ **Kill Certificate**

→ **Safety Proof**

These six together can make the system feel dramatically more mature without requiring hundreds of additional features.

---

# **PHASE 5 — Final integration**

All four members stop working independently.

Run the entire system from:

**Market Data**

through

**Strategy**

through

**Risk**

through

**Broker**

through

**Fill**

through

**Accounting**

through

**Recovery**

through

**Dashboard**

No isolated module is accepted as “done.”

---

# **PHASE 6 — Final adversarial testing**

Don't only demonstrate the happy path.

Break it deliberately.

**Spam the strategy.**

**Duplicate a fill.**

**Drop the broker connection.**

**Create local/broker drift.**

**Restart the server.**

**Partially fill an order.**

**Trigger the risk limit.**

**Press kill during execution.**

Then verify:

> **Does AlgoShield remain safe?**

That aligns directly with the project's Phase 3 goal: intentionally break the system and recover it.

---

# **THE FINAL DEMO STORY**

This is what I would build everything around:

### **1\. Normal operation**

**3 strategies running**

A: \+100

B: \-60

C: \+20

Account: \+60

### **2\. Risk attack**

Strategy requests:

BUY30

Current \+80  
Pending \+20  
Projected \+110  
Limit \+100

→ **REJECTED**

### **3\. Partial execution**

BUY100

→ Fill 40

→ Position \+40

### **4\. Failure injection**

Local:

\+60

Broker:

\+80

→ **DRIFT DETECTED**

### **5\. Recovery**

RECONCILING

→ Missing execution recovered

→ **MATCHED**

### **6\. Emergency kill**

Press:

**KILL**

Show:

Gate Closed

Strategies Stopped

Orders Cancelled

Residual Position Flattened

Broker Verified

→ **VERIFIED SAFE \<10s**

That tells the complete story of PS-06 in a few minutes.

---

# **ONE RULE I WOULD GIVE ALL FOUR MEMBERS**

Put this at the top of the team document:

> **Every improvement must answer four questions: What PS-06 problem does it solve? Why is the current prototype insufficient? How will we implement it? How will we prove that it works?**

That will stop the team from competing with the stronger-looking teams by simply adding more screens or flashy features.

Your strongest route is different:

**Prevent unsafe actions.**  
**Know exactly what executed.**  
**Recover when state diverges.**  
**Prove the account is safe.**

That is already the central idea behind your architecture, and the next round should make those four claims **measurable and demonstrable**, not merely descriptive.

### **The four members' final missions**

**Member 1:** *Financial truth*  
**Member 2:** *Execution truth*  
**Member 3:** *Safety under failure*  
**Member 4:** *Market-to-user experience*

And the final team objective:

# **“When the system is stressed, AlgoShield should still know what happened, prevent what must not happen, and prove when it is safe again.”**


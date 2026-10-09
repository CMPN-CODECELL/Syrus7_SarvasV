**MEMBER 2**

# Order Execution & Broker Integration

**Round 2 — Final Implementation, Hardening & Acceptance Report**

**Scope**  Order lifecycle, broker integration, execution-event handling, identity mapping, causality safety, reconciliation and cross-member accounting integrity.

| Final Status | PASS — based on the reported verification run |
| :---- | :---- |
| **P0 Lifecycle Fix** | OPEN \-\> REJECTED safely constrained to zero executed quantity |
| **P1 Hardening** | Broker-ID mapping \+ event causality \+ adversarial testing |
| **Full Test Result** | 338 passed, 1 skipped, 1 warning |
| **Lint Result** | Ruff: all checks passed |

*Prepared from the implementation agent’s reported command outputs and verification summary.*

**Evidence note:** This report records the implementation and test results exactly as reported in the working-session output. The report does not independently execute commands against the user’s local repository.

# **1\. Executive Summary**

Member 2 is responsible for the Order → Broker → Execution Event portion of the AlgoShield execution chain. The Round 2 work focused on one P0 lifecycle defect and three P1 hardening areas: safe broker rejection handling, decoupled local/broker order identity, event causality protection, and adversarial/integration proof.

* P0 lifecycle safety was corrected: OPEN \-\> REJECTED is allowed only when no quantity has been executed, and the rejection path creates no financial mutation.  
* Broker identity was decoupled from local/client identity using an additive broker\_order\_id field and lookup path, without creating a new table.  
* No new event sequencing architecture was introduced because the current BrokerUpdate contract has no trustworthy monotonic ordering source.  
* State-machine validation, ledger idempotency, attribution checks, reconciliation and terminal-state rules were used as the primary safety mechanisms.  
* The final hardening pass added ten adversarial scenarios plus cross-member integration tests covering Member 2 → Member 1 accounting behavior.

# **2\. Member 2 Scope and Boundaries**

The implementation was kept within the intended Member 2 boundary:

Member 2  
Order Intent → Order Lifecycle → Broker Adapter → Broker Event → Execution State

Cross-member integration was verified through the downstream chain:

Member 4 Strategy \-\> Risk Approval (Member 3\) \-\> Member 2 Order \-\> Broker \-\> Broker Event \-\> Member 1 Fill \-\> Position/P\&L

| Area | Member 2 responsibility | Boundary decision |
| :---- | :---- | :---- |
| Order lifecycle | Submission, status transitions, cancellation, broker updates | Included |
| Broker identity | Store and resolve broker\_order\_id against local order ID | Included |
| Execution events | Attribution, state validation, deduplication and safety | Included |
| Accounting | Preserve correct propagation to Member 1; do not own P\&L logic | Integration only |
| Risk controls | Respect risk/kill/recovery gates; do not redesign Member 3 | Boundary frozen |
| Strategy/market data | Consume upstream intent only; no strategy changes | Boundary frozen |

**021 adapter:** No speculative implementation; deferred until a concrete 021 specification is available.

# **3\. P0 Fix — Safe OPEN \-\> REJECTED Lifecycle**

## **3.1 Problem addressed**

The P0 issue was the unsafe lifecycle path from OPEN to REJECTED. The corrected behavior permits rejection only when the order has no executed quantity. This prevents an order with financial execution already attached to it from being silently moved into a clean rejected state.

## **3.2 Acceptance invariant**

OPEN  
  ├── filled\_quantity \= 0  → REJECTED  (allowed; zero financial mutation)  
  └── filled\_quantity \> 0  → reject transition (fail closed)

* REJECTED remains terminal.  
* Rejected orders cannot receive fills.  
* Existing executed quantity and positions are preserved.  
* No ledger/fill mutation is created by the rejection itself.

# **4\. P1 — Client Order ID \<-\> Broker Order ID Mapping**

## **4.1 Design goal**

Client / Local Order ID       Broker Order ID  
        ord-123        \<-\>           brk-999

The local/client order ID remains the stable platform identity while the broker-provided order ID is stored separately. Broker events can therefore be attributed even when the broker and platform use different identifiers.

## **4.2 Implementation**

* Added an additive nullable broker\_order\_id TEXT column to the orders table.  
* Added an idx\_orders\_broker\_id index for broker-ID lookup.  
* Extended CanonicalOrder with optional broker\_order\_id: str | None \= None for backward compatibility.  
* Updated submission, ingestion, transition, cancellation and broker-update paths to resolve by either local ID or broker ID where appropriate.  
* Persisted broker\_order\_id in mock fixtures and restart/persistence flows.  
* Hardened snapshot verification to resolve orders/fills using either identifier.

## **4.3 Mapping test coverage**

| Scenario | Expected behavior | Result |
| :---- | :---- | :---- |
| Different client and broker IDs | Broker event resolves to stable local order | PASS |
| Broker update via broker\_order\_id | Fill attributed and accounted once | PASS |
| Duplicate broker event | No second fill/accounting mutation | PASS |
| Unknown broker ID | Fail safely; zero financial mutation | PASS |
| Same client/broker ID | Existing mocks remain compatible | PASS |
| Restart/persistence | Mapping remains available after reopen | PASS |

# **5\. P1 — Event Ordering and Causality**

## **5.1 Current broker contract finding**

The reported inspection found these fields on BrokerUpdate:

* update\_id — arbitrary event/update identifier; not a monotonic sequence.  
* order\_id — event target identifier, which may be local or broker-side.  
* update\_type and optional status/fill payloads.  
* fill\_id and fill timestamp within fill payloads.  
* timestamp — wall-clock time, not a sufficiently trustworthy distributed total-order source.

**Decision:** No new sequence-number architecture was introduced. Existing state-machine validation and ledger idempotency were treated as the minimum safe causality mechanism.

| Event condition | Protection used | Result |
| :---- | :---- | :---- |
| Duplicate fill | Ledger fill-ID deduplication | Ignored/idempotent |
| Conflicting duplicate | Fail-closed ledger validation | Rejected safely |
| Stale status | Strict transition validation | Illegal transition rejected |
| Terminal order update | Terminal-state protection | No regression |
| Partial-fill inconsistency | Executed-quantity/state consistency checks | Rejected safely |
| Overfill | Quantity bound validation | Fails closed to UNCERTAIN |

# **6\. P1 — Adversarial Hardening Suite**

A dedicated acceptance suite was added in tests/test\_member2\_acceptance.py. The reported suite covers ten failure/race classes:

| Failure / race class | Proof objective | Result |
| :---- | :---- | :---- |
| Duplicate broker event | Deduplication with zero second accounting mutation and audit evidence. | PASS |
| Cancel/fill race | Completed fill remains financially authoritative; no state regression. | PASS |
| Retry race after timeout | UNKNOWN/UNCERTAIN gating prevents blind resubmission; reconciliation resolves truth. | PASS |
| Out-of-order events | State-machine validation prevents stale status from corrupting execution state. | PASS |
| Late fill on cancelled order | Late execution is handled explicitly and audited without corrupting state. | PASS |
| Overfill | Execution beyond requested quantity is rejected and fails closed. | PASS |
| Disconnect/reconnect | Trading gate remains restricted until reconciliation is satisfied. | PASS |
| Incomplete snapshot | Incomplete snapshot raises SNAPSHOT\_INCOMPLETE / SnapshotError as designed. | PASS |
| Attribution mismatch / wrong broker ID | Mismatch is rejected with zero financial mutation. | PASS |
| Terminal rejected order | REJECTED cannot return to OPEN and cannot receive fills. | PASS |

# **7\. Cross-Member Integration Acceptance**

## **7.1 Successful execution chain**

Order Intent  
   ↓  
Risk Approval  
   ↓  
Member 2 Order  
   ↓  
Broker Submission / ACK  
   ↓  
Broker Fill (broker\_order\_id \= brk-chain-999)  
   ↓  
Resolve local order (ord-chain-123)  
   ↓  
Member 1 Ledger  
   ↓  
Position / P\&L

Reported acceptance result:

* Local order ord-chain-123 was mapped to broker order brk-chain-999.  
* A fill referencing the broker ID was resolved to the correct local order.  
* The Member 1 ledger applied the fill exactly once.  
* Position net quantity was reported as 60\.  
* Charges were reported as 2.50.  
* The duplicate broker event caused no second accounting mutation.

## **7.2 Timeout / ambiguity chain**

Broker timeout  
   ↓  
UNKNOWN  
   ↓  
No blind retry  
   ↓  
Reconciliation  
   ↓  
True state resolved to OPEN  
   ↓  
Safe execution resumes

## **7.3 Rejection chain**

OPEN  
   ↓  
Broker reject  
   ↓  
REJECTED  
   ↓  
Zero financial mutation  
   ↓  
No fill allowed

# **8\. Implementation File Inventory**

| File | Purpose of change | Category |
| :---- | :---- | :---- |
| backend/execution/orders.py | P0 rejection guard; broker-ID resolution across submission, ingest, transitions, cancellation and broker updates. | Production |
| backend/shared/contracts.py | Optional broker\_order\_id on CanonicalOrder. | Production |
| backend/shared/store.py | Additive orders.broker\_order\_id column and broker-ID index. | Production |
| backend/reliability/snapshots.py | Snapshot verification by local or broker order identifier. | Production |
| backend/broker/mock\_persistence.py | Preserve broker\_order\_id across mock persistence/restart. | Production/support |
| tests/test\_broker\_updates.py | P0, broker-ID mapping and causality regression coverage. | Test |
| tests/test\_execution\_state\_machine.py | OPEN \-\> REJECTED transition invariance test. | Test |
| tests/test\_member2\_acceptance.py | Dedicated adversarial and cross-member acceptance suite. | Test |
| uv.lock | Wheel hashes changed by uv environment setup; reported dependency versions unchanged. | Environment artifact |
| frontend/package-lock.json | Reported as modified by git status during local tooling. | Verification item |

**Important Git verification note:** The final agent output shows frontend/package-lock.json as modified in git status, while git diff \--name-only did not list it and the report labeled it a generated environment artifact. Because the evidence is internally inconsistent, this file should be inspected once with git diff \-- frontend/package-lock.json before final commit/merge. Untracked files are also not included by git diff \--name-only, so tests/test\_member2\_acceptance.py must be considered from git status as well.

# **9\. Final Verification Results**

| Verification | Reported command | Result |
| :---- | :---- | :---- |
| Focused acceptance tests | pytest tests/test\_member2\_acceptance.py \+ tests/test\_broker\_updates.py | PASS — reported passing |
| Earlier lifecycle-focused tests | pytest tests/test\_broker\_updates.py \+ tests/test\_execution\_state\_machine.py | PASS — 43 passed, 1 warning at Step 6 |
| Full suite | uv run \--extra dev pytest | PASS — 338 passed, 1 skipped, 1 warning |
| Lint | uv run \--extra dev ruff check backend/ tests/ | PASS — All checks passed |
| Whitespace / diff check | git diff \--check | PASS — Clean |

## **9.1 Test limitation and warning**

* One test was skipped: tests/test\_postgres\_integration.py. The agent reported that local execution uses SQLite and that the PostgreSQL integration is validated against the Neon target.  
* The warning was a StarletteDeprecationWarning from FastAPI/Starlette TestClient regarding httpx usage; it did not cause test failure.

# **10\. Final Member 2 Acceptance Matrix**

| Acceptance criterion | Status | Evidence summary |
| :---- | :---- | :---- |
| OPEN \-\> REJECTED safe only with zero executed quantity | PASS | P0 tests and final acceptance test |
| REJECTED remains terminal | PASS | Terminal-state adversarial test |
| Rejected order cannot receive fill | PASS | Terminal rejection fill test |
| Client ID \<-\> broker ID mapping | PASS | Dedicated mapping tests |
| Unknown broker ID fails safely | PASS | Attribution / wrong broker ID test |
| Duplicate events are idempotent | PASS | Duplicate event tests |
| Out-of-order events cannot corrupt state | PASS | Causality tests \+ state-machine validation |
| Partial-fill integrity | PASS | Partial-fill race/ordering tests |
| Overfill protection | PASS | Overfill adversarial test |
| Timeout has no blind retry | PASS | UNKNOWN/UNCERTAIN \+ reconciliation test |
| Member 1 receives valid fill exactly once | PASS | Cross-member chain test |
| Position/P\&L not duplicated | PASS | Ledger and integration assertions |
| No speculative 021 implementation | PASS | Explicitly deferred |
| Ruff clean | PASS | All checks passed |
| Full test suite | PASS | 338 passed, 1 skipped, 1 warning |

# **11\. Round 2 Task Board — Final State**

| ID | Task | Priority | Final status |
| :---- | :---- | :---- | :---- |
| M2-P0-01 | Fix OPEN \-\> REJECTED safely | P0 | DONE |
| M2-P0-02 | Timeout / ambiguity regression proof | P0 | COVERED BY FINAL HARDENING |
| M2-P1-01 | Client ID \<-\> Broker ID separation | P1 | DONE |
| M2-P1-02 | Broker event ordering / causality | P1 | DONE |
| M2-P1-03 | Adversarial event/race suite | P1 | DONE |
| M2-COND-01 | Real 021 adapter | Conditional | DEFERRED — 021 SPEC REQUIRED |
| P2 | Unrelated broker features / overengineering | P2 | DEFERRED |

# **12\. Reproducible Verification Commands**

For future review or final merge validation, the following command set is sufficient:

uv run \--extra dev pytest  
uv run \--extra dev ruff check backend/ tests/  
git diff \--check  
git diff \--stat  
git status \--short  
git diff \--name-only

Before committing, inspect any environment or package-lock changes explicitly:

git diff \-- uv.lock  
git diff \-- frontend/package-lock.json

# **13\. Final Conclusion**

Based on the reported implementation and verification output, Member 2 Round 2 has reached a PASS state. The work addressed the identified P0 lifecycle defect without weakening accounting integrity, added broker/client identity separation without unnecessary schema proliferation, used the existing state machine and ledger idempotency to handle causality safely, and expanded the proof surface with adversarial and cross-member tests.

The most important system-level result is that a broker execution referenced by an external broker order identifier can be resolved back to the stable local order and propagated exactly once into Member 1 accounting. The timeout and rejection paths were also demonstrated as fail-safe: ambiguous broker state is reconciled rather than blindly retried, and OPEN \-\> REJECTED performs no financial mutation when no execution exists.

**Final sign-off condition:** Before merging or committing, inspect frontend/package-lock.json explicitly because the final status output reported it as modified while the reported diff-name listing did not include it. This is a repository-hygiene check, not a functional test failure.


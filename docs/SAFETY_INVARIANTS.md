# Safety Invariants

These are stronger than feature descriptions. They are properties that should always remain true.

## I1 — No broker bypass
Every broker order created by AlgoShield must map to an approved platform risk decision.

## I2 — Fills create positions
For a strategy:
```text
position = sum(unique signed executed fills)
```
Submitted/accepted order quantity alone must never change position.

## I3 — Fill idempotency
The same broker fill must affect accounting at most once.

## I4 — Strategy attribution
Every platform-originated fill must be attributable to exactly one strategy instance.

## I5 — Position risk
An approved intent must not exceed configured projected exposure:
```text
abs(filled position + pending BUY + new BUY) <= limit
abs(filled position - pending SELL - new SELL) <= limit
```

## I6 — Kill gate
If global trading state is not `RUNNING`, new risk-increasing strategy intents cannot reach the broker.
An individually stopped or callback-faulted subscription also cannot reach the broker even while the global gate is `RUNNING`.

## I7 — Restart safety
Strategies must not auto-resume after process restart until reconciliation succeeds.

## I8 — Broker reconciliation
For each symbol, when the platform declares `HEALTHY`:
```text
sum(strategy virtual positions)
+ explicitly modeled external positions
== broker/account observed position
```
External/manual positions are not yet implemented: any unexplained difference fails closed.

## I9 — Kill completion
Kill is not `SUCCESS` merely because cancel/flatten commands were sent.

Success requires verified target state:
```text
open orders == 0
net broker positions == 0
virtual strategy positions == 0
elapsed time < 10 seconds for SUCCESS
```
according to sponsor sandbox semantics.

## I10 — Unknown state cannot increase risk
If broker/reconciliation state is materially uncertain, the system must block new exposure or enter an explicitly degraded mode.

## Suggested UI proof
Expose live invariant status:
- No risk bypass;
- Strategy sum == broker position;
- Duplicate fills processed = 0;
- Unattributed fills = 0;
- Reconciliation healthy;
- Trading gate state;
- Kill SLA result.

## Bootstrap limits
Mock tests encode I1-I10. The implementation assumes one process and serialized callbacks; real network deadlines, durable kill latch, feed freshness and arbitrary-code isolation are required before live execution. The dashboard reports gate/health and execution evidence, not a fabricated universal invariant pass. See PHASE_PLAN.md.

## Runtime Safety Proof projection

The read-only proof service exposes current evidence for: broker bypass prevention; fill-derived positions; fill idempotency; attribution; position-policy evidence; global gate/runtime consistency; restart reconciliation/resume ordering; fresh broker reconciliation; kill completion; and unknown-state containment. Historical policy reconstruction remains `UNKNOWN` where authoritative history is unavailable. Stale reconciliation, broker or feed evidence cannot be presented as verified. A STOPPED/KILLED platform may still be safe because proof verdict and trading state are separate.

Account net/gross checks and strategy checks reserve under the same process lock. Pending BUY and SELL endpoints are evaluated independently. Existing over-limit exposure may strictly reduce but may not increase. LIMIT-price reasonability uses only a fresh mark and Decimal arithmetic.

# 021 Integration — Known Unknowns

The official wire contract is documented in [OFFICIAL_API_CONTRACT](021/OFFICIAL_API_CONTRACT.md), with implementation order in [INTEGRATION_BLUEPRINT](021/INTEGRATION_BLUEPRINT.md). This branch now contains a bounded authenticated REST adapter, durable provider-order mapping, strict market-frame parsing, and a composed `MarketData021Provider`; all remain `IMPLEMENTED_UNVERIFIED` until a sandbox read-only smoke test is run. Mock/fixture evidence still cannot resolve provider fees, correction/bust semantics, complete history coverage, external/manual trade attribution, account mapping, or kill semantics.

Implemented transport scope:

- `Broker021Adapter` authenticates from process configuration, loads and validates the instrument catalogue, encodes paise/signed quantities, submits and asynchronously verifies cancellation, polls orders/trades/positions, and preserves `platform_order_id ↔ provider_order_id` in `broker_order_mappings`.
- Canonical fills are created only from per-order REST trade evidence with a non-empty `tradeId`; order WebSocket events remain status evidence and never manufacture fills.
- `MarketData021Provider` consumes the documented sampled market packets through the ephemeral-key WebSocket and converts cumulative volume conservatively. Feed failure is fail-closed.
- No live order has been submitted by this implementation task. Enablement is explicit and off by default; credentials must stay in ignored environment/process configuration.

Do not assume answers absent from the official contract or until harmless authorized sandbox evidence confirms them.

DEC-027's [broker identity contract](CONTRACTS.md) requires provider/account-scoped
mapping, durable restart/cancel translation and canonical snapshot normalization.
Mock identity collision rejection is verified; real 021 mapping is not implemented.
Referenced corrections/busts and independent fee revisions remain unsupported
until replacement/delta/ordering/identity/session semantics and fixtures arrive.
No benchmark's FIX/IBKR/Kite fields establish 021 behavior.

## Market data
- How are raw ticks delivered?
- REST, WebSocket, or both?
- Exact tick fields?
- Authoritative timestamp?
- Sequence number / event ID available?
- Per-tick quantity or cumulative volume?
- Can missed data be replayed after reconnect?

## Orders
- Authentication mechanism?
- Place/modify/cancel endpoints?
- Exact broker order statuses?
- Client order ID / idempotency key?
- What does a timeout mean operationally?
- Can we safely retry?

## Executions
- Are partial fills delivered individually?
- Is each fill/trade uniquely identified?
- Can complete day trade history be fetched?
- Are events guaranteed ordered?
- Can duplicates occur?

## Positions
- Can current authoritative positions be queried?
- Are positions netted at account level?
- How should opposing strategy positions be represented relative to broker net position?
- Can manual/external trades exist during evaluation?

## Charges / P&L
- Does 021 provide charges directly?
- If not, what sandbox charge table/formula is expected?
- Does max daily loss include unrealized P&L?
- Does it include charges?

## Risk behavior
- On individual strategy daily-loss breach: stop only, cancel, or flatten?
- How should open-order exposure count toward position limit?
- Are there broker-side rate limits that matter?

## Kill switch
- Does “within 10 seconds” mean:
  - cancel/flatten requests submitted, or
  - sandbox confirms zero orders + zero positions?
- How should kill behave when opposing virtual strategies externally net to zero?

## Evaluation
- How will hidden tests invoke our system?
- UI, HTTP API, provided harness, direct code, or a combination?
- What live-change categories should architecture expect?

## Engineering rule
All answers above belong in `021BrokerAdapter` / `MarketData021Provider` configuration and mapping logic, not scattered throughout the codebase.

## Research status (2026-10-07)
The supplied official guide establishes the documented endpoint/authentication and packet schemas summarized in the canonical contract. It does not supply a charges table, prove live trade-ID scope/order association, establish cross-day history completeness, or certify kill timing. Fixture behavior must not be presented as observed sponsor behavior.

Additional blockers: snapshot completeness/pagination and consistency, short-selling/product restrictions, bounded request deadlines, opposing virtual exit sequencing, delayed charge corrections, and durable kill recovery.

## 2026-10-09 remediation boundary

Local operator authority and account response scoping do not confirm sponsor authentication or multi-account API semantics. Broker021Adapter remains live-disabled. Execution identity/corrections, history completeness/consistency, charges, netting/shorting and measured live kill semantics remain UNKNOWN/BLOCKED. No sandbox or production Neon access occurred; local fixture/mock evidence is recorded in progress/INTEGRATION.md.

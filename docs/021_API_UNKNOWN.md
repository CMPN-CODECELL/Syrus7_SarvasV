# 021 Integration — Known Unknowns

Do not assume answers until sponsor documentation or mentoring confirms them.

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
Public 021 Carbon sign-up material was found, but no authoritative sandbox endpoint, authentication, tick/order/fill schema or charge table was established. No CONFIRMED_021_BEHAVIOR exists yet. See DECISIONS.md for sources and classification. Adapter placeholders raise NotImplementedError; mock behavior must not be presented as sponsor behavior.

Additional blockers: snapshot completeness/pagination and consistency, short-selling/product restrictions, bounded request deadlines, opposing virtual exit sequencing, delayed charge corrections, and durable kill recovery.

## 2026-10-09 remediation boundary

Local operator authority and account response scoping do not confirm sponsor authentication or multi-account API semantics. Broker021Adapter remains a raising placeholder. Execution identity/corrections, history completeness/consistency, charges, netting/shorting and measured live kill semantics remain UNKNOWN/BLOCKED. No sandbox or production Neon access occurred; local mock regression evidence is recorded in progress/INTEGRATION.md.

# Integration Rules

These rules exist to prevent four developers and multiple AI models from creating conflicting implementations.

## Rule 1 — One canonical model per concept
Do not create separate `TradeIntent`, `OrderIntent`, `BrokerOrderRequest`, etc. unless their semantics are truly different.

Use shared contracts.

## Rule 2 — Strategy boundary
Member 4 outputs `OrderIntent`.
It does not call broker code.

## Rule 3 — Risk boundary
Member 3 outputs `RiskDecision`.
Only allowed intents reach Member 2's order manager.

## Rule 4 — Broker boundary
Member 2 outputs canonical broker events/fills.
It does not update position/P&L itself.

## Rule 5 — Accounting boundary
Member 1 consumes fills and produces positions/P&L.

## Rule 6 — Reconciliation boundary
Member 3 reads canonical local state + broker snapshots.
Repairs must go through owning services rather than raw DB manipulation where practical.

## Rule 7 — UI is not a source of truth
Frontend cannot locally invent fill/order/kill success.

## Rule 8 — Shared changes require coordination
Any change to:
- shared contracts;
- order statuses;
- strategy states;
- risk reason codes;
- DB identifiers;
must be reviewed across affected owners.

## Rule 9 — Feature flags for incomplete integration
If real 021 support is incomplete, keep mock/replay mode working instead of breaking the system.

## Rule 10 — Merge discipline
Before merging:
- tests pass;
- no duplicate models were introduced;
- docs updated if contract changed;
- main end-to-end flow still works.

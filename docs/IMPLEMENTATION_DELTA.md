# Implementation delta

Current task sequencing and ownership live in [TEAM_EXECUTION_PLAN](TEAM_EXECUTION_PLAN.md), the sole execution plan under DEC-028. Evidence is in [requirements traceability](REQUIREMENTS_TRACEABILITY.md) and [integration progress](progress/INTEGRATION.md).

2026-10-09 official-contract update: endpoint/wire shapes are now documented and strict fixture normalization plus isolated 021-03 strategy policies exist. This narrows, but does not clear, the provider gate.

Confirmed remaining gaps:

- P0: wire the policies into subscription/runtime composition; run an approved sandbox read-only smoke test; resolve provider charges/correction semantics, full-history coverage, external/manual trade attribution, and verified live kill behavior.
- P0: verify 021 orders, per-order trade association, asynchronous cancellation, today's-history coverage and charges in an authorized sandbox; no fabricated adapter behavior.
- P0: isolated PostgreSQL transaction, restart and ownership evidence; production access is excluded.
- P0: real-provider reconciliation coverage and verified kill/flatten semantics, including opposing strategies.
- P1: actual React browser smoke, deployment Origin/proxy configuration and reproducible runtime evidence.
- Conditional: correction/late-fee accounting only after an accepted provider event contract.

Implemented in the current 021 integration branch (fixture-verified, live-unverified): bounded REST/auth transport, instrument cache validation, durable provider-order mapping, asynchronous cancel verification, per-order trade attribution, sampled market WebSocket provider, and fail-closed feed handling.

Existing mock accounting, risk reservations, security projection, runtime isolation bounds and evidence panels must be reused. A passing mock suite does not certify live readiness. Member research is evidence to assess, not independent implementation authority.

Feature-branch extension: DEC-029 adds authenticated atomic multi-stock subscription orchestration while preserving one strategy instance per symbol and independent state, risk, accounting and failure isolation. It is verified for offline mock/replay only and remains outside the DEC-028 release baseline until reviewed and integrated there. Live symbol availability remains provider-blocked.

The [pre-promotion delta](archive/2026-10-09/IMPLEMENTATION_DELTA-pre-promotion.md) retains previous decisions and task history; it is not an active competing plan.

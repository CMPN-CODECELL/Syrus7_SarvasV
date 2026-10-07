# GitHub Copilot Instructions

Use `AGENTS.md` as canonical project guidance.

Key constraints:
- maintain shared contracts from `docs/CONTRACTS.md`;
- obey module ownership boundaries in `docs/TEAM_OWNERSHIP.md`;
- never let strategy code call broker APIs directly;
- positions/P&L update only from fills;
- 021-specific details stay inside broker/market adapters;
- all risk rules are platform-enforced;
- kill switch closes the trading gate before cancellation/flattening;
- restart must reconcile before strategy execution resumes;
- add tests for every business-rule change.

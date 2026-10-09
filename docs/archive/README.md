# Documentation inventory and archive

Inventory/references checked 2026-10-09 using `python scripts/check_docs.py`
and `rg` across README, agent entrypoints, source, tests, scripts, CI and Markdown.
Initial inventory: 42 Markdown files, zero broken local links. The script emits
each path, classification and inbound references; rerun after future moves.
Textual references are a discovery aid, not proof that a workflow executes them.

| Classification | Disposition |
|---|---|
| Active authority | AGENTS, README; PROJECT_TRUTH, IMPLEMENTATION_DELTA, REQUIREMENTS/PS/TRACEABILITY, ARCHITECTURE, CONTRACTS, SAFETY_INVARIANTS, DECISIONS |
| Required runbooks | SECURITY_OPERATIONS, TESTING, DEMO_AND_DEBUG, MOCK_BROKER_API, 021_API_UNKNOWN, TEAM_OWNERSHIP, DOMAIN_GLOSSARY, INTEGRATION_RULES |
| Agent aliases/templates | CLAUDE, GEMINI, Copilot instructions, AI_TASK_TEMPLATE point to AGENTS; no independent plan |
| Current evidence | progress/INTEGRATION, ROUND2_INTEGRATION_AUDIT |
| Historical progress | All four member logs retained at original paths for handoff/history; optional task-specific reading |
| Candidate research | Member-1/member-2/member-3/member-4 and ROUND2_RESEARCH_UPDATE retained verbatim at supplied paths, linked from the audit; reported evidence only |
| Older raw research | AlgoShield.md retained; member progress references it |
| Earlier audit | CURRENT_REPO_AUDIT retained as historical evidence |

The following tracked files were moved with `git mv`; short redirects preserve
old inbound paths. No source/test/script/CI execution depends on their contents.
Original body/history is preserved; relative navigation links were repaired.

| Original path | Archived path | Reason |
|---|---|---|
| docs/PHASE_PLAN.md | [2026-10-09/PHASE_PLAN.md](2026-10-09/PHASE_PLAN.md) | Superseded phase backlog |
| usp_implementation_plan.md | [2026-10-09/usp_implementation_plan.md](2026-10-09/usp_implementation_plan.md) | Superseded USP proposal |
| usp_implementation_prompt.md | [2026-10-09/usp_implementation_prompt.md](2026-10-09/usp_implementation_prompt.md) | Old instructions must not restart implementation |
| docs/design.md | [2026-10-09/design.md](2026-10-09/design.md) | Historical public-site reference, not product/API authority |

Applied migrations, executable fixtures, decision history, requirements,
deployment runbooks and user research were not deleted or relocated.

The [pre-promotion implementation delta](2026-10-09/IMPLEMENTATION_DELTA-pre-promotion.md) preserves historical task ordering. The sole active execution plan is [TEAM_EXECUTION_PLAN](../TEAM_EXECUTION_PLAN.md).

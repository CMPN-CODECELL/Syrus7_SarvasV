# AlgoShield — Research Verdicts, Decision Trace and Uncertainties

> Research Sessions 1–7, consolidated 2026-10-09. This file distinguishes **external engineering principles**, **accepted project design**, **reported code**, and **unverified sponsor behavior**. It does not replace the append-only `docs/DECISIONS.md`.

## Evidence order

1. Authenticated sponsor requirement > convenient research interpretation.
2. Current checked-out source + actually-run tests establishes implementation status (not necessarily adequacy).
3. Accepted `DEC-*` decisions establish chosen design unless a new explicit decision supersedes them.
4. Official specs and vendor/provider docs establish their own system's semantics, **not 021's**.
5. Third-party open-source source files teach patterns; repo popularity and README claims are not proof of tested compatibility.
6. Old proposal files and AI research are hypotheses. Never auto-implement their sample code or migration numbers.

## Conflict-resolution register

| Question | Resolution | Code/docs action |
|---|---|---|
| Is the product a strategy marketplace? | NO; PS safety + execution platform | Keep profitable-ML/marketplace out of backlog |
| Is the frontend vanilla? | NO; DEC-025 React/Vite canonical | Correct old docs, keep static legacy artifact only |
| Must 19-case SafetyBench be built? | Reported built under DEC-024 | Inspect/tests before modification |
| Is a risk ACK a trade? | NO; executions only | Preserve accounting invariants |
| Does net account=0 imply every strategy flat? | NO | Separate account and virtual end-state fields/tests |
| Does cancel request imply cancellation? | NO; cancellation and fills may race | Maintain pending and late fill evidence |
| Does timeout imply rejection? | NO; UNKNOWN reserved | No blind retries |
| Can incomplete broker history be self-healed? | Not into exact economics | Hold/reconcile with attributable evidence only |
| Can a fresh position snapshot certify global health? | Not without coverage/consistency of orders/fills and commands | Scope and freshness checks |
| Can arbitrary user Python safely run in callback threads? | NO; current workers isolate mutation/latency, not hostile bytecode | Exclude code uploads |
| Does the local kill budget equal sponsor guarantee? | NO; nine seconds internal vs ten-second external target | Measure full elapsed, honest outcomes |
| May applied migrations be renamed/reused? | NO | Inspect checksum ledger, add forward-only migration |
| Is live 021 implemented? | Not established; stubs/uncertainty reported | Authentic contract and sandbox fixture gate |
| Can historical progress mark current branch PASS? | NO | Fresh dev integration suite |

## External sources → techniques → targeted tests

| Source (authority) | Established practice | Adopted/conditional adaptation | Test |
|---|---|---|---|
| [FIX order state changes](https://www.fixtrading.org/online-specification/order-state-changes/) (SPEC) | Cancel, status, partial fill, correction/bust distinct | Separate order/exec event state; explicit correction policy | Late fill and correction fixtures |
| [Kite Connect orders](https://kite.trade/docs/connect/v3/orders/) (PROVIDER DOC) | API order placement is not fill confirmation | ACK != position | Ack vs fill test |
| [NautilusTrader reconciliation](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/execution/reconciliation.md) (OPEN-SOURCE DOC) | Incomplete history can prevent financial reconstruction | Evidence-gated recovery; no synthetic unknown economics | Missing/offsetting fills |
| [NautilusTrader source](https://github.com/nautechsystems/nautilus_trader) (SOURCE) | Risk/execution/portfolio boundaries | Maintain local canonical modules; no framework rewrite | Adapter + integration |
| [LEAN brokerage interface](https://github.com/QuantConnect/Lean/blob/master/Common/Interfaces/IBrokerage.cs) (SOURCE) | Broker operations and events decoupled | BrokerAdapter canonical methods | Contract suite |
| [Hummingbot](https://github.com/hummingbot/hummingbot) (SOURCE) | Trade IDs, in-flight orders, fees | Provider-scoped fill dedupe and attribution | Duplicate/mismatch tests |
| [vn.py gateway](https://github.com/vnpy/vnpy/blob/master/vnpy/trader/gateway.py) (SOURCE) | Separate tick/order/trade/position gateway events | Keep raw broker payload out of domain | Mapping tests |
| [Trading Technologies risk examples](https://library-staging.tradingtechnologies.com/setup/risk-management/risk-limits/reference-risk-limits/account-position-examples/) (VENDOR DOC) | Worst-case exposure includes working orders | Directional pending reservations | Net/gross/race tests |
| [PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html) (DB DOC) | Row/advisory locks have precise scope and lifetime | One controller, transactional local reservation | Process+commit failure |
| [Hypothesis stateful](https://hypothesis.readthedocs.io/en/latest/stateful.html) (TEST DOC) | Generate state-machine action chains | Supplement deterministic race scheduling | Property tests |
| [OWASP API5](https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/) (SECURITY) | Function-level authorization must be enforced on backend | All privileged operations scoped | 401/403 and no mutation |

These are sources/patterns, not a claim of running every external project, a code-license clearance, or an independently audited regulatory assessment. Review the version-specific license before copying source.

## Accepted product capabilities (do not create duplicate implementations)

1. Explainable Execution Authority: server-side risk math, reservation, correlation and fill trace.
2. Evidence-Gated Recovery: order/fill/position coverage; UNKNOWN if missing.
3. Dual-Scope Exposure: independent virtual strategy positions + broker account net/gross policies.
4. Verified Emergency Shutdown: durable gate latch, observed broker result and historical certificate.
5. Adversarial Reliability Lab: mock-only deterministic test scenarios and bounded measurements.

Safety Proof, metrics and trace viewer are evidence components supporting these, not additional strategic product families. DEC-024 reports them implemented; verify first.

## Accepted exclusions/rejections

No fabricated charges, endpoints, snapshots, guarantee of external fills inside 10s, synthetic balancing fills, unconditional self-healing, production-grade safety claims from mock tests, arbitrary third-party code execution, unnecessary Kafka/Redis/microservices, machine-learning trading or a full broker/FIX engine rewrite.

## Unresolved sponsor questions (no guessing)

- Authentic 021 REST/WebSocket endpoint docs, credentials, rate limits, sandbox states, client idempotency identifiers and execution identity scope.
- Completeness, coverage intervals, pagination and consistency of order/fill/position history after disconnect/restart.
- Execution corrections/busts, per-fill charges, revisions and mark data semantics.
- Instrument/product/shorting rules and broker netting behavior for opposing virtual strategies and individual emergency exits.
- Precisely what the sponsor calls a successful <10-second kill and whether externally rejected close orders count as failure.
- Market feed tick volume, timestamp identity, backfill, trading holidays and special sessions.
- Daily-loss calculation and account/multi-user permission model, where sponsor specific.

## Research-to-coding acceptance rule

No source claim becomes a code task until it is mapped to a real gap in `docs/IMPLEMENTATION_DELTA.md`, the corresponding source and live contract are inspected, and a failing or missing acceptance test is identified. Append genuinely new accepted trade-offs to `docs/DECISIONS.md`; update `docs/021_API_UNKNOWN.md` rather than asserting undocumented provider behavior.

## Conflict/resolution update (2026-10-09)

- PS.md now contains supplied PS-06 text. Claims that it is still a placeholder are superseded by inspected contents; authenticated sponsor provenance remains UNKNOWN.
- Anonymous privileged controls were already denied at b0930c5. The proven gaps were any-user global authority and unscoped nested/action responses; DEC-026 repairs these without rebuilding existing authentication.
- SQLite is now v12 and canonical intents accept MARKET/LIMIT. Old v2 and MARKET-only descriptions are historical bootstrap facts.
- Old phase/USP proposals are preserved with historical labels; current tasks come from IMPLEMENTATION_DELTA.
- Neon project identities are still unresolved; no production database was inspected or changed. PostgreSQL migration 011 is additive, with remote verification BLOCKED.

# Security operations

## Authorization policy

Public registration creates an ordinary account user and never grants operator
authority. Ordinary users may read their account projection and manage their own
subscriptions, strategy policy/state, account risk policy, and owned orders.

Platform-wide reconcile/resume/reduce-only/kill/reset, broker controls, market
override, account administration, replay, Failure Lab mutation, and SafetyBench
execution require an explicit durable operator grant. The existing database-backed
session verifies the grant before the operation; kill adds no network dependency.

Operators still receive only their account's financial and identity projection.
Global gate/health/verdict, kill result/timing, and aggregate diagnostics may be
shown without exposing another account's private evidence.

## Offline SQLite provisioning

Register the intended user, stop the backend, then run:

```powershell
python -m backend.shared.provision_operator --sqlite-path data/platform.db --username alice
python -m backend.shared.provision_operator --sqlite-path data/platform.db --username alice --revoke
```

Restart and sign in. Each protected request re-reads the durable grant, so
revocation affects existing sessions. The command requires an existing SQLite
file and registered user. It deliberately ignores `DATABASE_URL` and cannot
grant access in PostgreSQL or Neon.

## Deployment limits

SQLite provisioning is `IMPLEMENTED_VERIFIED` for offline mock/replay.
PostgreSQL migration `011_operator_grants.sql` is packaged but
`IMPLEMENTED_UNVERIFIED` because no isolated PostgreSQL database was available.
Production identity integration, secure-cookie/TLS policy, operator governance,
and Neon environment identity remain `BLOCKED`. Never point the offline CLI or
tests at production.

Failure Lab and SafetyBench also require the existing isolated mock guard.
Operator status never permits fault injection against PostgreSQL or a non-mock
broker.

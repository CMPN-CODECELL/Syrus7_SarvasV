# Security operations

## 021 credentials and mode boundary

`ALGOSHIELD_021_ENABLED` defaults to `false` and accepts only literal `true`/`false`. When explicitly enabled, the bounded REST/market transport reads UCC/password or bearer token from server process configuration; the browser never receives these values or an ephemeral WebSocket key. Credentials must never enter frontend state, audit payloads, fixtures or Git. A login invalidates the previous bearer token, so one bounded server-side owner per UCC must control refresh. This branch has not submitted a live order; operator provisioning alone does not authorize a broker write. Failure Lab remains current-platform SQLite/mock-only. SafetyBench is isolated: every run creates fresh in-memory SQLite/mock platforms and never touches the current 021 or PostgreSQL provider.

Git direct-push permission is separate from application operator authority. DEC-028 makes PRs optional and retains server-side permissions. No GitHub access grants or protection changes were made. Deployment Origin/proxy verification remains a task in [TEAM_EXECUTION_PLAN](TEAM_EXECUTION_PLAN.md).

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

## Demo Trader/Operator mode (DEC-042)

`ALGOSHIELD_DEMO_ROLE_MODE=true` removes signup/sign-in/sign-out from the demo
UI and enables `POST /api/demo-role` for exactly `trader` or `operator`. The
server owns the configurable usernames/account IDs, creates deliberately
password-disabled durable principals, issues an HttpOnly session, and continues
to derive operator authority from `operator_grants` on every request. The
browser cannot submit an account ID or `is_operator` value.

This is convenience, not authentication: anyone who can reach the demo can
select Operator. Configuration therefore refuses this mode when `DATABASE_URL`
is set and `NEON_BRANCH=production`. Use SQLite or a dedicated non-production
Neon branch, restrict network access, and never share 021/database secrets with
the browser. Ordinary password registration/login remains available only when
demo-role mode is disabled for compatibility tests and non-demo deployments.

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

Failure Lab requires the existing current-platform mock guard. SafetyBench's
isolated per-case platforms are independently mock-backed, so its operator
action may run while the current platform uses PostgreSQL or 021; it cannot
inject events into, submit orders to, or mutate that provider state.

## Browser and proxy policy (DEC-027)

`ALGOSHIELD_TRUSTED_ORIGINS` is a comma-separated exact allowlist from process
configuration or ignored .env files. Defaults permit localhost/127.0.0.1 ports
8000 and 5173 (Vite). Replace the list for deployment; never use wildcard or
derive trust from Host, Referer or forwarded headers. An explicitly empty list
denies all browser mutations and cookie WebSockets. No CORS allow-all is added.

Unsafe HTTP requests require a trusted Origin, including registration/login/
logout. Missing, null or untrusted Origin is denied before the route runs.
Nonbrowser requests may omit Origin only with explicit Bearer authorization;
the route still validates the token and account/operator authority. CLI login
must send a configured trusted Origin, then use the returned bearer token.
Cookie WebSockets require trusted Origin before acceptance. Nonbrowser WS may
omit Origin with a Bearer header and no cookie; query tokens alone do not waive
Origin. Any supplied untrusted Origin is rejected, including bearer requests.
Stream session revalidation and DEC-026 projection remain unchanged.

Run one worker with `--no-proxy-headers` (also the Docker default). Login limiting
uses the ASGI connection peer; it never reads X-Forwarded-For. Behind a proxy all
users may share one limit. Do not enable unrestricted forwarded-header trust;
production ingress/IP policy remains a deployment decision. Origin is a browser
CSRF boundary, not a credential or a substitute for authentication/TLS.

## Passwords, throttling and audits

New records use `pbkdf2-sha256$v1$600000$<digest>` and the existing random salt
column. Python standard-library PBKDF2-HMAC-SHA256 avoids a new dependency.
Legacy 64-hex salted SHA-256 verifies only for compatibility and upgrades using
a compare-and-swap on successful login. Wrong passwords never modify the record;
malformed/unsupported versions fail authentication. Sessions, accounts and
operator grants are unchanged; no migration is needed (existing TEXT columns).
Parameters follow [OWASP password guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Login allows five failures/in-flight attempts per peer per rolling 60 seconds,
using a monotonic clock. Successful attempts remove only their own reservation,
not other failures. Up to 1024 peers are retained; at capacity unseen peers are
temporarily denied instead of evicting active failures. Expiry cleans entries.
Generic 401/429 do not distinguish usernames. Blocked bursts create no repeated
audit entry; attempted login stores only outcome (LOGIN_FAILED/LOGIN_SUCCEEDED),
never username, IP, password, hash, salt or token. Headers add nosniff, DENY
framing and strict-origin-when-cross-origin referrer policy, including denials.
This process-local limiter resets on restart and is not distributed protection.

Secure cookies/TLS, identity integration, audit retention/storage limits and
public registration resource controls remain production deployment work.

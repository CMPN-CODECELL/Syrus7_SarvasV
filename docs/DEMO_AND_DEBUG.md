# Demo and debug

Start using README commands. Open the dashboard, run replay, inspect the three subscriptions, EMA/mean-reversion/5-minute-breakout signal evidence, attributed fills, both candle intervals, independent virtual positions, market-data counters and backend health. Demo ends STOPPED after reconciliation; enabled subscriptions show READY rather than pretending to run. Per-strategy stop/start is durable and risk-enforced. Kill produces actual mock closing fills and a verified certificate; failed/late results must remain visible.

Use tests to demonstrate partial fill, pending exposure, duplicate events, drift and restart. Do not edit broker/local values in UI to simulate success. API `/api/state` exposes actual audit and fill history, `/health` separates process uptime from trading gate. Swagger `/docs` exposes account/subscription endpoints.

Debug owner: wrong fills/P&L -> Member 1; submission/lifecycle -> Member 2; unsafe approval/drift/kill -> Member 3; ticks/candles/signals -> Member 4. First inspect gate, canonical order status, fill evidence and audit. UNKNOWN submissions must be reconciled, not resent blindly.

If persisted local history meets a fresh in-memory mock broker after restart, reconciliation failure is expected. Use a new DB path for a fresh demo; retain broker object in tests for recovery. Durable external mock state is pending.

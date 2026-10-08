# AlgoShield â€” Demo, Rehearsal & Debug Guide

## Overview
This document outlines deterministic demonstration scenarios, execution commands, and a step-by-step 4â€“5 minute live walkthrough script for technical vivas, hackathon evaluation, and regression validation.

All scenarios execute authentic platform workflows:
`Strategy Callback -> OrderIntent -> RiskGateway -> OrderManager -> MockBroker -> Fills -> Ledger`.
No positions or P&L figures are ever fabricated. Local state is expected state; broker state is observed truth.

---

## Concise Run Commands

### 1. Automated Rehearsal Runner (Non-Interactive)
Run all 7 deterministic scenarios sequentially in an isolated temporary SQLite database:
```bash
python scripts/rehearsal_runner.py
```

Run a specific scenario:
```bash
# Available: candles, partial, risk, recovery, restart, kill, drift
python scripts/rehearsal_runner.py --scenario candles
python scripts/rehearsal_runner.py --scenario partial
python scripts/rehearsal_runner.py --scenario risk
python scripts/rehearsal_runner.py --scenario recovery
python scripts/rehearsal_runner.py --scenario restart
python scripts/rehearsal_runner.py --scenario kill
python scripts/rehearsal_runner.py --scenario drift
```

### 2. Interactive Dashboard Rehearsal (UI Inspection)
Pre-populate an isolated database with authentic multi-strategy trades, orders, fills, and risk audit logs, then launch the local HTTP server:
```bash
python scripts/rehearsal_runner.py --serve --port 8000
```
- **Dashboard UI**: `http://127.0.0.1:8000`
- **Swagger API**: `http://127.0.0.1:8000/docs`
- **Demo User Credentials**: `username: demo_user`, `password: password123`

### 3. Scenario Regression Suite
Execute the dedicated deterministic test suite:
```bash
python -m pytest tests/test_demo_scenarios.py -v
```

Execute the full platform test suite:
```bash
python -m pytest -q --basetemp=.pytest-tmp
```

---

## 4â€“5 Minute Navigation & Live Demo Script

| Time | Phase | Target Screen / Endpoint | Key Observations & Talking Points |
| :--- | :--- | :--- | :--- |
| **0:00 â€“ 0:45** | **Clean Startup & Account Authentication** | `http://127.0.0.1:8000/login` | â€¢ Log in as `demo_user` (`password123`).<br>â€¢ Note server-side session token issued and verified.<br>â€¢ Platform initializes in clean state; storage is isolated temporary SQLite (`rehearsal.db`), never touching production Neon data.<br>â€¢ Gate transitions safely: `RECOVERING -> reconciled -> RUNNING`. |
| **0:45 â€“ 1:45** | **1m/5m Candles, Warmup & Opposing Strategy Entries** | Dashboard `Subscriptions` & `Positions` tables | â€¢ Point out 3 active strategy subscriptions on the **same account (`acc_demo`)**: `strat_mom` (momentum), `strat_mr` (mean reversion), and `strat_bo` (5m breakout) all trading **`TCS`**.<br>â€¢ Observe indicator warmup counter: exactly 5 candles required for momentum/mean reversion before emitting risk-increasing intents.<br>â€¢ When the 5th 1m candle closes, price surge triggers **simultaneous opposing signals**:<br>&nbsp;&nbsp;&nbsp;&nbsp;- `strat_mom` triggers **BUY** (3/5 EMA bullish crossover).<br>&nbsp;&nbsp;&nbsp;&nbsp;- `strat_mr` triggers **SELL** (close is +4.5% above 5-period mean).<br>â€¢ **Crucial architecture highlight**: Platform maintains independent virtual accounting per strategy. `strat_mom` has a **LONG** position (`+1`), while `strat_mr` has an opposing **SHORT** position (`-6`).<br>â€¢ Point to net broker position: broker sees only aggregate net (`-4`), while local platform faithfully tracks separate strategy P&L and Indian statutory charges. |
| **1:45 â€“ 2:45** | **5m Breakout, Partial Fill, Deduplication & Rejection** | Dashboard `Orders`, `Fills` & `Audit Timeline` | â€¢ At minute 10, the 5-minute candle closes above previous range high, triggering `strat_bo` **BUY**.<br>â€¢ Inspect `Orders` table: show order `intent_partial_1` in `PARTIALLY_FILLED` state (10 filled of 20 requested, remaining 10).<br>â€¢ Inspect `Audit Timeline`: show `DUPLICATE_FILL_IGNORED`. Point out that re-receiving an already processed fill ID alters zero ledger balances or positions.<br>â€¢ Inspect `intent_rej_1`: show broker rejection handled with `REJECTED` status without corrupting local state. |
| **2:45 â€“ 3:30** | **Non-Bypassable Platform Risk Layer & Missed Fill Recovery** | Dashboard `Audit Timeline` & `/api/state` | â€¢ Demonstrate risk policy enforcement: when an intent exceeds `max_position=5`, Platform Risk Gateway intercepts it **before** the broker, rejecting with code `RISK_MAX_POSITION`.<br>â€¢ Point out strategy code cannot bypass platform risk rules.<br>â€¢ Demonstrate missed fill recovery: show order `intent_missed_1` where a fill occurred at the broker during disconnected state. Upon reconciliation, the platform detects the unacknowledged fill in the broker snapshot, ingests it, advances order status from `OPEN` to `FILLED`, and syncs ledger quantity. |
| **3:30 â€“ 4:15** | **Process Restart Invariants (Fail Safe)** | Terminal & Dashboard `/api/state` | â€¢ Demonstrate reboot behavior: when the backend restarts, it starts in `Gate.RECOVERING` and `Health.RECOVERING` with strategies disabled.<br>â€¢ Show that the platform **never auto-resumes trading blindly** after a reboot.<br>â€¢ Only after successful reconciliation verifies persistent storage against the broker does `resume()` restore trading to `Gate.RUNNING` and `Health.HEALTHY`. |
| **4:15 â€“ 5:00** | **Verified Kill Switch & Unexplained Drift Blocking** | Dashboard `Kill Switch` & `Health Badge` | â€¢ Trigger Emergency Kill Switch via red dashboard button or `POST /api/kill`.<br>â€¢ Observe verified state transition under 10 seconds: execution gate latches closed (`KILLING -> KILLED`), pending orders are cancelled, counter flattening orders execute.<br>â€¢ Inspect `KillCertificate`: status `SUCCESS`, open orders `0`, broker positions `{}`, virtual positions `{}`.<br>â€¢ Demonstrate drift protection: inject an unverified external broker position (`UNEXPLAINED_DRIFT`).<br>â€¢ Reconciliation fails with `UNEXPLAINED_EXTERNAL_POSITION`. Platform transitions to `Gate.UNCERTAIN` and `Health.DRIFTED`.<br>â€¢ Point out that the platform **refuses to auto-fix or clear unexplained drift**, requiring human operator investigation. |

---

## Replay Dependencies & Constraints

1. **Ram's Broker Freshness Constraint (`RISK_STALE_BROKER_STATE`)**:
   - In `backend/reliability/control.py`, `check_evidence()` enforces that broker state was verified within `max_broker_age = 5` seconds (`-1 <= now - last_broker_at <= 5`).
   - In accelerated replay where an injected simulated clock advances minutes at a time (skipping wall-clock time), calling `p.reliability.resume()` at simulated minute intervals is an explicit rehearsal step to simulate periodic health checks. It is NOT proof of uninterrupted trading or automatic broker refresh.
   - For sustained real-time replay streams, synthetic ticks advance at a 1:1 wall-clock cadence with continuous background heartbeat sync.

2. **Operator Authorization Boundary**:
   - Global mutation endpoints (`POST /api/kill`, `POST /api/reconcile`, `POST /api/resume`, `PUT /api/risk/policies/{strategy}`) currently operate in offline demo mode. Platform-wide operator role authorization is being implemented by Ram (Member 3).

3. **External Drift Immutability**:
   - The platform strictly enforces that external position drift is never silently forgiven or synthesized away. A drifted platform can only resume after external broker truth aligns with local accounting.

---

## Component Debugging Ownership
- **Wrong Fills, Cash, or P&L**: Member 1 (Akshat). Inspect `backend/accounting/ledger.py` and `backend/accounting/charges.py`.
- **Order Submissions & Broker Lifecycle**: Member 2 (Sujal). Inspect `backend/execution/orders.py` and `backend/broker/adapters.py`.
- **Gate Closure, Drift, Reconcile & Kill Switch**: Member 3 (Ram). Inspect `backend/reliability/control.py` and `backend/risk/gateway.py`.
- **Market Data Ticks, Candles, Indicators & Strategy Callbacks**: Member 4. Inspect `backend/market_data/candles.py`, `backend/strategies/runtime.py`, and `backend/demo_scenarios.py`.

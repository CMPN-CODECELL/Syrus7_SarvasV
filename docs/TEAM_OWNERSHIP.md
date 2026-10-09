# Team Ownership

DEC-028 operational ownership: Member 1 owns accounting/persistence; Member 2 broker/execution contracts; Member 3 security/reliability and shared integration; Member 4 frontend/market-data consumers. Shared boundaries have one writer and affected-owner review. Use [TEAM_EXECUTION_PLAN](TEAM_EXECUTION_PLAN.md) for task packets and dependencies; historical assignments remain context.

The goal is equal, clean ownership so bugs are easy to localize.

## Member 1 — Accounting & Platform State
**Owns**
- execution/fill ledger;
- strategy virtual positions;
- weighted average price;
- realized/unrealized P&L;
- charges and net P&L;
- accounting database models;
- idempotent fill application;
- accounting UI panels.

**Primary question:** “What actually happened financially?”

**Must not**
- approve orders;
- parse raw 021 API payloads;
- generate strategy signals.

---

## Member 2 — Broker & Order Execution
**Owns**
- `BrokerAdapter`;
- `MockBrokerAdapter`;
- `021BrokerAdapter`;
- order state machine;
- place/modify/cancel;
- broker order/fill stream;
- reconnect handling;
- canonical mapping of broker statuses;
- broker/execution UI panels.

**Primary question:** “How does an approved order reach 021 and what happened to it?”

**Must not**
- mutate positions/P&L directly;
- implement trading strategy logic;
- silently bypass risk.

---

## Member 3 — Risk & Reliability
**Owns**
- `RiskGateway`;
- max position;
- max daily loss;
- max orders/minute;
- exposure reservation;
- global trading gate;
- strategy/global health states;
- reconciliation;
- fail-closed restart;
- kill switch;
- kill certificate;
- failure/reliability UI.

**Primary question:** “How do we remain safe when things fail?”

**Must not**
- calculate strategy signals;
- parse raw broker payloads;
- directly own accounting formulas.

---

## Member 4 — Market Data & Strategies
**Owns**
- `MarketDataProvider`;
- replay/mock feed;
- 021 market feed adapter;
- tick normalization;
- 1m/5m candles;
- EMA crossover;
- breakout;
- mean reversion;
- strategy subscription/runtime;
- strategy signal UI.

**Primary question:** “How does market data become a trade intent?”

**Must not**
- call broker directly;
- mutate position/P&L;
- bypass risk.

---

## Shared responsibilities
All members:
- maintain shared contracts;
- write tests for owned modules;
- help integration tests;
- understand the complete order → fill → position → P&L → risk flow;
- participate in viva preparation.

## Bootstrap file boundaries
- Member 1: `backend/accounting/`, accounting-facing schema and frontend ledger panel.
- Member 2: `backend/broker/`, `backend/execution/`, broker interfaces and order panels.
- Member 3: `backend/risk/`, `backend/reliability/`, risk policies and safety panels.
- Member 4: `backend/market_data/`, `backend/strategies/`, account/subscription APIs and signal panels.
- Shared coordination: `backend/shared/`, composition (`platform.py`), API wiring, CI/tooling and cross-module tests. No service writes another owner's financial tables; execution ingests through Ledger.apply.

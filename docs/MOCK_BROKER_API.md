# Mock Broker HTTP API

> [!IMPORTANT]
> **Prototype Broker Simulator Disclaimer**
> This HTTP API is an AlgoShield prototype broker simulator built for PS-06 testing, demonstrations, and Failure Lab scenarios while official sponsor 021 API documentation and sandbox credentials remain unavailable.
> It is **NOT** an imitation of the undocumented 021 API, and it does not claim compatibility with official 021 endpoints, payload formats, or authentication schemes.

---

## 1. Purpose
The Mock Broker HTTP API exposes an external broker boundary over HTTP. It allows AlgoShield to demonstrate:
- Order placement (market orders, acceptance, rejection);
- Partial fills and multi-stage executions;
- Full fills and remaining quantity decrement;
- Order cancellation on open and partially-filled orders;
- Authoritative broker account positions;
- Coherent, complete broker snapshots (`BrokerSnapshot`);
- Simulated timeout after acceptance (`504 Gateway Timeout` where broker retained state);
- Client disconnect and reconnect fail-closed semantics;
- External broker-side executions during client disconnection and subsequent reconciliation recovery;
- State persistence across mock broker process restarts.

---

## 2. Architecture
The Mock Broker HTTP API is intentionally decoupled from AlgoShield's internal control-plane API (`backend/api.py`). It runs as an independent service and wraps the canonical [`MockBrokerAdapter`](file:///C:/Users/dyara/AlgoShield/backend/broker/adapters.py) engine.

```
                           AlgoShield Platform (Port 8000)
                                      |
                            [Future HTTP Adapter]
                                      | (HTTP)
                                      v
                      Mock Broker HTTP API (e.g., Port 9001)
                                      |
                            MockBrokerAdapter
                         /          |          \
                    Orders        Fills      Positions
                         \          |          /
                        MockPersistence (JSON)
```

No platform risk checks, accounting virtual positions, or strategy logic live in the mock broker API; the mock broker represents external execution truth only.

---

## 3. How to Run It

Start the standalone mock broker server using `uvicorn`:
```bash
uvicorn backend.broker.mock_api:app --port 9001 --host 0.0.0.0
```

Optionally configure a persistent state file path using an environment variable:
```bash
# Windows PowerShell
$env:MOCK_BROKER_STORAGE_PATH = "data/mock_broker.json"
uvicorn backend.broker.mock_api:app --port 9001
```

Programmatic application factory:
```python
from backend.broker.mock_api import create_mock_broker_app

app = create_mock_broker_app(storage_path="data/mock_broker.json")
```

---

## 4. Main Routes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health and connectivity status (`{"service": "algoshield-mock-broker", "connected": bool}`). Never fails closed when disconnected. |
| `POST` | `/orders` | Submit order intent (`intent_id`, `strategy_instance_id`, `account_id`, `symbol`, `side`, `quantity`). Returns `201 Created` with canonical order evidence. |
| `GET` | `/orders` | Retrieve list of all orders known to the broker. |
| `GET` | `/orders/{order_id}` | Retrieve specific canonical order by order ID. |
| `POST` | `/orders/{order_id}/fills` | Simulate fill execution (`quantity`, `price`, `charges`). Returns `201 Created` with `Fill` evidence. |
| `GET` | `/fills` | Retrieve list of all executed fills. |
| `GET` | `/orders/{order_id}/fills` | Retrieve fills for a specific order. |
| `POST` | `/orders/{order_id}/cancel` | Request cancellation of open or partially-filled order. |
| `GET` | `/positions` | Authoritative mock broker account-level positions (`{"positions": [{"account_id": "...", "symbol": "...", "quantity": ...}]}`). |
| `GET` | `/snapshot` | Authoritative broker snapshot (`orders`, `fills`, `positions`, `is_complete: true`, `observed_at`). |
| `GET` | `/updates` | Polling endpoint for queued canonical broker updates. |
| `POST` | `/updates/drain` | Fetch and clear queued canonical broker updates. |

---

## 5. Controlled Failure Injection Routes (`/mock/*`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/mock/reject-next` | Sets mock flag to reject the next submitted order. |
| `POST` | `/mock/timeout-after-accept` | Simulates ambiguous submission: broker persists the accepted order but returns `504 Gateway Timeout` to caller. |
| `POST` | `/mock/disconnect` | Marks broker disconnected. All operational endpoints subsequently return `503 Service Unavailable`. |
| `POST` | `/mock/reconnect` | Restores normal broker connectivity. |
| `POST` | `/mock/orders/{order_id}/external-fill` | Simulates an execution occurring on the broker side while the client is disconnected. |
| `POST` | `/mock/reset` | Resets orders, fills, positions, queued updates, failure flags, and restores connection to clean state. |

---

## 6. Example Demo Walkthroughs

### Partial Fill Demo Walkthrough
```bash
# 1. Place BUY order for 100 shares
curl -X POST http://localhost:9001/orders \
  -H "Content-Type: application/json" \
  -d '{"intent_id": "order-1", "strategy_instance_id": "strat-1", "account_id": "acc-1", "symbol": "TCS", "side": "BUY", "quantity": 100}'
# -> {"order_id": "order-1", "status": "OPEN", "filled_quantity": 0, "remaining_quantity": 100, ...}

# 2. Simulate partial execution of 40 shares @ 3500.00
curl -X POST http://localhost:9001/orders/order-1/fills \
  -H "Content-Type: application/json" \
  -d '{"quantity": 40, "price": "3500.00", "charges": "5.00"}'
# -> {"fill_id": "order-1:40", "quantity": 40, "price": "3500.00", ...}

# 3. Inspect updated order state
curl http://localhost:9001/orders/order-1
# -> {"order_id": "order-1", "status": "PARTIALLY_FILLED", "filled_quantity": 40, "remaining_quantity": 60, ...}

# 4. Check broker positions
curl http://localhost:9001/positions
# -> {"positions": [{"account_id": "acc-1", "symbol": "TCS", "quantity": 40}]}

# 5. Cancel remaining 60 shares
curl -X POST http://localhost:9001/orders/order-1/cancel
# -> {"order_id": "order-1", "status": "CANCELLED", "filled_quantity": 40, "remaining_quantity": 60, ...}
```

### Ambiguous Timeout & Recovery Walkthrough
```bash
# 1. Arm simulated timeout
curl -X POST http://localhost:9001/mock/timeout-after-accept
# -> {"timeout_after_accept": true}

# 2. Submit order — returns 504 Gateway Timeout
curl -i -X POST http://localhost:9001/orders \
  -H "Content-Type: application/json" \
  -d '{"intent_id": "order-timeout-1", "strategy_instance_id": "strat-1", "account_id": "acc-1", "symbol": "INFY", "side": "BUY", "quantity": 50}'
# -> HTTP/1.1 504 Gateway Timeout
# -> {"detail": "acceptance is ambiguous to caller", "simulated_timeout": true}

# 3. Query broker snapshot to resolve ambiguous state
curl http://localhost:9001/snapshot
# -> Returns snapshot proving order-timeout-1 is actually OPEN at the broker!
```

---

## 7. Future HTTP Adapter Integration
After this task, a future HTTP broker adapter (`HTTPMockBrokerAdapter`) implementing the [`BrokerAdapter`](file:///C:/Users/dyara/AlgoShield/backend/broker/adapters.py) protocol can point to this service over HTTP without altering AlgoShield's core risk, execution, or accounting layers.

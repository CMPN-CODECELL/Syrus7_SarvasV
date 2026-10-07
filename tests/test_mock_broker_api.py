from pathlib import Path

from fastapi.testclient import TestClient

from backend.broker.mock_api import create_mock_broker_app


def test_mock_broker_api_health():
    app = create_mock_broker_app()
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "algoshield-mock-broker"
    assert data["connected"] is True


def test_mock_broker_api_order_placement_and_retrieval():
    app = create_mock_broker_app()
    client = TestClient(app)

    order_payload = {
        "intent_id": "intent-101",
        "strategy_instance_id": "strat-1",
        "account_id": "acc-1",
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 100,
        "order_type": "MARKET",
    }
    res = client.post("/orders", json=order_payload)
    assert res.status_code == 201
    order = res.json()
    assert order["order_id"] == "intent-101"
    assert order["status"] == "OPEN"
    assert order["filled_quantity"] == 0
    assert order["remaining_quantity"] == 100
    assert order["symbol"] == "RELIANCE"
    assert order["side"] == "BUY"

    # GET /orders/{order_id}
    res_get = client.get("/orders/intent-101")
    assert res_get.status_code == 200
    assert res_get.json()["order_id"] == "intent-101"

    # GET /orders
    res_all = client.get("/orders")
    assert res_all.status_code == 200
    assert len(res_all.json()) == 1

    # Non-existent order
    res_missing = client.get("/orders/missing-id")
    assert res_missing.status_code == 404


def test_mock_broker_api_partial_and_complete_fills():
    app = create_mock_broker_app()
    client = TestClient(app)

    client.post(
        "/orders",
        json={
            "intent_id": "intent-fill-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "TCS",
            "side": "BUY",
            "quantity": 100,
        },
    )

    # Partial fill 40
    fill_payload_1 = {
        "quantity": 40,
        "price": "3500.50",
        "charges": "5.25",
    }
    res_fill1 = client.post("/orders/intent-fill-1/fills", json=fill_payload_1)
    assert res_fill1.status_code == 201
    f1 = res_fill1.json()
    assert f1["quantity"] == 40
    assert f1["price"] == "3500.50"
    assert f1["charges"] == "5.25"
    assert f1["broker_order_id"] == "intent-fill-1"

    order_after_pfill = client.get("/orders/intent-fill-1").json()
    assert order_after_pfill["status"] == "PARTIALLY_FILLED"
    assert order_after_pfill["filled_quantity"] == 40
    assert order_after_pfill["remaining_quantity"] == 60

    # Overfill should fail (trying to fill 70 when remaining is 60)
    res_overfill = client.post(
        "/orders/intent-fill-1/fills",
        json={"quantity": 70, "price": "3501.00"},
    )
    assert res_overfill.status_code == 409

    # Complete fill 60
    res_fill2 = client.post(
        "/orders/intent-fill-1/fills",
        json={"quantity": 60, "price": "3502.00", "charges": "7.50"},
    )
    assert res_fill2.status_code == 201
    order_after_cfill = client.get("/orders/intent-fill-1").json()
    assert order_after_cfill["status"] == "FILLED"
    assert order_after_cfill["filled_quantity"] == 100
    assert order_after_cfill["remaining_quantity"] == 0

    # GET /fills and GET /orders/{order_id}/fills
    all_fills = client.get("/fills").json()
    assert len(all_fills) == 2
    order_fills = client.get("/orders/intent-fill-1/fills").json()
    assert len(order_fills) == 2


def test_mock_broker_api_positions():
    app = create_mock_broker_app()
    client = TestClient(app)

    client.post(
        "/orders",
        json={
            "intent_id": "intent-pos-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-demo",
            "symbol": "INFY",
            "side": "BUY",
            "quantity": 100,
        },
    )
    client.post(
        "/orders/intent-pos-1/fills",
        json={"quantity": 40, "price": "1500.00"},
    )

    res_pos = client.get("/positions")
    assert res_pos.status_code == 200
    positions = res_pos.json()["positions"]
    assert len(positions) == 1
    assert positions[0] == {"account_id": "acc-demo", "symbol": "INFY", "quantity": 40}


def test_mock_broker_api_cancellation():
    app = create_mock_broker_app()
    client = TestClient(app)

    # 1. Cancel OPEN order
    client.post(
        "/orders",
        json={
            "intent_id": "intent-cancel-open",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "SBIN",
            "side": "BUY",
            "quantity": 50,
        },
    )
    res_cancel1 = client.post("/orders/intent-cancel-open/cancel")
    assert res_cancel1.status_code == 200
    assert res_cancel1.json()["status"] == "CANCELLED"
    assert res_cancel1.json()["filled_quantity"] == 0

    # 2. Cancel PARTIALLY_FILLED order
    client.post(
        "/orders",
        json={
            "intent_id": "intent-cancel-pfill",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "HDFC",
            "side": "BUY",
            "quantity": 100,
        },
    )
    client.post(
        "/orders/intent-cancel-pfill/fills",
        json={"quantity": 40, "price": "1600.00"},
    )
    res_cancel2 = client.post("/orders/intent-cancel-pfill/cancel")
    assert res_cancel2.status_code == 200
    assert res_cancel2.json()["status"] == "CANCELLED"
    assert res_cancel2.json()["filled_quantity"] == 40
    assert res_cancel2.json()["remaining_quantity"] == 60

    # Repeated cancellation is idempotent and safe
    res_cancel_repeat = client.post("/orders/intent-cancel-pfill/cancel")
    assert res_cancel_repeat.status_code == 200
    assert res_cancel_repeat.json()["status"] == "CANCELLED"


def test_mock_broker_api_rejection_injection():
    app = create_mock_broker_app()
    client = TestClient(app)

    res_mock = client.post("/mock/reject-next")
    assert res_mock.status_code == 200
    assert res_mock.json()["reject_next"] is True

    res_order = client.post(
        "/orders",
        json={
            "intent_id": "intent-reject-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "WIPRO",
            "side": "BUY",
            "quantity": 30,
        },
    )
    assert res_order.status_code == 201
    order = res_order.json()
    assert order["status"] == "REJECTED"
    assert order["filled_quantity"] == 0


def test_mock_broker_api_snapshot():
    app = create_mock_broker_app()
    client = TestClient(app)

    client.post(
        "/orders",
        json={
            "intent_id": "intent-snap-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-snap",
            "symbol": "TATAMOTORS",
            "side": "BUY",
            "quantity": 100,
        },
    )
    client.post(
        "/orders/intent-snap-1/fills",
        json={"quantity": 40, "price": "750.00"},
    )

    res_snap = client.get("/snapshot")
    assert res_snap.status_code == 200
    snap = res_snap.json()
    assert snap["is_complete"] is True
    assert len(snap["orders"]) == 1
    assert snap["orders"][0]["order_id"] == "intent-snap-1"
    assert snap["orders"][0]["status"] == "PARTIALLY_FILLED"
    assert len(snap["fills"]) == 1
    assert snap["fills"][0]["quantity"] == 40
    assert snap["positions"] == [
        {"account_id": "acc-snap", "symbol": "TATAMOTORS", "quantity": 40}
    ]


def test_mock_broker_api_updates_and_drain():
    app = create_mock_broker_app()
    client = TestClient(app)

    # Submit -> ORDER_ACCEPTED
    client.post(
        "/orders",
        json={
            "intent_id": "intent-upd-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "AXISBANK",
            "side": "BUY",
            "quantity": 100,
        },
    )
    # Fill -> FILL
    client.post(
        "/orders/intent-upd-1/fills",
        json={"quantity": 50, "price": "1100.00"},
    )
    # Cancel -> ORDER_CANCELLED
    client.post("/orders/intent-upd-1/cancel")

    # Check updates without draining
    res_upds = client.get("/updates")
    assert res_upds.status_code == 200
    updates = res_upds.json()
    assert len(updates) == 3
    assert updates[0]["update_type"] == "ORDER_ACCEPTED"
    assert updates[1]["update_type"] == "FILL"
    assert updates[2]["update_type"] == "ORDER_CANCELLED"

    # Drain updates
    res_drain = client.post("/updates/drain")
    assert res_drain.status_code == 200
    drained = res_drain.json()
    assert len(drained) == 3

    # Subsequent drain should be empty
    res_drain_empty = client.post("/updates/drain")
    assert res_drain_empty.status_code == 200
    assert len(res_drain_empty.json()) == 0


def test_mock_broker_api_disconnect_reconnect():
    app = create_mock_broker_app()
    client = TestClient(app)

    # Disconnect
    res_dis = client.post("/mock/disconnect")
    assert res_dis.status_code == 200
    assert res_dis.json()["connected"] is False

    # /health still accessible but reports connected = False
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["connected"] is False

    # Normal operations fail closed with 503
    res_ord = client.post(
        "/orders",
        json={
            "intent_id": "intent-dis-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "ITC",
            "side": "BUY",
            "quantity": 100,
        },
    )
    assert res_ord.status_code == 503
    assert client.get("/snapshot").status_code == 503
    assert client.get("/positions").status_code == 503
    assert client.get("/orders").status_code == 503

    # Reconnect
    res_rec = client.post("/mock/reconnect")
    assert res_rec.status_code == 200
    assert res_rec.json()["connected"] is True

    # Operations work again
    res_ord2 = client.post(
        "/orders",
        json={
            "intent_id": "intent-dis-2",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "ITC",
            "side": "BUY",
            "quantity": 100,
        },
    )
    assert res_ord2.status_code == 201


def test_mock_broker_api_external_fill_during_disconnect():
    app = create_mock_broker_app()
    client = TestClient(app)

    # 1. Place order while connected
    client.post(
        "/orders",
        json={
            "intent_id": "intent-ext-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "LT",
            "side": "BUY",
            "quantity": 100,
        },
    )

    # 2. Client is disconnected
    client.post("/mock/disconnect")

    # 3. External broker fill occurs while client is disconnected
    res_ext = client.post(
        "/mock/orders/intent-ext-1/external-fill",
        json={"quantity": 40, "price": "3200.00"},
    )
    assert res_ext.status_code == 201
    assert res_ext.json()["quantity"] == 40

    # Normal client still cannot query snapshot
    assert client.get("/snapshot").status_code == 503

    # 4. Client reconnects and retrieves snapshot revealing the missed fill
    client.post("/mock/reconnect")
    snap = client.get("/snapshot").json()
    assert len(snap["fills"]) == 1
    assert snap["fills"][0]["quantity"] == 40
    assert snap["orders"][0]["filled_quantity"] == 40
    assert snap["orders"][0]["status"] == "PARTIALLY_FILLED"
    assert snap["positions"] == [
        {"account_id": "acc-1", "symbol": "LT", "quantity": 40}
    ]


def test_mock_broker_api_timeout_after_accept():
    app = create_mock_broker_app()
    client = TestClient(app)

    client.post("/mock/timeout-after-accept")

    res = client.post(
        "/orders",
        json={
            "intent_id": "intent-timeout-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "MARUTI",
            "side": "BUY",
            "quantity": 25,
        },
    )
    # Returns 504 Gateway Timeout
    assert res.status_code == 504
    assert res.json()["simulated_timeout"] is True

    # But broker actually persisted the order; subsequent snapshot reveals it exists!
    snap = client.get("/snapshot").json()
    assert len(snap["orders"]) == 1
    assert snap["orders"][0]["order_id"] == "intent-timeout-1"
    assert snap["orders"][0]["status"] == "OPEN"


def test_mock_broker_api_reset():
    app = create_mock_broker_app()
    client = TestClient(app)

    client.post(
        "/orders",
        json={
            "intent_id": "intent-reset-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-1",
            "symbol": "BAJAJ",
            "side": "BUY",
            "quantity": 50,
        },
    )
    client.post("/mock/disconnect")

    # Reset
    res_reset = client.post("/mock/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["reset"] is True
    assert res_reset.json()["connected"] is True

    # State is cleanly reset
    assert client.get("/health").json()["connected"] is True
    snap = client.get("/snapshot").json()
    assert len(snap["orders"]) == 0
    assert len(snap["fills"]) == 0
    assert len(snap["positions"]) == 0


def test_mock_broker_api_persistence(tmp_path: Path):
    storage_file = tmp_path / "mock_broker_state.json"

    # App 1: create order and fill
    app1 = create_mock_broker_app(storage_path=storage_file)
    client1 = TestClient(app1)
    client1.post(
        "/orders",
        json={
            "intent_id": "intent-persist-1",
            "strategy_instance_id": "strat-1",
            "account_id": "acc-p",
            "symbol": "CIPLA",
            "side": "BUY",
            "quantity": 100,
        },
    )
    client1.post(
        "/orders/intent-persist-1/fills",
        json={"quantity": 40, "price": "1200.00"},
    )

    # App 2: brand new app instance loading from same storage path
    app2 = create_mock_broker_app(storage_path=storage_file)
    client2 = TestClient(app2)

    snap = client2.get("/snapshot").json()
    assert len(snap["orders"]) == 1
    assert snap["orders"][0]["order_id"] == "intent-persist-1"
    assert snap["orders"][0]["filled_quantity"] == 40
    assert len(snap["fills"]) == 1
    assert snap["positions"] == [
        {"account_id": "acc-p", "symbol": "CIPLA", "quantity": 40}
    ]

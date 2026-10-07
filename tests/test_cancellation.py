from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.reliability.broker_calls import BrokerCallError
from backend.shared.contracts import (
    CanonicalOrder,
    OrderStatus,
)
from test_recovery import intent, ready


def test_cancel_open_order():
    p = ready()
    i = intent(p, "ord-open", 100)
    assert p.risk.submit(i).allowed

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-open'")
    assert rows[0]["status"] == OrderStatus.OPEN.value
    assert rows[0]["filled"] == 0

    cancelled = p.cancel("ord-open")
    assert isinstance(cancelled, CanonicalOrder)
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.filled_quantity == 0

    # Local DB updated
    updated = p.store.rows("SELECT * FROM orders WHERE id='ord-open'")[0]
    assert updated["status"] == OrderStatus.CANCELLED.value
    assert updated["filled"] == 0

    # Broker confirmed cancellation
    assert p.broker.orders["ord-open"].status == OrderStatus.CANCELLED

    # Audit evidence
    audits = [
        r
        for r in p.store.rows(
            "SELECT type, payload FROM audit WHERE payload LIKE '%ord-open%'"
        )
    ]
    types = [a["type"] for a in audits]
    assert "ORDER_CANCEL_REQUESTED" in types
    assert "ORDER_CANCELLED" in types

    # Ledger position remains 0 (orders are requests, not fills)
    assert p.ledger.quantity("a", "A", "X") == 0
    p.store.close()


def test_cancel_partially_filled_order():
    p = ready()
    i = intent(p, "ord-part", 100)
    p.risk.submit(i)

    # Fill 40 of 100
    fill = p.broker.execute("ord-part", 40, Decimal("100"), p.clock())
    p.ingest(fill)

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-part'")
    assert rows[0]["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert rows[0]["filled"] == 40
    assert p.ledger.quantity("a", "A", "X") == 40

    # Cancel remaining 60
    cancelled = p.cancel("ord-part")
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.filled_quantity == 40

    updated = p.store.rows("SELECT * FROM orders WHERE id='ord-part'")[0]
    assert updated["status"] == OrderStatus.CANCELLED.value
    assert updated["filled"] == 40

    # Audit records previous status and cancelled remainder
    cancel_audits = [
        r
        for r in p.store.rows(
            "SELECT type, payload FROM audit WHERE type='ORDER_CANCELLED'"
        )
        if "ord-part" in r["payload"]
    ]
    assert len(cancel_audits) == 1
    assert '"previous_status": "PARTIALLY_FILLED"' in cancel_audits[0]["payload"]
    assert '"filled": 40' in cancel_audits[0]["payload"]
    assert '"cancelled_quantity": 60' in cancel_audits[0]["payload"]

    # Fills are not reversed: accounting position remains 40
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_cancel_repeated_idempotent():
    p = ready()
    i = intent(p, "ord-idem", 50)
    p.risk.submit(i)

    res1 = p.cancel("ord-idem")
    assert res1.status == OrderStatus.CANCELLED

    # Second cancel must be safe, idempotent, and return current state without error
    res2 = p.cancel("ord-idem")
    assert res2.status == OrderStatus.CANCELLED
    assert res2.filled_quantity == 0

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-idem'")
    assert len(rows) == 1
    assert rows[0]["status"] == OrderStatus.CANCELLED.value
    p.store.close()


def test_cancel_filled_order_safe():
    p = ready()
    i = intent(p, "ord-filled", 50)
    p.risk.submit(i)

    fill = p.broker.execute("ord-filled", 50, Decimal("100"), p.clock())
    p.ingest(fill)

    # Order is completely FILLED
    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-filled'")
    assert rows[0]["status"] == OrderStatus.FILLED.value
    assert rows[0]["filled"] == 50

    # Cancelling a filled order safely returns FILLED without regression to CANCELLED
    res = p.cancel("ord-filled")
    assert res.status == OrderStatus.FILLED
    assert res.filled_quantity == 50

    updated = p.store.rows("SELECT * FROM orders WHERE id='ord-filled'")[0]
    assert updated["status"] == OrderStatus.FILLED.value
    p.store.close()


def test_cancel_unknown_order_fail_closed():
    p = ready()
    # Insert order in UNKNOWN state directly
    with p.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency, dispatch_started) "
            "VALUES ('ord-unk', 'A', 'a', 'X', 'BUY', 100, ?, 'UNKNOWN', 0, 0, 1)",
            (p.clock(),),
        )

    with pytest.raises(ValueError, match="reconciliation required before cancellation"):
        p.cancel("ord-unk")

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-unk'")
    assert rows[0]["status"] == "UNKNOWN"
    p.store.close()


def test_cancel_broker_failure_preserves_open():
    p = ready()
    i = intent(p, "ord-fail", 100)
    p.risk.submit(i)

    # Disconnect broker
    p.broker.connected = False

    with pytest.raises((BrokerCallError, ConnectionError)):
        p.cancel("ord-fail")

    # Local order MUST NOT be falsely marked CANCELLED
    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-fail'")
    assert rows[0]["status"] == OrderStatus.OPEN.value
    assert rows[0]["filled"] == 0

    fail_audits = [
        r
        for r in p.store.rows(
            "SELECT type, payload FROM audit WHERE type='ORDER_CANCEL_FAILED'"
        )
        if "ord-fail" in r["payload"]
    ]
    assert len(fail_audits) == 1
    p.store.close()


def test_cancel_unconfirmed_broker_status():
    p = ready()
    i = intent(p, "ord-unconf", 100)
    p.risk.submit(i)

    # Monkeypatch broker cancel to do nothing (so broker status remains OPEN)
    original_cancel = p.broker.cancel
    p.broker.cancel = lambda oid, timeout=None: None

    with pytest.raises(RuntimeError, match="cancellation not confirmed"):
        p.cancel("ord-unconf")

    # Local order MUST NOT transition to CANCELLED without broker evidence
    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-unconf'")
    assert rows[0]["status"] == OrderStatus.OPEN.value

    p.broker.cancel = original_cancel
    p.store.close()


def test_cancel_and_late_fills_race():
    p = ready()
    i = intent(p, "ord-race", 100)
    p.risk.submit(i)

    # Initial partial fill 40
    p.ingest(p.broker.execute("ord-race", 40, Decimal("100"), p.clock()))
    assert p.orders.cancel("ord-race").status == OrderStatus.CANCELLED

    # Late fill 20 arrives after cancellation
    late_fill_1 = p.broker.execute(
        "ord-race", 20, Decimal("100"), p.clock(), allow_late=True
    )
    p.ingest(late_fill_1)

    row = p.store.rows("SELECT * FROM orders WHERE id='ord-race'")[0]
    assert row["status"] == OrderStatus.CANCELLED.value
    assert row["filled"] == 60
    assert p.ledger.quantity("a", "A", "X") == 60

    # Final late fill 40 completes the requested 100 quantity -> transitions to FILLED
    late_fill_2 = p.broker.execute(
        "ord-race", 40, Decimal("100"), p.clock(), allow_late=True
    )
    p.ingest(late_fill_2)

    row2 = p.store.rows("SELECT * FROM orders WHERE id='ord-race'")[0]
    assert row2["status"] == OrderStatus.FILLED.value
    assert row2["filled"] == 100
    assert p.ledger.quantity("a", "A", "X") == 100
    p.store.close()


def test_cancel_api_endpoint():
    p = ready()
    i = intent(p, "ord-api", 50)
    p.risk.submit(i)

    app = create_app(p)
    with TestClient(app) as client:
        # Cancel existing order
        resp = client.post("/api/orders/ord-api/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CANCELLED"
        assert data["order_id"] == "ord-api"
        assert data["filled_quantity"] == 0

        # Cancel non-existent order returns 404
        resp_404 = client.post("/api/orders/non-existent/cancel")
        assert resp_404.status_code == 404
    p.store.close()

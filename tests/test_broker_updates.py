from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.execution.orders import IllegalOrderTransition
from backend.reliability.failure_lab import FailureLab
from backend.shared.contracts import (
    BrokerUpdate,
    BrokerUpdateType,
    Fill,
    OrderStatus,
    Side,
)
from test_recovery import intent, ready
from tests.usp_helpers import authenticate


@pytest.mark.parametrize("filled", [0, 40])
def test_authoritative_rejection_after_open_preserves_execution_truth(filled):
    p = ready()
    try:
        assert p.risk.submit(intent(p, "open-reject", 100)).allowed
        if filled:
            p.ingest(p.broker.execute("open-reject", filled, Decimal("100"), p.clock()))
        update = BrokerUpdate(
            update_id="reject-open",
            order_id="open-reject",
            update_type=BrokerUpdateType.ORDER_REJECTED,
            status=OrderStatus.REJECTED,
            timestamp=p.clock(),
        )
        if filled:
            with pytest.raises(IllegalOrderTransition):
                p.process_broker_update(update)
            expected = "PARTIALLY_FILLED"
        else:
            p.process_broker_update(update)
            expected = "REJECTED"
        row = p.store.rows("SELECT status, filled FROM orders WHERE id='open-reject'")[
            0
        ]
        assert (row["status"], row["filled"]) == (expected, filled)
        assert p.ledger.quantity("a", "A", "X") == filled
        budget = p.risk.budget("a", "A", "X")["position"]
        assert (budget["reserved_buy"], budget["reserved_sell"]) == (
            (60, 0) if filled else (0, 0)
        )
        if not filled:
            p.process_broker_update(update)
            assert p.risk.budget("a", "A", "X")["position"]["reserved_buy"] == 0
    finally:
        p.close()


def test_zero_fill_rejection_survives_restart_and_conserves_reservation(tmp_path):
    path = str(tmp_path / "rejection.db")
    p = ready(path)
    assert p.risk.submit(intent(p, "durable-reject", 100)).allowed
    p.process_broker_update(
        BrokerUpdate(
            update_id="final-reject",
            order_id="durable-reject",
            update_type=BrokerUpdateType.ORDER_REJECTED,
            timestamp=p.clock(),
        )
    )
    p.close()
    from backend.platform import Platform

    restarted = Platform(path)
    try:
        assert restarted.risk.state == "RECOVERING"
        assert (
            restarted.store.rows("SELECT status FROM orders WHERE id='durable-reject'")[
                0
            ]["status"]
            == "REJECTED"
        )
        assert restarted.risk.budget("a", "A", "X")["position"]["reserved_buy"] == 0
        assert restarted.ledger.quantity("a", "A", "X") == 0
        assert restarted.store.rows("SELECT * FROM fills") == []
    finally:
        restarted.close()


def test_open_update_from_unknown():
    p = ready()
    # Insert order in UNKNOWN state
    with p.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency, dispatch_started) "
            "VALUES ('ord-unk-open', 'A', 'a', 'X', 'BUY', 100, ?, 'UNKNOWN', 0, 0, 1)",
            (p.clock(),),
        )

    update = BrokerUpdate(
        update_id="upd-1",
        order_id="ord-unk-open",
        update_type=BrokerUpdateType.ORDER_ACCEPTED,
        status=OrderStatus.OPEN,
        timestamp=p.clock(),
    )
    res = p.process_broker_update(update)
    assert res.status == OrderStatus.OPEN
    assert res.filled_quantity == 0

    # Local DB updated
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-unk-open'")[0]
    assert row["status"] == OrderStatus.OPEN.value

    # Audit evidence
    audits = [
        r["type"]
        for r in p.store.rows(
            "SELECT type FROM audit WHERE payload LIKE '%ord-unk-open%'"
        )
    ]
    assert "BROKER_UPDATE_RECEIVED" in audits
    assert "BROKER_UPDATE_APPLIED" in audits
    p.store.close()


def test_rejected_update_from_unknown_has_no_financial_effect():
    p = ready()
    with p.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency, dispatch_started) "
            "VALUES ('ord-unk-rej', 'A', 'a', 'X', 'BUY', 100, ?, 'UNKNOWN', 0, 0, 1)",
            (p.clock(),),
        )

    update = BrokerUpdate(
        update_id="upd-rej",
        order_id="ord-unk-rej",
        update_type=BrokerUpdateType.ORDER_REJECTED,
        status=OrderStatus.REJECTED,
        timestamp=p.clock(),
    )
    res = p.process_broker_update(update)
    assert res.status == OrderStatus.REJECTED
    assert res.filled_quantity == 0

    row = p.store.rows("SELECT * FROM orders WHERE id='ord-unk-rej'")[0]
    assert row["status"] == OrderStatus.REJECTED.value

    # Zero financial effect
    assert p.ledger.quantity("a", "A", "X") == 0
    p.store.close()


def test_partial_fill_update():
    p = ready()
    i = intent(p, "ord-part-upd", 100)
    p.risk.submit(i)

    fill = p.broker.execute("ord-part-upd", 40, Decimal("100"), p.clock())
    update = BrokerUpdate(
        update_id="upd-fill-40",
        order_id="ord-part-upd",
        update_type=BrokerUpdateType.FILL,
        fill=fill,
        timestamp=p.clock(),
    )
    res = p.process_broker_update(update)
    assert res.status == OrderStatus.PARTIALLY_FILLED
    assert res.filled_quantity == 40

    row = p.store.rows("SELECT * FROM orders WHERE id='ord-part-upd'")[0]
    assert row["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert row["filled"] == 40
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_multiple_fills_to_complete():
    p = ready()
    i = intent(p, "ord-multi", 100)
    p.risk.submit(i)

    fill1 = p.broker.execute("ord-multi", 40, Decimal("100"), p.clock())
    upd1 = BrokerUpdate(
        update_id="upd-fill-1",
        order_id="ord-multi",
        update_type=BrokerUpdateType.FILL,
        fill=fill1,
        timestamp=p.clock(),
    )
    p.process_broker_update(upd1)

    fill2 = p.broker.execute("ord-multi", 60, Decimal("100"), p.clock())
    upd2 = BrokerUpdate(
        update_id="upd-fill-2",
        order_id="ord-multi",
        update_type=BrokerUpdateType.FILL,
        fill=fill2,
        timestamp=p.clock(),
    )
    res2 = p.process_broker_update(upd2)

    assert res2.status == OrderStatus.FILLED
    assert res2.filled_quantity == 100

    row = p.store.rows("SELECT * FROM orders WHERE id='ord-multi'")[0]
    assert row["status"] == OrderStatus.FILLED.value
    assert row["filled"] == 100
    assert p.ledger.quantity("a", "A", "X") == 100
    p.store.close()


def test_duplicate_fill_update_is_idempotent():
    p = ready()
    i = intent(p, "ord-dup-upd", 100)
    p.risk.submit(i)

    fill = p.broker.execute("ord-dup-upd", 40, Decimal("100"), p.clock())
    upd = BrokerUpdate(
        update_id="upd-dup-1",
        order_id="ord-dup-upd",
        update_type=BrokerUpdateType.FILL,
        fill=fill,
        timestamp=p.clock(),
    )
    p.process_broker_update(upd)
    assert p.ledger.quantity("a", "A", "X") == 40

    # Process identical fill again
    upd_dup = BrokerUpdate(
        update_id="upd-dup-2",
        order_id="ord-dup-upd",
        update_type=BrokerUpdateType.FILL,
        fill=fill,
        timestamp=p.clock(),
    )
    res_dup = p.process_broker_update(upd_dup)
    assert res_dup.status == OrderStatus.PARTIALLY_FILLED
    assert res_dup.filled_quantity == 40

    # No double-counting in ledger
    assert p.ledger.quantity("a", "A", "X") == 40

    audits = [
        r["type"]
        for r in p.store.rows(
            "SELECT type FROM audit WHERE payload LIKE '%ord-dup-upd%'"
        )
    ]
    assert "DUPLICATE_FILL_IGNORED" in audits
    p.store.close()


def test_cancellation_update_preserves_executed_quantity():
    p = ready()
    i = intent(p, "ord-cancel-upd", 100)
    p.risk.submit(i)

    # Partial fill of 40
    fill = p.broker.execute("ord-cancel-upd", 40, Decimal("100"), p.clock())
    p.process_broker_update(
        BrokerUpdate(
            update_id="upd-f40",
            order_id="ord-cancel-upd",
            update_type=BrokerUpdateType.FILL,
            fill=fill,
            timestamp=p.clock(),
        )
    )

    # Broker reports CANCELLED
    cancel_upd = BrokerUpdate(
        update_id="upd-cxl",
        order_id="ord-cancel-upd",
        update_type=BrokerUpdateType.ORDER_CANCELLED,
        status=OrderStatus.CANCELLED,
        timestamp=p.clock(),
    )
    res = p.process_broker_update(cancel_upd)
    assert res.status == OrderStatus.CANCELLED
    assert res.filled_quantity == 40

    row = p.store.rows("SELECT * FROM orders WHERE id='ord-cancel-upd'")[0]
    assert row["status"] == OrderStatus.CANCELLED.value
    assert row["filled"] == 40
    # Accounting position remains based on actual 40 executed fills
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_illegal_status_regression_rejected():
    p = ready()
    i = intent(p, "ord-regr", 50)
    p.risk.submit(i)

    fill = p.broker.execute("ord-regr", 50, Decimal("100"), p.clock())
    p.ingest(fill)

    # Order is FILLED
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-regr'")[0]
    assert row["status"] == OrderStatus.FILLED.value

    # Attempt illegal transition: FILLED -> OPEN via broker update
    illegal_upd = BrokerUpdate(
        update_id="upd-illegal",
        order_id="ord-regr",
        update_type=BrokerUpdateType.ORDER_ACCEPTED,
        status=OrderStatus.OPEN,
        timestamp=p.clock(),
    )
    with pytest.raises(IllegalOrderTransition):
        p.process_broker_update(illegal_upd)

    # Local state remains FILLED
    row_after = p.store.rows("SELECT * FROM orders WHERE id='ord-regr'")[0]
    assert row_after["status"] == OrderStatus.FILLED.value

    rej_audits = [
        r
        for r in p.store.rows(
            "SELECT type, payload FROM audit WHERE type='BROKER_UPDATE_REJECTED'"
        )
        if "ord-regr" in r["payload"]
    ]
    assert len(rej_audits) == 1
    p.store.close()


def test_attribution_mismatch_fails_closed():
    p = ready()
    i = intent(p, "ord-attr", 50)
    p.risk.submit(i)

    # Fill with mismatched symbol
    bad_fill = Fill(
        "bad-f-1",
        "ord-attr",
        "A",
        "a",
        "WRONG_SYMBOL",
        Side.BUY,
        10,
        Decimal("100"),
        p.clock(),
    )
    bad_upd = BrokerUpdate(
        update_id="upd-bad-attr",
        order_id="ord-attr",
        update_type=BrokerUpdateType.FILL,
        fill=bad_fill,
        timestamp=p.clock(),
    )
    with pytest.raises(ValueError, match="fill attribution mismatch"):
        p.process_broker_update(bad_upd)

    # Order remains OPEN with 0 fills
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-attr'")[0]
    assert row["status"] == OrderStatus.OPEN.value
    assert row["filled"] == 0

    audits = [
        r["type"]
        for r in p.store.rows("SELECT type FROM audit WHERE payload LIKE '%ord-attr%'")
    ]
    assert "BROKER_UPDATE_REJECTED" in audits
    p.store.close()


def test_sync_broker_updates_and_api():
    p = ready()
    # Submit order -> broker automatically creates ORDER_ACCEPTED update in mock queue
    i = intent(p, "ord-sync", 100)
    p.risk.submit(i)

    # Broker executes 40 -> adds FILL update
    p.broker.execute("ord-sync", 40, Decimal("100"), p.clock())

    # Verify mock adapter has accumulated updates
    updates = p.drain_broker_updates()
    assert len(updates) == 2
    types = [u.update_type for u in updates]
    assert BrokerUpdateType.ORDER_ACCEPTED in types
    assert BrokerUpdateType.FILL in types

    # Push updates back to test sync through API
    for u in updates:
        p.broker.emit_update(u)

    app = create_app(p)
    with TestClient(app) as client:
        authenticate(client, p)
        resp = client.post("/api/broker/updates/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 2

    # After sync, order is PARTIALLY_FILLED with 40
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-sync'")[0]
    assert row["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert row["filled"] == 40
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_failure_lab_broker_update_scenario():
    p = ready()
    lab = FailureLab(p)
    result = lab.run("broker_update")
    assert result["scenario"] == "broker_update"
    assert result["evidence"]["synced_updates_count"] >= 1
    assert result["evidence"]["executed_quantity"] == 40
    p.store.close()

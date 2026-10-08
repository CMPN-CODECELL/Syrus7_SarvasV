from dataclasses import replace
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.reliability.broker_calls import BrokerCallError
from backend.reliability.failure_lab import FailureLab
from backend.shared.contracts import OrderStatus
from test_recovery import intent, ready
from tests.usp_helpers import authenticate


def test_broker_disconnect_operations_fail():
    p = ready()
    res = p.disconnect_broker()
    assert res["connected"] is False
    assert p.broker.connected is False
    assert p.risk.state == "UNCERTAIN"

    # Audit records disconnection
    audits = [r["type"] for r in p.store.rows("SELECT type FROM audit")]
    assert "BROKER_DISCONNECTED" in audits
    assert "SAFETY_RESTRICTED" in audits

    # While disconnected, broker operations fail safely
    i = intent(p, "ord-fail-submit", 10)
    decision = p.risk.submit(i)
    # Risk gateway blocks submission while gate is UNCERTAIN
    assert not decision.allowed

    # Direct cancel or execute through broker calls fails safely
    with pytest.raises((BrokerCallError, ConnectionError)):
        p.broker_calls.call("snapshot")
    p.store.close()


def test_broker_reconnect_snapshot_available():
    p = ready()
    p.disconnect_broker()
    assert p.broker.connected is False

    rec = p.reconnect_broker()
    assert rec["connected"] is True
    assert rec["reconciled"] is True
    assert p.broker.connected is True

    audits = [r["type"] for r in p.store.rows("SELECT type FROM audit")]
    assert "BROKER_RECONNECTED" in audits
    assert "RECONCILED" in audits
    p.store.close()


def test_missed_fill_recovery_after_reconnect():
    p = ready()
    i = intent(p, "ord-missed", 100)
    assert p.risk.submit(i).allowed

    # Order is OPEN locally
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-missed'")[0]
    assert row["status"] == OrderStatus.OPEN.value
    assert row["filled"] == 0
    assert p.ledger.quantity("a", "A", "X") == 0

    # Broker disconnects
    p.disconnect_broker()
    assert p.risk.state == "UNCERTAIN"

    # Out-of-band trade execution happens at broker while AlgoShield is disconnected
    p.broker.connected = True
    p.broker.execute("ord-missed", 40, Decimal("100"), p.clock())
    p.broker.connected = False

    # Local state is still stale OPEN
    stale_row = p.store.rows("SELECT * FROM orders WHERE id='ord-missed'")[0]
    assert stale_row["status"] == OrderStatus.OPEN.value
    assert stale_row["filled"] == 0
    assert p.ledger.quantity("a", "A", "X") == 0

    # Reconnect and reconcile
    rec = p.reconnect_broker()
    assert rec["connected"] is True
    assert rec["reconciled"] is True

    # State repaired from broker truth
    repaired_row = p.store.rows("SELECT * FROM orders WHERE id='ord-missed'")[0]
    assert repaired_row["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert repaired_row["filled"] == 40
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_no_automatic_resume_after_reconnect():
    p = ready()
    p.disconnect_broker()
    rec = p.reconnect_broker()
    assert rec["reconciled"] is True

    # Trading must NOT silently resume to RUNNING
    assert p.risk.state == "STOPPED"
    assert rec["state"]["gate"] == "STOPPED"

    # Submissions remain blocked until explicit resume
    i = intent(p, "ord-blocked-until-resume", 10)
    decision = p.risk.submit(i)
    assert not decision.allowed

    # Explicit resume allows trading
    p.reliability.resume()
    assert p.risk.state == "RUNNING"
    p.store.close()


def test_unknown_order_recovery_on_reconnect():
    p = ready()
    p.broker.timeout_after_accept = True
    i = intent(p, "ord-unk-rec", 50)
    p.risk.submit(i)

    # Order is in UNKNOWN state
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-unk-rec'")[0]
    assert row["status"] == OrderStatus.UNKNOWN.value

    # Reconnect and reconcile
    rec = p.reconnect_broker()
    assert rec["reconciled"] is True

    # Order authoritatively transitioned to OPEN
    row_after = p.store.rows("SELECT * FROM orders WHERE id='ord-unk-rec'")[0]
    assert row_after["status"] == OrderStatus.OPEN.value
    p.store.close()


def test_incomplete_snapshot_on_reconnect_fails_closed(monkeypatch):
    p = ready()
    i = intent(p, "ord-incomp", 10)
    p.risk.submit(i)

    p.disconnect_broker()

    # Broker has incomplete snapshot
    def mock_incomplete_snapshot(timeout=None):
        snap = p.broker.snapshot()
        return replace(snap, is_complete=False)

    monkeypatch.setattr(p.broker_calls, "snapshot", mock_incomplete_snapshot)

    rec = p.reconnect_broker()
    assert rec["reconciled"] is False
    assert p.risk.state == "UNCERTAIN"
    p.store.close()


def test_broker_disconnect_and_reconnect_api():
    p = ready()
    app = create_app(p)
    with TestClient(app) as client:
        authenticate(client, p)
        # Disconnect
        resp_disc = client.post("/api/broker/disconnect")
        assert resp_disc.status_code == 200
        data_disc = resp_disc.json()
        assert data_disc["connected"] is False
        assert data_disc["state"]["gate"] == "UNCERTAIN"

        # Reconnect
        resp_rec = client.post("/api/broker/reconnect")
        assert resp_rec.status_code == 200
        data_rec = resp_rec.json()
        assert data_rec["connected"] is True
        assert data_rec["reconciled"] is True
        assert data_rec["state"]["gate"] == "STOPPED"
    p.store.close()


def test_failure_lab_disconnect_recovery_scenario():
    p = ready()
    lab = FailureLab(p)
    res = lab.run("disconnect_recovery")
    assert res["scenario"] == "disconnect_recovery"

    evidence = res["evidence"]
    assert evidence["before_disconnect"]["status"] == "OPEN"
    assert evidence["during_disconnect"]["connected"] is False
    assert evidence["during_disconnect"]["platform_state"] == "UNCERTAIN"
    assert evidence["broker_truth"]["filled"] == 40
    assert evidence["reconciliation_result"] is True
    assert evidence["after_reconciliation"]["status"] == "PARTIALLY_FILLED"
    assert evidence["after_reconciliation"]["filled"] == 40
    assert evidence["recovered_fill_quantity"] == 40
    assert evidence["position"] == 40
    p.store.close()

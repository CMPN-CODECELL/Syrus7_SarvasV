import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform


def test_replay_survives_real_platform_recreation(tmp_path):
    path = str(tmp_path / "platform.db")
    first = Platform(path)
    result = first.demo()
    quantity = first.ledger.aggregate()
    assert quantity
    first.store.close()
    second = Platform(path)
    assert second.risk.state == "RECOVERING"
    assert second.ledger.aggregate() == quantity
    assert second.reliability.reconcile()
    assert second.risk.state == "STOPPED"
    assert len(second.demo()["fills"]) > len(result["fills"])
    second.store.close()


def test_failure_lab_exposes_real_partial_rejection_and_risk():
    p = Platform()
    with TestClient(create_app(p)) as client:
        partial = client.post("/api/failure-lab/partial").json()
        assert partial["state"]["orders"][-1]["filled"] == 40
        assert partial["state"]["positions"][-1]["net_quantity"] == 40
        rejected = client.post("/api/failure-lab/rejection").json()
        assert rejected["state"]["orders"][-1]["status"] == "REJECTED"
        limited = client.post("/api/failure-lab/position_limit").json()
        assert limited["decisions"][-1]["reason_code"] == "RISK_MAX_POSITION"
        assert not limited["decisions"][-1]["allowed"]
        assert client.post("/api/kill").json()["status"] == "SUCCESS"
    p.store.close()


def test_corrupt_external_mock_fails_closed(tmp_path):
    path = str(tmp_path / "platform.db")
    p = Platform(path)
    p.demo()
    p.store.close()
    (tmp_path / "platform.db.broker.json").write_text("corrupt")
    with pytest.raises(ValueError, match="mock state unreadable"):
        Platform(path)

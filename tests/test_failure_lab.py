import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.platform import Platform


@pytest.mark.parametrize(
    "scenario",
    [
        "duplicate_fill",
        "conflicting_fill",
        "missed_fill",
        "unknown_submission",
        "spam",
        "stale_feed",
        "drift",
        "kill_partial",
    ],
)
def test_failure_lab_evidence(scenario):
    p = Platform()
    with TestClient(create_app(p)) as client:
        response = client.post("/api/failure-lab/" + scenario)
        assert response.status_code == 200
        result = response.json()
        if scenario == "duplicate_fill":
            assert result["evidence"]["applied_again"] is False
            assert result["state"]["safety"]["fills"]["duplicates_ignored"] >= 1
        elif scenario == "conflicting_fill":
            assert result["evidence"]["conflict_rejected"]
            assert result["state"]["gate"] == "UNCERTAIN"
        elif scenario == "missed_fill":
            assert result["evidence"]["quantity_before_recovery"] == 0
            assert result["evidence"]["quantity_after_recovery"] == 4
        elif scenario == "unknown_submission":
            assert result["state"]["safety"]["unknown_orders"]
            assert client.post("/api/reconcile").json()["reconciled"]
            assert len(p.broker.orders) == 1
        elif scenario == "spam":
            assert [d["reason_code"] for d in result["decisions"]] == [
                "ALLOWED",
                "ALLOWED",
                "RISK_RATE_LIMIT",
                "RISK_RATE_LIMIT",
            ]
        elif scenario == "stale_feed":
            assert result["decisions"][0]["reason_code"] == "RISK_STALE_MARKET_DATA"
        elif scenario == "drift":
            assert result["state"]["gate"] == "UNCERTAIN"
            assert (
                client.post("/api/failure-lab/clear_drift").json()["state"]["gate"]
                == "STOPPED"
            )
        else:
            assert result["evidence"]["kill"]["status"] == "SUCCESS"
    # Every normal and emergency broker order has an approving platform decision.
    approvals = {
        json.loads(r["payload"])["intent_id"]
        for r in p.store.rows("SELECT payload FROM audit WHERE type='RISK_DECISION'")
        if json.loads(r["payload"])["allowed"]
    }
    assert set(p.broker.orders) <= approvals
    p.store.close()


def test_disconnect_reconnect_requires_verification():
    p = Platform()
    with TestClient(create_app(p)) as client:
        assert (
            client.post("/api/failure-lab/disconnect").json()["state"]["gate"]
            == "UNCERTAIN"
        )
        assert (
            client.post("/api/failure-lab/reconnect").json()["state"]["gate"]
            == "STOPPED"
        )
    p.store.close()


def test_proof_expires_and_never_reads_as_live_after_restart(tmp_path):
    path = str(tmp_path / "proof.db")
    p = Platform(path)
    p.demo()
    assert p.snapshot()["safety"]["position_comparison"]["status"] == "VERIFIED"
    p.reliability.last_broker_at -= 6
    assert p.snapshot()["safety"]["position_comparison"]["status"] == "UNKNOWN"
    p.store.close()
    p = Platform(path)
    assert p.snapshot()["safety"]["position_comparison"]["status"] == "UNKNOWN"
    p.store.close()

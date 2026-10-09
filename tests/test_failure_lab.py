import json
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.platform import Platform
from tests.usp_helpers import authenticate


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
        authenticate(client, p, "failure-lab", f"user-{scenario}")
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


def test_failure_lab_scenarios_are_discovered_from_backend():
    p = Platform()
    with TestClient(create_app(p)) as client:
        authenticate(client, p, "failure-lab", "scenario-list-user")
        response = client.get("/api/failure-lab/scenarios")
        assert response.status_code == 200
        assert response.json()["scenarios"] == sorted(response.json()["scenarios"])
        assert "duplicate_fill" in response.json()["scenarios"]
    p.store.close()


def test_disconnect_reconnect_requires_verification():
    p = Platform()
    with TestClient(create_app(p)) as client:
        authenticate(client, p, "failure-lab", "disconnect-user")
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


def test_failure_lab_custom_parameters_and_metadata():
    p = Platform()
    with TestClient(create_app(p)) as client:
        authenticate(client, p, "failure-lab", "params-user")
        res = client.get("/api/failure-lab/scenarios")
        assert res.status_code == 200
        body = res.json()
        assert "details" in body
        assert "partial" in body["details"]
        partial_meta = body["details"]["partial"]
        assert "what_it_does" in partial_meta
        assert len(partial_meta["steps"]) >= 3
        assert len(partial_meta["parameters"]) >= 2

        # Run with custom parameters
        run_res = client.post(
            "/api/failure-lab/partial",
            json={"order_quantity": 50, "fill_quantity": 20},
        )
        assert run_res.status_code == 200
        run_body = run_res.json()
        assert run_body["status"] == "PASS"
        assert run_body["evidence"]["filled"] == 20
        assert run_body["parameters_used"]["order_quantity"] == 50
        assert run_body["parameters_used"]["fill_quantity"] == 20
        assert "simple_evidence" in run_body
        assert "explanation" in run_body
        assert "20 shares" in run_body["explanation"]
    p.store.close()

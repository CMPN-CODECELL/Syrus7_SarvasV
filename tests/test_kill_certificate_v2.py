from backend.platform import Platform
from backend.shared.contracts import KillCertificate


def test_kill_certificate_has_stage_timings_and_final_evidence():
    platform = Platform()
    certificate = platform.kill()
    assert certificate.status == "SUCCESS"
    assert certificate.target_seconds == 10
    assert certificate.stage_durations_ms["gate_closed"] >= 0
    assert certificate.stage_durations_ms["final_broker_verified"] >= 0
    assert certificate.final_evidence["open_orders"] == 0
    assert certificate.final_evidence["virtual_positions_flat"] is True
    platform.close()


def test_old_persisted_kill_certificate_contract_still_loads():
    old = KillCertificate("FAILED", 1.0, -1, {}, False, "old")
    assert old.target_seconds == 10
    assert old.stage_durations_ms == {}
    assert old.final_evidence == {}

from decimal import Decimal

from backend.platform import Platform
from backend.shared.contracts import Tick


def test_proof_is_read_only_and_freshness_expires_to_unknown():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    before = len(platform.store.rows("SELECT * FROM audit"))
    proof = platform.safety_proof.build()
    assert len(platform.store.rows("SELECT * FROM audit")) == before
    assert {item["status"] for item in proof["invariants"]} <= {
        "VERIFIED",
        "FAILED",
        "UNKNOWN",
        "NOT_APPLICABLE",
    }
    assert (
        next(item for item in proof["invariants"] if item["id"] == "I9")["status"]
        == "NOT_APPLICABLE"
    )
    platform.reliability.last_broker_at -= 6
    stale = platform.safety_proof.build()
    assert (
        next(item for item in stale["invariants"] if item["id"] == "I8")["status"]
        == "UNKNOWN"
    )
    assert stale["verdict"] != "VERIFIED_SAFE"
    platform.close()

from dataclasses import replace
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import OrderStatus, Tick
from tests.usp_helpers import authenticate


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class ConnectedProvider:
    supports_live_broker = True

    def stop(self):
        return True

    def telemetry(self):
        return {
            "provider": "021",
            "source": "021_LIVE",
            "connected": True,
            "last_received_at": None,
        }


class AlreadyStartedProvider(ConnectedProvider):
    symbols = ("X",)

    def start(self):
        return False


def configured_platform(*, external=False):
    clock = Clock()
    platform = Platform(clock=clock)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    if external:
        platform.configure_external_market_data(ConnectedProvider())
        source = "021_LIVE"
    else:
        source = "MOCK_REPLAY"
    platform.tick(
        Tick(
            "X", int(clock()), Decimal("100"), 0, "readiness-mark", data_source=source
        ),
        replay=not external,
    )
    return platform, clock


def test_connected_but_incomplete_and_missing_subscription_evidence_is_unknown(
    monkeypatch,
):
    platform, _ = configured_platform(external=True)
    complete = platform.broker.snapshot()
    monkeypatch.setattr(
        platform.broker_calls,
        "snapshot",
        lambda timeout=None: replace(complete, is_complete=False),
    )

    assert platform.reliability.reconcile() is False
    readiness = platform.provider_readiness("a")

    assert readiness["connectivity"]["market"]["status"] == "CONNECTED"
    assert readiness["subscription"]["status"] == "UNKNOWN"
    assert readiness["snapshot_coverage"]["status"] == "UNKNOWN"
    assert readiness["reconciliation"]["status"] == "UNKNOWN"
    assert readiness["resume"]["eligible"] is False
    assert readiness["actions"]["new_exposure"]["status"] == "BLOCKED"
    assert readiness["kill_verification"]["status"] == "UNKNOWN"
    platform.close()


def test_already_started_provider_still_starts_broker_evidence_worker(monkeypatch):
    platform = Platform()
    platform.broker.provider = "021"
    provider = AlreadyStartedProvider()
    platform.configure_external_market_data(provider)
    monkeypatch.setattr(platform, "start_broker_order_stream", lambda: True)

    assert platform.start_external_market_data() is False
    assert platform._broker_refresh_thread.is_alive()
    platform.close()


def test_fresh_generation_scoped_observation_proves_required_symbol_is_serving():
    platform, _ = configured_platform(external=True)
    platform.external_market_data.telemetry = lambda: {
        "provider": "021",
        "source": "021_LIVE",
        "connected": True,
        "last_received_at": platform.clock(),
        "subscribed_symbols": ["X"],
        "symbol_generations": {"X": 7},
        "serving_evidence": [
            {
                "symbol": "X",
                "evidence_type": "FRESH_VALID_OBSERVATION",
                "connection_generation": 7,
                "observed_at": platform.clock(),
            }
        ],
    }
    assert platform.reliability.reconcile() is True

    readiness = platform.provider_readiness("a")
    assert readiness["subscription"] == {
        "status": "VERIFIED",
        "observed_at": platform.clock(),
        "reason_code": "PROVIDER_SERVING_OBSERVATION_VERIFIED",
        "required_symbols": ["X"],
        "serving_symbols": ["X"],
    }
    assert readiness["resume"]["eligible"] is True
    platform.close()


def test_connection_and_send_list_alone_do_not_prove_serving():
    platform, _ = configured_platform(external=True)
    platform.external_market_data.telemetry = lambda: {
        "provider": "021",
        "source": "021_LIVE",
        "connected": True,
        "subscribed_symbols": ["X"],
        "requested_symbols": ["X"],
        "symbol_generations": {"X": 2},
        "serving_evidence": [],
    }
    assert platform.reliability.reconcile() is True
    readiness = platform.provider_readiness("a")
    assert readiness["subscription"]["status"] == "UNKNOWN"
    assert readiness["resume"]["eligible"] is False
    platform.close()


def test_symbol_a_evidence_does_not_authorize_symbol_b_or_old_generation():
    platform, _ = configured_platform(external=True)
    evidence = {
        "provider": "021",
        "source": "021_LIVE",
        "connected": True,
        "symbol_generations": {"X": 4},
        "serving_evidence": [
            {
                "symbol": "Y",
                "evidence_type": "FRESH_VALID_OBSERVATION",
                "connection_generation": 4,
                "observed_at": platform.clock(),
            }
        ],
    }
    platform.external_market_data.telemetry = lambda: evidence
    assert platform.reliability.reconcile() is True
    assert platform.provider_readiness("a")["subscription"]["status"] == "UNKNOWN"

    evidence["serving_evidence"][0]["symbol"] = "X"
    evidence["serving_evidence"][0]["connection_generation"] = 3
    assert platform.provider_readiness("a")["subscription"]["status"] == "UNKNOWN"
    platform.close()


def test_no_execution_demand_is_not_execution_ready():
    platform = Platform()
    platform.account("a")
    assert platform.reliability.reconcile() is True
    readiness = platform.provider_readiness("a")
    assert readiness["resume"]["eligible"] is False
    assert "NO_EXECUTION_DEMAND" in readiness["blocking_reason_codes"]
    platform.close()


def test_stale_market_and_broker_evidence_are_not_ready():
    platform, clock = configured_platform()
    assert platform.reliability.reconcile() is True
    clock.now += 16

    readiness = platform.provider_readiness("a")

    assert readiness["market_freshness"]["status"] == "STALE"
    assert readiness["broker_freshness"]["status"] == "STALE"
    assert readiness["resume"]["eligible"] is False
    assert readiness["actions"]["new_exposure"]["status"] == "BLOCKED"
    platform.close()


def test_broker_evidence_refresh_preserves_gate_only_for_complete_match(monkeypatch):
    platform, clock = configured_platform()
    platform.reliability.resume()
    gate = platform.risk.state
    clock.now += 4

    assert platform.reliability.refresh_broker_evidence() is True
    assert platform.risk.state == gate
    assert platform.reliability.last_broker_at == clock.now

    complete = platform.broker.snapshot()
    monkeypatch.setattr(
        platform.broker_calls,
        "snapshot",
        lambda timeout=None: replace(complete, is_complete=False),
    )
    assert platform.reliability.refresh_broker_evidence() is False
    assert platform.risk.state == "UNCERTAIN"
    assert platform.reliability.report["reason"] == "SNAPSHOT_INCOMPLETE"
    platform.close()


def test_complete_reconciliation_requires_explicit_resume():
    platform, _ = configured_platform()

    assert platform.reliability.reconcile() is True
    readiness = platform.provider_readiness("a")

    assert platform.risk.state == "STOPPED"
    assert platform.strategies.enabled is False
    assert readiness["reconciliation"]["status"] == "VERIFIED"
    assert readiness["resume"] == {
        "required": True,
        "eligible": True,
        "runtime_enabled": False,
        "reason_code": "EXPLICIT_RESUME_ELIGIBLE",
    }
    assert readiness["actions"]["new_exposure"]["status"] == "BLOCKED"
    platform.close()


def test_complete_reconciliation_does_not_replace_market_readiness():
    platform, clock = configured_platform()
    assert platform.reliability.reconcile() is True
    with platform.store.transaction() as db:
        db.execute(
            "UPDATE risk_marks SET received_at=?, event_timestamp=? WHERE symbol='X'",
            (clock() - 16, int(clock()) - 16),
        )

    readiness = platform.provider_readiness("a")

    assert readiness["reconciliation"]["status"] == "VERIFIED"
    assert readiness["broker_freshness"]["status"] == "VERIFIED"
    assert readiness["market_freshness"]["status"] == "STALE"
    assert readiness["resume"]["eligible"] is False
    platform.close()


def test_provider_readiness_endpoint_is_account_scoped():
    platform, _ = configured_platform()
    platform.account("b")
    platform.strategies.subscribe("b", "other", "momentum", "Y")
    with platform.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) "
            "VALUES (?,?,?,?,?,?,?,?,0,0,1)",
            (
                "foreign-unknown",
                "other",
                "b",
                "Y",
                "BUY",
                1,
                platform.clock(),
                OrderStatus.UNKNOWN,
            ),
        )

    with TestClient(create_app(platform)) as client:
        authenticate(client, platform, "a", "readiness-user", operator=False)
        response = client.get("/api/provider-readiness")
        state_response = client.get("/api/state")

    assert response.status_code == 200
    assert state_response.status_code == 200
    readiness = response.json()
    assert readiness["unknown_order_count"] == 0
    assert state_response.json()["provider_readiness"]["unknown_order_count"] == 0
    assert "foreign-unknown" not in response.text
    assert "foreign-unknown" not in state_response.text
    assert "b" not in readiness
    platform.close()

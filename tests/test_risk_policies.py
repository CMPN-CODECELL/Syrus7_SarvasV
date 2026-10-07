from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, RiskPolicy, Side, StrategyState


def subscribed(path=":memory:", broker=None, clock=lambda: 1_700_000_000):
    p = Platform(path, broker=broker, clock=clock)
    if not p.store.rows("SELECT id FROM accounts WHERE id='a'"):
        p.account("a")
        p.strategies.subscribe("a", "A", "momentum", "X")
    p.reliability.resume()
    return p


def request(p, key, qty, side=Side.BUY):
    return OrderIntent(key, "A", "a", "X", side, qty, p.clock())


def test_policy_and_loss_halt_survive_restart(tmp_path):
    path = str(tmp_path / "risk.db")
    p = subscribed(path)
    p.risk.policies["A"] = RiskPolicy(Decimal("5"), 50, 3)
    p.risk.submit(request(p, "1-buy", 2))
    p.ingest(p.broker.execute("1-buy", 2, Decimal("100"), p.clock()))
    p.risk.submit(request(p, "2-sell", 2, Side.SELL))
    p.ingest(p.broker.execute("2-sell", 2, Decimal("96"), p.clock(), Decimal("1")))
    assert (
        p.risk.submit(request(p, "3-blocked", 1)).reason_code == "RISK_MAX_DAILY_LOSS"
    )
    assert p.risk.strategy_state("A") == StrategyState.LOSS_HALTED
    p.store.close()
    new = Platform(path, clock=lambda: 1_700_000_000)
    assert new.risk.policies["A"] == RiskPolicy(Decimal("5"), 50, 3)
    assert new.risk.strategy_state("A") == StrategyState.LOSS_HALTED
    assert new.risk.state == "RECOVERING"
    new.reliability.resume()
    assert (
        new.risk.submit(request(new, "4-blocked", 1)).reason_code
        == "RISK_MAX_DAILY_LOSS"
    )
    with pytest.raises(ValueError, match="still breached"):
        new.risk.set_strategy_state("A", StrategyState.RUNNING)
    new.store.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"max_position": 0},
        {"max_position": True},
        {"max_orders_per_minute": -1},
        {"max_daily_loss": Decimal("NaN")},
        {"max_daily_loss": Decimal("Infinity")},
    ],
)
def test_invalid_policy_cannot_weaken_platform(changes):
    with pytest.raises(ValueError):
        RiskPolicy(**changes)


def test_budget_tracks_reservation_conversion_and_release():
    p = subscribed()
    p.risk.submit(request(p, "one", 100))
    p.ingest(p.broker.execute("one", 40, Decimal("100"), p.clock()))
    budget = p.risk.budget("a", "A", "X")
    assert (budget["position"]["filled"], budget["position"]["reserved_buy"]) == (
        40,
        60,
    )
    assert budget["position"]["available_buy"] == 0
    p.broker.cancel("one")
    assert p.reliability.reconcile()
    assert p.risk.budget("a", "A", "X")["position"]["available_buy"] == 60
    p.store.close()


def test_policy_api_changes_authoritative_risk():
    p = subscribed()
    with TestClient(create_app(p)) as client:
        assert (
            client.put(
                "/api/risk/policies/A",
                json={
                    "max_daily_loss": "10",
                    "max_position": 2,
                    "max_orders_per_minute": 2,
                },
            ).status_code
            == 200
        )
        assert not p.risk.submit(request(p, "too-big", 3)).allowed
        assert (
            client.put("/api/risk/strategies/A", json={"state": "HALTED"}).status_code
            == 200
        )
        assert (
            p.risk.submit(request(p, "halted", 1)).reason_code == "RISK_STRATEGY_HALTED"
        )
        assert client.get("/api/risk/budgets").json()[0]["state"] == "HALTED"
        assert (
            client.put(
                "/api/risk/policies/missing",
                json={
                    "max_daily_loss": "10",
                    "max_position": 2,
                    "max_orders_per_minute": 2,
                },
            ).status_code
            == 409
        )
    p.store.close()


def test_lower_policy_does_not_drop_existing_reservations():
    p = subscribed()
    p.risk.submit(request(p, "one", 100))
    p.risk.policies["A"] = RiskPolicy(max_position=50)
    assert p.risk.submit(request(p, "two", 1)).reason_code == "RISK_MAX_POSITION"
    assert p.risk.budget("a", "A", "X")["position"]["reserved_buy"] == 100
    p.store.close()

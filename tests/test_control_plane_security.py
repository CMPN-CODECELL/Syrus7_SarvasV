from decimal import Decimal

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick
from tests.usp_helpers import authenticate


def _ready(platform, account="owner", strategy="owned"):
    platform.account(account)
    platform.strategies.subscribe(account, strategy, "momentum", "X")
    platform.tick(Tick("X", int(platform.clock()), Decimal("100"), 0, "mark"))
    platform.reliability.resume()


def test_critical_control_plane_requires_authentication():
    platform = Platform()
    with TestClient(create_app(platform)) as client:
        requests = [
            ("post", "/api/reconcile", None),
            ("post", "/api/resume", None),
            ("post", "/api/reduce-only", None),
            ("post", "/api/kill", None),
            ("post", "/api/kill/reset", None),
            ("post", "/api/broker/disconnect", None),
            ("post", "/api/broker/reconnect", None),
            ("post", "/api/failure-lab/partial", None),
            ("post", "/api/market/session", {"status": "OPEN"}),
        ]
        for method, url, body in requests:
            response = (
                getattr(client, method)(url, json=body)
                if body
                else getattr(client, method)(url)
            )
            assert response.status_code == 401, url
        assert client.get("/api/state").status_code == 401
    platform.close()


def test_cross_account_strategy_and_order_mutation_is_forbidden():
    platform = Platform()
    _ready(platform)
    platform.risk.submit(
        OrderIntent("owned-order", "owned", "owner", "X", Side.BUY, 1, platform.clock())
    )
    with TestClient(create_app(platform)) as client:
        authenticate(client, platform, "attacker", "attacker")
        policy = client.put(
            "/api/risk/policies/owned",
            json={
                "max_daily_loss": "10",
                "max_position": 1,
                "max_orders_per_minute": 1,
            },
        )
        assert policy.status_code == 403
        assert client.post("/api/orders/owned-order/cancel").status_code == 403
    platform.close()

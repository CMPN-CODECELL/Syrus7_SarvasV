import json
import subprocess
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick
from backend.shared.presentation import AccountResponseScope
from tests.usp_helpers import authenticate


GLOBAL_ACTIONS = [
    ("post", "/api/reconcile", None),
    ("post", "/api/resume", None),
    ("post", "/api/reduce-only", None),
    ("post", "/api/kill", None),
    ("post", "/api/kill/reset", None),
    ("post", "/api/broker/disconnect", None),
    ("post", "/api/broker/reconnect", None),
    ("post", "/api/broker/updates/sync", None),
    ("post", "/api/accounts", {"account_id": "forbidden-account"}),
    ("post", "/api/market/session", {"status": "CLOSED"}),
    ("post", "/api/demo", None),
    ("post", "/api/failure-lab/partial", None),
    ("post", "/api/safety-bench/run", {"iterations": 1}),
]


def test_private_identifiers_cannot_relabel_global_safety_truth():
    p = Platform()
    try:
        p.account("owner")
        p.account("other")
        for identity in ("SUCCESS", "I1", "orders"):
            p.strategies.subscribe("other", identity, "momentum", "PRIVATE")
        scope = AccountResponseScope(p.store, "owner")
        result = scope.project(
            {
                "status": "SUCCESS",
                "orders": [],
                "invariants": [{"id": "I1", "status": "FAILED", "evidence": {}}],
            }
        )
        assert result["status"] == "SUCCESS"
        assert result["orders"] == []
        assert result["invariants"][0]["id"] == "I1"
        assert result["invariants"][0]["status"] == "FAILED"
    finally:
        p.close()


def test_owned_compound_identifier_is_not_redacted_by_foreign_substring():
    p = Platform()
    try:
        p.account("owner")
        p.account("other")
        p.strategies.subscribe("other", "breakout", "breakout", "PRIVATE")
        p.strategies.subscribe(
            "owner", "owner:breakout", "breakout", "OWNER_SYMBOL"
        )
        with p.store.transaction() as db:
            db.execute(
                "INSERT INTO orders(id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "owner:breakout:trace-1",
                    "owner:breakout",
                    "owner",
                    "OWNER_SYMBOL",
                    "BUY",
                    1,
                    1.0,
                    "FILLED",
                    1,
                    0,
                    1,
                ),
            )
        scope = AccountResponseScope(p.store, "owner")

        result = scope.project(
            {
                "strategy_instance_id": "owner:breakout",
                "trace_id": "owner:breakout:trace-1",
            }
        )

        assert result["strategy_instance_id"] == "owner:breakout"
        assert result["trace_id"] == "owner:breakout:trace-1"
    finally:
        p.close()


@pytest.mark.parametrize("method,path,body", GLOBAL_ACTIONS)
def test_global_mutations_require_explicit_grant_without_side_effects(
    method, path, body
):
    p = Platform(clock=lambda: 1_700_000_000)
    try:
        with TestClient(create_app(p)) as client:
            before = p.snapshot()
            assert getattr(client, method)(path, json=body).status_code == 401
            authenticate(client, p, "ordinary-account", "ordinary-user", operator=False)
            before = p.snapshot()
            assert getattr(client, method)(path, json=body).status_code == 403
            assert p.snapshot() == before
            assert not p.store.rows("SELECT * FROM operator_grants")
    finally:
        p.close()


def test_grants_survive_restart_and_revoke_existing_session(tmp_path):
    db_path = str(tmp_path / "operator.db")
    p = Platform(db_path)
    result = p.auth.register("operator-user", "safe-password")
    assert not p.auth.verify_token(result["token"])["is_operator"]
    p.close()
    provision = [
        sys.executable,
        "-m",
        "backend.shared.provision_operator",
        "--sqlite-path",
        db_path,
        "--username",
        "operator-user",
    ]
    assert subprocess.run(provision, capture_output=True, text=True).returncode == 0
    p = Platform(db_path)
    try:
        assert p.auth.verify_token(result["token"])["is_operator"] == 1
        with TestClient(create_app(p)) as client:
            client.cookies.set("algoshield_session", result["token"])
            assert client.post("/api/reconcile").status_code == 200
            p.auth.provision_operator("operator-user", granted=False)
            gate_before = p.risk.state
            orders_before = len(p.store.rows("SELECT * FROM orders"))
            fills_before = len(p.store.rows("SELECT * FROM fills"))
            assert client.post("/api/kill").status_code == 403
            assert client.post("/api/reconcile").status_code == 403
            assert client.post("/api/resume").status_code == 403
            assert p.risk.state == gate_before == "STOPPED"
            assert len(p.store.rows("SELECT * FROM orders")) == orders_before
            assert len(p.store.rows("SELECT * FROM fills")) == fills_before
            me_res = client.get("/api/auth/me")
            assert me_res.status_code == 200
            assert me_res.json()["user"]["is_operator"] == 0
            assert client.get("/api/state").status_code == 200
        with pytest.raises(ValueError, match="existing registered"):
            p.auth.provision_operator("missing-user", granted=True)
    finally:
        p.close()


def test_registration_cannot_self_promote_and_owner_controls_still_work():
    p = Platform()
    try:
        with TestClient(create_app(p)) as client:
            assert (
                client.post(
                    "/api/auth/register",
                    json={
                        "username": "attacker",
                        "password": "safe-password",
                        "is_operator": True,
                    },
                ).status_code
                == 422
            )
            client.post(
                "/api/auth/register",
                json={"username": "ordinary", "password": "safe-password"},
            )
            assert not client.get("/api/auth/me").json()["user"]["is_operator"]
            assert (
                client.post(
                    "/api/subscriptions",
                    json={
                        "strategy_instance_id": "own-strategy",
                        "kind": "momentum",
                        "symbol": "OWN",
                    },
                ).status_code
                == 201
            )
            assert (
                client.post("/api/subscriptions/own-strategy/stop").status_code == 200
            )
            assert (
                client.put(
                    "/api/risk/policies/own-strategy",
                    json={
                        "max_daily_loss": "100",
                        "max_position": 10,
                        "max_orders_per_minute": 10,
                    },
                ).status_code
                == 200
            )
            assert (
                client.put(
                    "/api/risk/account-policy", json={"max_net_position_per_symbol": 20}
                ).status_code
                == 200
            )
    finally:
        p.close()


RESPONSE_ROUTES = [
    ("get", "/api/state"),
    ("get", "/api/safety-proof"),
    ("get", "/api/reconciliation"),
    ("get", "/api/traces"),
    ("get", "/api/metrics"),
    ("get", "/api/orders"),
    ("get", "/api/fills"),
    ("get", "/api/traces/own-order"),
    ("get", "/api/safety-bench/latest"),
    ("post", "/api/orders/own-order/cancel"),
    ("post", "/api/demo"),
    ("post", "/api/safety-bench/run"),
    ("post", "/api/reconcile"),
    ("post", "/api/resume"),
    ("post", "/api/reduce-only"),
    ("post", "/api/kill"),
    ("post", "/api/kill/reset"),
    ("post", "/api/broker/disconnect"),
    ("post", "/api/broker/reconnect"),
    ("post", "/api/broker/updates/sync"),
    ("post", "/api/failure-lab/partial"),
]


@pytest.mark.parametrize("method,path", RESPONSE_ROUTES)
def test_all_response_families_hide_other_account_and_preserve_own_evidence(
    method, path
):
    p = Platform(clock=lambda: 1_700_000_000)
    try:
        with TestClient(create_app(p)) as client:
            authenticate(client, p, "owner-account", "owner-user")
            p.account("private-account")
            for account, strategy, symbol in [
                ("owner-account", "own-strategy", "OWN"),
                ("private-account", "private-strategy", "PRIVATE"),
            ]:
                p.strategies.subscribe(account, strategy, "momentum", symbol)
                p.tick(
                    Tick(symbol, int(p.clock()), Decimal("100"), 0, "mark-" + symbol)
                )
            p.reliability.resume()
            for account, strategy, symbol, order, fill in [
                ("owner-account", "own-strategy", "OWN", "own-order", "own-order:1"),
                (
                    "private-account",
                    "private-strategy",
                    "PRIVATE",
                    "private-order",
                    "private-order:1",
                ),
            ]:
                assert p.risk.submit(
                    OrderIntent(
                        order, strategy, account, symbol, Side.BUY, 3, p.clock()
                    )
                ).allowed
                p.sync_broker_updates()
                p.ingest(p.broker.execute(order, 1, Decimal("100"), p.clock()))
            assert p.reliability.reconcile()
            # Mixed nested audit data must not escape even when outer event is owned.
            with p.store.transaction():
                p.store.audit(
                    "OWNED_MIXED_EVIDENCE",
                    {
                        "account_id": "owner-account",
                        "items": [
                            {"account_id": "owner-account", "order_id": "own-order"},
                            {
                                "account_id": "private-account",
                                "order_id": "private-order",
                            },
                        ],
                        "broker_positions": {
                            "owner-account/OWN": 1,
                            "private-account/PRIVATE": 1,
                        },
                    },
                )
            if path == "/api/kill/reset":
                assert p.kill().status == "SUCCESS"
            if path == "/api/safety-bench/latest":
                p.safety_bench.run()
            response = (
                getattr(client, method)(path, json={"iterations": 1})
                if path == "/api/safety-bench/run"
                else getattr(client, method)(path)
            )
            assert response.status_code == 200, response.text
            text = response.text
            for private in (
                "private-account",
                "private-strategy",
                "private-order",
                "private-order:1",
                "PRIVATE",
            ):
                assert private not in text, (path, private, text)
            own = client.get("/api/state").json()
            assert own["subscriptions"][0]["id"] == "own-strategy"
            assert own["counts"]["orders"] >= 1
            assert any(row["id"] == "own-order" for row in own["orders"])
            assert any(row["id"] == "own-order:1" for row in own["fills"])
            assert p.store.rows(
                "SELECT id FROM subscriptions WHERE account='private-account'"
            )
            for event in own["audit"]:
                assert "private-account" not in json.dumps(event)
    finally:
        p.close()


def test_operator_injection_refused_for_non_mock_and_errors_do_not_leak(monkeypatch):
    p = Platform()
    try:
        with TestClient(create_app(p)) as client:
            authenticate(client, p)
            p.broker = object()
            assert client.post("/api/failure-lab/partial").status_code == 409
            assert (
                client.post("/api/safety-bench/run", json={"iterations": 1}).status_code
                == 200
            )

            def fail():
                raise ValueError("private-account/private-order broker error")

            monkeypatch.setattr(p.reliability, "reconcile", fail)
            response = client.post("/api/reconcile")
            assert response.status_code == 409
            assert "private-account" not in response.text
    finally:
        p.close()

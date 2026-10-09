from decimal import Decimal
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.api import create_app
from backend.platform import Platform
from backend.shared.contracts import Candle, Fill, KillCertificate, Side


def closed_candle(symbol="X", interval=60, start=0, open_p="100", close_p="102"):
    return Candle(
        symbol,
        interval,
        start,
        start + interval,
        Decimal(open_p),
        max(Decimal(open_p), Decimal(close_p)),
        min(Decimal(open_p), Decimal(close_p)),
        Decimal(close_p),
        10,
        True,
    )


def test_anonymous_reads_and_streams_rejected():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            # Anonymous reads rejected with 401
            assert client.get("/api/state").status_code == 401
            assert client.get("/api/subscriptions").status_code == 401
            assert (
                client.post(
                    "/api/subscriptions",
                    json={
                        "strategy_instance_id": "test",
                        "kind": "momentum",
                        "symbol": "X",
                    },
                ).status_code
                == 401
            )
            assert client.get("/api/orders").status_code == 401
            assert client.get("/api/fills").status_code == 401
            assert client.get("/api/risk/budgets").status_code == 401
            assert client.get("/api/stream/telemetry").status_code == 401

            # Anonymous websocket stream rejected (closes with 1008 before sending data)
            with pytest.raises(Exception):
                with client.websocket_connect("/api/stream/ws") as ws:
                    ws.receive_json()
    finally:
        platform.close()


def test_authenticated_workflow_register_subscribe_start_observe_stop():
    platform = Platform()
    try:
        with TestClient(create_app(platform)) as client:
            # 1. Register & Login Alice
            reg = client.post(
                "/api/auth/register",
                json={"username": "alice", "password": "password123"},
            )
            assert reg.status_code == 201
            assert reg.json()["token"]
            alice_account = reg.json()["user"]["account_id"]
            assert alice_account == "acc_alice"

            # 2. Subscribe to strategy
            sub_resp = client.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "alice_ema",
                    "kind": "momentum",
                    "symbol": "TCS",
                },
            )
            assert sub_resp.status_code == 201
            subs = sub_resp.json()
            assert len(subs) == 1
            assert subs[0]["id"] == "alice_ema"
            assert subs[0]["account"] == alice_account
            assert subs[0]["state"] == "READY"
            assert subs[0]["readiness"]["samples"] == 0
            assert subs[0]["readiness"]["ready"] is False

            # 3. Observe initial state via /api/state
            state = client.get("/api/state").json()
            assert len(state["subscriptions"]) == 1
            assert state["subscriptions"][0]["id"] == "alice_ema"
            assert state["counts"]["orders"] == 0
            assert state["counts"]["fills"] == 0

            # 4. Resume platform and start subscription
            platform.reliability.resume()
            start_resp = client.post("/api/subscriptions/alice_ema/start")
            assert start_resp.status_code == 200
            assert start_resp.json()[0]["state"] == "RUNNING"

            # 5. Observe warmup candles -> signals
            for i in range(4):
                platform.strategies.on_candle(
                    closed_candle("TCS", start=i * 60, close_p=str(100 + i * 2)),
                    platform.clock(),
                )
                r = platform.strategies.readiness_for("alice_ema")
                assert r["samples"] == i + 1
                assert r["ready"] is False

            # 5th candle completes warmup and emits signal
            intents = platform.strategies.on_candle(
                closed_candle("TCS", start=240, close_p="110"),
                platform.clock(),
            )
            assert len(intents) == 1
            assert intents[0].strategy_instance_id == "alice_ema"

            # State now reflects readiness and emitted signal
            state = client.get("/api/state").json()
            assert state["subscriptions"][0]["readiness"]["ready"] is True
            assert len(state["signals"]) >= 1
            assert state["signals"][0]["strategy"] == "alice_ema"
            assert state["signals"][0]["account"] == alice_account

            # 6. Stop subscription
            stop_resp = client.post("/api/subscriptions/alice_ema/stop")
            assert stop_resp.status_code == 200
            assert stop_resp.json()[0]["state"] == "STOPPED"

            # State reflects stopped
            state = client.get("/api/state").json()
            assert state["subscriptions"][0]["state"] == "STOPPED"
    finally:
        platform.close()


def test_two_account_complete_isolation():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client_a, TestClient(app) as client_b:
            # Register User A (Alice)
            reg_a = client_a.post(
                "/api/auth/register",
                json={"username": "user_a", "password": "passwordA"},
            )
            assert reg_a.status_code == 201
            acc_a = reg_a.json()["user"]["account_id"]

            # Register User B (Bob)
            reg_b = client_b.post(
                "/api/auth/register",
                json={"username": "user_b", "password": "passwordB"},
            )
            assert reg_b.status_code == 201
            acc_b = reg_b.json()["user"]["account_id"]

            # User A subscribes to strat_a
            sub_a = client_a.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_a",
                    "kind": "momentum",
                    "symbol": "AAA",
                },
            )
            assert sub_a.status_code == 201
            # Response must ONLY contain Alice's subscription
            assert len(sub_a.json()) == 1
            assert sub_a.json()[0]["id"] == "strat_a"

            # User B subscribes to strat_b
            sub_b = client_b.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_b",
                    "kind": "breakout",
                    "symbol": "BBB",
                },
            )
            assert sub_b.status_code == 201
            # Response must ONLY contain Bob's subscription
            assert len(sub_b.json()) == 1
            assert sub_b.json()[0]["id"] == "strat_b"

            # Check GET /api/subscriptions isolation
            list_a = client_a.get("/api/subscriptions").json()
            list_b = client_b.get("/api/subscriptions").json()
            assert [s["id"] for s in list_a] == ["strat_a"]
            assert [s["id"] for s in list_b] == ["strat_b"]

            # Add financial activity: orders, fills, unknown orders, positions
            with platform.store.transaction() as db:
                # Alice order and fill
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_a', 'strat_a', ?, 'AAA', 'BUY', 10, 100.0, 'FILLED', 10, 0)",
                    (acc_a,),
                )
                db.execute(
                    "INSERT INTO fills VALUES ('fill_a', 'ord_a', 'strat_a', ?, 'AAA', 'BUY', 10, '100', 100.0, '0.5')",
                    (acc_a,),
                )
                # Bob order and fill and unknown order
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_b', 'strat_b', ?, 'BBB', 'BUY', 20, 100.0, 'FILLED', 20, 0)",
                    (acc_b,),
                )
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_b_unk', 'strat_b', ?, 'BBB', 'BUY', 5, 100.0, 'UNKNOWN', 0, 0)",
                    (acc_b,),
                )
                db.execute(
                    "INSERT INTO fills VALUES ('fill_b', 'ord_b', 'strat_b', ?, 'BBB', 'BUY', 20, '200', 100.0, '1.0')",
                    (acc_b,),
                )

            # Ingest fills into ledger for position calculation
            platform.ledger.apply(
                Fill(
                    "fill_a",
                    "ord_a",
                    "strat_a",
                    acc_a,
                    "AAA",
                    Side.BUY,
                    10,
                    Decimal("100"),
                    100.0,
                    Decimal("0.5"),
                )
            )
            platform.ledger.apply(
                Fill(
                    "fill_b",
                    "ord_b",
                    "strat_b",
                    acc_b,
                    "BBB",
                    Side.BUY,
                    20,
                    Decimal("200"),
                    100.0,
                    Decimal("1.0"),
                )
            )

            # Verify GET /api/risk/budgets isolation
            budgets_a = client_a.get("/api/risk/budgets").json()
            budgets_b = client_b.get("/api/risk/budgets").json()
            assert [b["strategy_instance_id"] for b in budgets_a] == ["strat_a"]
            assert [b["strategy_instance_id"] for b in budgets_b] == ["strat_b"]

            # Setup multi-account reconciliation, kill certificate, and audit events
            platform.reliability._health("HEALTHY")
            platform.reliability.last_broker_at = platform.clock()
            platform.reliability.report = {
                "verified": True,
                "reason": "MATCHED",
                "observed_at": platform.clock(),
                "orders": 10,
                "unique_fills": 5,
                "duplicate_snapshot_fills": 2,
                "open_orders": 4,
                "broker_positions": [
                    {"account_id": acc_a, "symbol": "AAA", "quantity": 10},
                    {"account_id": acc_b, "symbol": "BBB", "quantity": 20},
                ],
                "unexplained_positions": [],
                "unattributed_fills": 0,
                "accounts": {
                    acc_a: {
                        "orders": 1,
                        "unique_fills": 1,
                        "open_orders": 0,
                        "duplicate_snapshot_fills": 0,
                        "unattributed_fills": 0,
                    },
                    acc_b: {
                        "orders": 2,
                        "unique_fills": 1,
                        "open_orders": 1,
                        "duplicate_snapshot_fills": 0,
                        "unattributed_fills": 0,
                    },
                },
            }
            platform.reliability.certificate = KillCertificate(
                "SUCCESS",
                2.5,
                4,
                {f"{acc_a}/AAA": 10, f"{acc_b}/BBB": 20},
                False,
                "verified kill flatten",
            )
            # Add audit entries attributed to A and B
            platform.store.audit(
                "DUPLICATE_FILL_IGNORED",
                {"fill_id": "dup_fill_a", "account_id": acc_a},
            )
            platform.store.audit(
                "SAFETY_RESTRICTED",
                {"reason": "FILL_EVENT_REJECTED", "account_id": acc_b},
            )

            # Verify User A's /api/state
            snap_a = client_a.get("/api/state").json()
            assert [s["id"] for s in snap_a["subscriptions"]] == ["strat_a"]
            assert len(snap_a["positions"]) == 1
            assert snap_a["positions"][0]["account_id"] == acc_a
            assert snap_a["positions"][0]["symbol"] == "AAA"
            assert [o["id"] for o in snap_a["orders"]] == ["ord_a"]
            assert [f["id"] for f in snap_a["fills"]] == ["fill_a"]
            assert snap_a["counts"]["orders"] == 1
            assert snap_a["counts"]["fills"] == 1
            assert len(snap_a["risk_budgets"]) == 1
            assert snap_a["risk_budgets"][0]["strategy_instance_id"] == "strat_a"

            # Check nested safety evidence isolation for User A
            assert snap_a["safety"]["fills"]["unique_applied"] == 1
            assert snap_a["safety"]["fills"]["duplicates_ignored"] == 1
            assert snap_a["safety"]["fills"]["rejected_events"] == 0
            assert (
                snap_a["safety"]["fills"]["unattributed_in_last_verified_snapshot"] == 0
            )
            assert snap_a["safety"]["unknown_orders"] == []
            assert [
                v["account_id"]
                for v in snap_a["safety"]["position_comparison"]["virtual"]
            ] == [acc_a]
            assert [
                b["account_id"]
                for b in snap_a["safety"]["position_comparison"]["broker"]
            ] == [acc_a]
            assert [
                b["account_id"]
                for b in snap_a["safety"]["reconciliation"]["broker_positions"]
            ] == [acc_a]
            assert snap_a["safety"]["reconciliation"]["orders"] == 1
            assert snap_a["safety"]["reconciliation"]["unique_fills"] == 1
            assert snap_a["safety"]["reconciliation"]["open_orders"] == 0
            assert snap_a["safety"]["reconciliation"]["unattributed_fills"] == 0

            # Check kill certificate isolation for User A
            assert snap_a["kill"]["status"] == "SUCCESS"
            assert list(snap_a["kill"]["broker_positions"].keys()) == [f"{acc_a}/AAA"]
            assert snap_a["kill"]["broker_positions"][f"{acc_a}/AAA"] == 10
            assert f"{acc_b}/BBB" not in snap_a["kill"]["broker_positions"]

            # Check audit isolation for User A
            for row in snap_a["audit"]:
                payload_str = str(row["payload"])
                assert acc_b not in payload_str
                assert "strat_b" not in payload_str

            # Verify User B's /api/state
            snap_b = client_b.get("/api/state").json()
            assert [s["id"] for s in snap_b["subscriptions"]] == ["strat_b"]
            assert len(snap_b["positions"]) == 1
            assert snap_b["positions"][0]["account_id"] == acc_b
            assert snap_b["positions"][0]["symbol"] == "BBB"
            assert sorted([o["id"] for o in snap_b["orders"]]) == ["ord_b", "ord_b_unk"]
            assert [f["id"] for f in snap_b["fills"]] == ["fill_b"]
            assert snap_b["counts"]["orders"] == 2
            assert snap_b["counts"]["fills"] == 1

            # Check nested safety evidence isolation for User B
            assert snap_b["safety"]["fills"]["unique_applied"] == 1
            assert snap_b["safety"]["fills"]["duplicates_ignored"] == 0
            assert snap_b["safety"]["fills"]["rejected_events"] == 1
            assert (
                snap_b["safety"]["fills"]["unattributed_in_last_verified_snapshot"] == 0
            )
            assert snap_b["safety"]["unknown_orders"] == ["ord_b_unk"]
            assert [
                v["account_id"]
                for v in snap_b["safety"]["position_comparison"]["virtual"]
            ] == [acc_b]
            assert [
                b["account_id"]
                for b in snap_b["safety"]["position_comparison"]["broker"]
            ] == [acc_b]
            assert [
                b["account_id"]
                for b in snap_b["safety"]["reconciliation"]["broker_positions"]
            ] == [acc_b]
            assert snap_b["safety"]["reconciliation"]["orders"] == 2
            assert snap_b["safety"]["reconciliation"]["unique_fills"] == 1
            assert snap_b["safety"]["reconciliation"]["open_orders"] == 1
            assert snap_b["safety"]["reconciliation"]["unattributed_fills"] == 0

            # Check kill certificate isolation for User B
            assert snap_b["kill"]["status"] == "SUCCESS"
            assert list(snap_b["kill"]["broker_positions"].keys()) == [f"{acc_b}/BBB"]
            assert snap_b["kill"]["broker_positions"][f"{acc_b}/BBB"] == 20
            assert f"{acc_a}/AAA" not in snap_b["kill"]["broker_positions"]

            # Check audit isolation for User B
            for row in snap_b["audit"]:
                payload_str = str(row["payload"])
                assert acc_a not in payload_str
                assert "strat_a" not in payload_str

    finally:
        platform.close()


def test_cross_account_start_stop_denied():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client_a, TestClient(app) as client_b:
            client_a.post(
                "/api/auth/register",
                json={"username": "alice", "password": "password123"},
            )
            client_b.post(
                "/api/auth/register",
                json={"username": "bob", "password": "password123"},
            )

            # Alice creates strat_alice
            client_a.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_alice",
                    "kind": "momentum",
                    "symbol": "AAA",
                },
            )

            # Bob attempts to start or stop Alice's strategy -> 403 Forbidden
            start_denied = client_b.post("/api/subscriptions/strat_alice/start")
            assert start_denied.status_code == 403
            assert "access denied" in start_denied.json()["detail"]

            stop_denied = client_b.post("/api/subscriptions/strat_alice/stop")
            assert stop_denied.status_code == 403
            assert "access denied" in stop_denied.json()["detail"]

            # Attempts on non-existent subscription -> 404 Not Found
            not_found_start = client_a.post("/api/subscriptions/missing_strat/start")
            assert not_found_start.status_code == 404

            not_found_stop = client_a.post("/api/subscriptions/missing_strat/stop")
            assert not_found_stop.status_code == 404
    finally:
        platform.close()


def test_logout_and_expiry_terminates_telemetry():
    platform = Platform()
    try:
        app = create_app(platform)
        # 1. SSE stream rejected on logged-out / expired session
        with TestClient(app) as client:
            reg = client.post(
                "/api/auth/register",
                json={"username": "stream_user", "password": "password123"},
            )
            token = reg.json()["token"]

            # Active token can connect
            with client.stream("GET", "/api/stream/telemetry?max_events=1") as response:
                assert response.status_code == 200

            # Revoke session token
            platform.auth.logout(token)

            # Reconnection or read after logout rejected with 401
            assert client.get("/api/stream/telemetry").status_code == 401

            # Expired token rejected with 401
            exp_token = platform.auth.create_token("stream_user")
            with platform.store.transaction() as db:
                db.execute(
                    "UPDATE user_tokens SET expires_at=0 WHERE token=?", (exp_token,)
                )
            assert (
                client.get(f"/api/stream/telemetry?token={exp_token}").status_code
                == 401
            )

        # 2. WebSocket stream termination immediately upon logout/expiry during streaming
        user2 = platform.auth.register("ws_logout_user", "password123")
        token2 = user2["token"]
        with TestClient(app, cookies={"algoshield_session": token2}) as client2:
            with client2.websocket_connect("/api/stream/ws") as ws:
                first = ws.receive_json()
                assert "subscriptions" in first

                # Revoke session while socket is streaming
                platform.auth.logout(token2)

                # Next cycle detects revoked token and terminates with 1008
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 1008
    finally:
        platform.close()


def test_backend_derived_states_preserved():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            client.post(
                "/api/auth/register",
                json={"username": "state_user", "password": "password123"},
            )
            client.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "state_strat",
                    "kind": "momentum",
                    "symbol": "XYZ",
                },
            )

            # Initially READY (enabled=1, but platform runtime not started)
            snap = client.get("/api/state").json()
            sub = snap["subscriptions"][0]
            assert sub["state"] == "READY"
            assert sub["readiness"]["ready"] is False

            # Started -> RUNNING
            platform.reliability.resume()
            client.post("/api/subscriptions/state_strat/start")
            snap = client.get("/api/state").json()
            assert snap["subscriptions"][0]["state"] == "RUNNING"

            # Stopped -> STOPPED
            client.post("/api/subscriptions/state_strat/stop")
            snap = client.get("/api/state").json()
            assert snap["subscriptions"][0]["state"] == "STOPPED"

            # Risk Halted -> HALTED
            client.post("/api/subscriptions/state_strat/start")
            platform.risk.set_strategy_state("state_strat", "HALTED")
            snap = client.get("/api/state").json()
            assert snap["subscriptions"][0]["state"] == "HALTED"
    finally:
        platform.close()


def test_unavailable_backend_and_reconnect_handling():
    # Browser session invalidation is exercised behaviorally in
    # frontend/src/test/telemetry.test.jsx (logout/account switch, HTTP 401,
    # WS 1008, stale socket teardown). This test owns backend lifecycle behavior.
    # Backend shutdown and restore lifecycle
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            reg = client.post(
                "/api/auth/register",
                json={"username": "recon_user", "password": "password123"},
            )
            assert reg.status_code == 201
            snap1 = client.get("/api/state").json()
            assert snap1["counts"]["orders"] == 0

        # Simulate backend unavailable by closing platform
        platform.close()

        # New platform instance with restored data
        restarted = Platform()
        try:
            app_restarted = create_app(restarted)
            with TestClient(app_restarted) as client2:
                # With fresh backend, valid session authenticates and receives fresh scoped state
                reg2 = client2.post(
                    "/api/auth/register",
                    json={"username": "recon_user2", "password": "password123"},
                )
                assert reg2.status_code == 201
                snap2 = client2.get("/api/state").json()
                assert snap2["counts"]["orders"] == 0
                assert snap2["subscriptions"] == []
        finally:
            restarted.close()
    finally:
        pass


def test_truthful_scoped_safety_evidence():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client_a, TestClient(app) as client_b:
            reg_a = client_a.post(
                "/api/auth/register",
                json={"username": "user_a", "password": "passwordA"},
            )
            reg_b = client_b.post(
                "/api/auth/register",
                json={"username": "user_b", "password": "passwordB"},
            )
            acc_a = reg_a.json()["user"]["account_id"]
            acc_b = reg_b.json()["user"]["account_id"]

            client_a.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_a",
                    "kind": "momentum",
                    "symbol": "AAA",
                },
            )
            client_b.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_b",
                    "kind": "momentum",
                    "symbol": "BBB",
                },
            )

            # 1. Unknown attribution stays unknown:
            # Report with unattributed fills > 0 or unverified status must NOT hardcode 0.
            platform.reliability._health("HEALTHY")
            platform.reliability.last_broker_at = platform.clock()
            platform.reliability.report = {
                "verified": False,
                "reason": "DRIFTED",
                "observed_at": 50.0,
                "orders": 1,
                "unique_fills": 1,
                "unattributed_fills": 1,
            }
            snap_a = client_a.get("/api/state").json()
            # When unverified or unattributed fills exist, attribution stays null/unknown
            assert (
                snap_a["safety"]["fills"]["unattributed_in_last_verified_snapshot"]
                is None
            )
            assert snap_a["safety"]["reconciliation"]["orders"] is None
            assert snap_a["safety"]["reconciliation"]["unattributed_fills"] is None
            # Uncertainty in position comparison stays UNKNOWN/FAILED, never converted to pass
            assert snap_a["safety"]["position_comparison"]["status"] in {
                "UNKNOWN",
                "FAILED",
            }

            # 2. Failed kill retains uncertainty:
            # Status FAILED, open_orders=-1, virtual_positions_flat=False must NOT be rewritten
            platform.reliability.certificate = KillCertificate(
                "FAILED",
                9.1,
                -1,
                {f"{acc_a}/AAA": 10, f"{acc_b}/BBB": 20},
                False,
                "kill deadline exceeded",
            )
            snap_a = client_a.get("/api/state").json()
            assert snap_a["kill"]["status"] == "FAILED"
            assert snap_a["kill"]["open_orders"] == -1
            assert snap_a["kill"]["virtual_positions_flat"] is False
            assert snap_a["kill"]["reason"] == "kill deadline exceeded"
            # Sensitive fields for other accounts stripped
            assert list(snap_a["kill"]["broker_positions"].keys()) == [f"{acc_a}/AAA"]

            # 3. Later trades do not alter historical certificates:
            # Emit order and fill on Account A
            with platform.store.transaction() as db:
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_a_1', 'strat_a', ?, 'AAA', 'BUY', 10, 100.0, 'FILLED', 10, 0)",
                    (acc_a,),
                )
                db.execute(
                    "INSERT INTO fills VALUES ('fill_a_1', 'ord_a_1', 'strat_a', ?, 'AAA', 'BUY', 10, '100', 100.0, '0.5')",
                    (acc_a,),
                )
            platform.ledger.apply(
                Fill(
                    "fill_a_1",
                    "ord_a_1",
                    "strat_a",
                    acc_a,
                    "AAA",
                    Side.BUY,
                    10,
                    Decimal("100"),
                    100.0,
                    Decimal("0.5"),
                )
            )

            # Historical kill certificate must remain UNCHANGED despite later trades!
            snap_a_after = client_a.get("/api/state").json()
            assert snap_a_after["kill"]["status"] == "FAILED"
            assert snap_a_after["kill"]["open_orders"] == -1
            assert snap_a_after["kill"]["virtual_positions_flat"] is False
            assert snap_a_after["counts"]["orders"] == 1
            assert snap_a_after["counts"]["fills"] == 1

            # 4. Scoped historical reports describe snapshot at observed_at, not live counts
            # Set verified historical snapshot at observed_at=100.0 with 1 order for acc_a and 1 order for acc_b
            platform.reliability._health("HEALTHY")
            platform.reliability.last_broker_at = platform.clock()
            platform.reliability.report = {
                "verified": True,
                "reason": "MATCHED",
                "observed_at": 100.0,
                "orders": 2,
                "unique_fills": 2,
                "duplicate_snapshot_fills": 0,
                "open_orders": 0,
                "broker_positions": [
                    {"account_id": acc_a, "symbol": "AAA", "quantity": 10},
                    {"account_id": acc_b, "symbol": "BBB", "quantity": 20},
                ],
                "unexplained_positions": [],
                "unattributed_fills": 0,
                "accounts": {
                    acc_a: {
                        "orders": 1,
                        "unique_fills": 1,
                        "open_orders": 0,
                        "duplicate_snapshot_fills": 0,
                        "unattributed_fills": 0,
                    },
                    acc_b: {
                        "orders": 1,
                        "unique_fills": 1,
                        "open_orders": 0,
                        "duplicate_snapshot_fills": 0,
                        "unattributed_fills": 0,
                    },
                },
            }

            # Now add 2 more local orders for Account A *after* observed_at
            with platform.store.transaction() as db:
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_a_2', 'strat_a', ?, 'AAA', 'BUY', 5, 200.0, 'NEW', 0, 0)",
                    (acc_a,),
                )
                db.execute(
                    "INSERT INTO orders (id, strategy, account, symbol, side, quantity, created, status, filled, emergency) "
                    "VALUES ('ord_a_3', 'strat_a', ?, 'AAA', 'BUY', 5, 201.0, 'NEW', 0, 0)",
                    (acc_a,),
                )

            snap_a_hist = client_a.get("/api/state").json()
            snap_b_hist = client_b.get("/api/state").json()

            # Reconciliation counts describe the verified snapshot at observed_at (orders=1)
            # NOT current local counts (counts.orders=3)
            assert snap_a_hist["safety"]["reconciliation"]["orders"] == 1
            assert snap_a_hist["safety"]["reconciliation"]["unique_fills"] == 1
            assert snap_a_hist["safety"]["reconciliation"]["open_orders"] == 0
            assert snap_a_hist["safety"]["reconciliation"]["unattributed_fills"] == 0
            assert snap_a_hist["safety"]["reconciliation"]["observed_at"] == 100.0
            assert snap_a_hist["counts"]["orders"] == 3  # Current live counter
            assert (
                snap_a_hist["safety"]["fills"]["unattributed_in_last_verified_snapshot"]
                == 0
            )

            # Bob's reconciliation is scoped to Bob and not affected by Alice's later orders
            assert snap_b_hist["safety"]["reconciliation"]["orders"] == 1
            assert snap_b_hist["counts"]["orders"] == 0
            assert [
                b["account_id"]
                for b in snap_b_hist["safety"]["reconciliation"]["broker_positions"]
            ] == [acc_b]
            assert [
                b["account_id"]
                for b in snap_a_hist["safety"]["reconciliation"]["broker_positions"]
            ] == [acc_a]
    finally:
        platform.close()

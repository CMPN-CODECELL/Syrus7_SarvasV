"""Targeted WebSocket security, authorization, and telemetry scoping tests.

Covers:
- Unauthenticated / missing credential rejection (close code 1008)
- Forged / invalid token rejection (close code 1008)
- Multiple authentication channels: Cookie, Query param, Bearer header
- Strict multi-account telemetry isolation across concurrent sessions
- Active session expiry / logout termination
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api import create_app
from backend.platform import Platform


def test_websocket_missing_credentials_rejected():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/api/stream/ws"):
                    pass
            assert exc.value.code == 1008
    finally:
        platform.close()


def test_websocket_invalid_token_rejected():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/api/stream/ws?token=forged_token_xyz"):
                    pass
            assert exc.value.code == 1008
    finally:
        platform.close()


def test_websocket_token_channels_cookie_query_and_header():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            reg = client.post(
                "/api/auth/register",
                json={"username": "ws_channel_user", "password": "password123"},
            )
            assert reg.status_code == 201
            token = reg.json()["token"]

            # 1. Via Query Parameter
            with client.websocket_connect(f"/api/stream/ws?token={token}") as ws:
                snap = ws.receive_json()
                assert "gate" in snap
                assert "counts" in snap

            # 2. Via Cookie (automatically set in client during register)
            with client.websocket_connect("/api/stream/ws") as ws:
                snap = ws.receive_json()
                assert "gate" in snap

            # 3. Via Authorization Header (new client with no cookies)
            with TestClient(app) as fresh_client:
                with fresh_client.websocket_connect(
                    "/api/stream/ws", headers={"Authorization": f"Bearer {token}"}
                ) as ws:
                    snap = ws.receive_json()
                    assert "gate" in snap
    finally:
        platform.close()


def test_websocket_strict_account_isolation():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client_a, TestClient(app) as client_b:
            reg_a = client_a.post(
                "/api/auth/register",
                json={"username": "ws_user_a", "password": "passwordA"},
            )
            reg_b = client_b.post(
                "/api/auth/register",
                json={"username": "ws_user_b", "password": "passwordB"},
            )
            assert reg_a.status_code == 201
            assert reg_b.status_code == 201

            # User A subscribes to a strategy
            client_a.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_a",
                    "kind": "momentum",
                    "symbol": "TCS",
                },
            )

            # User B subscribes to a strategy
            client_b.post(
                "/api/subscriptions",
                json={
                    "strategy_instance_id": "strat_b",
                    "kind": "mean_reversion",
                    "symbol": "INFY",
                },
            )

            # Both connect to WebSocket stream
            with (
                client_a.websocket_connect("/api/stream/ws") as ws_a,
                client_b.websocket_connect("/api/stream/ws") as ws_b,
            ):
                snap_a = ws_a.receive_json()
                snap_b = ws_b.receive_json()

                # User A stream contains ONLY User A subscriptions
                sub_ids_a = [s["id"] for s in snap_a.get("subscriptions", [])]
                assert "strat_a" in sub_ids_a
                assert "strat_b" not in sub_ids_a

                # User B stream contains ONLY User B subscriptions
                sub_ids_b = [s["id"] for s in snap_b.get("subscriptions", [])]
                assert "strat_b" in sub_ids_b
                assert "strat_a" not in sub_ids_b
    finally:
        platform.close()


def test_websocket_session_logout_terminates_active_connection():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            reg = client.post(
                "/api/auth/register",
                json={"username": "ws_logout_user", "password": "password123"},
            )
            assert reg.status_code == 201

            with client.websocket_connect("/api/stream/ws") as ws:
                # Active connection receives first push
                snap = ws.receive_json()
                assert "gate" in snap

                # Logout invalidates token in backend
                logout_resp = client.post("/api/auth/logout")
                assert logout_resp.status_code == 200

                # Next read must trigger disconnect with code 1008
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws.receive_json()
                assert exc.value.code == 1008
    finally:
        platform.close()

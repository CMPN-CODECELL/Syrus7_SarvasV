import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api import create_app
from backend.platform import Platform
from backend.shared.browser_security import LoginLimiter


@pytest.fixture
def security_client():
    p = Platform(":memory:")
    c = TestClient(create_app(p))
    yield p, c
    c.close()
    p.close()


@pytest.mark.parametrize("origin", ["https://evil.example", "null", ""])
@pytest.mark.parametrize("operator", [False, True])
def test_origin_denial_precedes_cookie_mutation_and_telemetry(
    security_client, origin, operator
):
    p, c = security_client
    user = p.auth.register("origin-user", "secure-password", "a")
    if operator:
        p.auth.provision_operator("origin-user", granted=True)
    c.cookies.set("algoshield_session", user["token"])
    before = p.store.rows("SELECT * FROM audit")
    assert c.post("/api/kill", headers={"Origin": origin}).status_code == 403
    assert p.store.rows("SELECT * FROM audit") == before
    assert p.risk.state == "RECOVERING"
    with pytest.raises(WebSocketDisconnect) as error:
        with c.websocket_connect("/api/stream/ws", headers={"Origin": origin}) as ws:
            ws.receive_json()
    assert error.value.code == 1008


def test_trusted_origin_and_explicit_bearer_keep_authority(security_client):
    p, c = security_client
    user = p.auth.register("trusted-user", "secure-password", "a")
    c.cookies.set("algoshield_session", user["token"])
    assert (
        c.post("/api/kill", headers={"Origin": "http://localhost:8000"}).status_code
        == 403
    )
    with c.websocket_connect(
        "/api/stream/ws", headers={"Origin": "http://localhost:8000"}
    ) as ws:
        assert ws.receive_json()["gate"] == "RECOVERING"
    p.auth.provision_operator("trusted-user", granted=True)
    assert (
        c.post(
            "/api/reconcile",
            headers={"Origin": "", "Authorization": f"Bearer {user['token']}"},
        ).status_code
        == 200
    )


def test_cookie_security_attributes_follow_explicit_configuration():
    for secure in (False, True):
        p = Platform(":memory:")
        try:
            with TestClient(create_app(p, cookie_secure=secure)) as client:
                response = client.post(
                    "/api/auth/register",
                    json={
                        "username": f"cookie-{secure}",
                        "password": "secure-password",
                    },
                )
                assert response.status_code == 201
                assert ("secure" in response.headers["set-cookie"].lower()) is secure
                logout = client.post("/api/auth/logout")
                assert logout.status_code == 200
                cleared = logout.headers["set-cookie"].lower()
                assert ("secure" in cleared) is secure
                assert "samesite=strict" in cleared
        finally:
            p.close()


def test_sse_query_token_is_rejected_but_cookie_and_bearer_work(security_client):
    p, client = security_client
    user = p.auth.register("sse-user", "secure-password", "a")
    assert client.get(f"/api/stream/telemetry?token={user['token']}").status_code == 401
    client.cookies.set("algoshield_session", user["token"])
    assert client.get("/api/stream/telemetry?max_events=1").status_code == 200
    with TestClient(create_app(p)) as bearer_client:
        assert (
            bearer_client.get(
                "/api/stream/telemetry?max_events=1",
                headers={"Authorization": f"Bearer {user['token']}"},
            ).status_code
            == 200
        )


def test_anonymous_and_untrusted_host_cannot_bypass_origin(security_client):
    _, c = security_client
    assert (
        c.post("/api/kill", headers={"Origin": "http://localhost:8000"}).status_code
        == 401
    )
    assert (
        c.post(
            "/api/auth/login",
            json={"username": "none", "password": "secret"},
            headers={
                "Origin": "https://evil.example",
                "Host": "evil.example",
                "X-Forwarded-Host": "localhost:8000",
            },
        ).status_code
        == 403
    )


def test_versioned_hash_and_legacy_upgrade_preserve_operator(security_client):
    p, _ = security_client
    user = p.auth.register("hash-user", "secure-password", "a")
    row = p.store.rows("SELECT * FROM users WHERE username='hash-user'")[0]
    assert row["password_hash"].startswith("pbkdf2-sha256$v1$600000$")
    legacy = hashlib.sha256((row["salt"] + "secure-password").encode()).hexdigest()
    with p.store.transaction() as db:
        db.execute(
            "UPDATE users SET password_hash=? WHERE username='hash-user'", (legacy,)
        )
    p.auth.provision_operator("hash-user", granted=True)
    assert p.auth.login("hash-user", "wrong-password") is None
    assert (
        p.store.rows("SELECT password_hash FROM users WHERE username='hash-user'")[0][
            "password_hash"
        ]
        == legacy
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: p.auth.login("hash-user", "secure-password"), range(2))
        )
    assert all(result["account_id"] == "a" for result in results)
    assert p.auth.verify_token(user["token"])["is_operator"] == 1
    assert p.auth.login("hash-user", "secure-password")
    assert p.store.rows("SELECT password_hash FROM users WHERE username='hash-user'")[
        0
    ]["password_hash"].startswith("pbkdf2-sha256$v1$")


@pytest.mark.parametrize(
    "record",
    [
        "unsupported$v9$bad",
        "pbkdf2-sha256$v1$999999999$aa",
        "a" * 64,
        "pbkdf2-sha256$v1$600000$zz",
    ],
)
def test_malformed_hash_fails_safely(security_client, record):
    p, _ = security_client
    p.auth.register("malformed-user", "secure-password")
    with p.store.transaction() as db:
        db.execute(
            "UPDATE users SET password_hash=? WHERE username='malformed-user'",
            (record,),
        )
    assert p.auth.login("malformed-user", "secure-password") is None
    assert (
        p.store.rows("SELECT password_hash FROM users WHERE username='malformed-user'")[
            0
        ]["password_hash"]
        == record
    )


def test_login_failure_window_headers_and_secret_free_audit(security_client):
    p, c = security_client
    p.auth.register("limit-user", "secure-password")
    now = [100.0]
    c.app.state.login_limiter.clock = lambda: now[0]
    for attempt in range(5):
        response = c.post(
            "/api/auth/login",
            json={
                "username": "limit-user" if attempt % 2 else "missing-user",
                "password": "wrong-password",
            },
            headers={
                "Origin": "http://localhost:8000",
                "X-Forwarded-For": str(attempt),
            },
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid credentials"}
    assert (
        c.post(
            "/api/auth/login",
            json={"username": "limit-user", "password": "secure-password"},
        ).status_code
        == 429
    )
    now[0] += 60
    response = c.post(
        "/api/auth/login",
        json={"username": "limit-user", "password": "secure-password"},
    )
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    payloads = str(
        p.store.rows(
            "SELECT payload FROM audit WHERE type IN ('LOGIN_FAILED','LOGIN_SUCCEEDED')"
        )
    )
    assert "wrong-password" not in payloads and "secure-password" not in payloads
    assert response.json()["token"] not in payloads
    assert "missing-user" not in payloads


def test_limiter_bounds_expiry_and_concurrent_attempts():
    now = [100.0]
    limiter = LoginLimiter(clock=lambda: now[0], capacity=2)
    with ThreadPoolExecutor(max_workers=10) as pool:
        tickets = list(pool.map(lambda _: limiter.acquire("peer"), range(10)))
    assert sum(bool(ticket) for ticket in tickets) == 5
    assert limiter.acquire("other-peer")
    assert not limiter.acquire("new-peer")
    assert len(limiter.entries) == 2
    now[0] += 60
    assert limiter.acquire("new-peer")
    assert len(limiter.entries) == 1


def test_success_removes_only_its_own_attempt():
    limiter = LoginLimiter(clock=lambda: 100)
    failure = limiter.acquire("peer")
    success = limiter.acquire("peer")
    limiter.succeeded("peer", success)
    assert list(limiter.entries["peer"])[0][1] is failure
    assert len(limiter.entries["peer"]) == 1

from fastapi.testclient import TestClient
import pytest

from backend.api import create_app
from backend.platform import Platform
from backend.shared.auth import AuthService
from backend.shared.store import Store


def test_auth_service_registration_and_login():
    store = Store(":memory:")
    auth = AuthService(store)

    # Register new user
    user = auth.register("alice", "password123", "acc-alice")
    assert user["username"] == "alice"
    assert user["account_id"] == "acc-alice"
    assert "password_hash" not in user
    assert "salt" not in user

    # Duplicate registration fails
    with pytest.raises(ValueError, match="already exists"):
        auth.register("alice", "anotherpass")

    # Empty username/password fails
    with pytest.raises(ValueError):
        auth.register("", "pass")
    with pytest.raises(ValueError):
        auth.register("bob", "12")

    # Successful login
    logged_in = auth.login("alice", "password123")
    assert logged_in is not None
    assert logged_in["username"] == "alice"
    assert logged_in["account_id"] == "acc-alice"

    # Failed login with wrong password
    assert auth.login("alice", "wrongpassword") is None
    # Failed login with non-existent user
    assert auth.login("nonexistent", "password123") is None


def test_auth_service_tokens():
    store = Store(":memory:")
    auth = AuthService(store)

    auth.register("carol", "secret123")
    token = auth.create_token("carol")
    assert isinstance(token, str) and len(token) > 10

    # Verify token
    user = auth.verify_token(token)
    assert user is not None
    assert user["username"] == "carol"

    # Verify invalid token
    assert auth.verify_token("invalid_token_123") is None

    # Logout revokes token
    auth.logout(token)
    assert auth.verify_token(token) is None


def test_auth_api_endpoints():
    platform = Platform(":memory:")
    app = create_app(platform)
    client = TestClient(app)

    # React auth routes share the production SPA entry point.
    resp_login_page = client.get("/login")
    assert resp_login_page.status_code == 200
    assert "text/html" in resp_login_page.headers["content-type"]
    assert 'id="root"' in resp_login_page.text

    resp_register_page = client.get("/register")
    assert resp_register_page.status_code == 200
    assert "text/html" in resp_register_page.headers["content-type"]
    assert resp_register_page.text == resp_login_page.text

    # Dashboard access requires a valid session.
    anonymous_dashboard = client.get("/", follow_redirects=False)
    assert anonymous_dashboard.status_code == 303
    assert anonymous_dashboard.headers["location"] == "/login"

    # Register via API
    reg_resp = client.post(
        "/api/auth/register",
        json={"username": "dave", "password": "pass4dave"},
    )
    assert reg_resp.status_code == 201
    data = reg_resp.json()
    assert data["user"]["username"] == "dave"
    assert data["user"]["account_id"] == "acc_dave"
    token = data["token"]
    assert "algoshield_session=" in reg_resp.headers["set-cookie"]
    assert "HttpOnly" in reg_resp.headers["set-cookie"]
    assert client.get("/").status_code == 200
    direct_route = client.get("/strategies")
    assert direct_route.status_code == 200
    assert 'id="root"' in direct_route.text
    assert client.get("/failure-lab").status_code == 200

    # A caller cannot select a different trading account during registration.
    injected_account = client.post(
        "/api/auth/register",
        json={
            "username": "erin",
            "password": "pass4erin",
            "account_id": "someone-else",
        },
    )
    assert injected_account.status_code == 422

    # Verify /api/auth/me with Bearer token
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == "dave"

    # Duplicate registration returns 409
    dup_resp = client.post(
        "/api/auth/register",
        json={"username": "dave", "password": "newpass"},
    )
    assert dup_resp.status_code == 409

    # Login via API
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "dave", "password": "pass4dave"},
    )
    assert login_resp.status_code == 200
    new_token = login_resp.json()["token"]

    # Invalid login returns 401
    bad_login = client.post(
        "/api/auth/login",
        json={"username": "dave", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    # Logout
    logout_resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert logout_resp.status_code == 200

    # Me after logout returns 401
    after_logout = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert after_logout.status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303

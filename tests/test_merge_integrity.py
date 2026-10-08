"""Regression test validating the integrity of the merge between main and codex/usp-evidence-layer.

Covers:
- Preserved Member 4 Tasks 1-8 components (rehearsal runner, demo scenarios, static dashboard artifact)
- USP evidence layer endpoints and auth boundaries
- React SPA build artifacts serving
"""

from pathlib import Path
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.demo_scenarios import RehearsalRunner
from backend.platform import Platform


def test_preserved_static_dashboard_and_dist_artifacts():
    repo_root = Path(__file__).resolve().parent.parent
    static_dashboard = repo_root / "frontend" / "static_dashboard.html"
    dist_index = repo_root / "frontend" / "dist" / "index.html"
    index_html = repo_root / "frontend" / "index.html"

    # Static standalone dashboard preserved from Task 8
    assert static_dashboard.is_file(), (
        "frontend/static_dashboard.html must be preserved"
    )
    text = static_dashboard.read_text(encoding="utf-8")
    assert "feed-status-strip" in text
    assert "strategy-cards-grid" in text

    # Vite root index.html
    assert index_html.is_file()
    assert 'id="root"' in index_html.read_text(encoding="utf-8")

    # Production dist build
    assert dist_index.is_file(), "frontend/dist/index.html must exist after build"
    assert 'id="root"' in dist_index.read_text(encoding="utf-8")


def test_api_serves_spa_with_auth_flow():
    platform = Platform()
    try:
        app = create_app(platform)
        with TestClient(app) as client:
            # Unauthenticated GET / redirects to /login (status 303)
            resp = client.get("/", follow_redirects=False)
            assert resp.status_code == 303
            assert resp.headers["location"] == "/login"

            # Register user
            reg = client.post(
                "/api/auth/register",
                json={"username": "merge_test_user", "password": "password123"},
            )
            assert reg.status_code == 201

            # Authenticated GET / returns 200 with SPA shell
            dash = client.get("/")
            assert dash.status_code == 200
            assert 'id="root"' in dash.text

            # USP Evidence endpoints respond properly
            proof = client.get("/api/safety-proof")
            assert proof.status_code == 200
            data = proof.json()
            assert "verdict" in data

            recon = client.get("/api/reconciliation")
            assert recon.status_code == 200

            metrics = client.get("/api/metrics")
            assert metrics.status_code == 200
    finally:
        platform.close()


def test_demo_rehearsal_runner_isolated_instantiation():
    runner = RehearsalRunner()
    try:
        assert runner.username == "demo_user"
        assert runner.account_id == "acc_demo"
        # Setup base opposing strategies first
        runner.run_candles_and_opposing_strategies()
        # Run risk scenario
        res = runner.run_risk_limit_rejection()
        assert res.passed
        assert "RISK_MAX_POSITION" in res.summary
    finally:
        runner.close()

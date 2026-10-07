from dataclasses import replace
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.market_data.candles import CandleBuilder
from backend.shared.contracts import Tick, OrderStatus
from test_recovery import ready, intent


def test_response_filled_without_execution_closes_gate(monkeypatch):
    p = ready()
    original = p.broker.submit

    def unsupported(i):
        return replace(
            original(i), status=OrderStatus.FILLED, filled_quantity=i.quantity
        )

    monkeypatch.setattr(p.broker, "submit", unsupported)
    p.risk.submit(intent(p))
    assert p.risk.state == "UNCERTAIN"
    assert p.ledger.quantity("a", "A", "X") == 0
    assert p.store.rows("SELECT status FROM orders")[0][0] == "UNKNOWN"
    p.store.close()


def test_unknown_broker_status_cannot_prove_health(monkeypatch):
    p = ready()
    p.risk.submit(intent(p))
    snapshot = p.broker.snapshot()
    monkeypatch.setattr(
        p.broker,
        "snapshot",
        lambda: replace(
            snapshot, orders=(replace(snapshot.orders[0], status="UNMAPPED"),)
        ),
    )
    assert not p.reliability.reconcile()
    assert p.reliability.report["reason"] == "INVALID_BROKER_STATUS"
    p.store.close()


def test_halted_callback_and_callback_errors_close_gate(monkeypatch):
    p = ready()
    p.risk.set_strategy_state("A", "HALTED")
    p.tick(Tick("X", int(p.clock()) + 60, Decimal("101"), 1, "next-minute"))
    assert not p.broker.orders
    p.risk.set_strategy_state("A", "RUNNING")

    def failed(*args):
        raise RuntimeError("untrusted callback")

    monkeypatch.setattr(p.strategies, "on_candle", failed)
    with pytest.raises(ValueError, match="execution stopped"):
        p.tick(Tick("X", int(p.clock()) + 120, Decimal("102"), 1, "callback-failure"))
    assert p.risk.state == "UNCERTAIN" and not p.strategies.enabled
    p.store.close()


def test_dedupe_bounded_without_reaccepting_old_or_conflicting_ticks():
    b = CandleBuilder(max_seen=2)
    first = Tick("X", 0, Decimal("100"), 1, "one")
    b.ingest(first)
    with pytest.raises(ValueError, match="conflicting"):
        b.ingest(replace(first, price=Decimal("200")))
    for n in range(1, 10):
        b.ingest(Tick("X", n, Decimal("100"), 1, str(n)))
    assert len(b.seen) == 2
    with pytest.raises(ValueError, match="late"):
        b.ingest(first)
    current = Tick("X", 9, Decimal("100"), 1, "same-time")
    b.ingest(current)
    with pytest.raises(ValueError, match="capacity"):
        b.ingest(replace(current, event_id="overflow"))
    assert len(b.seen) == 2


def test_history_pagination_preserves_exact_economics_and_total():
    p = ready()
    p.risk.submit(intent(p))
    for q, price in ((4, "100"), (6, "101")):
        p.ingest(
            p.broker.execute("one", q, Decimal(price), p.clock(), Decimal("0.123456"))
        )
    with TestClient(create_app(p)) as client:
        first = client.get("/api/fills?limit=1").json()
        second = client.get("/api/fills?limit=1&offset=1").json()
        assert first["total"] == second["total"] == 2
        assert first["items"][0]["id"] != second["items"][0]["id"]
        assert first["items"][0]["charges"] == "0.123456"
        state = client.get("/api/state").json()
        assert isinstance(state["positions"][0]["net_pnl"], str)
        assert state["positions"][0]["charges"] == "0.246912"
        assert client.get("/api/fills?limit=501").status_code == 422
        assert client.get("/api/orders?offset=-1").status_code == 422
        assert (
            client.put(
                "/api/risk/policies/A",
                json={
                    "max_daily_loss": "10",
                    "max_position": True,
                    "max_orders_per_minute": 2,
                },
            ).status_code
            == 422
        )
    p.store.close()

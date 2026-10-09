from decimal import Decimal

import pytest

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick


def test_order_trace_is_durable_ordered_and_account_scoped():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    platform.risk.submit(
        OrderIntent("trace-1", "s", "a", "X", Side.BUY, 2, platform.clock())
    )
    platform.ingest(
        platform.broker.execute("trace-1", 2, Decimal("100"), platform.clock())
    )
    trace = platform.traces.trace("trace-1", "a")
    assert [event["sequence"] for event in trace["events"]] == sorted(
        event["sequence"] for event in trace["events"]
    )
    assert {event["type"] for event in trace["events"]} >= {
        "RISK_DECISION",
        "ORDER_SUBMITTED",
        "ORDER_STATUS_CHANGED",
    }
    with pytest.raises(PermissionError):
        platform.traces.trace("trace-1", "other")
    # Verify reconstructed order, fills, and financial outcome
    assert trace["order"]["order_id"] == "trace-1"
    assert trace["order"]["status"] == "FILLED"
    assert trace["order"]["filled_quantity"] == 2
    assert len(trace["fills"]) == 1
    assert trace["fills"][0]["quantity"] == 2
    assert trace["financial_outcome"]["net_quantity"] == 2
    assert trace["financial_outcome"]["symbol"] == "X"
    platform.close()


def test_full_trace_chain_signal_to_risk_to_order_to_fill_to_position():
    """Verify complete causality chain: Signal -> Intent -> RiskDecision -> Order -> Fill -> Position/P&L."""
    from fastapi.testclient import TestClient
    from backend.api import create_app
    from backend.shared.contracts import Candle

    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("acc_trace")
    platform.strategies.subscribe("acc_trace", "strat_trace", "momentum", "TCS")
    platform.tick(Tick("TCS", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()

    # Generate signal via closed candles to produce Strategy signal -> OrderIntent
    for i in range(4):
        c = Candle(
            "TCS",
            60,
            i * 60,
            (i + 1) * 60,
            Decimal(100 + i),
            Decimal(101 + i),
            Decimal(99 + i),
            Decimal(100 + i),
            10,
            True,
        )
        platform.strategies.on_candle(c, platform.clock())

    # 5th candle triggers momentum entry signal and produces OrderIntent
    c5 = Candle(
        "TCS",
        60,
        240,
        300,
        Decimal("104"),
        Decimal("110"),
        Decimal("103"),
        Decimal("110"),
        20,
        True,
    )
    intents = platform.strategies.on_candle(c5, platform.clock())
    assert len(intents) >= 1
    intent = intents[0]

    # Process through centralized risk layer
    decision = platform.risk.submit(intent)
    assert decision.allowed is True

    # Broker executes fill
    fill = platform.broker.execute(
        intent.intent_id,
        intent.quantity,
        Decimal("110.00"),
        platform.clock(),
        Decimal("0.25"),
    )
    assert platform.ingest(fill) is True

    # Inspect full trace reconstruction
    trace = platform.traces.trace(intent.intent_id, "acc_trace")
    assert trace["trace_id"] == intent.intent_id
    assert trace["strategy_instance_id"] == "strat_trace"
    assert trace["account_id"] == "acc_trace"

    # All chain stages present in audit events
    event_types = set(e["type"] for e in trace["events"])
    assert "STRATEGY_SIGNAL" in event_types
    assert "RISK_DECISION" in event_types
    assert "ORDER_SUBMITTED" in event_types
    assert "ORDER_STATUS_CHANGED" in event_types
    assert "FILL_APPLIED" in event_types

    # Order details reconstructed
    assert trace["order"] is not None
    assert trace["order"]["order_id"] == intent.intent_id
    assert trace["order"]["symbol"] == "TCS"
    assert trace["order"]["status"] == "FILLED"
    assert trace["order"]["filled_quantity"] == intent.quantity

    # Fills reconstructed
    assert len(trace["fills"]) == 1
    assert trace["fills"][0]["price"] == "110.00"
    assert trace["fills"][0]["charges"] == "0.25"

    # Financial outcome reconstructed with exact Decimal representation
    assert trace["financial_outcome"] is not None
    assert trace["financial_outcome"]["symbol"] == "TCS"
    assert trace["financial_outcome"]["net_quantity"] == intent.quantity
    assert trace["financial_outcome"]["charges"] == "0.25"

    # Verify through authenticated API endpoint
    app = create_app(platform)
    with TestClient(app) as client:
        # Register user with matching account acc_trace
        reg = client.post(
            "/api/auth/register", json={"username": "trace", "password": "password123"}
        )
        assert reg.status_code == 201
        assert reg.json()["user"]["account_id"] == "acc_trace"
        # Query recent traces
        res = client.get("/api/traces")
        assert res.status_code == 200
        # Query specific trace for user's account
        t_resp = client.get(f"/api/traces/{intent.intent_id}")
        assert t_resp.status_code == 200
        data = t_resp.json()
        assert data["trace_id"] == intent.intent_id
        assert data["order"]["status"] == "FILLED"
        assert len(data["fills"]) == 1
        assert data["financial_outcome"]["symbol"] == "TCS"

    platform.close()

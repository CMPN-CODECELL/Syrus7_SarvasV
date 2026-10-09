from decimal import Decimal
import pytest

from backend.broker.adapters import Broker021Adapter, MockBrokerAdapter
from backend.shared.contracts import (
    BrokerSnapshot,
    BrokerUpdateType,
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    Side,
)


def make_intent(
    key: str = "ord-contract-1",
    qty: int = 100,
    side: Side = Side.BUY,
    strat: str = "strat-1",
    acc: str = "acc-1",
    sym: str = "AAPL",
) -> OrderIntent:
    return OrderIntent(
        intent_id=key,
        strategy_instance_id=strat,
        account_id=acc,
        symbol=sym,
        side=side,
        quantity=qty,
        created_at=1_700_000_000.0,
    )


@pytest.fixture(params=["mock", "http"])
def broker(request):
    """Factory fixture for broker adapter testing across both in-process and HTTP adapters."""
    if request.param == "mock":
        yield MockBrokerAdapter()
    elif request.param == "http":
        from fastapi.testclient import TestClient

        from backend.broker.http_adapter import HTTPMockBrokerAdapter
        from backend.broker.mock_api import create_mock_broker_app

        app = create_mock_broker_app()
        client = TestClient(app)
        adapter = HTTPMockBrokerAdapter(client=client)
        yield adapter
        adapter.close()


# Contract A — Submission Identity
def test_contract_submission_identity(broker):
    intent = make_intent("ord-1", 100, Side.BUY)
    order = broker.submit(intent)

    assert isinstance(order, CanonicalOrder)
    assert order.order_id == intent.intent_id
    assert order.intent == intent
    assert order.intent.strategy_instance_id == "strat-1"
    assert order.intent.account_id == "acc-1"
    assert order.intent.symbol == "AAPL"
    assert order.intent.side == Side.BUY
    assert order.intent.quantity == 100
    assert order.status == OrderStatus.OPEN
    assert order.filled_quantity == 0
    assert order.remaining_quantity == 100


def test_contract_identity_collision_never_reuses_foreign_order(broker):
    original = make_intent("global-identity", acc="account-one")
    broker.submit(original)
    with pytest.raises((ValueError, RuntimeError)):
        broker.submit(make_intent("global-identity", acc="account-two"))
    assert broker.orders["global-identity"].intent == original
    assert len(broker.fills) == 0


# Contract B — Rejection
def test_contract_rejection(broker):
    broker.reject_next = True
    intent = make_intent("ord-rej", 50)
    order = broker.submit(intent)

    assert order.status == OrderStatus.REJECTED
    assert order.filled_quantity == 0
    assert order.remaining_quantity == 50
    # Rejection must not fabricate any fills
    assert len(broker.fills) == 0


# Contract C — Partial and Complete Fills
def test_contract_partial_and_complete_fills(broker):
    intent = make_intent("ord-fills", 100)
    broker.submit(intent)

    # Partial execution 40
    fill1 = broker.execute(
        "ord-fills", 40, Decimal("150.00"), 1000.0, charges=Decimal("1.50")
    )
    assert isinstance(fill1, Fill)
    assert fill1.broker_order_id == "ord-fills"
    assert fill1.strategy_instance_id == "strat-1"
    assert fill1.account_id == "acc-1"
    assert fill1.symbol == "AAPL"
    assert fill1.side == Side.BUY
    assert fill1.quantity == 40
    assert fill1.price == Decimal("150.00")
    assert fill1.timestamp == 1000.0
    assert fill1.charges == Decimal("1.50")

    order_part = broker.orders["ord-fills"]
    assert order_part.filled_quantity == 40
    assert order_part.remaining_quantity == 60
    assert order_part.status == OrderStatus.PARTIALLY_FILLED

    # Complete remaining 60
    fill2 = broker.execute(
        "ord-fills", 60, Decimal("151.00"), 1001.0, charges=Decimal("2.00")
    )
    assert fill2.quantity == 60

    order_full = broker.orders["ord-fills"]
    assert order_full.filled_quantity == 100
    assert order_full.remaining_quantity == 0
    assert order_full.status == OrderStatus.FILLED


# Contract D — Fill Identity
def test_contract_fill_identity(broker):
    intent = make_intent("ord-id", 100)
    broker.submit(intent)

    fill1 = broker.execute("ord-id", 40, Decimal("100"), 1000.0)
    fill2 = broker.execute("ord-id", 60, Decimal("100"), 1001.0)

    # Fills have distinct, deterministic IDs
    assert fill1.fill_id != fill2.fill_id
    assert fill1.fill_id in broker.fills
    assert fill2.fill_id in broker.fills


# Contract E — Cancellation
def test_contract_cancellation(broker):
    # Open cancellation
    intent1 = make_intent("ord-cxl-open", 100)
    broker.submit(intent1)
    broker.cancel("ord-cxl-open")
    assert broker.orders["ord-cxl-open"].status == OrderStatus.CANCELLED
    assert broker.orders["ord-cxl-open"].filled_quantity == 0

    # Partial-fill cancellation: does not undo executed fills
    intent2 = make_intent("ord-cxl-part", 100)
    broker.submit(intent2)
    broker.execute("ord-cxl-part", 40, Decimal("100"), 1000.0)
    broker.cancel("ord-cxl-part")
    assert broker.orders["ord-cxl-part"].status == OrderStatus.CANCELLED
    assert broker.orders["ord-cxl-part"].filled_quantity == 40

    # Repeated cancellation is harmless and idempotent
    broker.cancel("ord-cxl-part")
    assert broker.orders["ord-cxl-part"].status == OrderStatus.CANCELLED
    assert broker.orders["ord-cxl-part"].filled_quantity == 40


# Contract F — Broker Updates
def test_contract_broker_updates(broker):
    intent = make_intent("ord-upd", 100)
    broker.submit(intent)
    broker.execute("ord-upd", 40, Decimal("100"), 1000.0)
    broker.cancel("ord-upd")

    updates = broker.drain_updates()
    assert len(updates) == 3

    types = [u.update_type for u in updates]
    assert types == [
        BrokerUpdateType.ORDER_ACCEPTED,
        BrokerUpdateType.FILL,
        BrokerUpdateType.ORDER_CANCELLED,
    ]

    # Verify update structure and attribution
    fill_upd = updates[1]
    assert fill_upd.update_type == BrokerUpdateType.FILL
    assert fill_upd.fill is not None
    assert fill_upd.fill.quantity == 40
    assert fill_upd.order_id == "ord-upd"

    # Queue is drained
    assert len(broker.drain_updates()) == 0


# Contract G — Disconnect Behavior
def test_contract_disconnect_behavior(broker):
    intent = make_intent("ord-disc", 100)
    broker.submit(intent)

    broker.disconnect()
    assert broker.connected is False

    with pytest.raises(ConnectionError, match="disconnected"):
        broker.submit(make_intent("ord-disc-2", 50))

    with pytest.raises(ConnectionError, match="disconnected"):
        broker.execute("ord-disc", 10, Decimal("100"), 1000.0)

    with pytest.raises(ConnectionError, match="disconnected"):
        broker.cancel("ord-disc")

    with pytest.raises(ConnectionError, match="disconnected"):
        broker.snapshot()


# Contract H — Reconnect and Snapshot
def test_contract_reconnect_and_snapshot(broker):
    broker.disconnect()
    broker.reconnect()
    assert broker.connected is True

    snap = broker.snapshot()
    assert isinstance(snap, BrokerSnapshot)
    assert snap.is_complete is True
    assert isinstance(snap.orders, tuple)
    assert isinstance(snap.fills, tuple)
    assert isinstance(snap.positions, dict)


# Contract I — Snapshot Consistency
def test_contract_snapshot_consistency(broker):
    intent = make_intent("ord-snap", 100, Side.BUY, acc="acc-1", sym="AAPL")
    broker.submit(intent)
    broker.execute("ord-snap", 40, Decimal("150.00"), 1000.0)

    snap = broker.snapshot()
    assert snap.is_complete is True

    # Order represented accurately
    orders = {o.order_id: o for o in snap.orders}
    assert "ord-snap" in orders
    assert orders["ord-snap"].status == OrderStatus.PARTIALLY_FILLED
    assert orders["ord-snap"].filled_quantity == 40

    # Fills represented accurately
    assert len(snap.fills) == 1
    assert snap.fills[0].quantity == 40
    assert snap.fills[0].broker_order_id == "ord-snap"

    # Position accurately aggregates fills
    assert snap.positions.get(("acc-1", "AAPL")) == 40


# Contract J — Ambiguous Submission / Timeout
def test_contract_ambiguous_submission_timeout(broker):
    broker.timeout_after_accept = True
    intent = make_intent("ord-timeout", 100)

    with pytest.raises(TimeoutError, match="ambiguous"):
        broker.submit(intent)

    # Crucial guarantee: timeout != rejection; order exists at broker
    assert "ord-timeout" in broker.orders
    assert broker.orders["ord-timeout"].status == OrderStatus.OPEN

    # Discovery through snapshot is possible
    snap = broker.snapshot()
    order_ids = [o.order_id for o in snap.orders]
    assert "ord-timeout" in order_ids


# Contract K — External Persistence / Restart Truth
def test_contract_external_persistence_across_restart(tmp_path):
    store_path = str(tmp_path / "broker_truth.json")

    # Instance A places trade
    broker_a = MockBrokerAdapter(store_path)
    intent = make_intent("ord-restart", 100, Side.BUY, acc="acc-1", sym="AAPL")
    broker_a.submit(intent)
    broker_a.execute("ord-restart", 40, Decimal("100"), 1000.0)

    # Instance B loads same external broker truth
    broker_b = MockBrokerAdapter(store_path)
    snap = broker_b.snapshot()
    assert snap.is_complete is True

    orders = {o.order_id: o for o in snap.orders}
    assert "ord-restart" in orders
    assert orders["ord-restart"].status == OrderStatus.PARTIALLY_FILLED
    assert orders["ord-restart"].filled_quantity == 40
    assert snap.positions.get(("acc-1", "AAPL")) == 40


# Broker021Adapter Contract Honesty
def test_contract_021_adapter_is_disabled_and_fails_closed():
    adapter = Broker021Adapter()
    with pytest.raises(RuntimeError, match="disabled"):
        adapter.submit(make_intent())
    with pytest.raises(RuntimeError, match="disabled"):
        adapter.cancel("ord-1")
    with pytest.raises(RuntimeError, match="disabled"):
        adapter.snapshot()
    assert adapter.drain_updates() == []
    adapter.disconnect()
    assert adapter.connected is False
    with pytest.raises(RuntimeError, match="disabled"):
        adapter.reconnect()

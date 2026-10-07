from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from backend.broker.http_adapter import HTTPMockBrokerAdapter, MockBrokerControlClient
from backend.broker.mock_api import create_mock_broker_app
from backend.platform import Platform
from backend.shared.contracts import (
    GlobalTradingState,
    OrderIntent,
    OrderStatus,
    Side,
)


@pytest.fixture
def http_setup():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    control = MockBrokerControlClient(client=client)
    platform = Platform(path=":memory:", broker=adapter)

    # Set up basic account and subscription
    platform.account("acc-1")
    platform.strategies.subscribe("acc-1", "strat-1", "momentum", "AAPL")
    platform.reliability.resume()
    from backend.shared.contracts import Tick

    now = int(platform.clock())
    tick = Tick(
        symbol="AAPL",
        event_timestamp=now,
        price=Decimal("150.00"),
        quantity=10,
        event_id="init-tick-1",
    )
    platform.reliability.observe_tick(tick)
    platform.reliability.last_broker_at = platform.clock()
    platform.reliability.report["verified"] = True
    platform.reliability._health("HEALTHY")

    yield platform, adapter, control
    adapter.close()


def test_http_broker_submit_open(http_setup):
    platform, adapter, control = http_setup

    intent = OrderIntent(
        intent_id="intent-open-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    decision = platform.risk.submit(intent)
    assert decision.allowed is True

    # Order exists in platform and HTTP broker as OPEN
    row = platform.store.rows("SELECT * FROM orders WHERE id=?", ("intent-open-1",))[0]
    assert row["status"] == OrderStatus.OPEN.value
    assert row["filled"] == 0
    assert row["quantity"] == 100

    broker_order = adapter.orders["intent-open-1"]
    assert broker_order.status == OrderStatus.OPEN


def test_http_broker_rejection(http_setup):
    platform, adapter, control = http_setup

    control.reject_next()

    intent = OrderIntent(
        intent_id="intent-rej-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=50,
        created_at=platform.clock(),
    )
    decision = platform.risk.submit(intent)
    assert decision.allowed is True

    row = platform.store.rows("SELECT * FROM orders WHERE id=?", ("intent-rej-1",))[0]
    assert row["status"] == OrderStatus.REJECTED.value
    assert row["filled"] == 0
    assert len(adapter.fills) == 0


def test_http_broker_partial_fill_and_update(http_setup):
    platform, adapter, control = http_setup

    intent = OrderIntent(
        intent_id="intent-fill-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    platform.risk.submit(intent)

    # Broker executes partial fill
    control.fill("intent-fill-1", 40, "150.00", "1.50", platform.clock())

    # Drain and apply broker updates through platform
    updates = platform.sync_broker_updates()
    assert len(updates) > 0

    row = platform.store.rows("SELECT * FROM orders WHERE id=?", ("intent-fill-1",))[0]
    assert row["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert row["filled"] == 40

    # Member 1 ledger has updated position
    assert platform.ledger.quantity("acc-1", "strat-1", "AAPL") == 40


def test_http_broker_cancellation(http_setup):
    platform, adapter, control = http_setup

    intent = OrderIntent(
        intent_id="intent-cxl-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    platform.risk.submit(intent)
    control.fill("intent-cxl-1", 40, "150.00", "1.50", platform.clock())
    platform.sync_broker_updates()

    # Cancel remaining quantity
    cancelled_order = platform.cancel("intent-cxl-1")
    assert cancelled_order.status == OrderStatus.CANCELLED
    assert cancelled_order.filled_quantity == 40
    assert cancelled_order.remaining_quantity == 60

    # Remote broker also CANCELLED
    assert adapter.orders["intent-cxl-1"].status == OrderStatus.CANCELLED


def test_http_broker_snapshot_parsing(http_setup):
    platform, adapter, control = http_setup

    intent = OrderIntent(
        intent_id="intent-snap-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    platform.risk.submit(intent)
    control.fill("intent-snap-1", 30, "150.00", "1.00", platform.clock())

    snap = adapter.snapshot()
    assert snap.is_complete is True
    assert len(snap.orders) == 1
    assert snap.orders[0].order_id == "intent-snap-1"
    assert len(snap.fills) == 1
    assert snap.fills[0].quantity == 30
    assert snap.positions.get(("acc-1", "AAPL")) == 30


def test_http_broker_timeout_after_accept_unknown_and_recovery(http_setup):
    platform, adapter, control = http_setup

    control.timeout_after_accept()

    intent = OrderIntent(
        intent_id="intent-timeout-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=50,
        created_at=platform.clock(),
    )

    # Submit encounters timeout, marking submission UNKNOWN without blindly retrying
    decision = platform.risk.submit(intent)
    assert decision.allowed is True

    # Platform enters UNCERTAIN state and order remains RESERVED in local DB
    assert platform.risk.state == GlobalTradingState.UNCERTAIN
    row = platform.store.rows("SELECT * FROM orders WHERE id=?", ("intent-timeout-1",))[
        0
    ]
    assert row["status"] in {OrderStatus.RESERVED.value, OrderStatus.UNKNOWN.value}

    # Reconciliation resolves the ambiguous submission by querying the authoritative snapshot
    reconciled = platform.reliability.reconcile()
    assert reconciled is True

    # Resolved to OPEN after discovering external broker truth
    row_recovered = platform.store.rows(
        "SELECT * FROM orders WHERE id=?", ("intent-timeout-1",)
    )[0]
    assert row_recovered["status"] == OrderStatus.OPEN.value
    assert row_recovered["filled"] == 0


def test_http_broker_disconnect_blocks_trading(http_setup):
    platform, adapter, control = http_setup

    res = platform.disconnect_broker()
    assert res["connected"] is False
    assert platform.risk.state == GlobalTradingState.UNCERTAIN

    # New order intents are blocked
    intent = OrderIntent(
        intent_id="intent-blocked-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=10,
        created_at=platform.clock(),
    )
    decision = platform.risk.submit(intent)
    assert decision.allowed is False


def test_http_broker_external_fill_during_disconnect_and_reconciliation(http_setup):
    platform, adapter, control = http_setup

    # 1. Place order
    intent = OrderIntent(
        intent_id="intent-ext-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    platform.risk.submit(intent)

    # 2. Broker disconnects
    platform.disconnect_broker()
    assert platform.risk.state == GlobalTradingState.UNCERTAIN

    # 3. External broker fill occurs while client cannot connect
    control.external_fill("intent-ext-1", 40, "150.00", "2.00", platform.clock())

    # 4. Reconnect broker
    rec_res = platform.reconnect_broker()
    assert rec_res["connected"] is True
    assert rec_res["reconciled"] is True

    # 5. Local state has recovered the missed fill
    row = platform.store.rows("SELECT * FROM orders WHERE id=?", ("intent-ext-1",))[0]
    assert row["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert row["filled"] == 40
    assert platform.ledger.quantity("acc-1", "strat-1", "AAPL") == 40


def test_http_broker_replay_executes_fills_and_reconciles():
    app = create_mock_broker_app()
    client = TestClient(app)
    adapter = HTTPMockBrokerAdapter(client=client)
    platform = Platform(path=":memory:", broker=adapter, demo_enabled=True)
    try:
        state = platform.demo()
        assert state["counts"]["orders"] > 0
        assert state["counts"]["fills"] > 0
        assert state["market_data"]["accepted_ticks"] > 0
        assert state["safety"]["position_comparison"]["status"] == "VERIFIED"
    finally:
        adapter.close()


def test_http_broker_reconnect_does_not_auto_resume(http_setup):
    platform, adapter, control = http_setup

    platform.disconnect_broker()
    platform.reconnect_broker()

    # Reconnect transitions to STOPPED (or RECOVERING), never automatically to RUNNING
    assert platform.risk.state != GlobalTradingState.RUNNING


def test_http_broker_duplicate_fill_ignored(http_setup):
    platform, adapter, control = http_setup

    intent = OrderIntent(
        intent_id="intent-dup-1",
        strategy_instance_id="strat-1",
        account_id="acc-1",
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        created_at=platform.clock(),
    )
    platform.risk.submit(intent)
    control.fill("intent-dup-1", 50, "150.00", "1.00", platform.clock())

    # Ingest once
    updates1 = platform.sync_broker_updates()
    assert len(updates1) > 0
    assert platform.ledger.quantity("acc-1", "strat-1", "AAPL") == 50

    # Re-ingest the same fill directly or via sync
    snap = adapter.snapshot()
    fill = snap.fills[0]
    platform.ingest(fill)  # duplicate ingestion

    # Position remains 50, does not double count
    assert platform.ledger.quantity("acc-1", "strat-1", "AAPL") == 50

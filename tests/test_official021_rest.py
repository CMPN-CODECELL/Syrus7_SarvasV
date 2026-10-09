import gzip
import json
import struct
import time
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from backend.broker.adapters import Broker021Adapter
from backend.shared.contracts import OrderIntent, Side
from backend.shared.store import Store


INSTRUMENTS = (
    "token,exchange,underlying_token,underlying_exchange,min_lot_size,"
    "board_lot_quantity,freeze_quantity,lower_circuit,upper_circuit,expiry,"
    "option_type,strike_price,symbol,instrument_type,isin,ticksize\n"
    "2885,NSECM,2885,NSECM,0,1,1000,1,999999,0,,0,RELIANCE,STK,INE002A01018,5\n"
).encode()


def _platform():
    store = Store()
    store.db.execute("INSERT INTO accounts VALUES ('a')")
    store.db.execute(
        "INSERT INTO subscriptions VALUES ('s','a','momentum','RELIANCE',1)"
    )
    store.db.execute(
        "INSERT INTO orders(id,strategy,account,symbol,side,quantity,created,status,filled,emergency) "
        "VALUES ('i1','s','a','RELIANCE','BUY',2,100,'UNKNOWN',0,0)"
    )
    store.db.commit()
    return store


def test_rest_adapter_maps_orders_and_trades_to_canonical_evidence():
    store = _platform()
    state = {"order_status": "Executed"}

    def handler(request):
        path = request.url.path
        if path.endswith("/instruments"):
            return httpx.Response(
                200,
                content=gzip.compress(INSTRUMENTS),
                headers={"Content-Type": "text/csv", "Content-Encoding": "gzip"},
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            assert body == {
                "exchange": "NSE",
                "token": 2885,
                "qty": 2,
                "price": 0,
                "book": "RL",
                "trigger": 0,
                "discQuantity": 0,
                "product": "INTRADAY",
                "validity": "Day",
                "amo": False,
            }
            return httpx.Response(
                200,
                json={
                    "data": {"type": "SUCCESS", "message": "accepted", "orderId": "42"},
                    "success": True,
                    "error": None,
                },
            )
        if path.endswith("/orders"):
            return httpx.Response(
                200,
                json=[
                    {
                        "orderId": 42,
                        "qtyTraded": 2,
                        "status": state["order_status"],
                        "lastActivity": 101,
                    }
                ],
            )
        if path.endswith("/orders/42/trades"):
            return httpx.Response(
                200,
                json=[
                    {
                        "tradeId": 5001,
                        "tradeTime": 101,
                        "quantity": 2,
                        "token": 2885,
                        "exchange": "NSECM",
                        "product": "INTRADAY",
                        "price": 140000,
                        "symbol": "RELIANCE",
                    }
                ],
            )
        if path.endswith("/portfolio/positions"):
            return httpx.Response(
                200,
                json=[
                    {
                        "exchange": "NSECM",
                        "token": 2885,
                        "netQuantity": 2,
                        "symbol": "RELIANCE",
                    }
                ],
            )
        raise AssertionError(f"unexpected request {request.method} {path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    intent = OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100)
    order = adapter.submit(intent)
    assert order.order_id == "i1"
    assert (
        store.rows("SELECT provider_order_id FROM broker_order_mappings")[0][0] == "42"
    )
    snapshot = adapter.snapshot()
    assert snapshot.is_complete is False
    assert snapshot.orders[0].filled_quantity == 2
    assert snapshot.fills[0].fill_id == "021:5001"
    assert snapshot.fills[0].price == Decimal("1400")
    updates = adapter.drain_updates()
    assert any(update.fill and update.fill.fill_id == "021:5001" for update in updates)
    assert updates[0].fill is not None
    assert all(update.status.value != "FILLED" for update in updates[1:])
    assert adapter.drain_updates()[0].fill.fill_id == "021:5001"
    adapter.acknowledge_update(updates[0])
    assert adapter.drain_updates() == []


def test_catalogue_exposes_cash_equity_symbols_for_auto_market_setup(tmp_path):
    cache = tmp_path / "instruments.csv"
    cache.write_bytes(INSTRUMENTS)
    adapter = Broker021Adapter(
        _platform(),
        enabled=True,
        access_token="test-token",
        instrument_cache=str(cache),
    )

    assert adapter.all_market_symbols() == ("RELIANCE",)


@pytest.mark.xfail(
    strict=True,
    reason="Member 2 must prove UCC-to-account scope before order-WS mapping",
    raises=AssertionError,
)
def test_order_ws_event_never_cross_attributes_same_provider_order_id_across_accounts():
    """Frozen fixture for the required account/UCC mapping handoff.

    The unique database key permits the same provider order ID for two local
    accounts.  An event carrying UCC ``account-b`` must not select account A
    merely because it was inserted first.
    """
    store = Store()
    for account, strategy, order in (
        ("account-a", "sa", "oa"),
        ("account-b", "sb", "ob"),
    ):
        store.db.execute("INSERT INTO accounts VALUES (?)", (account,))
        store.db.execute(
            "INSERT INTO subscriptions VALUES (?,?,?, ?,1)",
            (strategy, account, "momentum", "RELIANCE"),
        )
        store.db.execute(
            "INSERT INTO orders(id,strategy,account,symbol,side,quantity,created,status,filled,emergency) "
            "VALUES (?,?,?,?,?,?,100,'OPEN',0,0)",
            (order, strategy, account, "RELIANCE", "BUY", 1),
        )
        store.db.execute(
            "INSERT INTO broker_order_mappings(platform_order_id,provider,provider_order_id,account,exchange,token,product,symbol,created) "
            "VALUES (?,?, '42', ?, 'NSE', 2885, 'INTRADAY', 'RELIANCE', 100)",
            (order, "021", account),
        )
    store.db.commit()
    adapter = Broker021Adapter(store, enabled=True, access_token="fixture-token")
    frame = bytearray(46)
    struct.pack_into(">HH", frame, 0, 4, 2)
    frame[4:14] = b"account-b "
    frame[14:34] = b"RELIANCE            "
    struct.pack_into(">IiI", frame, 34, 42, 1, 10100)

    assert adapter.parse_order_update(bytes(frame)) is None


def test_cnc_catalogue_ignores_derivatives_with_the_same_symbol(tmp_path):
    cache = tmp_path / "instruments.csv"
    cache.write_bytes(
        INSTRUMENTS
        + b"999,NSEFO,2885,NSECM,1,1,1000,1,999999,0,CALL,100,RELIANCE,OPTSTK,,5\n"
    )
    adapter = Broker021Adapter(
        _platform(),
        enabled=True,
        access_token="test-token",
        product="CNC",
        instrument_cache=str(cache),
    )

    assert adapter.all_market_symbols() == ("RELIANCE",)
    assert adapter._instrument("RELIANCE").product == "CNC"


def test_cash_catalogue_is_ranked_by_provider_freeze_quantity(tmp_path):
    cache = tmp_path / "instruments.csv"
    cache.write_bytes(
        INSTRUMENTS
        + b"1594,NSECM,1594,NSECM,0,1,5000,1,999999,0,,0,INFY,STK,INE009A01021,5\n"
    )
    adapter = Broker021Adapter(
        _platform(),
        enabled=True,
        access_token="test-token",
        instrument_cache=str(cache),
    )

    assert adapter.all_market_symbols() == ("INFY", "RELIANCE")


def test_submit_preserves_definitive_provider_rejection_without_order_id():
    store = _platform()

    def handler(request):
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if request.url.path.endswith("/orders") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "type": "FAILURE",
                        "message": "instrument is unavailable for this product",
                        "orderId": 0,
                    },
                    "success": True,
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    order = adapter.submit(OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100))

    assert order.status.value == "REJECTED"
    assert store.rows("SELECT * FROM broker_order_mappings") == []
    audit = store.rows("SELECT payload FROM audit WHERE type='021_ORDER_REJECTED'")
    assert "unavailable for this product" in audit[0]["payload"]


def test_submit_treats_reason_bearing_zero_order_id_as_rejected():
    store = _platform()

    def handler(request):
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if request.url.path.endswith("/orders") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "orderId": 0,
                        "reason": "instrument is in a non-tradable session",
                    },
                    "success": True,
                    "error": None,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    order = adapter.submit(OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100))
    assert order.status.value == "REJECTED"


def test_submit_resolves_zero_order_id_from_exact_provider_rejection():
    store = _platform()

    def handler(request):
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if request.url.path.endswith("/orders") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "data": {"type": "SUCCESS", "message": "submitted", "orderId": 0},
                    "success": True,
                    "error": None,
                },
            )
        if request.url.path.endswith("/orders") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "orderId": 0,
                        "status": "Rejected",
                        "token": 2885,
                        "product": "INTRADAY",
                        "qtyRemaining": 2,
                        "qtyTraded": 0,
                        "reason": "instrument is in a non-tradable session",
                    }
                ],
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    order = adapter.submit(OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100))

    assert order.status.value == "REJECTED"


def test_submit_maps_application_failure_envelope_to_rejected():
    store = _platform()

    def handler(request):
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if request.url.path.endswith("/orders") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "data": None,
                    "success": False,
                    "error": "market orders are unavailable for this instrument",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    order = adapter.submit(OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100))

    assert order.status.value == "REJECTED"


def test_submit_maps_provider_validation_http_response_to_rejected():
    store = _platform()

    def handler(request):
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if request.url.path.endswith("/orders") and request.method == "POST":
            return httpx.Response(422, json={"detail": "market order unavailable"})
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    order = adapter.submit(OrderIntent("i1", "s", "a", "RELIANCE", Side.BUY, 2, 100))

    assert order.status.value == "REJECTED"


def test_empty_virtual_account_bootstrap_requires_every_empty_view():
    def handler(request):
        if request.url.path.endswith(
            ("/orders", "/trades", "/portfolio/positions", "/portfolio/holdings")
        ):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    store = Store()
    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert adapter.snapshot().is_complete is True

    store.db.execute("INSERT INTO accounts VALUES ('a')")
    store.db.execute(
        "INSERT INTO subscriptions VALUES ('s','a','momentum','RELIANCE',1)"
    )
    store.db.execute(
        "INSERT INTO orders(id,strategy,account,symbol,side,quantity,created,status,filled,emergency) "
        "VALUES ('old','s','a','RELIANCE','BUY',1,100,'FILLED',1,0)"
    )
    store.db.commit()
    assert adapter.snapshot().is_complete is False


def test_nonempty_021_view_never_uses_empty_bootstrap():
    def handler(request):
        path = request.url.path
        if path.endswith("/orders"):
            return httpx.Response(200, json=[])
        if path.endswith("/trades"):
            return httpx.Response(200, json=[])
        if path.endswith("/portfolio/positions"):
            return httpx.Response(200, json=[])
        if path.endswith("/portfolio/holdings"):
            return httpx.Response(200, json=[{"symbol": "RELIANCE", "quantity": 1}])
        raise AssertionError(f"unexpected request {request.method} {path}")

    adapter = Broker021Adapter(
        Store(),
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert adapter.snapshot().is_complete is False


def test_zero_fill_terminal_provider_order_does_not_poison_empty_bootstrap():
    def handler(request):
        path = request.url.path
        if path.endswith("/orders"):
            return httpx.Response(
                200,
                json=[
                    {
                        "orderId": 0,
                        "status": "Rejected",
                        "qtyTraded": 0,
                        "reason": "not available for intraday trading",
                    }
                ],
            )
        if path.endswith(("/trades", "/portfolio/positions", "/portfolio/holdings")):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected request {request.method} {path}")

    adapter = Broker021Adapter(
        Store(),
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert adapter.snapshot().is_complete is True


def test_same_day_mapped_history_extends_verified_empty_bootstrap():
    now = time.time()
    store = _platform()
    store.db.execute(
        "INSERT INTO broker_order_mappings VALUES (?,?,?,?,?,?,?,?,?)",
        ("i1", "021", "42", "a", "NSECM", 2885, "INTRADAY", "RELIANCE", now - 5),
    )
    store.db.commit()
    store.audit(
        "RECONCILED",
        {
            "verified": True,
            "reason": "MATCHED",
            "observed_at": now - 10,
            "orders": 0,
            "unique_fills": 0,
            "broker_positions": [],
            "unexplained_positions": [],
        },
    )

    trade = {
        "tradeId": 5001,
        "tradeTime": now - 4,
        "quantity": 2,
        "token": 2885,
        "exchange": "NSECM",
        "product": "INTRADAY",
        "price": 140000,
        "symbol": "RELIANCE",
    }

    def handler(request):
        path = request.url.path
        if path.endswith("/instruments"):
            return httpx.Response(200, content=gzip.compress(INSTRUMENTS))
        if path.endswith("/orders/42/trades"):
            return httpx.Response(200, json=[trade])
        if path.endswith("/orders"):
            return httpx.Response(
                200,
                json=[
                    {
                        "orderId": 42,
                        "time": now - 5,
                        "qtyTraded": 2,
                        "status": "Executed",
                    }
                ],
            )
        if path.endswith("/trades"):
            return httpx.Response(200, json=[trade])
        if path.endswith("/portfolio/positions"):
            return httpx.Response(
                200,
                json=[
                    {
                        "exchange": "NSECM",
                        "token": 2885,
                        "netQuantity": 2,
                    }
                ],
            )
        if path.endswith("/portfolio/holdings"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected request {request.method} {path}")

    adapter = Broker021Adapter(
        store,
        enabled=True,
        access_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert adapter.snapshot().is_complete is True

    store.db.execute(
        "UPDATE audit SET payload=? WHERE type='RECONCILED'",
        (
            json.dumps(
                {
                    "verified": True,
                    "observed_at": now - 86_400,
                    "orders": 0,
                    "unique_fills": 0,
                    "broker_positions": [],
                    "unexplained_positions": [],
                }
            ),
        ),
    )
    store.db.commit()
    assert adapter.snapshot().is_complete is False


def test_order_websocket_disables_incompatible_client_ping_keepalive():
    adapter = Broker021Adapter(
        Store(),
        enabled=True,
        access_token="test-token",
        base_url="https://example.test/api/developer-api/v1",
    )
    adapter.ephemeral_key = lambda: "ephemeral"

    with patch("websockets.sync.client.connect", return_value="socket") as connect:
        assert adapter.connect_order_websocket() == "socket"

    connect.assert_called_once_with(
        "wss://example.test/api/developer/websocket/orders?token=ephemeral",
        ping_interval=None,
    )

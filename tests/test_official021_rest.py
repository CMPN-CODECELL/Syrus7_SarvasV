import gzip
import json
import struct
from decimal import Decimal

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

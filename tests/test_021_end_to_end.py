import gzip
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from backend.broker.official021_http import Official021RESTAdapter
from backend.platform import Platform
from backend.shared.contracts import Tick
from backend.shared.store import Store


INSTRUMENTS = (
    "token,exchange,underlying_token,underlying_exchange,min_lot_size,"
    "board_lot_quantity,freeze_quantity,lower_circuit,upper_circuit,expiry,"
    "option_type,strike_price,symbol,instrument_type,isin,ticksize\n"
    "2885,NSECM,2885,NSECM,0,1,1000,1,999999,0,,0,RELIANCE,STK,INE002A01018,5\n"
).encode()


def test_fake_021_quote_to_reconciled_fill_pipeline(tmp_path):
    now = datetime(2026, 10, 9, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    state = {"placed": False, "executed": False}

    def handler(request):
        path = request.url.path
        if path.endswith("/orders") and request.method == "POST":
            state["placed"] = True
            return httpx.Response(
                200,
                json={
                    "data": {"type": "SUCCESS", "orderId": "42"},
                    "success": True,
                    "error": None,
                },
            )
        if path.endswith("/orders"):
            if not state["placed"]:
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[
                    {
                        "orderId": 42,
                        "qtyTraded": 1 if state["executed"] else 0,
                        "status": "Executed" if state["executed"] else "Placed",
                        "lastActivity": now,
                    }
                ],
            )
        if path.endswith("/orders/42/trades"):
            return httpx.Response(
                200,
                json=(
                    [
                        {
                            "tradeId": 5001,
                            "tradeTime": now,
                            "quantity": 1,
                            "token": 2885,
                            "exchange": "NSECM",
                            "product": "INTRADAY",
                            "price": 10100,
                            "symbol": "RELIANCE",
                        }
                    ]
                    if state["executed"]
                    else []
                ),
            )
        if path.endswith("/portfolio/positions"):
            return httpx.Response(
                200,
                json=(
                    [
                        {
                            "exchange": "NSECM",
                            "token": 2885,
                            "netQuantity": 1,
                            "symbol": "RELIANCE",
                        }
                    ]
                    if state["executed"]
                    else []
                ),
            )
        raise AssertionError(f"unexpected fake 021 request: {request.method} {path}")

    class CompleteFake021(Official021RESTAdapter):
        def snapshot(self):
            # Test-only exchange fixture explicitly attests its entire state.
            return replace(super().snapshot(), is_complete=True, observed_at=now)

    cache = tmp_path / "instruments.csv.gz"
    cache.write_bytes(gzip.compress(INSTRUMENTS))
    store = Store()
    adapter = CompleteFake021(
        store,
        access_token="fixture-token",
        instrument_cache=str(cache),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    platform = Platform(store=store, broker=adapter, clock=lambda: now)

    class QuoteProvider:
        supports_live_broker = True

        def telemetry(self):
            return {
                "provider": "021",
                "source": "021_LIVE",
                "latest_quotes": [{"symbol": "RELIANCE", "official_open": "100"}],
            }

        def stop(self):
            return True

    platform.configure_external_market_data(QuoteProvider())
    try:
        platform.account("a")
        platform.strategies.subscribe(
            "a", "open-reliance", "open_1pct_tp5_sl5", "RELIANCE"
        )
        assert platform.reliability.reconcile() is True
        platform.reliability.resume()

        platform.tick(
            Tick(
                "RELIANCE",
                int(now),
                Decimal("101"),
                0,
                "fake-021-quote-1",
                data_source="021_LIVE",
            )
        )
        order = store.rows("SELECT * FROM orders")[0]
        assert order["status"] == "OPEN"
        assert state["placed"] is True

        state["executed"] = True
        platform.sync_broker_updates()
        order = store.rows("SELECT * FROM orders")[0]
        assert order["status"] == "FILLED"
        assert order["filled"] == 1
        assert store.rows("SELECT id FROM fills")[0]["id"] == "021:5001"
        assert platform.ledger.aggregate() == {("a", "RELIANCE"): 1}
        assert platform.reliability.reconcile() is True
        assert platform.reliability.report["verified"] is True
    finally:
        platform.close()
        adapter.close()

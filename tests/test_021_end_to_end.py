import gzip
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.broker.official021_http import Official021RESTAdapter
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick
from backend.shared.store import Store


INSTRUMENTS = (
    "token,exchange,underlying_token,underlying_exchange,min_lot_size,"
    "board_lot_quantity,freeze_quantity,lower_circuit,upper_circuit,expiry,"
    "option_type,strike_price,symbol,instrument_type,isin,ticksize\n"
    "2885,NSECM,2885,NSECM,0,1,1000,1,999999,0,,0,RELIANCE,STK,INE002A01018,5\n"
).encode()


def test_synthetic_complete_021_fixture_syncs_trade_before_terminal_fill(tmp_path):
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
        if path.endswith("/portfolio/holdings"):
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected fake 021 request: {request.method} {path}")

    class CompleteFake021(Official021RESTAdapter):
        def snapshot(self):
            # Synthetic fixture only: real 021 snapshots remain incomplete.
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

    try:
        platform.account("a")
        platform.strategies.subscribe("a", "fixture-momentum", "momentum", "RELIANCE")
        platform.tick(
            Tick("RELIANCE", int(now), Decimal("101"), 1, "fixture-market-tick")
        )
        assert platform.reliability.reconcile() is True
        platform.reliability.resume()
        assert platform.risk.submit(
            OrderIntent(
                "fixture-021-order",
                "fixture-momentum",
                "a",
                "RELIANCE",
                Side.BUY,
                1,
                now,
            )
        ).allowed
        order = store.rows("SELECT * FROM orders WHERE id='fixture-021-order'")[0]
        assert order["status"] == "OPEN"
        assert state["placed"] is True

        state["executed"] = True
        original_process = platform.process_broker_update
        platform.process_broker_update = lambda update: (_ for _ in ()).throw(
            RuntimeError("synthetic durable apply failure")
        )
        with pytest.raises(RuntimeError, match="synthetic durable apply failure"):
            platform.sync_broker_updates()
        # No acknowledgement occurs before a durable apply, so the provider
        # still offers the trade for retry.
        assert adapter.drain_updates()[0].fill.fill_id == "021:5001"

        platform.process_broker_update = original_process
        original_acknowledge = adapter.acknowledge_update
        acknowledgements = 0

        def fail_first_acknowledgement(update):
            nonlocal acknowledgements
            acknowledgements += 1
            if acknowledgements == 1:
                raise RuntimeError("synthetic acknowledgement failure")
            original_acknowledge(update)

        adapter.acknowledge_update = fail_first_acknowledgement
        with pytest.raises(RuntimeError, match="synthetic acknowledgement failure"):
            platform.sync_broker_updates()
        order = store.rows("SELECT * FROM orders WHERE id='fixture-021-order'")[0]
        assert order["status"] == "FILLED"
        assert order["filled"] == 1
        assert store.rows("SELECT id FROM fills")[0]["id"] == "021:5001"
        assert platform.ledger.aggregate() == {("a", "RELIANCE"): 1}
        # Replay after acknowledgement failure is financial-idempotent, then
        # the successful acknowledgement removes the provider retry evidence.
        assert platform.sync_broker_updates()[0].filled_quantity == 1
        assert platform.sync_broker_updates() == []
        assert platform.reliability.reconcile() is True
        assert platform.reliability.report["verified"] is True
    finally:
        platform.close()
        adapter.close()

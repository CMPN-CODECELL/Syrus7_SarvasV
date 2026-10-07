"""HTTP Mock Broker Adapter for AlgoShield PS-06 prototype.

Communicates with the standalone Mock Broker HTTP API (backend/broker/mock_api.py)
across the canonical BrokerAdapter protocol boundary.

IMPORTANT DISCLAIMER:
This adapter translates between AlgoShield canonical contracts and the prototype
Mock Broker HTTP API. It is NOT an implementation of the sponsor 021 broker API.
"""

from decimal import Decimal
import os
from typing import Any

import httpx

from backend.shared.contracts import (
    BrokerSnapshot,
    BrokerUpdate,
    BrokerUpdateType,
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    Side,
)


def _extract_detail(resp: httpx.Response, default: str) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("detail", default)
    except Exception:
        pass
    return default


class HTTPMockBrokerAdapter:
    """Adapts the external Mock Broker HTTP API to the BrokerAdapter protocol."""

    supports_virtual_closes = True

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 3.0,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        raw_url = base_url or os.getenv("MOCK_BROKER_URL", "http://127.0.0.1:9001")
        self.base_url = raw_url.rstrip("/")
        self.timeout = timeout
        if client is not None:
            self.client = client
            self._owns_client = False
        else:
            self.client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=transport,
            )
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    @property
    def connected(self) -> bool:
        try:
            resp = self.client.get(f"{self.base_url}/health")
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("connected", False))
        except Exception:
            return False
        return False

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        url = f"{self.base_url}{path}" if not path.startswith("http") else path
        try:
            resp = self.client.request(method, url, json=json)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"HTTP mock broker timeout: {exc}") from exc
        except httpx.NetworkError as exc:
            raise ConnectionError(f"HTTP mock broker connection error: {exc}") from exc
        except Exception as exc:
            raise ConnectionError(f"HTTP mock broker request error: {exc}") from exc

        if resp.status_code == 503:
            raise ConnectionError(_extract_detail(resp, "mock broker disconnected"))
        if resp.status_code == 504:
            raise TimeoutError(
                _extract_detail(resp, "mock broker timeout after acceptance")
            )
        if resp.status_code == 404:
            raise ValueError(_extract_detail(resp, "order not found at broker"))
        if resp.status_code == 409:
            raise ValueError(_extract_detail(resp, "invalid execution / conflict"))
        if resp.is_error:
            raise RuntimeError(
                f"HTTP mock broker error {resp.status_code}: {resp.text}"
            )
        return resp

    def submit(self, intent: OrderIntent) -> CanonicalOrder:
        payload = {
            "intent_id": intent.intent_id,
            "strategy_instance_id": intent.strategy_instance_id,
            "account_id": intent.account_id,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "limit_price": str(intent.limit_price) if intent.limit_price is not None else None,
            "created_at": intent.created_at,
        }
        resp = self._request("POST", "/orders", json=payload)
        data = resp.json()
        if (
            data.get("order_id") != intent.intent_id
            or data.get("intent_id") != intent.intent_id
        ):
            raise ValueError("broker response attribution mismatch")
        return CanonicalOrder(
            order_id=data["order_id"],
            intent=intent,
            status=OrderStatus(data["status"]),
            filled_quantity=data["filled_quantity"],
        )

    def cancel(self, order_id: str, timeout: float | None = None) -> None:
        self._request("POST", f"/orders/{order_id}/cancel")

    def snapshot(self) -> BrokerSnapshot:
        resp = self._request("GET", "/snapshot")
        data = resp.json()
        orders = []
        for row in data.get("orders", []):
            intent = OrderIntent(
                intent_id=row["intent_id"],
                strategy_instance_id=row["strategy_instance_id"],
                account_id=row["account_id"],
                symbol=row["symbol"],
                side=Side(row["side"]),
                quantity=row["quantity"],
                order_type=row.get("order_type", "MARKET"),
                created_at=row["created_at"],
                limit_price=(
                    Decimal(row["limit_price"])
                    if row.get("limit_price") is not None
                    else None
                ),
            )
            orders.append(
                CanonicalOrder(
                    order_id=row["order_id"],
                    intent=intent,
                    status=OrderStatus(row["status"]),
                    filled_quantity=row["filled_quantity"],
                )
            )

        fills = []
        for row in data.get("fills", []):
            fill = Fill(
                fill_id=row["fill_id"],
                broker_order_id=row["broker_order_id"],
                strategy_instance_id=row["strategy_instance_id"],
                account_id=row["account_id"],
                symbol=row["symbol"],
                side=Side(row["side"]),
                quantity=row["quantity"],
                price=Decimal(row["price"]),
                timestamp=row["timestamp"],
                charges=Decimal(row.get("charges", "0")),
            )
            fills.append(fill)

        positions = {
            (p["account_id"], p["symbol"]): p["quantity"]
            for p in data.get("positions", [])
        }

        return BrokerSnapshot(
            orders=tuple(orders),
            fills=tuple(fills),
            positions=positions,
            is_complete=bool(data.get("is_complete", False)),
            observed_at=data.get("observed_at"),
        )

    def execute(
        self,
        order_id: str,
        quantity: int,
        price: Decimal,
        timestamp: float,
        charges: Decimal = Decimal("0"),
        allow_late: bool = False,
    ) -> Fill:
        payload = {
            "quantity": quantity,
            "price": str(price),
            "charges": str(charges),
            "timestamp": timestamp,
            "allow_late": allow_late,
        }
        resp = self._request("POST", f"/orders/{order_id}/fills", json=payload)
        row = resp.json()
        return Fill(
            fill_id=row["fill_id"],
            broker_order_id=row["broker_order_id"],
            strategy_instance_id=row["strategy_instance_id"],
            account_id=row["account_id"],
            symbol=row["symbol"],
            side=Side(row["side"]),
            quantity=row["quantity"],
            price=Decimal(row["price"]),
            timestamp=row["timestamp"],
            charges=Decimal(row.get("charges", "0")),
        )

    @property
    def reject_next(self) -> bool:
        return False

    @reject_next.setter
    def reject_next(self, value: bool) -> None:
        if value:
            self._request("POST", "/mock/reject-next")

    @property
    def timeout_after_accept(self) -> bool:
        return False

    @timeout_after_accept.setter
    def timeout_after_accept(self, value: bool) -> None:
        if value:
            self._request("POST", "/mock/timeout-after-accept")

    @property
    def orders(self) -> dict[str, CanonicalOrder]:
        return {o.order_id: o for o in self.snapshot().orders}

    @property
    def fills(self) -> dict[str, Fill]:
        return {f.fill_id: f for f in self.snapshot().fills}

    def drain_updates(self) -> list[BrokerUpdate]:
        resp = self._request("POST", "/updates/drain")
        data = resp.json()
        updates = []
        for u in data:
            fill = None
            if u.get("fill") is not None:
                f_row = u["fill"]
                fill = Fill(
                    fill_id=f_row["fill_id"],
                    broker_order_id=f_row["broker_order_id"],
                    strategy_instance_id=f_row["strategy_instance_id"],
                    account_id=f_row["account_id"],
                    symbol=f_row["symbol"],
                    side=Side(f_row["side"]),
                    quantity=f_row["quantity"],
                    price=Decimal(f_row["price"]),
                    timestamp=f_row["timestamp"],
                    charges=Decimal(f_row.get("charges", "0")),
                )
            update = BrokerUpdate(
                update_id=u["update_id"],
                order_id=u["order_id"],
                update_type=BrokerUpdateType(u["update_type"]),
                status=OrderStatus(u["status"]) if u.get("status") else None,
                fill=fill,
                timestamp=u.get("timestamp", 0.0),
            )
            updates.append(update)
        return updates

    def disconnect(self) -> None:
        """Prototype mock-only control: disconnects mock broker via POST /mock/disconnect."""
        self._request("POST", "/mock/disconnect")

    def reconnect(self) -> None:
        """Prototype mock-only control: reconnects mock broker via POST /mock/reconnect."""
        self._request("POST", "/mock/reconnect")


class MockBrokerControlClient:
    """Helper client for mock broker failure injection and testing controls."""

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        raw_url = base_url or os.getenv("MOCK_BROKER_URL", "http://127.0.0.1:9001")
        self.base_url = raw_url.rstrip("/")
        if client is not None:
            self.client = client
        else:
            self.client = httpx.Client(
                base_url=self.base_url,
                transport=transport,
            )

    def reject_next(self) -> bool:
        resp = self.client.post(f"{self.base_url}/mock/reject-next")
        resp.raise_for_status()
        return bool(resp.json().get("reject_next", False))

    def timeout_after_accept(self) -> bool:
        resp = self.client.post(f"{self.base_url}/mock/timeout-after-accept")
        resp.raise_for_status()
        return bool(resp.json().get("timeout_after_accept", False))

    def disconnect(self) -> bool:
        resp = self.client.post(f"{self.base_url}/mock/disconnect")
        resp.raise_for_status()
        return not resp.json().get("connected", True)

    def reconnect(self) -> bool:
        resp = self.client.post(f"{self.base_url}/mock/reconnect")
        resp.raise_for_status()
        return bool(resp.json().get("connected", False))

    def external_fill(
        self,
        order_id: str,
        quantity: int,
        price: Decimal | str | float,
        charges: Decimal | str | float = "0",
        timestamp: float | None = None,
        allow_late: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "quantity": quantity,
            "price": str(price),
            "charges": str(charges),
            "timestamp": timestamp,
            "allow_late": allow_late,
        }
        resp = self.client.post(
            f"{self.base_url}/mock/orders/{order_id}/external-fill",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def fill(
        self,
        order_id: str,
        quantity: int,
        price: Decimal | str | float,
        charges: Decimal | str | float = "0",
        timestamp: float | None = None,
        allow_late: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "quantity": quantity,
            "price": str(price),
            "charges": str(charges),
            "timestamp": timestamp,
            "allow_late": allow_late,
        }
        resp = self.client.post(
            f"{self.base_url}/orders/{order_id}/fills",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def reset(self) -> bool:
        resp = self.client.post(f"{self.base_url}/mock/reset")
        resp.raise_for_status()
        return bool(resp.json().get("reset", False))

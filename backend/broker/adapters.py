from dataclasses import replace
from decimal import Decimal
from typing import Protocol

from backend.shared.contracts import (
    BrokerSnapshot,
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    TERMINAL,
)


class BrokerAdapter(Protocol):
    def submit(self, intent: OrderIntent) -> CanonicalOrder: ...
    def cancel(self, order_id: str) -> None: ...
    def snapshot(self) -> BrokerSnapshot: ...


class MockBrokerAdapter:
    """External mock state survives Platform recreation if this object is retained."""

    def __init__(self):
        self.orders = {}
        self.fills = {}
        self.external_positions = {}
        self.connected = True
        self.reject_next = False
        self.timeout_after_accept = False

    def _check(self):
        if not self.connected:
            raise ConnectionError("mock broker disconnected")

    def submit(self, intent):
        self._check()
        if intent.intent_id in self.orders:
            return self.orders[intent.intent_id]
        status = OrderStatus.REJECTED if self.reject_next else OrderStatus.OPEN
        self.reject_next = False
        order = CanonicalOrder(intent.intent_id, intent, status)
        self.orders[order.order_id] = order
        if self.timeout_after_accept:
            self.timeout_after_accept = False
            raise TimeoutError("acceptance is ambiguous to caller")
        return order

    def execute(self, order_id, quantity, price, timestamp, charges=Decimal(0)):
        self._check()
        order = self.orders[order_id]
        if order.status in TERMINAL or not 0 < quantity <= order.remaining_quantity:
            raise ValueError("order cannot execute this quantity")
        if price <= 0 or charges < 0:
            raise ValueError("invalid execution price/charges")
        intent = order.intent
        fill = Fill(
            f"{order_id}:{order.filled_quantity + quantity}",
            order_id,
            intent.strategy_instance_id,
            intent.account_id,
            intent.symbol,
            intent.side,
            quantity,
            price,
            timestamp,
            charges,
        )
        self.fills[fill.fill_id] = fill
        filled = order.filled_quantity + quantity
        self.orders[order_id] = replace(
            order,
            filled_quantity=filled,
            status=OrderStatus.FILLED
            if filled == intent.quantity
            else OrderStatus.PARTIALLY_FILLED,
        )
        return fill

    def cancel(self, order_id):
        self._check()
        order = self.orders[order_id]
        if order.status not in TERMINAL:
            self.orders[order_id] = replace(order, status=OrderStatus.CANCELLED)

    def snapshot(self):
        self._check()
        positions = dict(self.external_positions)
        for fill in self.fills.values():
            key = (fill.account_id, fill.symbol)
            positions[key] = positions.get(key, 0) + fill.side.sign * fill.quantity
        return BrokerSnapshot(
            tuple(self.orders.values()),
            tuple(self.fills.values()),
            {k: v for k, v in positions.items() if v},
        )


class Broker021Adapter:
    def __init__(self):
        raise NotImplementedError(
            "021 contract/credentials unconfirmed; see docs/021_API_UNKNOWN.md"
        )

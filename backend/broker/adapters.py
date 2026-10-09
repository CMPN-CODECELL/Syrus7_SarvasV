from dataclasses import replace
from decimal import Decimal
from typing import Protocol

from backend.broker.mock_persistence import MockPersistence

from backend.shared.contracts import (
    BrokerSnapshot,
    BrokerUpdate,
    BrokerUpdateType,
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    TERMINAL,
)
from backend.broker.official021 import Provider021Blocked, parse_order_frame
from backend.broker.official021_http import Official021RESTAdapter


class BrokerAdapter(Protocol):
    def submit(self, intent: OrderIntent) -> CanonicalOrder: ...
    def cancel(self, order_id: str) -> None: ...
    def snapshot(self) -> BrokerSnapshot: ...
    def drain_updates(self) -> list[BrokerUpdate]: ...
    def disconnect(self) -> None: ...
    def reconnect(self) -> None: ...


class MockBrokerAdapter:
    """External mock state survives Platform recreation if this object is retained."""

    supports_virtual_closes = True

    def __init__(self, path=None):
        self.persistence = MockPersistence(path)
        self.orders, self.fills, self.external_positions = self.persistence.load()
        self.connected = True
        self.reject_next = False
        self.timeout_after_accept = False
        self.updates: list[BrokerUpdate] = []

    def disconnect(self):
        self.connected = False

    def reconnect(self):
        self.connected = True

    def _check(self):
        if not self.connected:
            raise ConnectionError("mock broker disconnected")

    def submit(self, intent):
        self._check()
        if intent.intent_id in self.orders:
            existing = self.orders[intent.intent_id]
            if existing.intent != intent:
                raise ValueError("order identity collision")
            return existing
        status = OrderStatus.REJECTED if self.reject_next else OrderStatus.OPEN
        self.reject_next = False
        order = CanonicalOrder(intent.intent_id, intent, status)
        self.orders[order.order_id] = order
        self.persist()
        self.updates.append(
            BrokerUpdate(
                update_id=f"upd-submit-{order.order_id}",
                order_id=order.order_id,
                update_type=(
                    BrokerUpdateType.ORDER_REJECTED
                    if status == OrderStatus.REJECTED
                    else BrokerUpdateType.ORDER_ACCEPTED
                ),
                status=status,
                timestamp=intent.created_at,
            )
        )
        if self.timeout_after_accept:
            self.timeout_after_accept = False
            raise TimeoutError("acceptance is ambiguous to caller")
        return order

    def _execute_internal(
        self,
        order_id,
        quantity,
        price,
        timestamp,
        charges=Decimal(0),
        allow_late=False,
    ):
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found at broker")
        if (
            (order.status in {OrderStatus.FILLED, OrderStatus.REJECTED})
            or (order.status == OrderStatus.CANCELLED and not allow_late)
            or not 0 < quantity <= order.remaining_quantity
        ):
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
        status = (
            OrderStatus.FILLED
            if filled == intent.quantity
            else (
                OrderStatus.CANCELLED
                if order.status == OrderStatus.CANCELLED
                else OrderStatus.PARTIALLY_FILLED
            )
        )
        self.orders[order_id] = replace(
            order,
            filled_quantity=filled,
            status=status,
        )
        self.persist()
        self.updates.append(
            BrokerUpdate(
                update_id=f"upd-fill-{fill.fill_id}",
                order_id=order_id,
                update_type=BrokerUpdateType.FILL,
                status=status,
                fill=fill,
                timestamp=timestamp,
            )
        )
        return fill

    def execute(
        self,
        order_id,
        quantity,
        price,
        timestamp,
        charges=Decimal(0),
        allow_late=False,
    ):
        self._check()
        return self._execute_internal(
            order_id,
            quantity,
            price,
            timestamp,
            charges=charges,
            allow_late=allow_late,
        )

    def execute_external(
        self,
        order_id,
        quantity,
        price,
        timestamp,
        charges=Decimal(0),
        allow_late=False,
    ):
        """Simulate broker-side execution while normal client connection is marked disconnected."""
        return self._execute_internal(
            order_id,
            quantity,
            price,
            timestamp,
            charges=charges,
            allow_late=allow_late,
        )

    def reset(self):
        """Reset mock broker state, queued updates, failure flags, and persistence."""
        self.orders.clear()
        self.fills.clear()
        self.external_positions.clear()
        self.updates.clear()
        self.reject_next = False
        self.timeout_after_accept = False
        self.connected = True
        self.persist()

    def cancel(self, order_id, timeout=None):
        self._check()
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found at broker")
        if order.status not in TERMINAL:
            self.orders[order_id] = replace(order, status=OrderStatus.CANCELLED)
            self.persist()
            self.updates.append(
                BrokerUpdate(
                    update_id=f"upd-cancel-{order_id}",
                    order_id=order_id,
                    update_type=BrokerUpdateType.ORDER_CANCELLED,
                    status=OrderStatus.CANCELLED,
                    timestamp=order.intent.created_at,
                )
            )

    def drain_updates(self) -> list[BrokerUpdate]:
        updates = list(self.updates)
        self.updates.clear()
        return updates

    def emit_update(self, update: BrokerUpdate) -> None:
        self.updates.append(update)

    def persist(self):
        self.persistence.save(self.orders, self.fills, self.external_positions)

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
            is_complete=True,
        )


class Broker021Adapter(Official021RESTAdapter):
    """Documented 021 REST adapter, fail-closed unless explicitly enabled."""

    def __init__(self, store=None, *, enabled=False, **kwargs):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.connected = False
            self.updates = []
            self.store = store
            return
        if store is None:
            raise ValueError("enabled 021 adapter requires the application store")
        super().__init__(store, **kwargs)

    def _require_enabled(self):
        if not self.enabled:
            raise Provider021Blocked(
                "021 live operations are disabled; set ALGOSHIELD_021_ENABLED=true"
            )

    def submit(self, intent: OrderIntent) -> CanonicalOrder:
        self._require_enabled()
        return super().submit(intent)

    def cancel(self, order_id: str, timeout=None) -> None:
        self._require_enabled()
        return super().cancel(order_id, timeout=timeout)

    def snapshot(self) -> BrokerSnapshot:
        self._require_enabled()
        return super().snapshot()

    def drain_updates(self) -> list[BrokerUpdate]:
        if not self.enabled:
            return []
        return super().drain_updates()

    def reconnect(self) -> None:
        self._require_enabled()
        return super().reconnect()

    def ephemeral_key(self) -> str:
        self._require_enabled()
        return super().ephemeral_key()

    def close(self) -> None:
        if self.enabled:
            super().close()

    def parse_update(self, raw_payload: bytes):
        """Decode order evidence without inventing a Fill/trade ID.

        TC4/TC8 status 1 remains provider evidence only.  It cannot become a
        canonical Fill until GET /orders/{orderId}/trades supplies a scoped,
        verifiable tradeId and cumulative quantity matches.
        """
        return parse_order_frame(raw_payload)

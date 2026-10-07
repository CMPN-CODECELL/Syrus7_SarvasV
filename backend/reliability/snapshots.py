"""Verify complete canonical broker evidence before importing any financial events."""

from math import isfinite

from backend.shared.contracts import OrderStatus, TERMINAL


class SnapshotError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def verify_snapshot(store, snapshot, now, max_age=5):
    if snapshot.is_complete is not True:
        raise SnapshotError("SNAPSHOT_INCOMPLETE")
    observed_at = now if snapshot.observed_at is None else snapshot.observed_at
    if not isfinite(observed_at) or not -1 <= now - observed_at <= max_age:
        raise SnapshotError("SNAPSHOT_STALE")
    local = {r["id"]: r for r in store.rows("SELECT * FROM orders")}
    orders = {}
    for order in snapshot.orders:
        if order.order_id in orders:
            raise SnapshotError("DUPLICATE_BROKER_ORDER")
        orders[order.order_id] = order
        row = local.get(order.order_id)
        if row is None:
            raise SnapshotError("UNKNOWN_BROKER_ORDER")
        i = order.intent
        if order.status not in set(OrderStatus):
            raise SnapshotError("INVALID_BROKER_STATUS")
        if (
            row["strategy"],
            row["account"],
            row["symbol"],
            row["side"],
            row["quantity"],
            row["id"],
        ) != (
            i.strategy_instance_id,
            i.account_id,
            i.symbol,
            i.side.value,
            i.quantity,
            i.intent_id,
        ):
            raise SnapshotError("ORDER_IDENTITY_MISMATCH")
        if order.status in {OrderStatus.UNKNOWN, OrderStatus.RESERVED}:
            raise SnapshotError("BROKER_ORDER_UNCERTAIN")
        if (
            type(order.filled_quantity) is not int
            or not 0 <= order.filled_quantity <= i.quantity
        ):
            raise SnapshotError("INVALID_CUMULATIVE_QUANTITY")
        if order.status == OrderStatus.FILLED and order.filled_quantity != i.quantity:
            raise SnapshotError("FILLED_WITHOUT_EVIDENCE")
        if (
            order.status == OrderStatus.PARTIALLY_FILLED
            and not 0 < order.filled_quantity < i.quantity
        ):
            raise SnapshotError("INVALID_PARTIAL_STATUS")
        if (
            order.status in {OrderStatus.OPEN, OrderStatus.REJECTED}
            and order.filled_quantity
        ):
            raise SnapshotError("INVALID_ORDER_STATUS")
        if row["status"] in TERMINAL and order.status != row["status"]:
            if not (
                row["status"] == OrderStatus.CANCELLED
                and order.status == OrderStatus.FILLED
            ):
                raise SnapshotError("TERMINAL_STATUS_REGRESSION")
    for oid in set(local) - set(orders):
        row = local[oid]
        if row["filled"] or not (
            row["status"] == OrderStatus.UNKNOWN
            or (
                not row["dispatch_started"]
                and row["status"] in {OrderStatus.RESERVED, OrderStatus.REJECTED}
            )
        ):
            raise SnapshotError("LOCAL_ORDER_MISSING_AT_BROKER")
    fills = {}
    duplicates = 0
    totals = {}
    positions = {}
    for fill in snapshot.fills:
        previous = fills.get(fill.fill_id)
        if previous is not None:
            if previous != fill:
                raise SnapshotError("CONFLICTING_BROKER_FILL")
            duplicates += 1
            continue
        order = orders.get(fill.broker_order_id)
        if order is None:
            raise SnapshotError("UNATTRIBUTED_BROKER_FILL")
        i = order.intent
        if (fill.strategy_instance_id, fill.account_id, fill.symbol, fill.side) != (
            i.strategy_instance_id,
            i.account_id,
            i.symbol,
            i.side,
        ):
            raise SnapshotError("FILL_ATTRIBUTION_MISMATCH")
        fills[fill.fill_id] = fill
        totals[fill.broker_order_id] = (
            totals.get(fill.broker_order_id, 0) + fill.quantity
        )
        key = (fill.account_id, fill.symbol)
        positions[key] = positions.get(key, 0) + fill.side.sign * fill.quantity
    for oid, order in orders.items():
        if totals.get(oid, 0) != order.filled_quantity:
            raise SnapshotError("CUMULATIVE_FILL_MISMATCH")
    if {r["id"] for r in store.rows("SELECT id FROM fills")} - set(fills):
        raise SnapshotError("LOCAL_FILL_MISSING_AT_BROKER")
    normalized = {}
    for key, quantity in snapshot.positions.items():
        if not isinstance(key, tuple) or len(key) != 2 or type(quantity) is not int:
            raise SnapshotError("INVALID_BROKER_POSITION")
        if quantity:
            normalized[key] = quantity
    if {k: q for k, q in positions.items() if q} != normalized:
        raise SnapshotError("UNEXPLAINED_EXTERNAL_POSITION")
    return orders, fills, observed_at, duplicates

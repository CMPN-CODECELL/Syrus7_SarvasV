from backend.shared.contracts import OrderStatus


class SubmissionBlocked(ValueError):
    pass


class IllegalOrderTransition(ValueError):
    """Raised when an order transition violates execution state machine invariants."""

    pass


LEGAL_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.RESERVED: {
        OrderStatus.RESERVED,
        OrderStatus.UNKNOWN,
        OrderStatus.REJECTED,
    },
    OrderStatus.UNKNOWN: {
        OrderStatus.UNKNOWN,
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.OPEN: {
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CANCELLED: {
        OrderStatus.CANCELLED,
        OrderStatus.FILLED,
    },
    OrderStatus.FILLED: {
        OrderStatus.FILLED,
    },
    OrderStatus.REJECTED: {
        OrderStatus.REJECTED,
    },
}


def validate_order_transition(
    current_status: OrderStatus | str,
    target_status: OrderStatus | str,
    current_filled: int = 0,
    target_filled: int = 0,
    order_quantity: int = 0,
) -> None:
    try:
        current = OrderStatus(current_status)
    except ValueError:
        raise IllegalOrderTransition(f"invalid current OrderStatus: {current_status}")
    try:
        target = OrderStatus(target_status)
    except ValueError:
        raise IllegalOrderTransition(f"invalid target OrderStatus: {target_status}")

    if type(order_quantity) is not int or order_quantity <= 0:
        raise ValueError("order_quantity must be a positive integer")
    if (
        type(current_filled) is not int
        or current_filled < 0
        or current_filled > order_quantity
    ):
        raise ValueError("invalid current_filled quantity")
    if (
        type(target_filled) is not int
        or target_filled < 0
        or target_filled > order_quantity
    ):
        raise ValueError("invalid target_filled quantity")

    allowed = LEGAL_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise IllegalOrderTransition(
            f"illegal order state transition: {current.value} -> {target.value}"
        )

    if target_filled < current_filled:
        raise IllegalOrderTransition(
            f"filled quantity cannot decrease: {current_filled} -> {target_filled}"
        )

    if target == OrderStatus.FILLED and target_filled != order_quantity:
        raise IllegalOrderTransition(
            f"FILLED status requires cumulative executed quantity == order_quantity ({target_filled} != {order_quantity})"
        )
    if target == OrderStatus.PARTIALLY_FILLED and not (
        0 < target_filled < order_quantity
    ):
        raise IllegalOrderTransition(
            f"PARTIALLY_FILLED status requires 0 < filled_quantity < order_quantity ({target_filled}/{order_quantity})"
        )
    if (
        target in {OrderStatus.OPEN, OrderStatus.RESERVED, OrderStatus.REJECTED}
        and target_filled != 0
    ):
        raise IllegalOrderTransition(
            f"{target.value} status requires filled_quantity == 0 (got {target_filled})"
        )
    if target == OrderStatus.CANCELLED and target_filled == order_quantity:
        raise IllegalOrderTransition(
            f"fully filled order cannot remain CANCELLED (target_filled == {order_quantity})"
        )


class OrderManager:
    def __init__(self, store, broker, ledger):
        self.store, self.broker, self.ledger = store, broker, ledger
        self.authorize_dispatch = lambda intent, row: False

    def submit_reserved(self, intent, timeout=None):
        with self.store.lock:
            call = self._start_reserved(intent)
        try:
            order = self.broker.wait(call, timeout)
        except Exception:
            with self.store.transaction():
                self.store.audit("SUBMISSION_UNKNOWN", {"order_id": intent.intent_id})
            raise
        if order.order_id != intent.intent_id or order.intent != intent:
            raise ValueError("broker response attribution mismatch")
        if (
            order.status not in {OrderStatus.OPEN, OrderStatus.REJECTED}
            or order.filled_quantity != 0
        ):
            raise ValueError("submission response requires execution reconciliation")
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM orders WHERE id=?", (intent.intent_id,)
            ).fetchone()
            if not row:
                raise ValueError("order missing")
            current_status = OrderStatus(row["status"])
            target_status = OrderStatus(order.status)
            validate_order_transition(
                current_status,
                target_status,
                current_filled=row["filled"],
                target_filled=order.filled_quantity,
                order_quantity=row["quantity"],
            )
            db.execute(
                "UPDATE orders SET status=? WHERE id=? AND status=? AND filled=0",
                (target_status.value, intent.intent_id, OrderStatus.UNKNOWN.value),
            )
            self.store.audit(
                "ORDER_SUBMITTED",
                {"order_id": intent.intent_id, "status": target_status.value},
            )
            if target_status != current_status:
                self.store.audit(
                    "ORDER_STATUS_CHANGED",
                    {
                        "order_id": intent.intent_id,
                        "previous_status": current_status.value,
                        "status": target_status.value,
                        "filled": row["filled"],
                        "quantity": row["quantity"],
                    },
                )
        return order

    def _start_reserved(self, intent):
        rows = self.store.rows("SELECT * FROM orders WHERE id=?", (intent.intent_id,))
        if not rows or rows[0]["status"] != OrderStatus.RESERVED.value:
            raise ValueError("no approved reservation")
        row = rows[0]
        if (
            row["strategy"],
            row["account"],
            row["symbol"],
            row["side"],
            row["quantity"],
        ) != (
            intent.strategy_instance_id,
            intent.account_id,
            intent.symbol,
            intent.side.value,
            intent.quantity,
        ):
            raise ValueError("intent does not match approved reservation")
        if not self.authorize_dispatch(intent, row):
            validate_order_transition(
                OrderStatus.RESERVED,
                OrderStatus.REJECTED,
                current_filled=row["filled"],
                target_filled=row["filled"],
                order_quantity=row["quantity"],
            )
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE orders SET status=? WHERE id=?",
                    (OrderStatus.REJECTED.value, intent.intent_id),
                )
                self.store.audit("DISPATCH_BLOCKED", {"order_id": intent.intent_id})
                self.store.audit(
                    "ORDER_STATUS_CHANGED",
                    {
                        "order_id": intent.intent_id,
                        "previous_status": OrderStatus.RESERVED.value,
                        "status": OrderStatus.REJECTED.value,
                        "filled": row["filled"],
                        "quantity": row["quantity"],
                    },
                )
            raise SubmissionBlocked("execution gate closed before dispatch")
        validate_order_transition(
            OrderStatus.RESERVED,
            OrderStatus.UNKNOWN,
            current_filled=row["filled"],
            target_filled=row["filled"],
            order_quantity=row["quantity"],
        )
        with self.store.transaction() as db:
            db.execute(
                "UPDATE orders SET status=?,dispatch_started=1 WHERE id=?",
                (OrderStatus.UNKNOWN.value, intent.intent_id),
            )
            self.store.audit(
                "ORDER_STATUS_CHANGED",
                {
                    "order_id": intent.intent_id,
                    "previous_status": OrderStatus.RESERVED.value,
                    "status": OrderStatus.UNKNOWN.value,
                    "filled": row["filled"],
                    "quantity": row["quantity"],
                },
            )
        return self.broker.start("submit", intent)

    def ingest(self, fill):
        with self.store.transaction():
            return self._ingest_locked(fill)

    def _ingest_locked(self, fill):
        if fill.quantity <= 0:
            raise ValueError("invalid fill quantity")
        rows = self.store.rows(
            "SELECT * FROM orders WHERE id=?", (fill.broker_order_id,)
        )
        if not rows:
            self.store.audit(
                "UNATTRIBUTED_FILL_REJECTED",
                {"fill_id": fill.fill_id, "broker_order_id": fill.broker_order_id},
            )
            raise ValueError("unattributed execution")
        o = rows[0]
        if (o["strategy"], o["account"], o["symbol"], o["side"]) != (
            fill.strategy_instance_id,
            fill.account_id,
            fill.symbol,
            fill.side.value,
        ):
            self.store.audit(
                "FILL_ATTRIBUTION_MISMATCH",
                {
                    "fill_id": fill.fill_id,
                    "broker_order_id": fill.broker_order_id,
                    "expected": {
                        "strategy": o["strategy"],
                        "account": o["account"],
                        "symbol": o["symbol"],
                        "side": o["side"],
                    },
                    "received": {
                        "strategy": fill.strategy_instance_id,
                        "account": fill.account_id,
                        "symbol": fill.symbol,
                        "side": fill.side.value,
                    },
                },
            )
            raise ValueError("fill attribution mismatch")

        current_status = OrderStatus(o["status"])
        if current_status == OrderStatus.REJECTED:
            self.store.audit(
                "EXECUTION_ON_REJECTED_ORDER",
                {"fill_id": fill.fill_id, "order_id": o["id"]},
            )
            raise ValueError("cannot ingest fill for rejected order")
        if current_status == OrderStatus.RESERVED:
            self.store.audit(
                "EXECUTION_ON_UNDISPATCHED_ORDER",
                {"fill_id": fill.fill_id, "order_id": o["id"]},
            )
            raise ValueError("cannot ingest fill for undispatched order")

        with self.store.transaction() as db:
            prior = db.execute(
                "SELECT id FROM fills WHERE id=?", (fill.fill_id,)
            ).fetchone()
            if not prior and o["filled"] + fill.quantity > o["quantity"]:
                self.store.audit(
                    "OVERFILL_REJECTED",
                    {
                        "fill_id": fill.fill_id,
                        "order_id": o["id"],
                        "current_filled": o["filled"],
                        "fill_quantity": fill.quantity,
                        "order_quantity": o["quantity"],
                    },
                )
                raise ValueError("overfill")

            applied = self.ledger.apply(fill)
            if not applied:
                self.store.audit("DUPLICATE_FILL_IGNORED", {"fill_id": fill.fill_id})
            if applied:
                filled = o["filled"] + fill.quantity
                if filled == o["quantity"]:
                    target_status = OrderStatus.FILLED
                elif current_status == OrderStatus.CANCELLED:
                    target_status = OrderStatus.CANCELLED
                else:
                    target_status = OrderStatus.PARTIALLY_FILLED

                validate_order_transition(
                    current_status,
                    target_status,
                    current_filled=o["filled"],
                    target_filled=filled,
                    order_quantity=o["quantity"],
                )
                db.execute(
                    "UPDATE orders SET filled=?,status=? WHERE id=?",
                    (filled, target_status.value, o["id"]),
                )
                self.store.audit(
                    "ORDER_STATUS_CHANGED",
                    {
                        "order_id": o["id"],
                        "previous_status": current_status.value,
                        "status": target_status.value,
                        "filled": filled,
                        "quantity": o["quantity"],
                    },
                )
                if current_status == OrderStatus.CANCELLED:
                    self.store.audit(
                        "LATE_FILL_ON_CANCELLED",
                        {
                            "order_id": o["id"],
                            "fill_id": fill.fill_id,
                            "filled": filled,
                            "status": target_status.value,
                        },
                    )
            return applied

    def transition_status(
        self,
        order_id: str,
        target_status: OrderStatus | str,
        target_filled: int | None = None,
    ) -> OrderStatus:
        """Authoritatively validate and transition order state."""
        target = OrderStatus(target_status)
        with self.store.transaction() as db:
            rows = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchall()
            if not rows:
                raise ValueError(f"order {order_id} not found")
            o = rows[0]
            current_status = OrderStatus(o["status"])
            current_filled = o["filled"]
            new_filled = current_filled if target_filled is None else target_filled
            order_qty = o["quantity"]

            validate_order_transition(
                current_status,
                target,
                current_filled=current_filled,
                target_filled=new_filled,
                order_quantity=order_qty,
            )

            if target != current_status or new_filled != current_filled:
                db.execute(
                    "UPDATE orders SET status=?, filled=? WHERE id=?",
                    (target.value, new_filled, order_id),
                )
                self.store.audit(
                    "ORDER_STATUS_CHANGED",
                    {
                        "order_id": order_id,
                        "previous_status": current_status.value,
                        "status": target.value,
                        "filled": new_filled,
                        "quantity": order_qty,
                    },
                )
            return target

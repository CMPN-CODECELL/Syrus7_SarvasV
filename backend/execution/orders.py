from backend.shared.contracts import (
    BrokerUpdate,
    BrokerUpdateType,
    CanonicalOrder,
    OrderIntent,
    OrderStatus,
    Side,
)


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

    def _row_to_canonical(self, row) -> CanonicalOrder:
        intent = OrderIntent(
            intent_id=row["id"],
            strategy_instance_id=row["strategy"],
            account_id=row["account"],
            symbol=row["symbol"],
            side=Side(row["side"]),
            quantity=row["quantity"],
            created_at=row["created"],
        )
        return CanonicalOrder(
            order_id=row["id"],
            intent=intent,
            status=OrderStatus(row["status"]),
            filled_quantity=row["filled"],
        )

    def cancel(self, order_id: str, timeout: float | None = None) -> CanonicalOrder:
        """Cancel an open or partially filled order with broker confirmation and state validation."""
        with self.store.lock:
            rows = self.store.rows("SELECT * FROM orders WHERE id=?", (order_id,))
            if not rows:
                raise ValueError(f"order {order_id} not found")
            row = rows[0]
            current_status = OrderStatus(row["status"])
            filled = row["filled"]
            quantity = row["quantity"]

            # Terminal states cannot be cancelled
            if current_status in {
                OrderStatus.FILLED,
                OrderStatus.REJECTED,
                OrderStatus.CANCELLED,
            }:
                return self._row_to_canonical(row)

            # Undispatched reservation: reject locally without calling broker
            if current_status == OrderStatus.RESERVED:
                self.transition_status(order_id, OrderStatus.REJECTED)
                updated_row = self.store.rows(
                    "SELECT * FROM orders WHERE id=?", (order_id,)
                )[0]
                return self._row_to_canonical(updated_row)

            # UNKNOWN state is uncertain; cannot assume broker state
            if current_status == OrderStatus.UNKNOWN:
                raise ValueError(
                    f"order {order_id} is in UNKNOWN state; reconciliation required before cancellation"
                )

            # Order is OPEN or PARTIALLY_FILLED
            self.store.audit(
                "ORDER_CANCEL_REQUESTED",
                {
                    "order_id": order_id,
                    "status": current_status.value,
                    "filled": filled,
                    "remaining": quantity - filled,
                },
            )

        # Call broker adapter outside store lock using bounded mechanism
        try:
            if hasattr(self.broker, "start") and hasattr(self.broker, "wait"):
                call = self.broker.start("cancel", order_id)
                self.broker.wait(call, timeout=timeout)
            elif hasattr(self.broker, "cancel"):
                try:
                    self.broker.cancel(order_id, timeout=timeout)
                except TypeError:
                    self.broker.cancel(order_id)
            else:
                raise ValueError("broker does not support cancellation")
        except Exception:
            with self.store.transaction():
                self.store.audit("ORDER_CANCEL_FAILED", {"order_id": order_id})
            raise

        # Verify broker state if accessible
        adapter = getattr(self.broker, "adapter", self.broker)
        broker_orders = getattr(adapter, "orders", None)
        if isinstance(broker_orders, dict) and order_id in broker_orders:
            bo = broker_orders[order_id]
            if bo.status not in {OrderStatus.CANCELLED, OrderStatus.FILLED}:
                with self.store.transaction():
                    self.store.audit(
                        "ORDER_CANCEL_FAILED",
                        {
                            "order_id": order_id,
                            "reason": "UNCONFIRMED_BROKER_STATUS",
                            "broker_status": bo.status.value,
                        },
                    )
                raise RuntimeError(
                    f"broker order {order_id} status is {bo.status.value}, cancellation not confirmed"
                )

        # Confirm cancellation and update local state
        with self.store.lock:
            fresh_rows = self.store.rows("SELECT * FROM orders WHERE id=?", (order_id,))
            fresh = fresh_rows[0]
            fresh_status = OrderStatus(fresh["status"])
            fresh_filled = fresh["filled"]

            # If order was filled by a racing fill while cancel was in flight, do not regress FILLED
            if fresh_status == OrderStatus.FILLED:
                return self._row_to_canonical(fresh)

            self.transition_status(order_id, OrderStatus.CANCELLED)

            with self.store.transaction():
                self.store.audit(
                    "ORDER_CANCELLED",
                    {
                        "order_id": order_id,
                        "previous_status": fresh_status.value,
                        "filled": fresh_filled,
                        "cancelled_quantity": fresh["quantity"] - fresh_filled,
                    },
                )
            final_row = self.store.rows("SELECT * FROM orders WHERE id=?", (order_id,))[
                0
            ]
            return self._row_to_canonical(final_row)

    def process_broker_update(self, update: BrokerUpdate) -> CanonicalOrder:
        """Process a canonical broker update (status or fill) with validation and state transition."""
        if not isinstance(update, BrokerUpdate):
            raise ValueError("invalid broker update")

        with self.store.transaction():
            self.store.audit(
                "BROKER_UPDATE_RECEIVED",
                {
                    "update_id": update.update_id,
                    "order_id": update.order_id,
                    "type": update.update_type.value,
                    "status": update.status.value if update.status else None,
                    "has_fill": update.fill is not None,
                },
            )

        if update.update_type == BrokerUpdateType.FILL:
            if update.fill is None:
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_UPDATE_REJECTED",
                        {
                            "update_id": update.update_id,
                            "order_id": update.order_id,
                            "reason": "MISSING_FILL",
                        },
                    )
                raise ValueError("fill missing in FILL update")
            try:
                applied = self.ingest(update.fill)
            except Exception as exc:
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_UPDATE_REJECTED",
                        {
                            "update_id": update.update_id,
                            "order_id": update.order_id,
                            "reason": str(exc),
                        },
                    )
                raise

            with self.store.transaction():
                self.store.audit(
                    "BROKER_UPDATE_APPLIED",
                    {
                        "update_id": update.update_id,
                        "order_id": update.order_id,
                        "type": update.update_type.value,
                        "fill_id": update.fill.fill_id,
                        "applied": applied,
                    },
                )
            row = self.store.rows(
                "SELECT * FROM orders WHERE id=?", (update.order_id,)
            )[0]
            return self._row_to_canonical(row)

        # Status update: ORDER_ACCEPTED, ORDER_REJECTED, ORDER_CANCELLED, ORDER_STATUS
        target_status = update.status
        if update.update_type == BrokerUpdateType.ORDER_ACCEPTED:
            target_status = OrderStatus.OPEN
        elif update.update_type == BrokerUpdateType.ORDER_REJECTED:
            target_status = OrderStatus.REJECTED
        elif update.update_type == BrokerUpdateType.ORDER_CANCELLED:
            target_status = OrderStatus.CANCELLED

        if target_status is None:
            with self.store.transaction():
                self.store.audit(
                    "BROKER_UPDATE_REJECTED",
                    {
                        "update_id": update.update_id,
                        "order_id": update.order_id,
                        "reason": "MISSING_TARGET_STATUS",
                    },
                )
            raise ValueError("target status required for order update")

        with self.store.lock:
            rows = self.store.rows(
                "SELECT * FROM orders WHERE id=?", (update.order_id,)
            )
            if not rows:
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_UPDATE_REJECTED",
                        {
                            "update_id": update.update_id,
                            "order_id": update.order_id,
                            "reason": "ORDER_NOT_FOUND",
                        },
                    )
                raise ValueError(f"order {update.order_id} not found")
            row = rows[0]
            current_status = OrderStatus(row["status"])
            current_filled = row["filled"]
            order_qty = row["quantity"]

            # Idempotent status update if already at target
            if current_status == target_status:
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_UPDATE_APPLIED",
                        {
                            "update_id": update.update_id,
                            "order_id": update.order_id,
                            "type": update.update_type.value,
                            "status": target_status.value,
                            "idempotent": True,
                        },
                    )
                return self._row_to_canonical(row)

            # Validate state transition
            try:
                validate_order_transition(
                    current_status,
                    target_status,
                    current_filled=current_filled,
                    target_filled=current_filled,
                    order_quantity=order_qty,
                )
            except Exception as exc:
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_UPDATE_REJECTED",
                        {
                            "update_id": update.update_id,
                            "order_id": update.order_id,
                            "current_status": current_status.value,
                            "target_status": target_status.value,
                            "reason": str(exc),
                        },
                    )
                raise

            self.transition_status(
                update.order_id, target_status, target_filled=current_filled
            )
            with self.store.transaction():
                self.store.audit(
                    "BROKER_UPDATE_APPLIED",
                    {
                        "update_id": update.update_id,
                        "order_id": update.order_id,
                        "type": update.update_type.value,
                        "previous_status": current_status.value,
                        "status": target_status.value,
                        "filled": current_filled,
                    },
                )
            final_row = self.store.rows(
                "SELECT * FROM orders WHERE id=?", (update.order_id,)
            )[0]
            return self._row_to_canonical(final_row)

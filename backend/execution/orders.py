from backend.shared.contracts import OrderStatus


class SubmissionBlocked(ValueError):
    pass


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
        with self.store.transaction() as db:
            if (
                order.status in {OrderStatus.OPEN, OrderStatus.REJECTED}
                and not order.filled_quantity
            ):
                db.execute(
                    "UPDATE orders SET status=? WHERE id=? AND status=? AND filled=0",
                    (order.status, intent.intent_id, OrderStatus.UNKNOWN),
                )
            self.store.audit(
                "ORDER_SUBMITTED",
                {"order_id": intent.intent_id, "status": order.status},
            )
        return order

    def _start_reserved(self, intent):
        rows = self.store.rows("SELECT * FROM orders WHERE id=?", (intent.intent_id,))
        if not rows or rows[0]["status"] != OrderStatus.RESERVED:
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
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE orders SET status=? WHERE id=?",
                    (OrderStatus.REJECTED, intent.intent_id),
                )
                self.store.audit("DISPATCH_BLOCKED", {"order_id": intent.intent_id})
            raise SubmissionBlocked("execution gate closed before dispatch")
        with self.store.transaction() as db:
            db.execute(
                "UPDATE orders SET status=?,dispatch_started=1 WHERE id=?",
                (OrderStatus.UNKNOWN, intent.intent_id),
            )
        return self.broker.start("submit", intent)

    def ingest(self, fill):
        with self.store.transaction():
            return self._ingest_locked(fill)

    def _ingest_locked(self, fill):
        rows = self.store.rows(
            "SELECT * FROM orders WHERE id=?", (fill.broker_order_id,)
        )
        if not rows:
            raise ValueError("unattributed execution")
        o = rows[0]
        if (o["strategy"], o["account"], o["symbol"], o["side"]) != (
            fill.strategy_instance_id,
            fill.account_id,
            fill.symbol,
            fill.side.value,
        ):
            raise ValueError("fill attribution mismatch")
        with self.store.transaction() as db:
            # Ledger is the owning service; nested transaction uses the same connection.
            prior = db.execute(
                "SELECT id FROM fills WHERE id=?", (fill.fill_id,)
            ).fetchone()
            if not prior and o["filled"] + fill.quantity > o["quantity"]:
                raise ValueError("overfill")
            applied = self.ledger.apply(fill)
            if applied:
                filled = o["filled"] + fill.quantity
                status = (
                    OrderStatus.FILLED
                    if filled == o["quantity"]
                    else (
                        OrderStatus.CANCELLED
                        if o["status"] == OrderStatus.CANCELLED
                        else OrderStatus.PARTIALLY_FILLED
                    )
                )
                db.execute(
                    "UPDATE orders SET filled=?,status=? WHERE id=?",
                    (filled, status, o["id"]),
                )
            return applied

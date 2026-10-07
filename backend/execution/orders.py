from backend.shared.contracts import OrderStatus


class OrderManager:
    def __init__(self, store, broker, ledger):
        self.store, self.broker, self.ledger = store, broker, ledger

    def submit_reserved(self, intent):
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
        try:
            order = self.broker.submit(intent)
        except Exception:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE orders SET status=? WHERE id=?",
                    (OrderStatus.UNKNOWN, intent.intent_id),
                )
                self.store.audit("SUBMISSION_UNKNOWN", {"order_id": intent.intent_id})
            raise
        with self.store.transaction() as db:
            db.execute(
                "UPDATE orders SET status=? WHERE id=?",
                (order.status, intent.intent_id),
            )
            self.store.audit(
                "ORDER_SUBMITTED",
                {"order_id": intent.intent_id, "status": order.status},
            )
        return order

    def ingest(self, fill):
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

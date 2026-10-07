from dataclasses import asdict
from uuid import uuid4

from backend.shared.contracts import (
    KillCertificate,
    OrderIntent,
    OrderStatus,
    Side,
    TERMINAL,
)


class Reliability:
    def __init__(self, store, broker, ledger, manager, risk, runtime, clock):
        self.store, self.broker, self.ledger, self.manager = (
            store,
            broker,
            ledger,
            manager,
        )
        self.risk, self.runtime, self.clock = risk, runtime, clock
        self.health = "RECOVERING"
        self.certificate = None

    def reconcile(self):
        with self.store.lock:
            self.runtime.enabled = False
            self.risk.state = "RECOVERING"
            try:
                snapshot = self.broker.snapshot()
                for fill in sorted(
                    snapshot.fills, key=lambda f: (f.timestamp, f.fill_id)
                ):
                    self.manager.ingest(fill)
                local = {o["id"]: o for o in self.store.rows("SELECT * FROM orders")}
                observed = {o.order_id: o for o in snapshot.orders}
                if set(observed) - set(local):
                    raise ValueError("unattributed broker order")
                with self.store.transaction() as db:
                    for oid, row in local.items():
                        order = observed.get(oid)
                        if order is None:
                            raise ValueError("local order absent from broker history")
                        i = order.intent
                        if (
                            row["strategy"],
                            row["account"],
                            row["symbol"],
                            row["side"],
                            row["quantity"],
                        ) != (
                            i.strategy_instance_id,
                            i.account_id,
                            i.symbol,
                            i.side.value,
                            i.quantity,
                        ) or row["filled"] != order.filled_quantity:
                            raise ValueError("order/fill mismatch")
                        if (
                            order.status == OrderStatus.FILLED
                            and row["filled"] != row["quantity"]
                        ):
                            raise ValueError("FILLED without execution evidence")
                        db.execute(
                            "UPDATE orders SET status=? WHERE id=?", (order.status, oid)
                        )
                    if self.ledger.aggregate() != snapshot.positions:
                        raise ValueError(
                            "position drift; no automatic financial adjustment"
                        )
                    self.store.audit(
                        "RECONCILED",
                        {"orders": len(observed), "fills": len(snapshot.fills)},
                    )
                self.health = "HEALTHY"
                self.risk.state = "STOPPED"
                return True
            except Exception as exc:
                self.health = "DRIFTED"
                self.risk.state = "UNCERTAIN"
                with self.store.transaction():
                    self.store.audit("RECONCILIATION_FAILED", {"reason": str(exc)})
                return False

    def resume(self):
        with self.store.lock:
            if not self.reconcile():
                raise ValueError("reconciliation required")
            if self.certificate is not None:
                raise ValueError(
                    "kill is latched for this process; operator recovery required"
                )
            self.risk.state = "RUNNING"
            self.runtime.enabled = True

    def kill(self, flatten_executor=None):
        with self.store.lock:
            start = self.clock()
            self.risk.state = "KILLING"
            self.runtime.enabled = False
            with self.store.transaction():
                self.store.audit("KILL_GATE_CLOSED", {})
            reason = ""
            try:
                snapshot = self.broker.snapshot()
                for order in snapshot.orders:
                    if order.status not in TERMINAL:
                        self.broker.cancel(order.order_id)
                if not self.reconcile():
                    raise ValueError("cannot flatten uncertain/unattributed state")
                self.risk.state = "KILLING"
                # Close each virtual strategy through real attributed executions.
                # Opposing closes may briefly increase broker net; no synthetic fills.
                for (
                    account,
                    strategy,
                    symbol,
                ), position in self.ledger.positions().items():
                    if not position.net_quantity:
                        continue
                    intent = OrderIntent(
                        "kill:" + str(uuid4()),
                        strategy,
                        account,
                        symbol,
                        Side.SELL if position.net_quantity > 0 else Side.BUY,
                        abs(position.net_quantity),
                        self.clock(),
                        reason="verified kill flatten",
                    )
                    with self.store.transaction() as db:
                        self.store.audit(
                            "EMERGENCY_AUTHORIZED", {"intent_id": intent.intent_id}
                        )
                        db.execute(
                            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,0,1)",
                            (
                                intent.intent_id,
                                strategy,
                                account,
                                symbol,
                                intent.side.value,
                                intent.quantity,
                                self.clock(),
                                OrderStatus.RESERVED,
                            ),
                        )
                    order = self.manager.submit_reserved(intent)
                    if flatten_executor:
                        flatten_executor(order)
                if not self.reconcile():
                    raise ValueError("post-flatten reconciliation failed")
            except Exception as exc:
                reason = str(exc)
            try:
                final = self.broker.snapshot()
                open_count = sum(o.status not in TERMINAL for o in final.orders)
                positions = {f"{a}/{s}": q for (a, s), q in final.positions.items()}
            except Exception as exc:
                open_count, positions = -1, {}
                reason = str(exc)
            virtual_flat = all(
                p.net_quantity == 0 for p in self.ledger.positions().values()
            )
            elapsed = self.clock() - start
            safe = not reason and not open_count and not positions and virtual_flat
            status = (
                "SUCCESS"
                if safe and elapsed < 10
                else "SAFE_LATE"
                if safe
                else "FAILED"
            )
            self.certificate = KillCertificate(
                status, elapsed, open_count, positions, virtual_flat, reason
            )
            self.risk.state = "KILLED" if safe else "UNCERTAIN"
            self.health = "HEALTHY" if safe else "DRIFTED"
            with self.store.transaction():
                self.store.audit("KILL_VERIFIED", asdict(self.certificate))
            return self.certificate

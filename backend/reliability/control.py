from dataclasses import asdict
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from backend.reliability.snapshots import SnapshotError, verify_snapshot
from backend.reliability.state import SafetyRepository
from backend.shared.contracts import (
    GlobalTradingState as Gate,
    KillCertificate,
    OrderIntent,
    OrderStatus,
    ReconciliationState as Health,
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
        self.operation_lock = RLock()
        self.safety = SafetyRepository(store)
        self.health = Health.RECOVERING
        saved = self.safety.get("kill_certificate")
        self.certificate = KillCertificate(**saved) if saved else None
        self.last_broker_at = None
        self.max_broker_age = 5
        self.max_feed_age = 15
        self.report = {"verified": False, "reason": "STARTUP_RECONCILIATION_REQUIRED"}
        for mark in store.rows("SELECT * FROM risk_marks"):
            ledger.marks[mark["symbol"]] = Decimal(mark["price"])
        self.risk.evidence_gate = self.check_evidence
        self.risk.on_uncertain = self.fail_closed
        self._health(Health.RECOVERING)

    @property
    def kill_latched(self):
        return self.safety.get("kill_latched", False) is not False

    def _health(self, value):
        self.health = Health(value)
        self.safety.set("health", self.health)

    def fail_closed(self, code, health=Health.DRIFTED):
        with self.store.transaction():
            self.risk.state = Gate.UNCERTAIN
            self.runtime.enabled = False
            self._health(health)
            self.store.audit("SAFETY_RESTRICTED", {"reason": code})

    def observe_tick(self, tick, *, replay=False):
        self.safety.mark(tick, self.clock(), "REPLAY" if replay else "LIVE")
        self.ledger.marks[tick.symbol] = tick.price

    def check_evidence(self, intent):
        now = self.clock()
        if self.health not in {Health.HEALTHY, Health.DEGRADED} or not self.report.get(
            "verified"
        ):
            return "RISK_RECONCILIATION_REQUIRED"
        if (
            self.last_broker_at is None
            or not -1 <= now - self.last_broker_at <= self.max_broker_age
        ):
            self.fail_closed("RISK_STALE_BROKER_STATE", Health.DEGRADED)
            return "RISK_STALE_BROKER_STATE"
        marks = self.store.rows(
            "SELECT * FROM risk_marks WHERE symbol=?", (intent.symbol,)
        )
        if (
            not marks
            or not -1 <= now - marks[0]["received_at"] <= self.max_feed_age
            or (
                marks[0]["source"] == "LIVE"
                and not -1 <= now - marks[0]["event_timestamp"] <= self.max_feed_age
            )
        ):
            self.fail_closed("RISK_STALE_MARKET_DATA", Health.DEGRADED)
            return "RISK_STALE_MARKET_DATA"
        return ""

    def reconcile(self):
        with self.operation_lock, self.store.lock:
            previous_gate = self.risk.state
            self.runtime.enabled = False
            self.risk.state = (
                Gate.RECOVERING if previous_gate != Gate.KILLING else Gate.KILLING
            )
            try:
                snapshot = self.broker.snapshot()
                orders, fills, observed_at, duplicates = verify_snapshot(
                    self.store, snapshot, self.clock(), self.max_broker_age
                )
                with self.store.transaction() as db:
                    for fill in sorted(
                        fills.values(), key=lambda f: (f.timestamp, f.fill_id)
                    ):
                        self.manager.ingest(fill)
                    for oid, order in orders.items():
                        local = db.execute(
                            "SELECT filled FROM orders WHERE id=?", (oid,)
                        ).fetchone()
                        if local["filled"] != order.filled_quantity:
                            raise SnapshotError("LOCAL_CUMULATIVE_MISMATCH")
                        db.execute(
                            "UPDATE orders SET status=? WHERE id=?", (order.status, oid)
                        )
                    if self.ledger.aggregate() != {
                        k: q for k, q in snapshot.positions.items() if q
                    }:
                        raise SnapshotError("VIRTUAL_POSITION_DRIFT")
                    self.report = {
                        "verified": True,
                        "reason": "MATCHED",
                        "observed_at": observed_at,
                        "orders": len(orders),
                        "unique_fills": len(fills),
                        "duplicate_snapshot_fills": duplicates,
                        "open_orders": sum(
                            o.status not in TERMINAL for o in orders.values()
                        ),
                        "broker_positions": [
                            {"account_id": a, "symbol": s, "quantity": q}
                            for (a, s), q in snapshot.positions.items()
                            if q
                        ],
                        "unexplained_positions": [],
                        "unattributed_fills": 0,
                    }
                    self.safety.set("reconciliation_report", self.report)
                    self.store.audit("RECONCILED", self.report)
                self.last_broker_at = observed_at
                self._health(Health.HEALTHY)
                self.risk.state = (
                    Gate.KILLING
                    if previous_gate == Gate.KILLING
                    else Gate.KILLED
                    if self.kill_latched
                    else Gate.STOPPED
                )
                return True
            except Exception as exc:
                reason = (
                    exc.code
                    if isinstance(exc, SnapshotError)
                    else "RECONCILIATION_" + type(exc).__name__.upper()
                )
                self.report = {
                    "verified": False,
                    "reason": reason,
                    "observed_at": self.clock(),
                }
                self.last_broker_at = None
                self.safety.set("reconciliation_report", self.report)
                self.fail_closed(reason)
                return False

    def resume(self, *, reduce_only=False):
        with self.operation_lock, self.store.lock:
            if self.kill_latched:
                raise ValueError(
                    "kill is durably latched; verified operator reset required"
                )
            if not self.reconcile():
                raise ValueError("reconciliation required")
            self.risk.state = Gate.REDUCE_ONLY if reduce_only else Gate.RUNNING
            self.runtime.enabled = True

    def reset_kill(self):
        with self.operation_lock, self.store.lock:
            if (
                not self.reconcile()
                or self.report["open_orders"]
                or self.ledger.aggregate()
                or any(p.net_quantity for p in self.ledger.positions().values())
            ):
                raise ValueError(
                    "kill reset requires verified zero broker/virtual positions and no open orders"
                )
            with self.store.transaction():
                self.safety.set("kill_latched", False)
                self.risk.state = Gate.STOPPED
                self.store.audit("KILL_LATCH_RESET", {})

    def evidence(self):
        now = self.clock()
        marks = self.store.rows("SELECT * FROM risk_marks")
        return {
            "reconciliation": self.report,
            "kill_latched": self.kill_latched,
            "broker": {
                "last_verified_at": self.last_broker_at,
                "fresh": self.last_broker_at is not None
                and -1 <= now - self.last_broker_at <= self.max_broker_age,
            },
            "feeds": [
                {
                    "symbol": r["symbol"],
                    "source": r["source"],
                    "age_seconds": now - r["received_at"],
                    "fresh": -1 <= now - r["received_at"] <= self.max_feed_age
                    and (
                        r["source"] == "REPLAY"
                        or -1 <= now - r["event_timestamp"] <= self.max_feed_age
                    ),
                }
                for r in marks
            ],
            "unknown_orders": [
                r["id"]
                for r in self.store.rows(
                    "SELECT id FROM orders WHERE status=?", (OrderStatus.UNKNOWN,)
                )
            ],
        }

    def kill(self, flatten_executor=None):
        with self.operation_lock, self.store.lock:
            start = self.clock()
            with self.store.transaction():
                self.safety.set("kill_latched", True)
                self.risk.state = Gate.KILLING
                self.runtime.enabled = False
                self.store.audit("KILL_GATE_CLOSED", {})
            reason = ""
            try:
                snapshot = self.broker.snapshot()
                if not snapshot.is_complete:
                    raise SnapshotError("SNAPSHOT_INCOMPLETE")
                for order in snapshot.orders:
                    if order.status not in TERMINAL:
                        self.broker.cancel(order.order_id)
                if not self.reconcile():
                    raise SnapshotError("CANNOT_FLATTEN_UNCERTAIN_STATE")
                self.risk.state = Gate.KILLING
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
                    raise SnapshotError("POST_FLATTEN_RECONCILIATION_FAILED")
            except Exception as exc:
                reason = (
                    exc.code
                    if isinstance(exc, SnapshotError)
                    else "KILL_" + type(exc).__name__.upper()
                )
            try:
                final = self.broker.snapshot()
                if not final.is_complete:
                    raise SnapshotError("SNAPSHOT_INCOMPLETE")
                open_count = sum(o.status not in TERMINAL for o in final.orders)
                positions = {
                    f"{a}/{s}": q for (a, s), q in final.positions.items() if q
                }
            except Exception:
                open_count, positions = -1, {}
                reason = reason or "FINAL_BROKER_EVIDENCE_UNAVAILABLE"
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
            with self.store.transaction():
                self.safety.set("kill_certificate", asdict(self.certificate))
                self.risk.state = Gate.KILLED if safe else Gate.UNCERTAIN
                self._health(Health.HEALTHY if safe else Health.DRIFTED)
                self.store.audit("KILL_VERIFIED", asdict(self.certificate))
            return self.certificate

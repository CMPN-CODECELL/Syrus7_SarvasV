from dataclasses import asdict
from decimal import Decimal
from threading import RLock
import time
from backend.reliability.broker_calls import Deadline
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

    def reconcile(self, *, timeout=None):
        with self.operation_lock:
            previous_gate = self.risk.state
            self.runtime.enabled = False
            self.risk.state = (
                Gate.RECOVERING if previous_gate != Gate.KILLING else Gate.KILLING
            )
            try:
                snapshot = self.broker.snapshot(timeout=timeout)
                with self.store.transaction() as db:
                    orders, fills, observed_at, duplicates = verify_snapshot(
                        self.store, snapshot, self.clock(), self.max_broker_age
                    )
                    for row in self.store.rows(
                        "SELECT * FROM orders WHERE status IN ('UNKNOWN','RESERVED')"
                    ):
                        if row["id"] not in orders:
                            db.execute(
                                "UPDATE orders SET status='REJECTED',dispatch_started=0 WHERE id=?",
                                (row["id"],),
                            )
                            self.store.audit(
                                "ABSENT_SUBMISSION_RESOLVED", {"order_id": row["id"]}
                            )
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
                self.broker.acknowledge_verified()
                self._health(Health.HEALTHY)
                self.risk.state = (
                    Gate.KILLING
                    if previous_gate == Gate.KILLING or self.risk.state == Gate.KILLING
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
        with self.operation_lock:
            if self.kill_latched or self.risk.kill_requested.is_set():
                raise ValueError(
                    "kill is durably latched; verified operator reset required"
                )
            if not self.reconcile():
                raise ValueError("reconciliation required")
            with self.store.lock:
                if self.kill_latched or self.risk.kill_requested.is_set():
                    raise ValueError("kill is latched")
                self.risk.state = Gate.REDUCE_ONLY if reduce_only else Gate.RUNNING
                self.runtime.enabled = True

    def reset_kill(self):
        with self.operation_lock:
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
                self.risk.kill_requested.clear()
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

    def kill(
        self,
        flatten_executor=None,
        *,
        deadline_seconds=9,
        max_rounds=64,
        deadline_clock=time.monotonic,
    ):
        deadline = Deadline(deadline_seconds, deadline_clock)
        self.risk.kill_requested.set()
        with self.store.transaction():
            self.safety.set("kill_latched", True)
            self.risk.state = Gate.KILLING
            self.runtime.enabled = False
            self.store.audit("KILL_GATE_CLOSED", {})
        acquired = self.operation_lock.acquire(timeout=deadline.remaining)
        reason, safe, open_count, positions = "", False, -1, {}
        self.kill_deadline = deadline
        try:
            if not acquired:
                raise SnapshotError("KILL_CONTROLLER_BUSY")
            for _ in range(max_rounds):
                if not deadline.remaining:
                    raise SnapshotError("KILL_DEADLINE_EXPIRED")
                self.risk.state = Gate.KILLING
                if not self.reconcile(timeout=deadline.remaining):
                    raise SnapshotError(self.report["reason"])
                open_count = self.report["open_orders"]
                positions = {
                    f"{r['account_id']}/{r['symbol']}": r["quantity"]
                    for r in self.report["broker_positions"]
                }
                virtual = [
                    (key, p.net_quantity)
                    for key, p in self.ledger.positions().items()
                    if p.net_quantity
                ]
                if (
                    not open_count
                    and not positions
                    and not virtual
                    and not self.broker.unsettled
                ):
                    safe = True
                    break
                # Only progress/cancel orders already proven by a complete snapshot.
                snapshot = self.broker.snapshot(timeout=deadline.remaining)
                with self.store.lock:
                    verify_snapshot(
                        self.store, snapshot, self.clock(), self.max_broker_age
                    )
                for order in snapshot.orders:
                    if order.status in TERMINAL:
                        continue
                    row = self.store.rows(
                        "SELECT emergency FROM orders WHERE id=?", (order.order_id,)
                    )[0]
                    if row["emergency"]:
                        if flatten_executor:
                            flatten_executor(order)
                    else:
                        self.broker.cancel(order.order_id, timeout=deadline.remaining)
                if open_count:
                    continue  # Observe cancellation/fill evidence before creating an exit.
                if virtual and not getattr(
                    self.broker.adapter, "supports_virtual_closes", False
                ):
                    raise SnapshotError("UNCONFIRMED_VIRTUAL_CLOSE_SEMANTICS")
                for (account, strategy, symbol), quantity in virtual:
                    if not deadline.remaining:
                        raise SnapshotError("KILL_DEADLINE_EXPIRED")
                    intent = OrderIntent(
                        "kill:" + str(uuid4()),
                        strategy,
                        account,
                        symbol,
                        Side.SELL if quantity > 0 else Side.BUY,
                        abs(quantity),
                        self.clock(),
                        reason="verified kill flatten",
                    )
                    self.risk.authorize_emergency(intent)
                    order = self.manager.submit_reserved(
                        intent, timeout=deadline.remaining
                    )
                    if order.status == OrderStatus.REJECTED:
                        raise SnapshotError("EMERGENCY_EXIT_REJECTED")
                    if flatten_executor:
                        flatten_executor(order)
            else:
                reason = "KILL_ROUND_LIMIT"
        except Exception as exc:
            reason = (
                exc.code
                if isinstance(exc, SnapshotError)
                else "KILL_" + type(exc).__name__.upper()
            )
            open_count = -1
        finally:
            if acquired:
                self.operation_lock.release()
        virtual_flat = all(not p.net_quantity for p in self.ledger.positions().values())
        elapsed = deadline.elapsed
        status = (
            "SUCCESS" if safe and elapsed < 10 else "SAFE_LATE" if safe else "FAILED"
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

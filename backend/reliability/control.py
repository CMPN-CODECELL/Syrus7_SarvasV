from dataclasses import asdict
from decimal import Decimal
from threading import RLock, Event
import time
from backend.reliability.broker_calls import BrokerCallUnsettled, Deadline
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
    def __init__(
        self,
        store,
        broker,
        ledger,
        manager,
        risk,
        runtime,
        clock,
        *,
        market_session=None,
    ):
        self.store, self.broker, self.ledger, self.manager = (
            store,
            broker,
            ledger,
            manager,
        )
        self.risk, self.runtime, self.clock = risk, runtime, clock
        self.market_session = market_session
        self.operation_lock = RLock()
        self.safety = SafetyRepository(store)
        self.health = Health.RECOVERING
        saved = self.safety.get("kill_certificate")
        self.certificate = KillCertificate(**saved) if saved else None
        self.last_broker_at = None
        self.max_broker_age = 5
        self.max_feed_age = 15
        self.metrics = None
        self.report = {"verified": False, "reason": "STARTUP_RECONCILIATION_REQUIRED"}
        self.external_market_data = None
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

    def fail_closed(self, code, health=Health.DRIFTED, account_id=None):
        with self.store.transaction():
            self.risk.state = Gate.UNCERTAIN
            self.runtime.enabled = False
            self._health(health)
            payload = {"reason": code}
            if account_id:
                payload["account_id"] = account_id
            self.store.audit("SAFETY_RESTRICTED", payload)
        if self.metrics is not None:
            try:
                self.metrics.counter("safety_restriction_count")
            except Exception:
                pass

    def observe_tick(self, tick, *, replay=False):
        source = "REPLAY" if replay else "LIVE"
        if not replay and getattr(tick, "event_time_status", "VERIFIED") != "VERIFIED":
            source = "LIVE_UNVERIFIED_EVENT_TIME"
        self.safety.mark(tick, tick.received_at or self.clock(), source)
        self.ledger.marks[tick.symbol] = tick.price

    def evaluate_safety_evidence(
        self,
        *,
        account_id=None,
        symbols=None,
        external_market_data=None,
        broker_connected=None,
    ):
        """Canonical evaluator of platform safety evidence.

        Separates evidence readiness from gate/runtime authorization.
        Admission, pre-dispatch, resume and readiness projection consume
        this consistent underlying evidence.
        """
        now = self.clock()
        evidence = self.evidence()
        report = evidence["reconciliation"]
        broker = evidence["broker"]
        adapter = getattr(self.broker, "adapter", self.broker)

        if broker_connected is not None:
            connected = broker_connected
        else:
            connected = getattr(adapter, "connected", True)

        has_external = (
            self.external_market_data is not None
            if external_market_data is None
            else external_market_data
        )

        if symbols is not None:
            required_symbols = set(symbols)
        elif account_id is None and hasattr(self, "required_symbols_provider"):
            required_symbols = set(self.required_symbols_provider())
        elif account_id:
            subscriptions = self.store.rows(
                "SELECT symbol FROM subscriptions WHERE account=? AND enabled=1",
                (account_id,),
            )
            required_symbols = {row["symbol"] for row in subscriptions}
        else:
            subscriptions = self.store.rows(
                "SELECT symbol FROM subscriptions WHERE enabled=1"
            )
            required_symbols = {row["symbol"] for row in subscriptions}

        marks = {
            row["symbol"]: row
            for row in self.store.rows("SELECT * FROM risk_marks")
            if row["symbol"] in required_symbols
        }
        market_observed_at = (
            min((row["received_at"] for row in marks.values()), default=None)
            if required_symbols
            else None
        )
        event_observed_at = (
            min((row["event_timestamp"] for row in marks.values()), default=None)
            if required_symbols
            else None
        )
        missing_marks = required_symbols - set(marks)
        unverified_event_marks = {
            symbol
            for symbol, row in marks.items()
            if row["source"] == "LIVE_UNVERIFIED_EVENT_TIME"
        }
        stale_marks = {
            symbol
            for symbol, row in marks.items()
            if not -1 <= now - row["received_at"] <= self.max_feed_age
            or (
                row["source"] == "LIVE"
                and not -1 <= now - row["event_timestamp"] <= self.max_feed_age
            )
        }
        if not required_symbols or missing_marks or unverified_event_marks:
            market_status = "UNKNOWN"
            market_reason = (
                "MARKET_EVENT_TIME_UNVERIFIED"
                if unverified_event_marks
                else "MARKET_EVIDENCE_UNAVAILABLE"
            )
        elif stale_marks:
            market_status = "STALE"
            market_reason = "MARKET_EVIDENCE_STALE"
        else:
            market_status = "VERIFIED"
            market_reason = "MARKET_EVIDENCE_FRESH"

        if connected is False:
            broker_status, broker_reason = "DISCONNECTED", "BROKER_DISCONNECTED"
        elif broker["call_unsettled"]:
            broker_status, broker_reason = "UNKNOWN", "BROKER_CALL_UNSETTLED"
        elif broker["requires_reconciliation"]:
            broker_status, broker_reason = "UNKNOWN", "BROKER_RECONCILIATION_REQUIRED"
        elif broker["last_verified_at"] is None:
            broker_status, broker_reason = "UNKNOWN", "BROKER_EVIDENCE_UNAVAILABLE"
        elif not broker["fresh"]:
            broker_status, broker_reason = "STALE", "BROKER_EVIDENCE_STALE"
        else:
            broker_status, broker_reason = "VERIFIED", "BROKER_EVIDENCE_FRESH"

        coverage_verified = report.get("verified") is True and self.health in {
            Health.HEALTHY,
            Health.DEGRADED,
        }
        coverage_status = "VERIFIED" if coverage_verified else "UNKNOWN"
        coverage_reason = (
            "SNAPSHOT_COVERAGE_VERIFIED"
            if coverage_verified
            else report.get("reason") or "SNAPSHOT_COVERAGE_UNKNOWN"
        )
        reconciliation_status = "VERIFIED" if coverage_verified else "UNKNOWN"
        reconciliation_reason = report.get("reason") or "RECONCILIATION_UNAVAILABLE"

        provider_state = {}
        if has_external and self.external_market_data is not None:
            telemetry = getattr(self.external_market_data, "telemetry", None)
            if telemetry is not None:
                provider_state = telemetry()
        serving_evidence = {
            item.get("symbol"): item
            for item in provider_state.get("serving_evidence") or ()
            if item.get("symbol")
        }
        current_generations = provider_state.get("symbol_generations") or {}
        fresh_serving_symbols = {
            symbol
            for symbol, item in serving_evidence.items()
            if item.get("evidence_type")
            in {
                "PROVIDER_ACKNOWLEDGEMENT",
                "FRESH_VALID_OBSERVATION",
            }
            and item.get("connection_generation") == current_generations.get(symbol)
            and isinstance(item.get("observed_at"), (int, float))
            and -1 <= now - item["observed_at"] <= self.max_feed_age
        }
        serving_observed_at = (
            min(
                serving_evidence[symbol]["observed_at"]
                for symbol in required_symbols & fresh_serving_symbols
            )
            if required_symbols and required_symbols <= fresh_serving_symbols
            else None
        )
        subscription_observed = bool(
            has_external
            and required_symbols
            and provider_state.get("connected") is True
            and required_symbols <= fresh_serving_symbols
        )
        subscription_status = (
            "NOT_APPLICABLE"
            if not required_symbols
            else "VERIFIED"
            if subscription_observed
            else "UNKNOWN"
            if has_external
            else "NOT_APPLICABLE"
        )
        subscription_reason = (
            "NO_REQUIRED_MARKET_SYMBOLS"
            if not required_symbols
            else "PROVIDER_SERVING_OBSERVATION_VERIFIED"
            if subscription_observed
            else "PROVIDER_SUBSCRIPTION_EVIDENCE_UNAVAILABLE"
            if has_external
            else "NO_EXTERNAL_PROVIDER_SUBSCRIPTION"
        )

        if account_id:
            unknown_order_count = self.store.rows(
                "SELECT COUNT(*) AS n FROM orders WHERE account=? AND status=?",
                (account_id, OrderStatus.UNKNOWN.value),
            )[0]["n"]
        else:
            unknown_order_count = self.store.rows(
                "SELECT COUNT(*) AS n FROM orders WHERE status=?",
                (OrderStatus.UNKNOWN.value,),
            )[0]["n"]

        session_open = True
        session_reason = "SESSION_OPEN"
        if self.market_session is not None:
            if self.market_session.status_at(now) == "HALTED":
                session_open = False
                session_reason = "RISK_MARKET_HALTED"
            elif not self.market_session.is_open(now):
                session_open = False
                session_reason = "RISK_MARKET_CLOSED"

        evidence_ready = all(
            (
                market_status == "VERIFIED",
                broker_status == "VERIFIED",
                coverage_status == "VERIFIED",
                reconciliation_status == "VERIFIED",
                subscription_status == "VERIFIED" if has_external else True,
                bool(required_symbols),
                unknown_order_count == 0,
                session_open,
                not self.kill_latched,
            )
        )

        blocking_reasons = []
        for status, reason in (
            (subscription_status, subscription_reason),
            (market_status, market_reason),
            (broker_status, broker_reason),
            (coverage_status, coverage_reason),
            (reconciliation_status, reconciliation_reason),
        ):
            if status not in {"VERIFIED", "NOT_APPLICABLE"}:
                blocking_reasons.append(reason)
        if unknown_order_count:
            blocking_reasons.append("UNKNOWN_ORDERS_PRESENT")
        if not session_open:
            blocking_reasons.append(
                "MARKET_SESSION_NOT_OPEN"
                if session_reason == "RISK_MARKET_CLOSED"
                else session_reason
            )
        if self.kill_latched:
            blocking_reasons.append("KILL_LATCHED")
        if not required_symbols:
            blocking_reasons.append("NO_EXECUTION_DEMAND")

        return {
            "evidence_ready": evidence_ready,
            "coverage_verified": coverage_verified,
            "market_status": market_status,
            "market_reason": market_reason,
            "market_observed_at": market_observed_at,
            "event_observed_at": event_observed_at,
            "broker_status": broker_status,
            "broker_reason": broker_reason,
            "broker_connected": connected,
            "coverage_status": coverage_status,
            "coverage_reason": coverage_reason,
            "reconciliation_status": reconciliation_status,
            "reconciliation_reason": reconciliation_reason,
            "subscription_status": subscription_status,
            "subscription_reason": subscription_reason,
            "required_symbols": sorted(required_symbols),
            "serving_symbols": sorted(fresh_serving_symbols),
            "serving_observed_at": serving_observed_at,
            "unknown_order_count": unknown_order_count,
            "session_open": session_open,
            "session_reason": session_reason,
            "kill_latched": self.kill_latched,
            "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
            "report": report,
            "broker": broker,
            "has_external": has_external,
        }

    def check_evidence(self, intent):
        evidence = self.evaluate_safety_evidence(
            account_id=intent.account_id,
            symbols=(intent.symbol,),
        )
        if evidence["evidence_ready"]:
            return ""

        if not evidence["coverage_verified"]:
            return "RISK_RECONCILIATION_REQUIRED"

        if evidence["broker_status"] == "DISCONNECTED":
            self.fail_closed("RISK_BROKER_DISCONNECTED", Health.DEGRADED)
            return "RISK_BROKER_DISCONNECTED"

        if evidence["broker_reason"] in {
            "BROKER_CALL_UNSETTLED",
            "BROKER_RECONCILIATION_REQUIRED",
        }:
            return "RISK_RECONCILIATION_REQUIRED"

        if evidence["broker_status"] in {"STALE", "UNKNOWN"}:
            self.fail_closed("RISK_STALE_BROKER_STATE", Health.DEGRADED)
            return "RISK_STALE_BROKER_STATE"

        if not evidence["session_open"]:
            return evidence["session_reason"]

        if evidence["subscription_status"] == "UNKNOWN":
            return "RISK_PROVIDER_SUBSCRIPTION_UNAVAILABLE"

        if evidence["market_status"] in {"STALE", "UNKNOWN"}:
            self.fail_closed("RISK_STALE_MARKET_DATA", Health.DEGRADED)
            return "RISK_STALE_MARKET_DATA"

        if evidence["unknown_order_count"] > 0:
            return "RISK_UNKNOWN_ORDERS_PRESENT"

        return "RISK_RECONCILIATION_REQUIRED"

    def reconcile(self, *, timeout=None):
        metric_started = time.perf_counter()
        position_diff = []
        recovered_fill_ids = []
        with self.operation_lock:
            previous_gate = self.risk.state
            self.runtime.enabled = False
            self.risk.state = (
                Gate.RECOVERING if previous_gate != Gate.KILLING else Gate.KILLING
            )
            try:
                snapshot = self.broker.snapshot(timeout=timeout)
                local_positions = self.ledger.aggregate()
                broker_positions = {
                    key: qty for key, qty in snapshot.positions.items() if qty
                }
                position_diff = [
                    {
                        "account_id": account,
                        "symbol": symbol,
                        "local": local_positions.get((account, symbol), 0),
                        "broker": broker_positions.get((account, symbol), 0),
                        "delta": broker_positions.get((account, symbol), 0)
                        - local_positions.get((account, symbol), 0),
                    }
                    for account, symbol in sorted(
                        set(local_positions) | set(broker_positions)
                    )
                    if local_positions.get((account, symbol), 0)
                    != broker_positions.get((account, symbol), 0)
                ]
                with self.store.transaction() as db:
                    before_fills = {
                        row["id"] for row in self.store.rows("SELECT id FROM fills")
                    }
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
                    recovered_fill_ids = sorted(set(fills) - before_fills)
                    for oid, order in orders.items():
                        local = db.execute(
                            "SELECT filled FROM orders WHERE id=?", (oid,)
                        ).fetchone()
                        if local["filled"] != order.filled_quantity:
                            raise SnapshotError("LOCAL_CUMULATIVE_MISMATCH")
                        db.execute(
                            "UPDATE orders SET status=? WHERE id=?", (order.status, oid)
                        )
                    local_positions = self.ledger.aggregate()
                    broker_positions = {
                        key: quantity
                        for key, quantity in snapshot.positions.items()
                        if quantity
                    }
                    position_diff = [
                        {
                            "account_id": account,
                            "symbol": symbol,
                            "local": local_positions.get((account, symbol), 0),
                            "broker": broker_positions.get((account, symbol), 0),
                            "delta": broker_positions.get((account, symbol), 0)
                            - local_positions.get((account, symbol), 0),
                        }
                        for account, symbol in sorted(
                            set(local_positions) | set(broker_positions)
                        )
                        if local_positions.get((account, symbol), 0)
                        != broker_positions.get((account, symbol), 0)
                    ]
                    if position_diff:
                        raise SnapshotError("VIRTUAL_POSITION_DRIFT")
                    accounts = {}
                    for order in orders.values():
                        account = getattr(
                            getattr(order, "intent", None), "account_id", None
                        )
                        if account:
                            item = accounts.setdefault(
                                account,
                                {
                                    "orders": 0,
                                    "unique_fills": 0,
                                    "open_orders": 0,
                                    "duplicate_snapshot_fills": 0,
                                    "unattributed_fills": 0,
                                },
                            )
                            item["orders"] += 1
                            item["open_orders"] += order.status not in TERMINAL
                    for fill in fills.values():
                        account = getattr(fill, "account_id", None)
                        if account:
                            item = accounts.setdefault(
                                account,
                                {
                                    "orders": 0,
                                    "unique_fills": 0,
                                    "open_orders": 0,
                                    "duplicate_snapshot_fills": 0,
                                    "unattributed_fills": 0,
                                },
                            )
                            item["unique_fills"] += 1
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
                        "position_diff": position_diff,
                        "recovered_fill_ids": recovered_fill_ids,
                        "recovered_fill_count": len(recovered_fill_ids),
                        "accounts": accounts,
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
                self._record_reconcile_metric(metric_started, True)
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
                    "position_diff": position_diff,
                    "recovered_fill_ids": recovered_fill_ids,
                    "recovered_fill_count": len(recovered_fill_ids),
                }
                self.last_broker_at = None
                self.safety.set("reconciliation_report", self.report)
                self.fail_closed(reason)
                self._record_reconcile_metric(metric_started, False)
                return False

    def refresh_broker_evidence(self, *, timeout=None):
        """Refresh an already-verified broker view without changing the gate.

        This is used by the live-provider heartbeat after explicit operator
        reconciliation/resume. It can preserve RUNNING/REDUCE_ONLY on a fresh,
        complete match, but it can never open a gate or recover from failure.
        """
        with self.operation_lock:
            try:
                snapshot = self.broker.snapshot(timeout=timeout)
                orders, fills, observed_at, duplicates = verify_snapshot(
                    self.store, snapshot, self.clock(), self.max_broker_age
                )
                local_positions = {
                    key: quantity
                    for key, quantity in self.ledger.aggregate().items()
                    if quantity
                }
                broker_positions = {
                    key: quantity
                    for key, quantity in snapshot.positions.items()
                    if quantity
                }
                if local_positions != broker_positions:
                    raise SnapshotError("VIRTUAL_POSITION_DRIFT")
                self.last_broker_at = observed_at
                self.broker.acknowledge_verified()
                self._health(Health.HEALTHY)
                self.report = dict(self.report) | {
                    "verified": True,
                    "reason": "MATCHED",
                    "observed_at": observed_at,
                    "orders": len(orders),
                    "unique_fills": len(fills),
                    "duplicate_snapshot_fills": duplicates,
                }
                self.safety.set("reconciliation_report", self.report)
                with self.store.transaction():
                    self.store.audit(
                        "BROKER_EVIDENCE_REFRESHED",
                        {
                            "observed_at": observed_at,
                            "orders": len(orders),
                            "unique_fills": len(fills),
                        },
                    )
                return True
            except BrokerCallUnsettled:
                # A strategy write owns the single broker call slot. The
                # heartbeat is best-effort and retries on its next interval;
                # it must not turn ordinary serialization into uncertainty.
                return None
            except Exception as exc:
                reason = (
                    exc.code
                    if isinstance(exc, SnapshotError)
                    else "BROKER_REFRESH_" + type(exc).__name__.upper()
                )
                self.last_broker_at = None
                self.report = {
                    "verified": False,
                    "reason": reason,
                    "observed_at": self.clock(),
                }
                self.safety.set("reconciliation_report", self.report)
                self.fail_closed(reason)
                return False

    def _record_reconcile_metric(self, started, success):
        if self.metrics is None:
            return
        try:
            self.metrics.observe(
                "reconciliation_latency_ms", (time.perf_counter() - started) * 1000
            )
            if not success:
                self.metrics.counter("reconciliation_failure_count")
        except Exception:
            pass

    def reconciliation_center(self):
        evidence = self.evidence()
        events = [
            dict(row)
            for row in self.store.rows(
                "SELECT sequence,type,payload,recorded_at FROM audit "
                "WHERE type IN ('RECONCILED','SAFETY_RESTRICTED','ABSENT_SUBMISSION_RESOLVED') "
                "ORDER BY sequence DESC LIMIT 20"
            )
        ]
        return {
            "report": self.report,
            "broker": evidence["broker"],
            "position_comparison": evidence["position_comparison"],
            "unknown_orders": evidence["unknown_orders"],
            "events": events,
        }

    def readiness_projection(
        self,
        *,
        account_id,
        symbols=None,
        market_data,
        external_market_data,
        broker_connected,
        supports_virtual_closes,
    ):
        """Compose provider readiness without granting execution authority.

        This projection intentionally does not change the gate or runtime.  In
        particular, transport connectivity and a subscription send are not
        evidence that the provider accepted or is serving the subscription.
        """
        now = self.clock()
        evidence = self.evaluate_safety_evidence(
            account_id=account_id,
            symbols=symbols,
            external_market_data=external_market_data,
            broker_connected=broker_connected,
        )
        gate = Gate(self.risk.state)
        report = evidence["report"]
        broker = evidence["broker"]
        connected = evidence["broker_connected"]

        market_connected = market_data.get("connected")
        market_connection_status = (
            "CONNECTED"
            if market_connected is True
            else "DISCONNECTED"
            if market_connected is False
            else "UNKNOWN"
        )
        broker_connection_status = (
            "CONNECTED"
            if connected is True
            else "DISCONNECTED"
            if connected is False
            else "UNKNOWN"
        )

        evidence_ready = evidence["evidence_ready"]
        resume_required = gate in {Gate.RECOVERING, Gate.STOPPED, Gate.UNCERTAIN}
        resume_eligible = resume_required and evidence_ready
        new_exposure_allowed = (
            gate == Gate.RUNNING and self.runtime.enabled and evidence_ready
        )
        cancellation_possible = (
            broker_connection_status == "CONNECTED"
            and not broker["call_unsettled"]
            and not broker["requires_reconciliation"]
        )
        emergency_candidate = (
            gate == Gate.KILLING
            and self.kill_latched
            and evidence["broker_status"] == "VERIFIED"
            and evidence["coverage_status"] == "VERIFIED"
            and evidence["reconciliation_status"] == "VERIFIED"
            and supports_virtual_closes
        )
        certificate = self.certificate
        current_kill_verified = bool(
            certificate
            and certificate.status in {"SUCCESS", "SAFE_LATE"}
            and gate == Gate.KILLED
            and evidence["broker_status"] == "VERIFIED"
            and evidence["reconciliation_status"] == "VERIFIED"
        )

        missing_core = any(
            status == "UNKNOWN"
            for status in (
                evidence["subscription_status"],
                evidence["market_status"],
                evidence["broker_status"],
                evidence["coverage_status"],
                evidence["reconciliation_status"],
            )
        )
        overall = (
            "READY"
            if new_exposure_allowed
            else "RESUME_ELIGIBLE"
            if resume_eligible
            else "UNKNOWN"
            if missing_core
            else "NOT_READY"
        )

        return {
            "status": overall,
            "generated_at": now,
            "provider": market_data.get("provider", "UNKNOWN"),
            "connectivity": {
                "market": {
                    "status": market_connection_status,
                    "observed_at": market_data.get("last_received_at"),
                    "reason_code": "CONNECTIVITY_IS_NOT_READINESS",
                },
                "broker": {
                    "status": broker_connection_status,
                    "observed_at": broker["last_verified_at"],
                    "reason_code": "CONNECTIVITY_IS_NOT_READINESS",
                },
            },
            "subscription": {
                "status": evidence["subscription_status"],
                "observed_at": evidence["serving_observed_at"],
                "reason_code": evidence["subscription_reason"],
                "required_symbols": evidence["required_symbols"],
                "serving_symbols": evidence["serving_symbols"],
            },
            "market_freshness": {
                "status": evidence["market_status"],
                "observed_at": evidence["market_observed_at"],
                "event_observed_at": evidence["event_observed_at"],
                "reason_code": evidence["market_reason"],
            },
            "broker_freshness": {
                "status": evidence["broker_status"],
                "observed_at": broker["last_verified_at"],
                "reason_code": evidence["broker_reason"],
            },
            "snapshot_coverage": {
                "status": evidence["coverage_status"],
                "observed_at": report.get("observed_at"),
                "reason_code": evidence["coverage_reason"],
            },
            "reconciliation": {
                "status": evidence["reconciliation_status"],
                "observed_at": report.get("observed_at"),
                "reason_code": evidence["reconciliation_reason"],
            },
            "resume": {
                "required": resume_required,
                "eligible": resume_eligible,
                "runtime_enabled": self.runtime.enabled,
                "reason_code": (
                    "EXPLICIT_RESUME_ELIGIBLE"
                    if resume_eligible
                    else "EXPLICIT_RESUME_REQUIRED"
                    if resume_required
                    else "KILL_RESET_REQUIRED"
                    if self.kill_latched
                    else "RESUME_NOT_REQUIRED"
                ),
            },
            "actions": {
                "new_exposure": {
                    "status": "ALLOWED" if new_exposure_allowed else "BLOCKED",
                    "reason_code": (
                        "READINESS_VERIFIED"
                        if new_exposure_allowed
                        else "READINESS_NOT_VERIFIED"
                    ),
                },
                "cancellation": {
                    "status": (
                        "CONDITIONALLY_ALLOWED" if cancellation_possible else "BLOCKED"
                    ),
                    "reason_code": (
                        "KNOWN_WORKING_ORDERS_ONLY"
                        if cancellation_possible
                        else "BROKER_MUTATION_UNCERTAIN"
                    ),
                },
                "verified_emergency_reduction": {
                    "status": (
                        "CONDITIONALLY_ALLOWED" if emergency_candidate else "BLOCKED"
                    ),
                    "reason_code": (
                        "PER_INTENT_REDUCTION_PROOF_REQUIRED"
                        if emergency_candidate
                        else "EMERGENCY_REDUCTION_NOT_VERIFIED"
                    ),
                },
            },
            "unknown_order_count": evidence["unknown_order_count"],
            "blocking_reason_codes": evidence["blocking_reasons"],
            "kill_verification": {
                "status": "VERIFIED" if current_kill_verified else "UNKNOWN",
                "observed_at": certificate.completed_at if certificate else None,
                "reason_code": (
                    "CURRENT_KILL_VERIFIED"
                    if current_kill_verified
                    else "CURRENT_FLATNESS_NOT_VERIFIED"
                ),
                "latest_certificate_status": certificate.status
                if certificate
                else None,
            },
        }

    def resume(self, *, reduce_only=False):
        with self.operation_lock:
            if self.kill_latched or self.risk.kill_requested.is_set():
                raise ValueError(
                    "kill is durably latched; verified operator reset required"
                )
            if not self.reconcile():
                reason = self.report.get("reason", "RECONCILIATION_REQUIRED")
                raise ValueError(f"reconciliation required: {reason}")

            evidence = self.evaluate_safety_evidence(account_id=None)
            if not evidence["session_open"]:
                raise ValueError(f"market session closed: {evidence['session_reason']}")
            if evidence["broker_status"] == "DISCONNECTED":
                raise ValueError(
                    f"broker evidence not ready: {evidence['broker_reason']}"
                )
            if evidence["broker_reason"] in {
                "BROKER_CALL_UNSETTLED",
                "BROKER_RECONCILIATION_REQUIRED",
            }:
                raise ValueError(
                    f"broker evidence not ready: {evidence['broker_reason']}"
                )
            if evidence["coverage_status"] != "VERIFIED":
                raise ValueError(
                    f"snapshot coverage not verified: {evidence['coverage_reason']}"
                )
            if evidence["reconciliation_status"] != "VERIFIED":
                raise ValueError(
                    f"reconciliation not verified: {evidence['reconciliation_reason']}"
                )
            if evidence["subscription_status"] not in {"VERIFIED", "NOT_APPLICABLE"}:
                raise ValueError(
                    f"provider subscription evidence unavailable: {evidence['subscription_reason']}"
                )
            if evidence["unknown_order_count"] > 0:
                raise ValueError(
                    "unresolved unknown orders present across accounts; reconciliation required"
                )

            adapter = getattr(self.broker, "adapter", self.broker)
            with self.store.lock:
                if self.kill_latched or self.risk.kill_requested.is_set():
                    raise ValueError("kill is latched")
                if getattr(adapter, "connected", True) is False:
                    raise ValueError("broker connection offline: BROKER_DISCONNECTED")
                self.risk.state = Gate.REDUCE_ONLY if reduce_only else Gate.RUNNING
                self.runtime.enabled = True
                with self.store.transaction():
                    self.store.audit(
                        "TRADING_RESUMED",
                        {"gate": self.risk.state, "reconciliation": "MATCHED"},
                    )

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
        broker_fresh = (
            self.last_broker_at is not None
            and -1 <= now - self.last_broker_at <= self.max_broker_age
        )
        virtual = self.ledger.aggregate()
        observed = {
            (r["account_id"], r["symbol"]): r["quantity"]
            for r in self.report.get("broker_positions", [])
        }
        trusted = (
            self.health == Health.HEALTHY
            and not self.broker.uncertain
            and self.risk.state != Gate.UNCERTAIN
            and self.report.get("verified", False)
            and broker_fresh
            and not self.broker.unsettled
        )
        return {
            "position_comparison": {
                "status": "VERIFIED"
                if trusted and virtual == observed
                else "FAILED"
                if trusted
                else "UNKNOWN",
                "virtual": [
                    {"account_id": a, "symbol": s, "quantity": q}
                    for (a, s), q in virtual.items()
                ],
                "broker": self.report.get("broker_positions"),
            },
            "fills": {
                "unique_applied": self.store.rows("SELECT COUNT(*) AS n FROM fills")[0][
                    "n"
                ],
                "duplicates_ignored": self.store.rows(
                    "SELECT COUNT(*) AS n FROM audit WHERE type='DUPLICATE_FILL_IGNORED'"
                )[0]["n"],
                "rejected_events": self.store.rows(
                    "SELECT COUNT(*) AS n FROM audit WHERE type='SAFETY_RESTRICTED' AND payload LIKE '%FILL_EVENT_REJECTED%'"
                )[0]["n"],
                "unattributed_in_last_verified_snapshot": self.report.get(
                    "unattributed_fills"
                )
                if trusted
                else None,
            },
            "reconciliation": self.report,
            "kill_latched": self.kill_latched,
            "broker": {
                "call_unsettled": self.broker.unsettled,
                "requires_reconciliation": self.broker.uncertain,
                "last_verified_at": self.last_broker_at,
                "fresh": broker_fresh,
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
        deadline=None,
    ):
        started_at = self.clock()
        if deadline is None:
            if isinstance(deadline_seconds, Deadline):
                deadline = deadline_seconds
            elif isinstance(deadline_seconds, (int, float)) and deadline_seconds <= 0:
                deadline = None
            else:
                deadline = Deadline(deadline_seconds, deadline_clock)
        stages = {}
        self.risk.kill_requested.set()
        with self.store.transaction():
            self.safety.set("kill_latched", True)
            self.risk.state = Gate.KILLING
            self.runtime.enabled = False
            self.store.audit("KILL_GATE_CLOSED", {})
        stages["gate_closed"] = deadline.elapsed * 1000 if deadline else 0
        if deadline is None or not deadline.remaining:
            elapsed = (
                deadline.elapsed if deadline else max(0.0, float(-deadline_seconds))
            )
            self.certificate = KillCertificate(
                "FAILED",
                elapsed,
                -1,
                {},
                False,
                "KILL_DEADLINE_EXPIRED",
                10.0,
                started_at,
                self.clock(),
                stages,
                {
                    "open_orders": -1,
                    "broker_positions": {},
                    "virtual_positions_flat": False,
                    "broker_unsettled": self.broker.unsettled,
                },
            )
            with self.store.transaction():
                self.safety.set("kill_certificate", asdict(self.certificate))
                self.risk.state = Gate.UNCERTAIN
                self._health(Health.DRIFTED)
                self.store.audit("KILL_VERIFIED", asdict(self.certificate))
            return self.certificate
        acquired = self.operation_lock.acquire(timeout=deadline.remaining)
        reason, safe, open_count, positions = "", False, -1, {}
        try:
            if not acquired:
                raise SnapshotError("KILL_CONTROLLER_BUSY")
            self.kill_deadline = deadline
            previous_evidence = None
            for _ in range(max_rounds):
                if not deadline.remaining:
                    raise SnapshotError("KILL_DEADLINE_EXPIRED")
                self.risk.state = Gate.KILLING
                if not self.reconcile(timeout=deadline.remaining):
                    raise SnapshotError(self.report["reason"])
                stages.setdefault("initial_reconciliation", deadline.elapsed * 1000)
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
                if not open_count:
                    stages.setdefault("open_orders_cleared", deadline.elapsed * 1000)
                if not virtual:
                    stages.setdefault("virtual_positions_flat", deadline.elapsed * 1000)
                current_evidence = (
                    open_count,
                    tuple(sorted(positions.items())),
                    tuple(virtual),
                    self.report["unique_fills"],
                )
                if current_evidence == previous_evidence:
                    Event().wait(min(0.05, deadline.remaining))
                previous_evidence = current_evidence
                if (
                    not open_count
                    and not positions
                    and not virtual
                    and not self.broker.unsettled
                ):
                    safe = True
                    stages.setdefault("final_broker_verified", deadline.elapsed * 1000)
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
            status,
            elapsed,
            open_count,
            positions,
            virtual_flat,
            reason,
            10.0,
            started_at,
            self.clock(),
            stages,
            {
                "open_orders": open_count,
                "broker_positions": positions,
                "virtual_positions_flat": virtual_flat,
                "broker_unsettled": self.broker.unsettled,
            },
        )
        if self.metrics is not None:
            try:
                self.metrics.observe(
                    "kill_gate_close_latency_ms", stages.get("gate_closed", 0)
                )
                self.metrics.observe("kill_verified_flat_latency_ms", elapsed * 1000)
            except Exception:
                pass
        with self.store.transaction():
            self.safety.set("kill_certificate", asdict(self.certificate))
            self.risk.state = Gate.KILLED if safe else Gate.UNCERTAIN
            self._health(Health.HEALTHY if safe else Health.DRIFTED)
            self.store.audit("KILL_VERIFIED", asdict(self.certificate))
        return self.certificate

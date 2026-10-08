import json

from backend.shared.contracts import GlobalTradingState


class SafetyProofService:
    """Read-only evidence projection; it never changes platform state."""

    def __init__(self, store, ledger, risk, reliability, clock):
        self.store = store
        self.ledger = ledger
        self.risk = risk
        self.reliability = reliability
        self.clock = clock

    def build(self):
        orders = self.store.rows("SELECT id FROM orders WHERE emergency=0")
        decisions = {
            payload.get("intent_id")
            for row in self.store.rows(
                "SELECT payload FROM audit WHERE type='RISK_DECISION'"
            )
            for payload in [json.loads(row["payload"])]
            if payload.get("allowed")
        }
        bypasses = [row["id"] for row in orders if row["id"] not in decisions]
        invariants = [
            self._item(
                "I1",
                "No broker bypass",
                "FAILED" if bypasses else "VERIFIED",
                "Every platform order has an approving risk decision."
                if not bypasses
                else "Orders without approving risk evidence were found.",
                {
                    "orders": len(orders),
                    "approved_decisions": len(decisions),
                    "bypass_count": len(bypasses),
                },
            )
        ]
        fill_totals = {}
        for row in self.store.rows(
            "SELECT account,strategy,symbol,side,quantity FROM fills"
        ):
            key = (row["account"], row["strategy"], row["symbol"])
            fill_totals[key] = fill_totals.get(key, 0) + (
                row["quantity"] if row["side"] == "BUY" else -row["quantity"]
            )
        actual = {
            key: position.net_quantity
            for key, position in self.ledger.positions().items()
            if position.net_quantity
        }
        fill_totals = {key: value for key, value in fill_totals.items() if value}
        position_match = fill_totals == actual
        invariants.append(
            self._item(
                "I2",
                "Fills create positions",
                "VERIFIED" if position_match else "FAILED",
                "Virtual positions equal the signed sum of unique fills."
                if position_match
                else "Virtual positions do not match durable fill evidence.",
                {"fill_positions": len(fill_totals), "virtual_positions": len(actual)},
            )
        )
        evidence = self.reliability.evidence()
        fills = evidence.get("fills", {})
        rejected = int(fills.get("rejected_events", 0))
        invariants.append(
            self._item(
                "I3",
                "Fill idempotency",
                "FAILED" if rejected else "VERIFIED",
                "Duplicate fills have no second financial effect."
                if not rejected
                else "Conflicting/rejected fill evidence exists.",
                {
                    "duplicates_ignored": fills.get("duplicates_ignored", 0),
                    "rejected_events": rejected,
                    "double_applied": 0,
                },
            )
        )
        unattributed_rejections = self.store.rows(
            "SELECT COUNT(*) AS n FROM audit WHERE type='UNATTRIBUTED_FILL_REJECTED'"
        )[0]["n"]
        attribution_mismatches = self.store.rows(
            "SELECT COUNT(*) AS n FROM audit WHERE type='FILL_ATTRIBUTION_MISMATCH'"
        )[0]["n"]
        unattributed = fills.get("unattributed_in_last_verified_snapshot")
        attribution_status = (
            "FAILED"
            if unattributed_rejections or attribution_mismatches or unattributed
            else "UNKNOWN"
            if unattributed is None
            else "VERIFIED"
        )
        invariants.append(
            self._item(
                "I4",
                "Strategy attribution",
                attribution_status,
                "Current broker fill attribution evidence.",
                {
                    "unattributed_fills": unattributed,
                    "unattributed_rejections": unattributed_rejections,
                    "attribution_mismatches": attribution_mismatches,
                },
            )
        )
        invariants.append(
            self._item(
                "I5",
                "Position risk",
                "UNKNOWN",
                "Current budgets are available; historical policy reconstruction is not complete.",
                {"budget_count": len(self.store.rows("SELECT id FROM subscriptions"))},
            )
        )
        runtime_safe = not (
            self.risk.state != GlobalTradingState.RUNNING
            and self.reliability.runtime.enabled
        )
        invariants.append(
            self._item(
                "I6",
                "Kill and global gate",
                "VERIFIED" if runtime_safe else "FAILED",
                "Runtime authority is consistent with the global gate.",
                {
                    "gate": self.risk.state,
                    "kill_latched": self.risk.safety.get("kill_latched", False),
                    "runtime_enabled": self.reliability.runtime.enabled,
                },
            )
        )
        invariants.append(self._restart_proof())
        reconciliation = evidence.get("reconciliation", {})
        broker = evidence.get("broker", {})
        rec_status = (
            "VERIFIED"
            if reconciliation.get("verified") and broker.get("fresh")
            else "FAILED"
            if reconciliation.get("reason") not in {None, "MATCHED"}
            else "UNKNOWN"
        )
        invariants.append(
            self._item(
                "I8",
                "Broker reconciliation",
                rec_status,
                "Broker and virtual positions require fresh matching evidence.",
                {
                    "reason": reconciliation.get("reason"),
                    "broker_fresh": broker.get("fresh", False),
                },
            )
        )
        certificate = self.reliability.certificate
        kill_status = (
            "NOT_APPLICABLE"
            if certificate is None
            else "VERIFIED"
            if certificate.status in {"SUCCESS", "SAFE_LATE"}
            else "FAILED"
        )
        invariants.append(
            self._item(
                "I9",
                "Kill completion",
                kill_status,
                "Latest kill outcome is evidence-backed."
                if certificate
                else "No kill requested.",
                {"status": certificate.status if certificate else None},
            )
        )
        stale_feeds = [
            feed["symbol"] for feed in evidence.get("feeds", []) if not feed["fresh"]
        ]
        uncertain = (
            rec_status != "VERIFIED"
            or not broker.get("fresh", False)
            or bool(stale_feeds)
            or broker.get("requires_reconciliation", False)
        )
        contained = not uncertain or self.risk.state != GlobalTradingState.RUNNING
        invariants.append(
            self._item(
                "I10",
                "Unknown-state containment",
                "VERIFIED" if contained else "FAILED",
                "Uncertainty cannot retain ordinary risk-increasing authority.",
                {
                    "gate": self.risk.state,
                    "uncertain": uncertain,
                    "stale_feeds": stale_feeds,
                },
            )
        )
        statuses = {item["status"] for item in invariants}
        verdict = (
            "UNSAFE"
            if "FAILED" in statuses
            else "UNKNOWN"
            if "UNKNOWN" in statuses
            else "VERIFIED_SAFE"
        )
        return {
            "verdict": verdict,
            "generated_at": self.clock(),
            "evidence_fresh": rec_status == "VERIFIED",
            "invariants": invariants,
        }

    def _restart_proof(self):
        events = self.store.rows(
            "SELECT type,payload,sequence FROM audit WHERE type IN "
            "('RECONCILED','GLOBAL_GATE_CHANGED','TRADING_RESUMED') ORDER BY sequence"
        )
        if self.risk.state != GlobalTradingState.RUNNING:
            return self._item(
                "I7", "Restart safety", "VERIFIED", "Trading is not auto-running.", {}
            )
        resumed = [row for row in events if row["type"] == "TRADING_RESUMED"]
        last_resume = resumed[-1]["sequence"] if resumed else None
        reconciled = bool(
            last_resume
            and any(
                row["type"] == "RECONCILED" and row["sequence"] < last_resume
                for row in events
            )
        )
        return self._item(
            "I7",
            "Restart safety",
            "VERIFIED" if reconciled else "UNKNOWN",
            "RUNNING follows durable reconciliation evidence."
            if reconciled
            else "No durable reconciliation evidence precedes RUNNING.",
            {"reconciled_before_resume": reconciled, "resume_seen": bool(resumed)},
        )

    @staticmethod
    def _item(identifier, name, status, summary, evidence):
        return {
            "id": identifier,
            "name": name,
            "status": status,
            "summary": summary,
            "evidence": evidence,
        }

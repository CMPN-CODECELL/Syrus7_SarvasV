"""Offline fault scenarios; all ordinary intents enter through platform risk."""

from dataclasses import replace
from decimal import Decimal
from backend.shared.contracts import OrderIntent, Side, Tick, RiskPolicy

SCENARIOS = {
    "partial",
    "rejection",
    "position_limit",
    "duplicate_fill",
    "conflicting_fill",
    "missed_fill",
    "unknown_submission",
    "disconnect",
    "reconnect",
    "spam",
    "stale_feed",
    "drift",
    "clear_drift",
    "kill_partial",
}


class FailureLab:
    def __init__(self, platform):
        self.platform = platform

    def run(self, scenario):
        p = self.platform
        p.require_offline_demo()
        if scenario not in SCENARIOS:
            raise ValueError("unknown failure scenario")
        decisions, evidence = [], {}
        if scenario == "disconnect":
            p.broker.connected = False
            p.reliability.reconcile()
        elif scenario == "reconnect":
            p.broker.connected = True
            p.reliability.reconcile()
        elif scenario == "clear_drift":
            p.broker.external_positions.pop(("failure-lab", "INJECTED"), None)
            p.broker.persist()
            p.reliability.reconcile()
        else:
            with p.store.lock:
                if not p.store.rows("SELECT id FROM accounts WHERE id='failure-lab'"):
                    p.account("failure-lab")
                counter = len(
                    p.store.rows(
                        "SELECT id FROM subscriptions WHERE account='failure-lab'"
                    )
                )
                strategy = f"lab-{scenario}-{counter}"
                p.strategies.subscribe("failure-lab", strategy, "momentum", "LAB")
            p.tick(Tick("LAB", int(p.clock()), Decimal("100"), 0, strategy + ":mark"))
            p.reliability.resume()

            def submit(suffix, quantity):
                i = OrderIntent(
                    f"{strategy}:{suffix}",
                    strategy,
                    "failure-lab",
                    "LAB",
                    Side.BUY,
                    quantity,
                    p.clock(),
                )
                decisions.append(p.risk.submit(i))
                return i

            def execute(i, quantity):
                return p.broker_calls.call(
                    "execute", i.intent_id, quantity, Decimal("100"), p.clock()
                )

            if scenario in {"partial", "kill_partial"}:
                i = submit("partial", 100)
                p.ingest(execute(i, 40))
                if scenario == "kill_partial":
                    evidence["kill"] = p.kill()
            elif scenario == "rejection":
                p.broker.reject_next = True
                submit("reject", 5)
            elif scenario == "position_limit":
                i = submit("filled", 80)
                p.ingest(execute(i, 80))
                submit("pending", 20)
                submit("blocked", 10)
            elif scenario in {"duplicate_fill", "conflicting_fill", "missed_fill"}:
                i = submit("fill", 10)
                f = execute(i, 4)
                if scenario == "missed_fill":
                    evidence["quantity_before_recovery"] = p.ledger.quantity(
                        "failure-lab", strategy, "LAB"
                    )
                    evidence["recovered"] = p.reliability.reconcile()
                    evidence["quantity_after_recovery"] = p.ledger.quantity(
                        "failure-lab", strategy, "LAB"
                    )
                else:
                    p.ingest(f)
                    if scenario == "duplicate_fill":
                        evidence["applied_again"] = p.ingest(f)
                    else:
                        try:
                            p.ingest(replace(f, price=Decimal("101")))
                        except ValueError:
                            evidence["conflict_rejected"] = True
            elif scenario == "unknown_submission":
                p.broker.timeout_after_accept = True
                i = submit("unknown", 10)
                evidence["order_id"] = i.intent_id
            elif scenario == "spam":
                p.risk.policies[strategy] = RiskPolicy(max_orders_per_minute=2)
                for n in range(4):
                    submit(str(n), 1)
            elif scenario == "stale_feed":
                # Explicit mock fixture time; never alters process clocks or financial events.
                with p.store.transaction() as db:
                    db.execute(
                        "UPDATE risk_marks SET received_at=? WHERE symbol='LAB'",
                        (p.clock() - p.reliability.max_feed_age - 1,),
                    )
                    p.store.audit("FAILURE_LAB_STALE_FEED", {"symbol": "LAB"})
                submit("stale", 1)
            elif scenario == "drift":
                p.broker.external_positions[("failure-lab", "INJECTED")] = 7
                p.broker.persist()
                p.reliability.reconcile()
            if scenario in {
                "partial",
                "rejection",
                "position_limit",
                "duplicate_fill",
                "spam",
            }:
                p.reliability.reconcile()
        with p.store.transaction():
            p.store.audit("FAILURE_LAB", {"scenario": scenario, "evidence": evidence})
        return {
            "scenario": scenario,
            "decisions": decisions,
            "evidence": evidence,
            "state": p.snapshot(),
        }

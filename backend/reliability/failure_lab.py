"""Deterministic development scenarios; normal intents still pass through risk."""

from decimal import Decimal

from backend.shared.contracts import OrderIntent, Side, Tick


class FailureLab:
    def __init__(self, platform):
        self.platform = platform

    def run(self, scenario):
        p = self.platform
        p.require_offline_demo()
        if scenario not in {"partial", "rejection", "position_limit"}:
            raise ValueError("unknown failure scenario")
        with p.store.lock:
            if not p.store.rows("SELECT id FROM accounts WHERE id='failure-lab'"):
                p.account("failure-lab")
            counter = len(
                p.store.rows("SELECT id FROM subscriptions WHERE account='failure-lab'")
            )
            strategy = f"lab-{scenario}-{counter}"
            p.strategies.subscribe("failure-lab", strategy, "momentum", "LAB")
            p.tick(Tick("LAB", int(p.clock()), Decimal("100"), 0, strategy + ":mark"))
            p.reliability.resume()
            decisions = []

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
                d = p.risk.submit(i)
                decisions.append(d)
                return i

            if scenario == "partial":
                i = submit("partial", 100)
                p.ingest(p.broker.execute(i.intent_id, 40, Decimal("100"), p.clock()))
            elif scenario == "rejection":
                p.broker.reject_next = True
                submit("reject", 5)
            else:
                i = submit("filled", 80)
                p.ingest(p.broker.execute(i.intent_id, 80, Decimal("100"), p.clock()))
                submit("pending", 20)
                submit("blocked", 10)
            p.reliability.reconcile()
            return {"scenario": scenario, "decisions": decisions, "state": p.snapshot()}

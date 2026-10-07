from collections.abc import MutableMapping
from decimal import Decimal

from backend.shared.contracts import RiskPolicy


class PolicyRepository(MutableMapping):
    """Mapping compatibility with durable, validated policy updates."""

    def __init__(self, store):
        self.store = store

    def __getitem__(self, strategy):
        rows = self.store.rows(
            "SELECT * FROM risk_policies WHERE strategy=?", (strategy,)
        )
        if not rows:
            raise KeyError(strategy)
        p = rows[0]
        return RiskPolicy(
            Decimal(p["max_daily_loss"]), p["max_position"], p["max_orders_per_minute"]
        )

    def __setitem__(self, strategy, policy):
        if not isinstance(policy, RiskPolicy):
            raise ValueError("canonical RiskPolicy required")
        with self.store.transaction() as db:
            if not db.execute(
                "SELECT id FROM subscriptions WHERE id=?", (strategy,)
            ).fetchone():
                raise ValueError("strategy is not subscribed")
            db.execute(
                "INSERT INTO risk_policies VALUES (?,?,?,?) ON CONFLICT(strategy) DO UPDATE SET "
                "max_daily_loss=excluded.max_daily_loss,max_position=excluded.max_position,"
                "max_orders_per_minute=excluded.max_orders_per_minute",
                (
                    strategy,
                    str(policy.max_daily_loss),
                    policy.max_position,
                    policy.max_orders_per_minute,
                ),
            )
            self.store.audit(
                "RISK_POLICY_UPDATED", {"strategy": strategy, "policy": policy.__dict__}
            )

    def __delitem__(self, strategy):
        raise ValueError("risk policies cannot be deleted; update explicit limits")

    def __iter__(self):
        return iter(
            r["strategy"] for r in self.store.rows("SELECT strategy FROM risk_policies")
        )

    def __len__(self):
        return len(self.store.rows("SELECT strategy FROM risk_policies"))

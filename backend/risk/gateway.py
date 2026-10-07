from backend.shared.contracts import (
    OrderStatus,
    RiskDecision,
    RiskPolicy,
    Side,
    TERMINAL,
)


class RiskGateway:
    def __init__(self, store, ledger, manager, clock):
        self.store, self.ledger, self.manager, self.clock = (
            store,
            ledger,
            manager,
            clock,
        )
        self.state = "RECOVERING"
        self.policies = {}

    def submit(self, intent):
        # One lock spans check, reservation, dispatch and kill gate transitions.
        with self.store.lock:
            reason, projected = self._check(intent)
            decision = RiskDecision(
                intent.intent_id, not reason, reason or "ALLOWED", projected
            )
            with self.store.transaction() as db:
                self.store.audit("RISK_DECISION", decision.__dict__)
                if reason:
                    return decision
                db.execute(
                    "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,0,0)",
                    (
                        intent.intent_id,
                        intent.strategy_instance_id,
                        intent.account_id,
                        intent.symbol,
                        intent.side.value,
                        intent.quantity,
                        self.clock(),
                        OrderStatus.RESERVED,
                    ),
                )
            try:
                self.manager.submit_reserved(intent)
            except Exception:
                self.state = "UNCERTAIN"
            return decision

    def _check(self, intent):
        if self.state != "RUNNING":
            return "RISK_GLOBAL_GATE", None
        if self.store.rows("SELECT id FROM orders WHERE id=?", (intent.intent_id,)):
            return "RISK_DUPLICATE_INTENT", None
        subscriptions = self.store.rows(
            "SELECT enabled FROM subscriptions WHERE id=? AND account=? AND symbol=?",
            (intent.strategy_instance_id, intent.account_id, intent.symbol),
        )
        if not subscriptions:
            return "RISK_NOT_SUBSCRIBED", None
        if not subscriptions[0]["enabled"]:
            return "RISK_STRATEGY_STOPPED", None
        policy = self.policies.get(intent.strategy_instance_id, RiskPolicy())
        now = self.clock()
        if (
            self.ledger.daily_net(intent.account_id, intent.strategy_instance_id, now)
            <= -policy.max_daily_loss
        ):
            return "RISK_MAX_DAILY_LOSS", None
        orders = self.store.rows(
            "SELECT * FROM orders WHERE strategy=? AND account=? AND emergency=0",
            (intent.strategy_instance_id, intent.account_id),
        )
        if (
            sum(now - 60 < o["created"] <= now for o in orders)
            >= policy.max_orders_per_minute
        ):
            return "RISK_RATE_LIMIT", None
        q = self.ledger.quantity(
            intent.account_id, intent.strategy_instance_id, intent.symbol
        )
        buys = sells = 0
        for o in orders:
            if o["symbol"] == intent.symbol and o["status"] not in TERMINAL:
                if o["side"] == Side.BUY:
                    buys += o["quantity"] - o["filled"]
                else:
                    sells += o["quantity"] - o["filled"]
        if intent.side == Side.BUY:
            buys += intent.quantity
        else:
            sells += intent.quantity
        # Opposing pending orders cannot be assumed to offset each other.
        projected = max(abs(q + buys), abs(q - sells))
        return (
            "RISK_MAX_POSITION" if projected > policy.max_position else ""
        ), projected

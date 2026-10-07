from backend.shared.contracts import (
    OrderStatus,
    RiskDecision,
    RiskPolicy,
    Side,
    TERMINAL,
    GlobalTradingState,
    StrategyState,
)
from backend.risk.policies import PolicyRepository


class RiskGateway:
    def __init__(self, store, ledger, manager, clock):
        self.store, self.ledger, self.manager, self.clock = (
            store,
            ledger,
            manager,
            clock,
        )
        self.state = GlobalTradingState.RECOVERING
        self.policies = PolicyRepository(store)

    def strategy_state(self, strategy):
        rows = self.store.rows(
            "SELECT state FROM strategy_controls WHERE strategy=?", (strategy,)
        )
        return StrategyState(rows[0]["state"]) if rows else StrategyState.RUNNING

    def set_strategy_state(self, strategy, state, reason="operator"):
        state = StrategyState(state)
        with self.store.transaction() as db:
            sub = db.execute(
                "SELECT account FROM subscriptions WHERE id=?", (strategy,)
            ).fetchone()
            if sub is None:
                raise ValueError("strategy is not subscribed")
            if state == StrategyState.RUNNING:
                policy = self.policies.get(strategy, RiskPolicy())
                if (
                    self.ledger.daily_net(sub["account"], strategy, self.clock())
                    <= -policy.max_daily_loss
                ):
                    raise ValueError("daily loss still breached")
            db.execute(
                "INSERT INTO strategy_controls VALUES (?,?,?,?) ON CONFLICT(strategy) DO UPDATE SET state=excluded.state,reason=excluded.reason,updated=excluded.updated",
                (strategy, state, reason, self.clock()),
            )
            self.store.audit(
                "STRATEGY_STATE_CHANGED",
                {"strategy": strategy, "state": state, "reason": reason},
            )

    def budget(self, account, strategy, symbol):
        policy = self.policies.get(strategy, RiskPolicy())
        q = self.ledger.quantity(account, strategy, symbol)
        orders = self.store.rows(
            "SELECT * FROM orders WHERE strategy=? AND account=? AND emergency=0",
            (strategy, account),
        )
        buys = sum(
            o["quantity"] - o["filled"]
            for o in orders
            if o["symbol"] == symbol
            and o["side"] == Side.BUY
            and o["status"] not in TERMINAL
        )
        sells = sum(
            o["quantity"] - o["filled"]
            for o in orders
            if o["symbol"] == symbol
            and o["side"] == Side.SELL
            and o["status"] not in TERMINAL
        )
        now = self.clock()
        rate = sum(now - 60 < o["created"] <= now for o in orders)
        loss = max(-self.ledger.daily_net(account, strategy, now), 0)
        return {
            "strategy_instance_id": strategy,
            "account_id": account,
            "symbol": symbol,
            "state": self.strategy_state(strategy),
            "policy": policy.__dict__,
            "position": {
                "limit": policy.max_position,
                "filled": q,
                "reserved_buy": buys,
                "reserved_sell": sells,
                "used": max(abs(q + buys), abs(q - sells)),
                "available_buy": max(0, policy.max_position - q - buys),
                "available_sell": max(0, policy.max_position + q - sells),
            },
            "daily_loss": {
                "limit": policy.max_daily_loss,
                "consumed": loss,
                "remaining": max(policy.max_daily_loss - loss, 0),
            },
            "rate": {
                "limit": policy.max_orders_per_minute,
                "consumed": rate,
                "remaining": max(policy.max_orders_per_minute - rate, 0),
            },
        }

    def submit(self, intent):
        # One lock spans check, reservation, dispatch and kill gate transitions.
        with self.store.lock:
            reason, projected = self._check(intent)
            decision = RiskDecision(
                intent.intent_id,
                not reason,
                reason or "ALLOWED",
                projected,
                reason.replace("_", " ").lower()
                if reason
                else "platform risk approved",
                (reason or "ALL_RULES_PASSED",),
                self.clock(),
                intent.intent_id if not reason else None,
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
        if not self.store.rows(
            "SELECT id FROM subscriptions WHERE id=? AND account=? AND symbol=?",
            (intent.strategy_instance_id, intent.account_id, intent.symbol),
        ):
            return "RISK_NOT_SUBSCRIBED", None
        policy = self.policies.get(intent.strategy_instance_id, RiskPolicy())
        now = self.clock()
        if (
            self.ledger.daily_net(intent.account_id, intent.strategy_instance_id, now)
            <= -policy.max_daily_loss
        ):
            self.set_strategy_state(
                intent.strategy_instance_id,
                StrategyState.LOSS_HALTED,
                "RISK_MAX_DAILY_LOSS",
            )
            return "RISK_MAX_DAILY_LOSS", None
        if self.strategy_state(intent.strategy_instance_id) != StrategyState.RUNNING:
            return "RISK_STRATEGY_HALTED", None
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

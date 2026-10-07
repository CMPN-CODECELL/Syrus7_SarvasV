from backend.shared.contracts import (
    OrderStatus,
    RiskDecision,
    RiskPolicy,
    Side,
    GlobalTradingState,
    StrategyState,
)
from backend.risk.policies import PolicyRepository
from backend.reliability.state import SafetyRepository
from threading import Event
from backend.execution.orders import SubmissionBlocked


class RiskGateway:
    def __init__(self, store, ledger, manager, clock):
        self.store, self.ledger, self.manager, self.clock = (
            store,
            ledger,
            manager,
            clock,
        )
        self.safety = SafetyRepository(store)
        self.kill_requested = Event()
        if self.safety.get("kill_latched", False):
            self.kill_requested.set()
        self._state = GlobalTradingState.RECOVERING
        self.state = GlobalTradingState.RECOVERING
        self.policies = PolicyRepository(store)
        self.evidence_gate = lambda intent: "RISK_NO_HEALTH_EVIDENCE"
        self.on_uncertain = lambda code: setattr(
            self, "state", GlobalTradingState.UNCERTAIN
        )
        self.manager.authorize_dispatch = self.authorize_dispatch

    def authorize_dispatch(self, intent, row):
        if row["emergency"]:
            return self.state == GlobalTradingState.KILLING and self.safety.get(
                "kill_latched", False
            )
        return (
            not self.kill_requested.is_set()
            and not self.safety.get("kill_latched", False)
            and self.state
            in {GlobalTradingState.RUNNING, GlobalTradingState.REDUCE_ONLY}
        )

    def authorize_emergency(self, intent):
        with self.store.transaction() as db:
            q = self.ledger.quantity(
                intent.account_id, intent.strategy_instance_id, intent.symbol
            )
            pending = db.execute(
                "SELECT id FROM orders WHERE account=? AND strategy=? AND symbol=? AND status NOT IN ('FILLED','CANCELLED','REJECTED')",
                (intent.account_id, intent.strategy_instance_id, intent.symbol),
            ).fetchone()
            if (
                self.state != GlobalTradingState.KILLING
                or not self.safety.get("kill_latched", False)
                or pending
                or q * intent.side.sign >= 0
                or intent.quantity > abs(q)
            ):
                raise ValueError("emergency intent is not a verified reducing exit")
            decision = RiskDecision(
                intent.intent_id,
                True,
                "EMERGENCY_REDUCING_EXIT",
                q + intent.side.sign * intent.quantity,
                created_at=self.clock(),
                reservation_id=intent.intent_id,
            )
            self.store.audit("RISK_DECISION", decision.__dict__)
            self.store.audit("EMERGENCY_AUTHORIZED", {"intent_id": intent.intent_id})
            db.execute(
                "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) VALUES (?,?,?,?,?,?,?,?,0,1,0)",
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
            return decision

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        value = GlobalTradingState(value)
        with self.store.transaction():
            previous = self.safety.get("gate")
            self._state = value
            self.safety.set("gate", value)
            if previous != value:
                self.store.audit(
                    "GLOBAL_GATE_CHANGED", {"previous": previous, "state": value}
                )

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
        now = self.clock()
        usage = self.store.rows(
            """SELECT
            COALESCE(SUM(CASE WHEN symbol=? AND side='BUY' AND status NOT IN ('FILLED','CANCELLED','REJECTED') THEN quantity-filled ELSE 0 END),0) AS buys,
            COALESCE(SUM(CASE WHEN symbol=? AND side='SELL' AND status NOT IN ('FILLED','CANCELLED','REJECTED') THEN quantity-filled ELSE 0 END),0) AS sells,
            COALESCE(SUM(CASE WHEN created>? AND created<=? THEN 1 ELSE 0 END),0) AS rate
            FROM orders WHERE strategy=? AND account=? AND emergency=0""",
            (symbol, symbol, now - 60, now, strategy, account),
        )[0]
        buys, sells, rate = usage["buys"], usage["sells"], usage["rate"]
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
        # Atomically reserve; network waits never hold the control-plane lock.
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
                    "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) VALUES (?,?,?,?,?,?,?,?,0,0,0)",
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
        except SubmissionBlocked:
            pass
        except Exception:
            self.on_uncertain("SUBMISSION_UNKNOWN")
        return decision

    def _check(self, intent):
        if self.kill_requested.is_set():
            return "RISK_GLOBAL_GATE", None
        if self.state not in {
            GlobalTradingState.RUNNING,
            GlobalTradingState.REDUCE_ONLY,
        } or self.safety.get("kill_latched", False):
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
        unsafe = self.evidence_gate(intent)
        if unsafe:
            return unsafe, None
        budget = self.budget(
            intent.account_id, intent.strategy_instance_id, intent.symbol
        )
        q = budget["position"]["filled"]
        reducing = (
            not budget["position"]["reserved_buy"]
            and not budget["position"]["reserved_sell"]
            and q * intent.side.sign < 0
            and intent.quantity <= abs(q)
        )
        reduce_only = self.state == GlobalTradingState.REDUCE_ONLY
        if reduce_only and not reducing:
            return "RISK_NOT_REDUCING", None
        if budget["daily_loss"]["consumed"] >= policy.max_daily_loss:
            self.set_strategy_state(
                intent.strategy_instance_id,
                StrategyState.LOSS_HALTED,
                "RISK_MAX_DAILY_LOSS",
            )
            if not (reduce_only and reducing):
                return "RISK_MAX_DAILY_LOSS", None
        strategy_state = self.strategy_state(intent.strategy_instance_id)
        if strategy_state == StrategyState.HALTED or (
            strategy_state == StrategyState.LOSS_HALTED
            and not (reduce_only and reducing)
        ):
            return "RISK_STRATEGY_HALTED", None
        if budget["rate"]["consumed"] >= policy.max_orders_per_minute:
            return "RISK_RATE_LIMIT", None
        buys, sells = (
            budget["position"]["reserved_buy"],
            budget["position"]["reserved_sell"],
        )
        if intent.side == Side.BUY:
            buys += intent.quantity
        else:
            sells += intent.quantity
        # Opposing pending orders cannot be assumed to offset each other.
        projected = max(abs(q + buys), abs(q - sells))
        return (
            "RISK_MAX_POSITION"
            if projected > policy.max_position and not (reduce_only and reducing)
            else ""
        ), projected

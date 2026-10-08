from dataclasses import dataclass, field
from decimal import Decimal
from time import perf_counter
from threading import Event

from backend.shared.contracts import (
    OrderStatus,
    RiskDecision,
    RiskPolicy,
    Side,
    GlobalTradingState,
    StrategyState,
)
from backend.risk.policies import PolicyRepository
from backend.risk.account_policies import AccountPolicyRepository
from backend.reliability.state import SafetyRepository
from backend.execution.orders import SubmissionBlocked


@dataclass
class RiskCheckResult:
    reason_code: str = ""
    projected_position: int | None = None
    reason_text: str = "platform risk approved"
    rule_results: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)


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
        self.account_policies = AccountPolicyRepository(store)
        self.metrics = None
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
        started = perf_counter()
        # Atomically reserve; network waits never hold the control-plane lock.
        with self.store.lock:
            result = self._check(intent)
            decision = RiskDecision(
                intent.intent_id,
                not result.reason_code,
                result.reason_code or "ALLOWED",
                result.projected_position,
                result.reason_text,
                result.rule_results or ("ALL_RULES_PASSED",),
                self.clock(),
                intent.intent_id if not result.reason_code else None,
                dict(result.details)
                | {
                    "account_id": intent.account_id,
                    "strategy_instance_id": intent.strategy_instance_id,
                    "symbol": intent.symbol,
                },
            )
            with self.store.transaction() as db:
                self.store.audit(
                    "RISK_DECISION", decision.__dict__, correlation_id=intent.intent_id
                )
                if result.reason_code:
                    self._record_metrics(started, False)
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
        self._record_metrics(started, True)
        try:
            self.manager.submit_reserved(intent)
        except SubmissionBlocked:
            pass
        except Exception:
            self.on_uncertain("SUBMISSION_UNKNOWN")
        return decision

    def _record_metrics(self, started, admitted):
        if self.metrics is None:
            return
        try:
            self.metrics.counter("risk_decisions_total")
            if admitted:
                self.metrics.counter("orders_admitted_total")
            self.metrics.observe(
                "risk_decision_latency_ms", (perf_counter() - started) * 1000
            )
        except Exception:
            pass

    def account_budget(self, account, symbol, incoming=None):
        positions = {
            strategy: position.net_quantity
            for (
                row_account,
                strategy,
                row_symbol,
            ), position in self.ledger.positions().items()
            if row_account == account and row_symbol == symbol
        }
        pending = self.store.rows(
            "SELECT strategy,side,quantity-filled AS remaining FROM orders "
            "WHERE account=? AND symbol=? AND emergency=0 "
            "AND status NOT IN ('FILLED','CANCELLED','REJECTED')",
            (account, symbol),
        )
        exposure = {strategy: {"buy": 0, "sell": 0} for strategy in positions}
        for row in pending:
            values = exposure.setdefault(row["strategy"], {"buy": 0, "sell": 0})
            values[row["side"].lower()] += row["remaining"]
        if incoming is not None:
            values = exposure.setdefault(
                incoming.strategy_instance_id, {"buy": 0, "sell": 0}
            )
            values[incoming.side.value.lower()] += incoming.quantity
            positions.setdefault(incoming.strategy_instance_id, 0)
        net_filled = sum(positions.values())
        total_buys = sum(item["buy"] for item in exposure.values())
        total_sells = sum(item["sell"] for item in exposure.values())
        net_projected = max(abs(net_filled + total_buys), abs(net_filled - total_sells))
        gross_filled = sum(abs(quantity) for quantity in positions.values())
        gross_projected = sum(
            max(
                abs(positions.get(strategy, 0) + values["buy"]),
                abs(positions.get(strategy, 0) - values["sell"]),
            )
            for strategy, values in exposure.items()
        )
        policy = self.account_policies.get(account)
        return {
            "account_id": account,
            "symbol": symbol,
            "net_filled": net_filled,
            "net_projected": net_projected,
            "gross_virtual": gross_filled,
            "gross_projected": gross_projected,
            "net_limit": policy.max_net_position_per_symbol,
            "gross_limit": policy.max_gross_virtual_position_per_symbol,
        }

    def _check(self, intent):
        passed = []

        def reject(code, text, *, projected=None, details=None, rule=None):
            return RiskCheckResult(
                code,
                projected,
                text,
                tuple(passed + [f"{rule or code}:FAIL"]),
                details or {},
            )

        if self.kill_requested.is_set():
            return reject(
                "RISK_GLOBAL_GATE",
                "REJECTED — GLOBAL GATE: Kill is latched; new strategy exposure is blocked.",
                details={"gate": self.state, "kill_latched": True},
                rule="GLOBAL_GATE",
            )
        if self.state not in {
            GlobalTradingState.RUNNING,
            GlobalTradingState.REDUCE_ONLY,
        } or self.safety.get("kill_latched", False):
            return reject(
                "RISK_GLOBAL_GATE",
                "REJECTED — GLOBAL GATE: The global trading gate does not permit new exposure.",
                details={
                    "gate": self.state,
                    "kill_latched": self.safety.get("kill_latched", False),
                },
                rule="GLOBAL_GATE",
            )
        passed.append("GLOBAL_GATE:PASS")
        if self.store.rows("SELECT id FROM orders WHERE id=?", (intent.intent_id,)):
            return reject(
                "RISK_DUPLICATE_INTENT",
                "The intent ID already exists and cannot be replayed.",
                details={"intent_id": intent.intent_id},
                rule="DUPLICATE_INTENT",
            )
        passed.append("DUPLICATE_INTENT:PASS")
        subscriptions = self.store.rows(
            "SELECT enabled FROM subscriptions WHERE id=? AND account=? AND symbol=?",
            (intent.strategy_instance_id, intent.account_id, intent.symbol),
        )
        if not subscriptions:
            return reject(
                "RISK_NOT_SUBSCRIBED",
                "The strategy is not subscribed to this account and symbol.",
                details={
                    "strategy_instance_id": intent.strategy_instance_id,
                    "account_id": intent.account_id,
                    "symbol": intent.symbol,
                },
                rule="SUBSCRIPTION",
            )
        if not subscriptions[0]["enabled"]:
            return reject(
                "RISK_STRATEGY_STOPPED",
                "The strategy subscription is stopped.",
                details={"strategy_instance_id": intent.strategy_instance_id},
                rule="SUBSCRIPTION",
            )
        passed.append("SUBSCRIPTION:PASS")
        policy = self.policies.get(intent.strategy_instance_id, RiskPolicy())
        unsafe = self.evidence_gate(intent)
        if unsafe:
            unsafe_texts = {
                "RISK_RECONCILIATION_REQUIRED": "REJECTED — RECONCILIATION REQUIRED: System requires verified broker reconciliation",
                "RISK_STALE_BROKER_STATE": "REJECTED — STALE BROKER STATE: Broker snapshot exceeds freshness threshold",
                "RISK_STALE_MARKET_DATA": "REJECTED — STALE MARKET DATA: Feed age exceeds 15-second freshness threshold",
                "RISK_MARKET_HALTED": "REJECTED — MARKET HALTED: Market trading is currently halted",
                "RISK_MARKET_CLOSED": "REJECTED — MARKET CLOSED: Market session is closed",
            }
            return reject(
                unsafe,
                unsafe_texts.get(unsafe, f"REJECTED — SAFETY GATE: {unsafe}"),
                details={"gate": self.state, "health_reason": unsafe},
                rule="HEALTH_EVIDENCE",
            )
        passed.append("HEALTH_EVIDENCE:PASS")
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
            return reject(
                "RISK_NOT_REDUCING",
                "The gate is reduce-only and this intent would not strictly reduce exposure.",
                details={
                    "filled": q,
                    "requested_side": intent.side,
                    "requested_quantity": intent.quantity,
                },
                rule="REDUCE_ONLY",
            )
        passed.append("REDUCE_ONLY:PASS")
        if budget["daily_loss"]["consumed"] >= policy.max_daily_loss:
            self.set_strategy_state(
                intent.strategy_instance_id,
                StrategyState.LOSS_HALTED,
                "RISK_MAX_DAILY_LOSS",
            )
            if not (reduce_only and reducing):
                return reject(
                    "RISK_MAX_DAILY_LOSS",
                    "The strategy daily loss has reached its configured maximum.",
                    details={
                        "current_loss": str(budget["daily_loss"]["consumed"]),
                        "limit": str(policy.max_daily_loss),
                    },
                    rule="DAILY_LOSS",
                )
        passed.append("DAILY_LOSS:PASS")
        strategy_state = self.strategy_state(intent.strategy_instance_id)
        if strategy_state == StrategyState.HALTED or (
            strategy_state == StrategyState.LOSS_HALTED
            and not (reduce_only and reducing)
        ):
            return reject(
                "RISK_STRATEGY_HALTED",
                "The strategy risk state is halted.",
                details={"strategy_state": strategy_state},
                rule="STRATEGY_STATE",
            )
        passed.append("STRATEGY_STATE:PASS")
        if budget["rate"]["consumed"] >= policy.max_orders_per_minute:
            return reject(
                "RISK_RATE_LIMIT",
                "REJECTED — RATE LIMIT: "
                f"Consumed: {budget['rate']['consumed']}, Requested: 1, "
                f"Limit: {policy.max_orders_per_minute} orders/min",
                details={
                    "current": budget["rate"]["consumed"],
                    "requested": 1,
                    "projected": budget["rate"]["consumed"] + 1,
                    "limit": policy.max_orders_per_minute,
                },
                rule="RATE_LIMIT",
            )
        passed.append("RATE_LIMIT:PASS")
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
        if projected > policy.max_position and not reducing:
            return reject(
                "RISK_MAX_POSITION",
                "REJECTED — POSITION LIMIT: "
                f"Current: {q}, Pending: {budget['position']['reserved_buy'] + budget['position']['reserved_sell']}, "
                f"Requested: {intent.quantity}, Projected: {projected}, "
                f"Limit: {policy.max_position}",
                projected=projected,
                details={
                    "filled": q,
                    "reserved_buy": budget["position"]["reserved_buy"],
                    "reserved_sell": budget["position"]["reserved_sell"],
                    "requested_side": intent.side,
                    "requested_quantity": intent.quantity,
                    "projected": projected,
                    "limit": policy.max_position,
                    "available_buy": budget["position"]["available_buy"],
                    "available_sell": budget["position"]["available_sell"],
                },
                rule="MAX_POSITION",
            )
        passed.append("MAX_POSITION:PASS")

        account_before = self.account_budget(intent.account_id, intent.symbol)
        account_after = self.account_budget(intent.account_id, intent.symbol, intent)
        account_reducing = (
            account_after["net_projected"] <= account_before["net_projected"]
            and account_after["gross_projected"] <= account_before["gross_projected"]
        )
        account_details = dict(account_after) | {
            "requested_side": intent.side,
            "requested_quantity": intent.quantity,
        }
        if (
            account_after["net_limit"] is not None
            and account_after["net_projected"] > account_after["net_limit"]
            and not account_reducing
        ):
            return reject(
                "RISK_ACCOUNT_NET_POSITION",
                "Projected account net position would exceed its configured maximum.",
                projected=projected,
                details=account_details,
                rule="ACCOUNT_NET_POSITION",
            )
        passed.append("ACCOUNT_NET_POSITION:PASS")
        if (
            account_after["gross_limit"] is not None
            and account_after["gross_projected"] > account_after["gross_limit"]
            and not account_reducing
        ):
            return reject(
                "RISK_ACCOUNT_GROSS_POSITION",
                "Projected account gross virtual exposure would exceed its configured maximum.",
                projected=projected,
                details=account_details,
                rule="ACCOUNT_GROSS_POSITION",
            )
        passed.append("ACCOUNT_GROSS_POSITION:PASS")

        if intent.order_type == "LIMIT":
            marks = self.store.rows(
                "SELECT price FROM risk_marks WHERE symbol=?", (intent.symbol,)
            )
            if not marks:
                return reject(
                    "RISK_STALE_MARKET_DATA",
                    "A fresh reference mark is required for a LIMIT order.",
                    details={"symbol": intent.symbol},
                    rule="PRICE_REASONABILITY",
                )
            reference = Decimal(marks[0]["price"])
            deviation_bps = (
                abs(intent.limit_price - reference) / reference * Decimal(10000)
            )
            if deviation_bps > policy.max_price_deviation_bps:
                return reject(
                    "RISK_PRICE_REASONABILITY",
                    "The LIMIT price is too far from the fresh market reference.",
                    projected=projected,
                    details={
                        "reference_price": str(reference),
                        "limit_price": str(intent.limit_price),
                        "deviation_bps": str(deviation_bps),
                        "max_deviation_bps": policy.max_price_deviation_bps,
                    },
                    rule="PRICE_REASONABILITY",
                )
        passed.append("PRICE_REASONABILITY:PASS")
        return RiskCheckResult(
            projected_position=projected,
            rule_results=tuple(passed),
            details={
                "strategy": budget["position"],
                "account": account_after,
            },
        )

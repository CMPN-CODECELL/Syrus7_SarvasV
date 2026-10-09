"""Guarded automatic stock selection and position management.

Auto mode is decision logic only. It never receives a broker reference and all
generated intents still pass through the platform RiskGateway and OrderManager.
No strategy can guarantee profit; the policy uses explicit take-profit and
loss-containment thresholds while reporting HOLD when evidence is insufficient.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from decimal import Decimal
from threading import Lock

from backend.shared.contracts import OrderIntent, Side


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:24] or "stock"


class AutoMode:
    kind = "auto_adaptive"
    managed_kinds = ("auto_adaptive", "auto_momentum")

    def __init__(
        self,
        platform,
        *,
        scan_limit=200,
        max_positions=3,
        lookback=5,
        entry_momentum=Decimal("0.003"),
        take_profit=Decimal("0.01"),
        stop_loss=Decimal("0.005"),
        cooldown_seconds=60,
    ):
        self.platform = platform
        self.scan_limit = int(scan_limit)
        self.max_positions = int(max_positions)
        self.lookback = int(lookback)
        self.entry_momentum = Decimal(entry_momentum)
        self.take_profit = Decimal(take_profit)
        self.stop_loss = Decimal(stop_loss)
        self.cooldown_seconds = int(cooldown_seconds)
        if self.scan_limit < 1 or self.max_positions < 1 or self.lookback < 2:
            raise ValueError("invalid auto-mode bounds")
        if min(self.entry_momentum, self.take_profit, self.stop_loss) <= 0:
            raise ValueError("auto-mode return thresholds must be positive")
        if self.cooldown_seconds < 0:
            raise ValueError("auto-mode cooldown cannot be negative")
        self._lock = Lock()
        self._states = {}
        self._sequence = 0

    def _catalogue_candidates(self):
        adapter = getattr(self.platform.broker_calls, "adapter", self.platform.broker)
        if hasattr(adapter, "all_market_symbols"):
            symbols = tuple(adapter.all_market_symbols())
        else:
            evidence = self.platform.market_data_evidence()
            symbols = tuple(
                dict.fromkeys(
                    [
                        *evidence.get("canonical_symbols", ()),
                        *evidence.get("symbols", ()),
                        *(
                            row["symbol"]
                            for row in self.platform.store.rows(
                                "SELECT DISTINCT symbol FROM subscriptions ORDER BY symbol"
                            )
                        ),
                    ]
                )
            )
        symbols = tuple(symbol for symbol in symbols if symbol)
        if len(symbols) <= self.scan_limit:
            return symbols
        # Provider adapters may rank their catalogue by execution suitability
        # (021 uses its freeze-quantity metadata as a liquidity proxy).
        return symbols[: self.scan_limit]

    def start(self, account_id, *, audit_type="AUTO_MODE_STARTED"):
        candidates = self._catalogue_candidates()
        if not candidates:
            raise ValueError("auto mode found no broker-supported stocks to scan")
        with self._lock:
            current = self._states.get(account_id, {})
            self._states[account_id] = {
                "enabled": True,
                "candidates": candidates,
                "history": current.get("history", {}),
                "decisions": current.get("decisions", {}),
                "last_action": current.get("last_action", {}),
                "last_order_at": current.get("last_order_at", {}),
                "last_attempt_at": current.get("last_attempt_at"),
                "started_at": self.platform.clock(),
            }
        with self.platform.store.transaction():
            self.platform.store.audit(
                audit_type,
                {
                    "account": account_id,
                    "candidate_count": len(candidates),
                    "scan_limit": self.scan_limit,
                    "max_positions": self.max_positions,
                },
            )
        self.platform.refresh_external_market_universe()
        return self.evidence(account_id)

    def restore(self):
        """Restore explicitly active scanners without reopening the trading gate."""
        latest = {}
        for row in self.platform.store.rows(
            "SELECT type,payload FROM audit WHERE type IN "
            "('AUTO_MODE_STARTED','AUTO_MODE_RESTORED','AUTO_MODE_STOPPED') "
            "ORDER BY sequence"
        ):
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            account_id = payload.get("account")
            if account_id:
                latest[account_id] = row["type"]
        restored = []
        for account_id, event_type in latest.items():
            if event_type != "AUTO_MODE_STOPPED":
                self.start(account_id, audit_type="AUTO_MODE_RESTORED")
                restored.append(account_id)
        return tuple(restored)

    def stop(self, account_id):
        with self._lock:
            state = self._states.get(account_id)
            if state:
                state["enabled"] = False
        for row in self.platform.store.rows(
            "SELECT id FROM subscriptions WHERE account=? "
            "AND kind IN ('auto_adaptive','auto_momentum') AND enabled=1",
            (account_id,),
        ):
            self.platform.strategies.set_enabled(account_id, row["id"], False)
        with self.platform.store.transaction():
            self.platform.store.audit("AUTO_MODE_STOPPED", {"account": account_id})
        self.platform.refresh_external_market_universe()
        return self.evidence(account_id)

    def market_symbols(self):
        with self._lock:
            return tuple(
                dict.fromkeys(
                    symbol
                    for state in self._states.values()
                    if state.get("enabled")
                    for symbol in state.get("candidates", ())
                )
            )

    def _strategy_id(self, account_id, symbol):
        account_hash = hashlib.sha256(account_id.encode()).hexdigest()[:8]
        return f"auto-{account_hash}-{_slug(symbol)}"

    def _ensure_subscription(self, account_id, symbol):
        strategy_id = self._strategy_id(account_id, symbol)
        rows = self.platform.store.rows(
            "SELECT * FROM subscriptions WHERE id=?", (strategy_id,)
        )
        if not rows:
            self.platform.strategies.subscribe(
                account_id, strategy_id, self.kind, symbol
            )
        elif (
            rows[0]["account"] != account_id
            or rows[0]["kind"] not in self.managed_kinds
        ):
            raise ValueError("auto strategy identity collision")
        elif not rows[0]["enabled"]:
            self.platform.strategies.set_enabled(account_id, strategy_id, True)
        return strategy_id

    def _select_subscription(self, account_id, symbol, selected_strategy):
        """Persist the currently selected Auto attribution before any order exists.

        Auto's policy family is evidence attached to one guarded auto instance;
        it is not registered as a second runnable strategy because that would
        emit duplicate intents for the same market observation.
        """
        strategy_id = self._ensure_subscription(account_id, symbol)
        for row in self.platform.store.rows(
            "SELECT id,symbol FROM subscriptions WHERE account=? AND id<>? "
            "AND kind IN ('auto_adaptive','auto_momentum') AND enabled=1",
            (account_id, strategy_id),
        ):
            position = self.platform.ledger.positions().get(
                (account_id, row["id"], row["symbol"])
            )
            if (position and position.net_quantity) or self._open_order(
                account_id, row["id"], row["symbol"]
            ):
                continue
            self.platform.strategies.set_enabled(account_id, row["id"], False)
        with self._lock:
            state = self._states[account_id]
            state["selected_symbol"] = symbol
            state["selected_strategy"] = selected_strategy
            state["selected_strategy_instance_id"] = strategy_id
        return strategy_id

    def readiness_for(self, account_id, symbol):
        """Return quote-observation readiness for an Auto-managed instance."""
        with self._lock:
            state = self._states.get(account_id) or {}
            samples = len((state.get("history") or {}).get(symbol, ()))
        return {
            "samples": min(samples, self.lookback),
            "warmup": self.lookback,
            "ready": samples >= self.lookback,
            "evidence": "NORMALIZED_MARKET_UPDATES",
        }

    def _open_order(self, account_id, strategy_id, symbol):
        return bool(
            self.platform.store.rows(
                "SELECT id FROM orders WHERE account=? AND strategy=? AND symbol=? "
                "AND status NOT IN ('FILLED','CANCELLED','REJECTED') LIMIT 1",
                (account_id, strategy_id, symbol),
            )
        )

    def _position_count(self, account_id):
        return sum(
            position.net_quantity != 0
            for (
                account,
                strategy,
                _,
            ), position in self.platform.ledger.positions().items()
            if account == account_id and strategy.startswith("auto-")
        )

    def _record(
        self,
        account_id,
        symbol,
        action,
        reason,
        score,
        now,
        *,
        selected_strategy=None,
        strategy_scores=None,
    ):
        decision = {
            "account": account_id,
            "symbol": symbol,
            "action": action,
            "reason": reason,
            "momentum": str(score) if score is not None else None,
            "selected_strategy": selected_strategy,
            "selected_score": (
                str((strategy_scores or {})[selected_strategy])
                if selected_strategy in (strategy_scores or {})
                else None
            ),
            "strategy_scores": {
                key: str(value) for key, value in (strategy_scores or {}).items()
            },
            "observed_at": now,
        }
        audit = False
        with self._lock:
            state = self._states[account_id]
            previous = state["last_action"].get(symbol)
            state["decisions"][symbol] = decision
            state["last_action"][symbol] = action
            audit = previous != action and action in {"BUY", "SELL"}
        if audit:
            with self.platform.store.transaction():
                self.platform.store.audit("AUTO_MODE_DECISION", decision)
        return decision

    def _strategy_opportunity(self, values):
        """Choose the strongest positive edge among three simple policy families."""
        first, previous, current = values[0], values[-2], values[-1]
        prior = values[:-1]
        momentum = current / first - Decimal(1)
        breakout = current / max(prior) - Decimal(1)
        prior_mean = sum(prior, Decimal(0)) / len(prior)
        mean_reversion = (
            prior_mean / current - Decimal(1)
            if current > previous and current < prior_mean
            else Decimal(0)
        )
        scores = {
            "momentum": momentum,
            "breakout": breakout,
            "mean_reversion": mean_reversion,
        }
        selected = max(scores, key=scores.get)
        return selected, scores[selected], scores

    def on_tick(self, tick):
        now = self.platform.clock()
        intents = []
        with self._lock:
            accounts = [
                account
                for account, state in self._states.items()
                if state.get("enabled") and tick.symbol in state.get("candidates", ())
            ]
        for account_id in accounts:
            with self._lock:
                state = self._states[account_id]
                history = state["history"].setdefault(
                    tick.symbol, deque(maxlen=self.lookback)
                )
                history.append(tick.price)
                histories = {
                    symbol: tuple(values) for symbol, values in state["history"].items()
                }
                last_order_at = state["last_order_at"].get(tick.symbol)

            if len(histories[tick.symbol]) < self.lookback:
                self._record(
                    account_id,
                    tick.symbol,
                    "HOLD",
                    f"warming market evidence {len(histories[tick.symbol])}/{self.lookback}",
                    None,
                    now,
                )
                continue

            opportunities = {
                symbol: self._strategy_opportunity(values)
                for symbol, values in histories.items()
                if len(values) >= self.lookback and values[0] > 0
            }
            selected_strategy, selected_score, strategy_scores = opportunities[
                tick.symbol
            ]
            momentum_score = strategy_scores["momentum"]
            strongest = max(opportunities, key=lambda item: opportunities[item][1])
            minimum_coverage = min(len(state["candidates"]), min(20, self.scan_limit))
            strategy_id = self._strategy_id(account_id, tick.symbol)
            if strongest == tick.symbol and len(opportunities) >= minimum_coverage:
                strategy_id = self._select_subscription(
                    account_id, tick.symbol, selected_strategy
                )
            position = self.platform.ledger.positions().get(
                (account_id, strategy_id, tick.symbol)
            )
            quantity = position.net_quantity if position else 0

            if self._open_order(account_id, strategy_id, tick.symbol):
                self._record(
                    account_id,
                    tick.symbol,
                    "HOLD",
                    "broker order is still open",
                    momentum_score,
                    now,
                    selected_strategy=selected_strategy,
                    strategy_scores=strategy_scores,
                )
                continue
            if (
                last_order_at is not None
                and now - last_order_at < self.cooldown_seconds
            ):
                self._record(
                    account_id,
                    tick.symbol,
                    "HOLD",
                    "cooldown prevents repeated orders",
                    momentum_score,
                    now,
                    selected_strategy=selected_strategy,
                    strategy_scores=strategy_scores,
                )
                continue

            side = None
            reason = "no entry or exit threshold crossed"
            order_quantity = 0
            if quantity > 0:
                change_from_entry = tick.price / position.average_price - Decimal(1)
                if change_from_entry >= self.take_profit:
                    side, order_quantity = Side.SELL, quantity
                    reason = "take-profit threshold reached"
                elif change_from_entry <= -self.stop_loss:
                    side, order_quantity = Side.SELL, quantity
                    reason = "loss-containment threshold reached"
                elif momentum_score <= -(self.entry_momentum / Decimal(2)):
                    side, order_quantity = Side.SELL, quantity
                    reason = "short-term momentum reversed"
                selected_strategy = "position_exit"
            elif quantity < 0:
                # Long-only is the default safety policy; flatten any recovered
                # short attribution rather than increasing it.
                side, order_quantity = Side.BUY, abs(quantity)
                reason = "long-only policy is flattening short exposure"
            else:
                if len(opportunities) < minimum_coverage:
                    reason = (
                        "comparing strategy evidence across stocks "
                        f"{len(opportunities)}/{minimum_coverage}"
                    )
                global_cooldown = state.get("last_attempt_at")
                if (
                    strongest == tick.symbol
                    and len(opportunities) >= minimum_coverage
                    and selected_score >= self.entry_momentum
                    and self._position_count(account_id) < self.max_positions
                    and (
                        global_cooldown is None
                        or now - global_cooldown >= self.cooldown_seconds
                    )
                ):
                    side, order_quantity = Side.BUY, 1
                    reason = (
                        f"{selected_strategy} has the strongest observed edge "
                        "across warmed stocks"
                    )
                elif (
                    strongest == tick.symbol
                    and global_cooldown is not None
                    and now - global_cooldown < self.cooldown_seconds
                ):
                    reason = "account-wide cooldown prevents another entry attempt"

            if side is None:
                self._record(
                    account_id,
                    tick.symbol,
                    "HOLD",
                    reason,
                    momentum_score,
                    now,
                    selected_strategy=selected_strategy,
                    strategy_scores=strategy_scores,
                )
                continue

            strategy_id = self._select_subscription(
                account_id, tick.symbol, selected_strategy
            )
            with self._lock:
                self._sequence += 1
                sequence = self._sequence
                self._states[account_id]["last_order_at"][tick.symbol] = now
                if side == Side.BUY and quantity == 0:
                    self._states[account_id]["last_attempt_at"] = now
            intent = OrderIntent(
                f"{strategy_id}:auto:{int(now)}:{sequence}",
                strategy_id,
                account_id,
                tick.symbol,
                side,
                order_quantity,
                now,
                reason=f"Auto mode [{selected_strategy}]: {reason}",
            )
            recorded = self._record(
                account_id,
                tick.symbol,
                side.value,
                reason,
                momentum_score,
                now,
                selected_strategy=selected_strategy,
                strategy_scores=strategy_scores,
            )
            with self._lock:
                recorded["intent_id"] = intent.intent_id
                recorded["result"] = "PENDING_RISK"
            intents.append(intent)
        return intents

    def record_risk_result(self, intent, decision):
        if not intent.strategy_instance_id.startswith("auto-"):
            return
        with self._lock:
            state = self._states.get(intent.account_id)
            if not state:
                return
            record = state["decisions"].get(intent.symbol)
            if not record or record.get("intent_id") != intent.intent_id:
                return
            record["result"] = "APPROVED" if decision.allowed else "REJECTED"
            record["result_reason"] = decision.reason_code

    def evidence(self, account_id):
        with self._lock:
            state = self._states.get(account_id)
            if not state:
                return {
                    "enabled": False,
                    "candidate_count": 0,
                    "evaluated_count": 0,
                    "decisions": [],
                    "selected_symbol": None,
                    "selected_strategy": None,
                    "selected_strategy_instance_id": None,
                    "policy": self._policy(),
                }
            decisions = sorted(
                state["decisions"].values(),
                key=lambda item: (item["observed_at"], item["symbol"]),
                reverse=True,
            )[:20]
            return {
                "enabled": bool(state["enabled"]),
                "candidate_count": len(state["candidates"]),
                "evaluated_count": len(state["history"]),
                "started_at": state.get("started_at"),
                "selected_symbol": state.get("selected_symbol"),
                "selected_strategy": state.get("selected_strategy"),
                "selected_strategy_instance_id": state.get(
                    "selected_strategy_instance_id"
                ),
                "decisions": decisions,
                "policy": self._policy(),
            }

    def _policy(self):
        return {
            "long_only": True,
            "strategy_selection": ["momentum", "breakout", "mean_reversion"],
            "scan_limit": self.scan_limit,
            "max_positions": self.max_positions,
            "lookback_updates": self.lookback,
            "entry_momentum": str(self.entry_momentum),
            "take_profit": str(self.take_profit),
            "stop_loss": str(self.stop_loss),
            "cooldown_seconds": self.cooldown_seconds,
            "profit_guaranteed": False,
        }

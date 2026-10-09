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
from collections import Counter, deque
from decimal import Decimal
from threading import Lock

from backend.shared.contracts import OrderIntent, Side


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:24] or "stock"


class AutoMode:
    kind = "auto_adaptive"
    managed_kinds = ("auto_adaptive", "auto_momentum")
    CAPTURE_LIMIT = 1000

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
        candidate_allowlist=(),
    ):
        self.platform = platform
        self.scan_limit = int(scan_limit)
        self.max_positions = int(max_positions)
        self.lookback = int(lookback)
        self.entry_momentum = Decimal(entry_momentum)
        self.take_profit = Decimal(take_profit)
        self.stop_loss = Decimal(stop_loss)
        self.cooldown_seconds = int(cooldown_seconds)
        self.candidate_allowlist = tuple(
            dict.fromkeys(
                str(symbol).strip().upper() for symbol in candidate_allowlist if symbol
            )
        )
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
        if self.candidate_allowlist:
            symbols = self.candidate_allowlist
            validator = getattr(self.platform, "validate_external_market_symbols", None)
            if validator is not None:
                validator(symbols)
        elif getattr(adapter, "provider", None) == "021":
            raise ValueError(
                "live Auto mode requires ALGOSHIELD_AUTO_SYMBOLS; "
                "catalogue order and freeze quantity are not suitability evidence"
            )
        elif hasattr(adapter, "all_market_symbols"):
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
        # Offline adapters may expose a deterministic catalogue order. Live 021
        # never reaches this branch because it requires the reviewed allowlist.
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
                "funnel": Counter(),
                "hold_reasons": Counter(),
                "capture": deque(maxlen=self.CAPTURE_LIMIT),
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
            if action == "HOLD":
                state["hold_reasons"][reason] += 1
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
                state["funnel"]["observations"] += 1
                state["funnel"]["evaluations"] += 1
                state["capture"].append(
                    {
                        "sequence": state["funnel"]["observations"],
                        "symbol": tick.symbol,
                        "price": str(tick.price),
                        "event_timestamp": tick.event_timestamp,
                        "received_at": tick.received_at,
                        "event_time_status": tick.event_time_status,
                    }
                )
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

            with self._lock:
                state["funnel"]["ready_evaluations"] += 1

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
                self._states[account_id]["funnel"]["signals"] += 1
                self._states[account_id]["funnel"]["risk_submissions"] += 1
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
            state["funnel"][
                "risk_admitted" if decision.allowed else "risk_rejected"
            ] += 1

    def evaluate_capture(self, account_id):
        """Evaluate ordered captured observations without risk or broker authority."""
        with self._lock:
            state = self._states.get(account_id) or {}
            captured = tuple(state.get("capture") or ())
            candidate_count = len(state.get("candidates") or ())
        event_time_statuses = Counter(
            item.get("event_time_status", "UNKNOWN") for item in captured
        )
        minimum_coverage = min(candidate_count, min(20, self.scan_limit))
        configurations = (
            ("baseline", self.entry_momentum),
            ("diagnostic_half_entry", self.entry_momentum / Decimal(2)),
            ("diagnostic_double_entry", self.entry_momentum * Decimal(2)),
        )
        results = []
        for label, threshold in configurations:
            histories = {}
            signal_count = 0
            cooldown_suppressed = 0
            last_signal_at = None
            for item in captured:
                history = histories.setdefault(
                    item["symbol"], deque(maxlen=self.lookback)
                )
                history.append(Decimal(item["price"]))
                opportunities = {
                    symbol: self._strategy_opportunity(tuple(values))
                    for symbol, values in histories.items()
                    if len(values) >= self.lookback and values[0] > 0
                }
                if (
                    len(opportunities) < minimum_coverage
                    or item["symbol"] not in opportunities
                ):
                    continue
                strongest = max(
                    opportunities, key=lambda symbol: opportunities[symbol][1]
                )
                if (
                    strongest != item["symbol"]
                    or opportunities[strongest][1] < threshold
                ):
                    continue
                observed_at = item["received_at"] or item["event_timestamp"]
                if (
                    last_signal_at is not None
                    and observed_at - last_signal_at < self.cooldown_seconds
                ):
                    cooldown_suppressed += 1
                    continue
                signal_count += 1
                last_signal_at = observed_at
            results.append(
                {
                    "label": label,
                    "entry_momentum_fraction": str(threshold),
                    "entry_momentum_percent": str(threshold * Decimal(100)),
                    "entry_signals": signal_count,
                    "cooldown_suppressed": cooldown_suppressed,
                }
            )
        return {
            "mode": "EVALUATION_ONLY",
            "dispatch_authority": False,
            "capture_count": len(captured),
            "capture_limit": self.CAPTURE_LIMIT,
            "ordered": True,
            "gaps_known": False,
            "event_time_status_counts": dict(event_time_statuses),
            "usable_for_live_threshold_assessment": bool(captured)
            and set(event_time_statuses) == {"VERIFIED"},
            "scope": "ENTRY_SIGNALS_ONLY_NO_FILL_OR_EXIT_SIMULATION",
            "status": (
                "AVAILABLE"
                if captured and minimum_coverage > 0
                else "INSUFFICIENT_CAPTURE"
            ),
            "results": results,
        }

    def market_symbols_for(self, account_id):
        with self._lock:
            state = self._states.get(account_id) or {}
            return tuple(state.get("candidates", ())) if state.get("enabled") else ()

    def evidence(self, account_id):
        with self._lock:
            state = self._states.get(account_id)
            if not state:
                return {
                    "enabled": False,
                    "state": "STOPPED",
                    "candidate_count": 0,
                    "evaluated_count": 0,
                    "decisions": [],
                    "selected_symbol": None,
                    "selected_strategy": None,
                    "selected_strategy_instance_id": None,
                    "policy": self._policy(),
                    "funnel": {
                        key: 0
                        for key in (
                            "observations",
                            "evaluations",
                            "ready_evaluations",
                            "signals",
                            "risk_submissions",
                            "risk_admitted",
                            "risk_rejected",
                            "orders",
                            "dispatched",
                            "fills",
                        )
                    },
                    "hold_reasons": {},
                }
            decisions = sorted(
                state["decisions"].values(),
                key=lambda item: (item["observed_at"], item["symbol"]),
                reverse=True,
            )[:20]
            ready_symbols = sum(
                len(values) >= self.lookback
                for values in state.get("history", {}).values()
            )
            funnel = dict(state.get("funnel") or {})
            strategy_prefix = (
                f"auto-{hashlib.sha256(account_id.encode()).hexdigest()[:8]}-%"
            )
            funnel["orders"] = self.platform.store.rows(
                "SELECT COUNT(*) AS n FROM orders WHERE account=? AND strategy LIKE ?",
                (account_id, strategy_prefix),
            )[0]["n"]
            funnel["dispatched"] = self.platform.store.rows(
                "SELECT COUNT(*) AS n FROM orders WHERE account=? "
                "AND strategy LIKE ? AND dispatch_started=1",
                (account_id, strategy_prefix),
            )[0]["n"]
            funnel["fills"] = self.platform.store.rows(
                "SELECT COUNT(*) AS n FROM fills WHERE account=? AND strategy LIKE ?",
                (account_id, strategy_prefix),
            )[0]["n"]
            for key in (
                "observations",
                "evaluations",
                "ready_evaluations",
                "signals",
                "risk_submissions",
                "risk_admitted",
                "risk_rejected",
            ):
                funnel.setdefault(key, 0)
            return {
                "enabled": bool(state["enabled"]),
                "state": (
                    "STOPPED"
                    if not state["enabled"]
                    else "WARMING_UP"
                    if ready_symbols
                    < min(len(state["candidates"]), min(20, self.scan_limit))
                    else "EVALUATING"
                ),
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
                "ready_symbol_count": ready_symbols,
                "funnel": funnel,
                "hold_reasons": dict(state.get("hold_reasons") or {}),
                "capture": {
                    "count": len(state.get("capture") or ()),
                    "limit": self.CAPTURE_LIMIT,
                    "ordered": True,
                },
            }

    def _policy(self):
        adapter = getattr(self.platform.broker_calls, "adapter", self.platform.broker)
        return {
            "long_only": True,
            "strategy_selection": ["momentum", "breakout", "mean_reversion"],
            "scan_limit": self.scan_limit,
            "candidate_source": (
                "CONFIGURED_ALLOWLIST"
                if self.candidate_allowlist
                else "OFFLINE_CATALOGUE"
            ),
            "candidate_allowlist": list(self.candidate_allowlist),
            "candidate_exchange": getattr(adapter, "instrument_exchange", None),
            "max_positions": self.max_positions,
            "lookback_updates": self.lookback,
            "entry_momentum": str(self.entry_momentum),
            "threshold_unit": "fractional_return",
            "entry_momentum_percent": str(self.entry_momentum * Decimal(100)),
            "take_profit": str(self.take_profit),
            "stop_loss": str(self.stop_loss),
            "cooldown_seconds": self.cooldown_seconds,
            "profit_guaranteed": False,
        }

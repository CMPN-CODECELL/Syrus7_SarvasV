import json
from collections import deque
from decimal import Decimal

from backend.shared.contracts import OrderIntent, Side


KINDS = {"momentum", "mean_reversion", "breakout"}


class StrategyRuntime:
    """Built-in callbacks receive candles only; broker authority is never passed in."""

    def __init__(self, store):
        self.store = store
        self.enabled = False
        self.may_run = lambda strategy: True
        self.indicators = {}
        self.signals = deque(maxlen=100)
        self.errors = deque(maxlen=50)
        for row in reversed(
            self.store.rows(
                "SELECT payload FROM audit WHERE type='STRATEGY_SIGNAL' "
                "ORDER BY sequence DESC LIMIT 100"
            )
        ):
            self.signals.append(json.loads(row["payload"]))
        for row in reversed(
            self.store.rows(
                "SELECT payload FROM audit WHERE type='STRATEGY_CALLBACK_FAILED' "
                "ORDER BY sequence DESC LIMIT 50"
            )
        ):
            self.errors.append(json.loads(row["payload"]))
        self.handlers = {
            "momentum": self._momentum,
            "mean_reversion": self._mean_reversion,
            "breakout": self._breakout,
        }

    def subscribe(self, account, strategy, kind, symbol):
        if kind not in KINDS:
            raise ValueError("unknown strategy")
        if not account or not strategy or not symbol:
            raise ValueError("account, strategy instance and symbol are required")
        with self.store.transaction() as db:
            if not db.execute(
                "SELECT id FROM accounts WHERE id=?", (account,)
            ).fetchone():
                raise ValueError("account does not exist")
            db.execute(
                "INSERT INTO subscriptions(id,account,kind,symbol,enabled) "
                "VALUES (?,?,?,?,1)",
                (strategy, account, kind, symbol),
            )
            self.store.audit("SUBSCRIBED", {"strategy": strategy, "account": account})

    def set_enabled(self, account, strategy, enabled):
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT id FROM subscriptions WHERE id=? AND account=?",
                (strategy, account),
            ).fetchone()
            if not row:
                raise ValueError("subscription does not exist")
            db.execute(
                "UPDATE subscriptions SET enabled=? WHERE id=?",
                (1 if enabled else 0, strategy),
            )
            self.store.audit(
                "SUBSCRIPTION_STARTED" if enabled else "SUBSCRIPTION_STOPPED",
                {"strategy": strategy, "account": account},
            )
        self.indicators.pop(strategy, None)

    def state_for(self, subscription):
        if not subscription["enabled"]:
            return "STOPPED"
        return "RUNNING" if self.enabled else "READY"

    def _momentum(self, subscription, candle):
        if candle.interval != 60:
            return None
        state = self.indicators.setdefault(subscription["id"], {})
        fast = state.get("ema_fast")
        slow = state.get("ema_slow")
        if fast is None:
            state.update(
                ema_fast=candle.close,
                ema_slow=candle.close,
                trend=0,
                samples=1,
            )
            return None
        fast = Decimal("0.5") * candle.close + Decimal("0.5") * fast
        slow = (
            Decimal("0.333333333333333333") * candle.close
            + Decimal("0.666666666666666667") * slow
        )
        trend = 1 if fast > slow else -1 if fast < slow else 0
        previous_trend = state["trend"]
        samples = state["samples"] + 1
        state.update(ema_fast=fast, ema_slow=slow, trend=trend, samples=samples)
        # The slow EMA is a five-period indicator. Rebuild that minimum history
        # after every process restart or explicit subscription restart before
        # allowing the strategy to emit a risk-increasing intent.
        if samples < 5:
            return None
        if not trend or (samples > 5 and trend == previous_trend):
            return None
        return (
            Side.BUY if trend > 0 else Side.SELL,
            "3/5 EMA bullish crossover" if trend > 0 else "3/5 EMA bearish crossover",
        )

    def _mean_reversion(self, subscription, candle):
        if candle.interval != 60:
            return None
        state = self.indicators.setdefault(subscription["id"], {})
        closes = state.setdefault("closes", deque(maxlen=5))
        closes.append(candle.close)
        if len(closes) < 5:
            return None
        mean = sum(closes, Decimal(0)) / len(closes)
        deviation = (candle.close - mean) / mean
        threshold = Decimal("0.005")
        if deviation > threshold:
            return Side.SELL, "close above five-period mean"
        if deviation < -threshold:
            return Side.BUY, "close below five-period mean"
        return None

    def _breakout(self, subscription, candle):
        if candle.interval != 300:
            return None
        state = self.indicators.setdefault(subscription["id"], {})
        previous_high = state.get("high")
        previous_low = state.get("low")
        state.update(high=candle.high, low=candle.low)
        if previous_high is None:
            return None
        if candle.close > previous_high:
            return Side.BUY, "5m close broke previous range high"
        if candle.close < previous_low:
            return Side.SELL, "5m close broke previous range low"
        return None

    def _halt_failed_subscription(self, subscription, exc):
        error = {
            "strategy": subscription["id"],
            "account": subscription["account"],
            "error_type": type(exc).__name__,
        }
        self.errors.append(error)
        with self.store.transaction() as db:
            db.execute(
                "UPDATE subscriptions SET enabled=0 WHERE id=?",
                (subscription["id"],),
            )
            self.store.audit("STRATEGY_CALLBACK_FAILED", error)

    def on_candle(self, candle, now):
        if not self.enabled or not candle.is_closed:
            return []
        intents = []
        for sub in self.store.rows(
            "SELECT * FROM subscriptions WHERE symbol=? AND enabled=1", (candle.symbol,)
        ):
            if not self.may_run(sub["id"]):
                continue
            try:
                signal = self.handlers[sub["kind"]](sub, candle)
            except Exception as exc:
                self._halt_failed_subscription(sub, exc)
                continue
            if signal is None:
                continue
            side, reason = signal
            intent = OrderIntent(
                f"{sub['id']}:{candle.interval}:{candle.start_time}",
                sub["id"],
                sub["account"],
                candle.symbol,
                side,
                1,
                now,
                reason=reason,
            )
            event = {
                "intent_id": intent.intent_id,
                "strategy": sub["id"],
                "kind": sub["kind"],
                "symbol": candle.symbol,
                "interval": candle.interval,
                "side": side.value,
                "reason": reason,
                "candle_start": candle.start_time,
            }
            self.signals.append(event)
            with self.store.transaction():
                self.store.audit("STRATEGY_SIGNAL", event)
            intents.append(intent)
        return intents

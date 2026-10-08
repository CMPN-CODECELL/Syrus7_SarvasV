from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from concurrent.futures.thread import _threads_queues, _worker
from decimal import Decimal
import inspect
import json
import threading
import weakref

from backend.shared.contracts import OrderIntent, Side

KINDS = {"momentum", "mean_reversion", "breakout", "rsi_reversal"}


class BoundedStrategyExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor with daemon worker threads for bounded strategy callback execution."""

    def _adjust_thread_count(self):
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = f"{self._thread_name_prefix or self}_{num_threads}"
            t = threading.Thread(
                name=thread_name,
                target=_worker,
                args=(
                    weakref.ref(self, weakref_cb),
                    self._work_queue,
                    self._initializer,
                    self._initargs,
                ),
                daemon=True,
            )
            t.start()
            self._threads.add(t)
            _threads_queues[t] = self._work_queue


def _call_handler(handler, subscription, candle, state):
    try:
        sig = inspect.signature(handler)
        if "state" in sig.parameters:
            return handler(subscription, candle, state=state)
    except (ValueError, TypeError):
        pass
    return handler(subscription, candle)


class StrategyRuntime:
    """Built-in callbacks receive candles only; broker authority is never passed in.

    LIMITATIONS & BOUNDARIES:
    Built-in callbacks are trusted code implementations representing untrusted
    decision logic. Callbacks execute in isolated daemon worker threads with bounded
    execution time (callback_timeout) and bounded outstanding concurrency (max_workers).
    Threads provide latency isolation and fail-closed timeout bounding; they are NOT
    an arbitrary-code sandbox against malicious bytecode or CPU spinning.
    Workers never receive store locks, risk gates, or broker authority.
    """

    def __init__(
        self,
        store,
        *,
        callback_timeout: float = 0.5,
        max_workers: int = 4,
        max_outstanding: int = 8,
    ):
        self.store = store
        self._enabled = False
        self._global_epoch = 1
        self._epoch_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._last_processed_candle: dict[tuple[str, int], int] = {}
        self._last_committed_candle: dict[tuple[str, int], int] = {}
        self.on_interval_registered = None
        self.may_run = lambda strategy: True
        self.indicators = {}
        self.signals = deque(maxlen=100)
        self.errors = deque(maxlen=50)
        self.callback_timeout = callback_timeout
        self.max_workers = max_workers
        self.max_outstanding = max_outstanding
        self._executor = BoundedStrategyExecutor(
            max_workers=max_workers, thread_name_prefix="strategy-worker"
        )
        self._work_semaphore = threading.Semaphore(max_outstanding)
        self._subscription_generations: dict[str, int] = {}
        for row in self.store.rows("SELECT id FROM subscriptions"):
            self._subscription_generations[row["id"]] = 1

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
        self.registry = {
            "momentum": {
                "handler": self._momentum,
                "interval": 60,
                "warmup": 5,
                "description": "3/5 EMA bullish/bearish crossover on 1m candles",
            },
            "mean_reversion": {
                "handler": self._mean_reversion,
                "interval": 60,
                "warmup": 5,
                "description": "5-period mean reversion (+/-0.5%) on 1m candles",
            },
            "breakout": {
                "handler": self._breakout,
                "interval": 300,
                "warmup": 1,
                "description": "Range high/low breakout on 5m candles",
            },
            "rsi_reversal": {
                "handler": self._rsi_reversal,
                "interval": 60,
                "warmup": 15,
                "description": "14-period RSI oversold (<30) and overbought (>70) reversal on 1m candles",
            },
        }
        self.handlers = {k: v["handler"] for k, v in self.registry.items()}

    @property
    def enabled(self) -> bool:
        with self._epoch_lock:
            return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        new_val = bool(value)
        with self._epoch_lock:
            if self._enabled != new_val:
                self._enabled = new_val
                self._global_epoch += 1

    def invalidate_in_flight(self):
        with self._epoch_lock:
            self._global_epoch += 1

    def close(self):
        """Shut down the bounded executor pool."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def register_strategy(
        self,
        kind: str,
        handler,
        *,
        interval: int = 60,
        warmup: int = 5,
        description: str = "",
    ):
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("strategy kind name required")
        kind = kind.strip().lower()
        if not callable(handler):
            raise ValueError("strategy handler must be callable")
        if type(interval) is not int or interval <= 0:
            raise ValueError("interval must be a positive integer")
        if type(warmup) is not int or warmup <= 0:
            raise ValueError("warmup must be a positive integer")
        self.registry[kind] = {
            "handler": handler,
            "interval": interval,
            "warmup": warmup,
            "description": description or f"Custom strategy {kind}",
        }
        self.handlers[kind] = handler
        KINDS.add(kind)
        if self.on_interval_registered is not None:
            self.on_interval_registered(interval)

    def readiness_for(self, strategy_id: str) -> dict[str, int | bool]:
        rows = self.store.rows(
            "SELECT kind FROM subscriptions WHERE id=?", (strategy_id,)
        )
        if not rows:
            return {"samples": 0, "warmup": 0, "ready": False}
        kind = rows[0]["kind"]
        meta = self.registry.get(kind, {})
        warmup = meta.get("warmup", 5)
        state = self.indicators.get(strategy_id, {})

        if kind == "momentum":
            samples = state.get("samples", 0)
        elif kind in ("mean_reversion", "rsi_reversal"):
            closes = state.get("closes", ())
            samples = len(closes)
        elif kind == "breakout":
            samples = 1 if "high" in state else 0
        else:
            if "samples" in state and isinstance(state["samples"], int):
                samples = state["samples"]
            elif "closes" in state and hasattr(state["closes"], "__len__"):
                samples = len(state["closes"])
            else:
                samples = len(state) if state else 0

        ready = bool(samples >= warmup)
        return {
            "samples": samples,
            "warmup": warmup,
            "ready": ready,
        }

    def list_registered(self):
        return [
            {
                "kind": kind,
                "interval": meta.get("interval", 60),
                "warmup": meta.get("warmup", 5),
                "description": meta.get("description", ""),
            }
            for kind, meta in self.registry.items()
        ]

    def subscribe(self, account, strategy, kind, symbol):
        if kind not in self.handlers:
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
            self._subscription_generations[strategy] = (
                self._subscription_generations.get(strategy, 0) + 1
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
        self._subscription_generations[strategy] = (
            self._subscription_generations.get(strategy, 0) + 1
        )
        self.indicators.pop(strategy, None)

    def is_subscription_enabled(self, strategy_id: str) -> bool:
        rows = self.store.rows(
            "SELECT enabled FROM subscriptions WHERE id=?", (strategy_id,)
        )
        return bool(rows and rows[0]["enabled"])

    def state_for(self, subscription):
        if not subscription["enabled"]:
            return "STOPPED"
        return "RUNNING" if self.enabled else "READY"

    @staticmethod
    def _copy_indicator_state(state: dict) -> dict:
        copied = {}
        for k, v in state.items():
            if isinstance(v, deque):
                copied[k] = deque(v, maxlen=v.maxlen)
            elif isinstance(v, list):
                copied[k] = list(v)
            elif isinstance(v, dict):
                copied[k] = dict(v)
            elif isinstance(v, set):
                copied[k] = set(v)
            else:
                copied[k] = v
        return copied

    def _momentum(self, subscription, candle, state=None):
        if candle.interval != 60:
            return None
        if state is None:
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

    def _mean_reversion(self, subscription, candle, state=None):
        if candle.interval != 60:
            return None
        if state is None:
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

    def _breakout(self, subscription, candle, state=None):
        if candle.interval != 300:
            return None
        if state is None:
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

    def _rsi_reversal(self, subscription, candle, state=None):
        if candle.interval != 60:
            return None
        if state is None:
            state = self.indicators.setdefault(subscription["id"], {})
        closes = state.setdefault("closes", deque(maxlen=15))
        closes.append(candle.close)
        if len(closes) < 15:
            return None
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(Decimal(0))
            elif diff < 0:
                gains.append(Decimal(0))
                losses.append(-diff)
            else:
                gains.append(Decimal(0))
                losses.append(Decimal(0))

        avg_gain = sum(gains, Decimal(0)) / Decimal(14)
        avg_loss = sum(losses, Decimal(0)) / Decimal(14)

        if avg_loss == Decimal(0):
            rsi = Decimal(100) if avg_gain > Decimal(0) else Decimal(50)
        else:
            rs = avg_gain / avg_loss
            rsi = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))

        previous_rsi = state.get("rsi")
        state["rsi"] = rsi

        if rsi < Decimal(30):
            if previous_rsi is not None and previous_rsi < Decimal(30):
                return None
            return Side.BUY, f"14-period RSI oversold reversal ({rsi:.1f} < 30)"
        if rsi > Decimal(70):
            if previous_rsi is not None and previous_rsi > Decimal(70):
                return None
            return Side.SELL, f"14-period RSI overbought reversal ({rsi:.1f} > 70)"
        return None

    def _halt_failed_subscription(self, subscription, exc):
        error = {
            "strategy": subscription["id"],
            "account": subscription["account"],
            "error_type": type(exc).__name__,
        }
        self.errors.append(error)
        self._subscription_generations[subscription["id"]] = (
            self._subscription_generations.get(subscription["id"], 0) + 1
        )
        self.indicators.pop(subscription["id"], None)
        with self.store.transaction() as db:
            db.execute(
                "UPDATE subscriptions SET enabled=0 WHERE id=?",
                (subscription["id"],),
            )
            self.store.audit("STRATEGY_CALLBACK_FAILED", error)

    def on_candle(self, candle, now):
        with self._epoch_lock:
            if not self._enabled or not candle.is_closed:
                return []
            expected_epoch = self._global_epoch

        subs = self.store.rows(
            "SELECT * FROM subscriptions WHERE symbol=? AND enabled=1 ORDER BY id",
            (candle.symbol,),
        )
        active_subs = [s for s in subs if self.may_run(s["id"])]
        if not active_subs:
            return []

        runs = []
        for sub in active_subs:
            strat_id = sub["id"]
            handler = self.handlers.get(sub["kind"])
            if not handler:
                continue

            strat_meta = self.registry.get(sub["kind"], {})
            strat_interval = strat_meta.get("interval", 60)
            if candle.interval != strat_interval:
                continue

            expected_gen = self._subscription_generations.get(strat_id, 1)
            key = (strat_id, expected_gen)

            with self._state_lock:
                last_proc = self._last_processed_candle.get(key, -1)
                if candle.start_time <= last_proc:
                    continue
                self._last_processed_candle[key] = candle.start_time
                working_state = self._copy_indicator_state(
                    self.indicators.get(strat_id, {})
                )

            # Bounded outstanding work via semaphore
            acquired = self._work_semaphore.acquire(
                timeout=min(0.05, self.callback_timeout)
            )
            if not acquired:
                self._halt_failed_subscription(
                    sub, TimeoutError("strategy worker pool saturated")
                )
                continue

            def worker_task(h=handler, s=dict(sub), c=candle, ws=working_state):
                try:
                    return _call_handler(h, s, c, ws)
                finally:
                    self._work_semaphore.release()

            try:
                future = self._executor.submit(worker_task)
                runs.append((sub, expected_gen, working_state, future))
            except Exception as exc:
                self._work_semaphore.release()
                self._halt_failed_subscription(sub, exc)

        intents = []
        for sub, expected_gen, working_state, future in runs:
            strat_id = sub["id"]
            key = (strat_id, expected_gen)
            try:
                signal = future.result(timeout=self.callback_timeout)
            except FutureTimeoutError:
                self._halt_failed_subscription(
                    sub,
                    TimeoutError(f"callback exceeded {self.callback_timeout}s timeout"),
                )
                continue
            except Exception as exc:
                self._halt_failed_subscription(sub, exc)
                continue

            # Validate originating run and serialize state commits
            with self._state_lock:
                with self._epoch_lock:
                    if not self._enabled or self._global_epoch != expected_epoch:
                        continue
                if not self.may_run(strat_id):
                    continue
                if self._subscription_generations.get(strat_id, 1) != expected_gen:
                    continue
                if not self.is_subscription_enabled(strat_id):
                    continue

                last_comm = self._last_committed_candle.get(key, -1)
                if candle.start_time <= last_comm:
                    # Newer or equal candle was already committed for this run
                    continue

                # Valid run: commit candidate indicator state
                self.indicators[strat_id] = working_state
                self._last_committed_candle[key] = candle.start_time

            if signal is None:
                continue

            side, reason = signal
            intent = OrderIntent(
                f"{strat_id}:{candle.interval}:{candle.start_time}",
                strat_id,
                sub["account"],
                candle.symbol,
                side,
                1,
                now,
                reason=reason,
            )
            event = {
                "intent_id": intent.intent_id,
                "strategy": strat_id,
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

import json
import time
from collections import deque
from collections.abc import Iterable
from threading import Event, Lock, Thread, current_thread
from dataclasses import asdict, replace
from decimal import Decimal

from backend.accounting.charges import calculate_indian_charges
from backend.accounting.ledger import Ledger
from backend.broker.adapters import MockBrokerAdapter
from backend.broker.http_adapter import HTTPMockBrokerAdapter
from backend.execution.orders import OrderManager
from backend.market_data.candles import CandleBuilder
from backend.market_data.session import MarketSession
from backend.observability import MetricsRegistry
from backend.reliability.control import Reliability
from backend.reliability.broker_calls import BrokerSession, Deadline
from backend.reliability.proof import SafetyProofService
from backend.reliability.safety_bench import SafetyBench
from backend.reliability.tracing import TraceService
from backend.risk.gateway import RiskGateway
from backend.shared.auth import AuthService
from backend.shared.contracts import GlobalTradingState as Gate, OrderStatus, Side, Tick
from backend.shared.store import Store
from backend.strategies.runtime import StrategyRuntime
from backend.strategies.auto_mode import AutoMode


def _contract_dict(value):
    """Serialize dataclass fields without converting exact decimals to floats."""
    return {
        key: str(field) if isinstance(field, Decimal) else field
        for key, field in asdict(value).items()
    }


class Platform:
    def __init__(
        self,
        path=":memory:",
        broker=None,
        clock=time.time,
        store=None,
        demo_enabled=True,
        broker_read_timeout=8.0,
        broker_write_timeout=8.0,
        reconciliation_timeout=10.0,
        auto_scan_limit=200,
        auto_max_positions=3,
        auto_lookback=5,
        auto_entry_momentum=0.003,
        auto_take_profit=0.01,
        auto_stop_loss=0.005,
        auto_cooldown_seconds=60,
    ):
        self.clock = clock
        self.demo_enabled = demo_enabled
        self.store = store if store is not None else Store(path)
        self.store.audit_clock = clock
        self.broker = (
            broker
            if broker is not None
            else MockBrokerAdapter(
                f"{path}.broker.json" if path != ":memory:" and store is None else None
            )
        )
        self.ledger = Ledger(self.store)
        self.broker_calls = BrokerSession(
            self.broker,
            read_timeout=broker_read_timeout,
            write_timeout=broker_write_timeout,
            reconciliation_timeout=reconciliation_timeout,
        )
        self.orders = OrderManager(self.store, self.broker_calls, self.ledger)
        self.risk = RiskGateway(self.store, self.ledger, self.orders, clock)
        self.strategies = StrategyRuntime(self.store)
        self.strategies.may_run = lambda strategy: (
            not self.risk.kill_requested.is_set()
            and self.risk.strategy_state(strategy) == "RUNNING"
        )
        self.market_session = MarketSession(clock=clock)
        self.reliability = Reliability(
            self.store,
            self.broker_calls,
            self.ledger,
            self.orders,
            self.risk,
            self.strategies,
            clock,
            market_session=self.market_session,
        )
        self.metrics = MetricsRegistry(clock=clock)
        self.risk.metrics = self.metrics
        self.reliability.metrics = self.metrics
        self.safety_proof = SafetyProofService(
            self.store, self.ledger, self.risk, self.reliability, clock
        )
        self.traces = TraceService(self.store, ledger=self.ledger)
        self.safety_bench = SafetyBench(self.store, clock)
        self.candles = CandleBuilder()
        self.strategies.on_interval_registered = self.candles.add_interval
        for meta in self.strategies.registry.values():
            self.candles.add_interval(meta["interval"])
        self.closed_candles = deque(maxlen=128)
        self._market_observations = {}
        self._market_rejected = 0
        self._candle_count_cache = {}
        self._restore_closed_candles("replay")
        self.auth = AuthService(self.store)
        self.auto_mode = AutoMode(
            self,
            scan_limit=auto_scan_limit,
            max_positions=auto_max_positions,
            lookback=auto_lookback,
            entry_momentum=auto_entry_momentum,
            take_profit=auto_take_profit,
            stop_loss=auto_stop_loss,
            cooldown_seconds=auto_cooldown_seconds,
        )
        self.demo_count = 0
        self._simulation_cursor = {}
        self._simulation_seq = 0
        self._replay_lock = Lock()
        self._replay_stop = Event()
        self._replay_thread = None
        self.external_market_data = None

    def configure_external_market_data(self, provider):
        """Attach one explicit source before any timeline has been ingested."""
        if self.candles.accepted_ticks or self._replay_thread:
            raise ValueError("market-data source cannot change after ingestion starts")
        if not isinstance(
            self.broker, (MockBrokerAdapter, HTTPMockBrokerAdapter)
        ) and not getattr(provider, "supports_live_broker", False):
            raise ValueError(
                "external market data source is not compatible with this broker"
            )
        self.external_market_data = provider
        self.reliability.external_market_data = provider
        provider_key = provider.telemetry().get("provider")
        self._restore_closed_candles(provider_key)

    def _restore_closed_candles(self, provider):
        from backend.shared.contracts import Candle

        self.closed_candles.clear()
        for row in self.store.candle_rows(limit=128, provider=provider):
            self.closed_candles.append(
                Candle(
                    row["symbol"],
                    row["interval"],
                    row["start_time"],
                    row["end_time"],
                    Decimal(row["open"]),
                    Decimal(row["high"]),
                    Decimal(row["low"]),
                    Decimal(row["close"]),
                    row["volume"],
                    bool(row["is_closed"]),
                    bool(row["volume_available"]),
                    row["data_source"],
                )
            )

    def start_external_market_data(self):
        if self.external_market_data is None:
            return False
        if self._replay_thread and self._replay_thread.is_alive():
            raise ValueError("replay and external market data cannot run together")
        # Starting a network feed never reopens execution. An operator must
        # separately reconcile/resume after fresh evidence exists.
        self.reliability.fail_closed(
            "021_FEED_STARTING"
            if getattr(self.external_market_data, "supports_live_broker", False)
            else "YAHOO_FEED_STARTING"
        )
        return self.external_market_data.start()

    def stop_external_market_data(self):
        if self.external_market_data is not None:
            return self.external_market_data.stop()
        return True

    def validate_external_market_symbols(self, symbols):
        """Validate symbols only when an external provider owns the universe."""
        normalized = [str(symbol).strip().upper() for symbol in symbols if symbol]
        if not normalized or self.external_market_data is None:
            return True
        validator = getattr(self.external_market_data, "validate_symbols", None)
        if validator is None:
            return True
        validator(normalized)
        return True

    def refresh_external_market_universe(self):
        """Ask an attached provider to rebuild its bounded subscription set."""
        if self.external_market_data is None:
            return True
        refresh = getattr(self.external_market_data, "refresh_universe", None)
        return True if refresh is None else refresh()

    def account(self, account_id):
        if not account_id:
            raise ValueError("account ID required")
        with self.store.transaction() as db:
            db.execute("INSERT INTO accounts VALUES (?)", (account_id,))
            self.store.audit("ACCOUNT_CREATED", {"account_id": account_id})

    def ingest(self, fill):
        started = time.perf_counter()
        with self.store.lock:
            try:
                result = self.orders.ingest(fill)
                self._metric_counter(
                    "fills_processed_total"
                    if result
                    else "duplicate_fill_ignored_count"
                )
                return result
            except Exception as exc:
                account_id = getattr(fill, "account_id", None)
                self.reliability.fail_closed(
                    "FILL_EVENT_REJECTED", account_id=account_id
                )
                self._metric_counter(
                    "unattributed_fill_count"
                    if "unattributed" in str(exc) or "attribution" in str(exc)
                    else "conflicting_fill_count"
                )
                raise
            finally:
                self._metric_observe(
                    "fill_processing_latency_ms",
                    (time.perf_counter() - started) * 1000,
                )

    def _metric_counter(self, name, amount=1):
        try:
            self.metrics.counter(name, amount)
        except Exception:
            pass

    def _metric_observe(self, name, value):
        try:
            self.metrics.observe(name, value)
        except Exception:
            pass

    def cancel(self, order_id, timeout=None):
        return self.orders.cancel(order_id, timeout=timeout)

    def process_broker_update(self, update):
        with self.store.lock:
            try:
                return self.orders.process_broker_update(update)
            except Exception:
                self.reliability.fail_closed("BROKER_UPDATE_REJECTED")
                raise

    def drain_broker_updates(self):
        adapter = getattr(self.broker_calls, "adapter", self.broker)
        if hasattr(adapter, "drain_updates"):
            return adapter.drain_updates()
        return []

    def sync_broker_updates(self):
        """Drain and authoritatively apply pending broker updates."""
        updates = self.drain_broker_updates()
        results = []
        adapter = getattr(self.broker_calls, "adapter", self.broker)
        for upd in updates:
            results.append(self.process_broker_update(upd))
            # A provider may retain a trade until the canonical fill has been
            # durably applied.  Acknowledge only after process_broker_update
            # completes; failures retain the provider evidence for retry.
            acknowledge = getattr(adapter, "acknowledge_update", None)
            if acknowledge is not None:
                acknowledge(upd)
        return results

    def disconnect_broker(self):
        """Simulate broker loss of connectivity and fail closed."""
        adapter = getattr(self.broker_calls, "adapter", self.broker)
        if hasattr(adapter, "disconnect"):
            adapter.disconnect()
        self.strategies.invalidate_in_flight()
        with self.store.transaction():
            self.store.audit("BROKER_DISCONNECTED", {})
        self.reliability.fail_closed("BROKER_DISCONNECTED")
        return {"connected": False, "state": self.snapshot()}

    def reconnect_broker(self, *, timeout=None):
        """Restore broker connectivity and reconcile local state with broker truth."""
        adapter = getattr(self.broker_calls, "adapter", self.broker)
        if hasattr(adapter, "reconnect"):
            adapter.reconnect()
        with self.store.transaction():
            self.store.audit("BROKER_RECONNECTED", {})
        reconciled = self.reliability.reconcile(timeout=timeout)
        return {
            "connected": getattr(adapter, "connected", True),
            "reconciled": reconciled,
            "state": self.snapshot(),
        }

    def tick(self, tick, *, replay=False):
        started = time.perf_counter()
        provider_telemetry = None
        if replay:
            self.require_replay_demo()
            if self.external_market_data is not None:
                self.reliability.fail_closed("MARKET_DATA_SOURCE_MIXED")
                raise ValueError(
                    "replay and external market data cannot share a timeline"
                )
            if tick.data_source == "UNSPECIFIED":
                tick = replace(tick, data_source="MOCK_REPLAY")
        elif self.external_market_data is not None:
            provider_telemetry = self.external_market_data.telemetry()
            expected_source = provider_telemetry.get("source")
            if not expected_source or tick.data_source != expected_source:
                self.reliability.fail_closed("MARKET_DATA_SOURCE_MIXED")
                if provider_telemetry.get("provider") == "YAHOO_EXTERNAL_QUOTES":
                    raise ValueError(
                        "only configured Yahoo updates may enter this timeline"
                    )
                raise ValueError(
                    "market update source does not match configured provider"
                )
        elif tick.data_source in {"YAHOO_EXTERNAL_QUOTES", "021_LIVE"}:
            self.reliability.fail_closed("MARKET_DATA_SOURCE_NOT_CONFIGURED")
            raise ValueError("external market data requires explicit provider opt-in")
        with self.store.lock:
            try:
                accepted, closed = self.candles.ingest_event(tick)
            except ValueError as exc:
                self._market_rejected += 1
                self.reliability.fail_closed("MARKET_EVENT_REJECTED")
                with self.store.transaction():
                    self.store.audit(
                        "MARKET_DATA_REJECTED",
                        {
                            "symbol": getattr(tick, "symbol", ""),
                            "event_id": getattr(tick, "event_id", ""),
                            "reason": (
                                "LATE_TICK"
                                if str(exc).startswith("late tick")
                                else "CONFLICTING_DUPLICATE"
                                if str(exc).startswith("conflicting duplicate")
                                else "INVALID_TICK"
                            ),
                        },
                    )
                # A conflicting replay duplicate is rejected and fail-closed,
                # but must not make a live ingestion loop crash or overwrite
                # the last accepted market mark.
                if str(exc).startswith("conflicting duplicate"):
                    return
                raise
            if not accepted:
                return
            self._metric_counter("ticks_processed_total")
            self._simulation_cursor[tick.symbol] = max(
                self._simulation_cursor.get(tick.symbol, 0),
                getattr(tick, "event_timestamp", 0),
            )
            self.ledger.marks[tick.symbol] = tick.price
            self._market_observations[tick.symbol] = {
                "symbol": tick.symbol,
                "provider_symbol": tick.symbol,
                "price": str(tick.price),
                "event_timestamp": tick.event_timestamp,
                "raw_event_timestamp": tick.raw_event_timestamp,
                "received_at": time.time(),
                "volume_available": tick.volume_available,
                "data_source": tick.data_source,
            }
            self.reliability.observe_tick(tick, replay=replay)
            for candle in closed:
                self.closed_candles.append(candle)
                self.store.save_candle(
                    candle,
                    provider=(
                        provider_telemetry.get("provider", "replay")
                        if provider_telemetry
                        else "replay"
                    ),
                )
                self._candle_count_cache.pop(
                    provider_telemetry.get("provider", "replay")
                    if provider_telemetry
                    else "replay",
                    None,
                )
        # Auto mode observes only an accepted canonical tick. Its policy work
        # stays outside the control-plane store lock; every returned intent
        # joins the same RiskGateway/OrderManager path as candle strategies.
        intents = list(self.auto_mode.on_tick(tick))
        for candle in closed:
            try:
                intents.extend(self.strategies.on_candle(candle, self.clock()))
            except Exception:
                self.reliability.fail_closed("STRATEGY_CALLBACK_FAILED")
                raise ValueError(
                    "strategy callback failed; execution stopped"
                ) from None
        for intent in intents:
            decision = self.risk.submit(intent)
            self.auto_mode.record_risk_result(intent, decision)
            if (
                decision.allowed
                and self.risk.state == "RUNNING"
                and isinstance(self.broker, (MockBrokerAdapter, HTTPMockBrokerAdapter))
            ):
                order = self.broker.orders.get(intent.intent_id)
                if order and order.remaining_quantity and order.status != "REJECTED":
                    trade_side = Side(order.intent.side)
                    charges_calc = calculate_indian_charges(
                        order.remaining_quantity,
                        tick.price,
                        trade_side,
                    )
                    self.ingest(
                        self.broker_calls.call(
                            "execute",
                            order.order_id,
                            order.remaining_quantity,
                            tick.price,
                            self.clock(),
                            charges_calc.total_charges,
                        )
                    )
        self._metric_observe(
            "tick_processing_latency_ms", (time.perf_counter() - started) * 1000
        )

    def get_simulation_cursor(self, symbol: str | None = None) -> int:
        """Return the highest simulation timestamp seen for symbol or globally."""
        candidates = [0]
        with self.store.lock:
            if symbol:
                if symbol in self._simulation_cursor:
                    candidates.append(self._simulation_cursor[symbol])
                if symbol in self.candles.last:
                    candidates.append(self.candles.last[symbol])
                rows = self.store.rows(
                    "SELECT event_timestamp FROM risk_marks WHERE symbol=?", (symbol,)
                )
                if rows and rows[0]["event_timestamp"] is not None:
                    candidates.append(int(rows[0]["event_timestamp"]))
            else:
                candidates.extend(self._simulation_cursor.values())
                candidates.extend(self.candles.last.values())
                for row in self.store.rows("SELECT event_timestamp FROM risk_marks"):
                    if row["event_timestamp"] is not None:
                        candidates.append(int(row["event_timestamp"]))

            for row in self.store.rows("SELECT id FROM orders"):
                parts = row["id"].rsplit(":", 1)
                if len(parts) > 1 and parts[1].isdigit():
                    candidates.append(int(parts[1]))

        return max(candidates)

    def generate_simulation_batch(
        self,
        symbols: Iterable[str],
        minutes: int = 1,
        offsets: tuple[int, ...] = (0, 20, 40),
        align: int = 60,
    ) -> list[Tick]:
        """Generate a deterministic, strictly advancing chronological batch of ticks."""
        sym_list = sorted(set(symbols))
        if not sym_list:
            return []

        with self._replay_lock:
            latest = max(self.get_simulation_cursor(s) for s in sym_list)
            if latest == 0:
                start_ts = 1_700_000_100
            else:
                start_ts = (latest // align + 1) * align

            batch: list[Tick] = []
            for minute in range(minutes):
                minute_base = start_ts + minute * 60
                for offset in offsets:
                    ts = minute_base + offset
                    for sym in sym_list:
                        self._simulation_seq += 1
                        eid = f"sim:{sym}:{ts}:{self._simulation_seq}"
                        elapsed_min = (ts - 1_700_000_000) // 60
                        step = offset // 20
                        price = Decimal(100 + elapsed_min + step)
                        batch.append(Tick(sym, ts, price, 5, eid))
                        self._simulation_cursor[sym] = max(
                            self._simulation_cursor.get(sym, 0), ts
                        )
            return batch

    def demo(self, account_id=None):
        with self.store.lock:
            if not self.demo_enabled:
                raise ValueError("replay demo is disabled for this database")
            self.require_replay_demo()
            subscriptions = self.store.rows("SELECT id FROM subscriptions")
            seed_account = account_id or (None if subscriptions else "demo")
            if seed_account:
                if not self.store.rows(
                    "SELECT id FROM accounts WHERE id=?", (seed_account,)
                ):
                    self.account(seed_account)
                for kind in ("momentum", "mean_reversion", "breakout"):
                    strategy_id = (
                        kind if seed_account == "demo" else f"{seed_account}:{kind}"
                    )
                    if not self.store.rows(
                        "SELECT id FROM subscriptions WHERE id=?", (strategy_id,)
                    ):
                        self.strategies.subscribe(
                            seed_account, strategy_id, kind, "DEMO"
                        )
            self.demo_count += 1
            symbols = {"DEMO"}
            symbols.update(
                row["symbol"]
                for row in self.store.rows(
                    "SELECT symbol FROM subscriptions WHERE enabled=1"
                )
            )
            events = self.generate_simulation_batch(
                sorted(symbols), minutes=11, align=300
            )
        events_iter = iter(events)
        self.tick(next(events_iter), replay=True)
        self.reliability.resume()
        for tick in events_iter:
            self.tick(tick, replay=True)
        self.reliability.reconcile()
        return self.snapshot(account_id=account_id)

    def start_replay_stream(self, interval=0.75):
        """Continue local mock ticks after an explicit replay action.

        This is intentionally available only for the HTTP mock adapter. It is
        a deterministic local simulator, not a live market-data connection.
        """
        if not isinstance(self.broker, HTTPMockBrokerAdapter):
            return False
        if not self.demo_enabled:
            return False
        if self.external_market_data is not None:
            return False

        with self._replay_lock:
            if (
                self.risk.kill_requested.is_set()
                or self.reliability.kill_latched
                or self.risk.state in {Gate.KILLING, Gate.KILLED}
            ):
                return False
            if self._replay_thread and self._replay_thread.is_alive():
                return True
            self._replay_stop.clear()

            def run():
                try:
                    if self.risk.state in {Gate.RECOVERING, Gate.STOPPED}:
                        self.reliability.resume()
                except Exception:
                    self.reliability.fail_closed("REPLAY_STREAM_FAILED")
                    return

                while not self._replay_stop.is_set():
                    if (
                        self.risk.kill_requested.is_set()
                        or self.reliability.kill_latched
                        or self.risk.state in {Gate.KILLING, Gate.KILLED}
                    ):
                        return

                    with self.store.lock:
                        symbols = {"DEMO"}
                        symbols.update(
                            row["symbol"]
                            for row in self.store.rows(
                                "SELECT symbol FROM subscriptions WHERE enabled=1"
                            )
                        )

                    batch = self.generate_simulation_batch(sorted(symbols), minutes=1)
                    for replay_tick in batch:
                        if self._replay_stop.wait(interval):
                            return
                        if (
                            self.risk.kill_requested.is_set()
                            or self.reliability.kill_latched
                            or self.risk.state in {Gate.KILLING, Gate.KILLED}
                        ):
                            return
                        try:
                            self.tick(replay_tick, replay=True)
                        except (ConnectionError, TimeoutError, ValueError):
                            self.reliability.fail_closed("REPLAY_STREAM_FAILED")
                            return

            self._replay_thread = Thread(
                target=run, daemon=True, name="algoshield-replay-stream"
            )
            self._replay_thread.start()
            return True

    def stop_replay_stream(self, timeout=1.0):
        self._replay_stop.set()
        thread = self._replay_thread
        if thread and thread is not current_thread():
            thread.join(timeout=timeout)

    def require_offline_demo(self):
        from backend.shared.postgres import PostgresStore

        if isinstance(self.store, PostgresStore) or not isinstance(
            self.broker, MockBrokerAdapter
        ):
            raise ValueError(
                "synthetic Failure Lab injection requires the offline mock broker; it cannot inject fake events into the 021 virtual exchange"
            )

    def require_replay_demo(self):
        """Allow replay only for an explicitly enabled local mock path."""
        if not self.demo_enabled or not isinstance(
            self.broker, (MockBrokerAdapter, HTTPMockBrokerAdapter)
        ):
            raise ValueError(
                "demo replay requires an explicitly enabled local mock broker"
            )

    def kill(self, deadline_seconds=9, deadline_clock=time.monotonic):
        # 1. Close execution admission gate before any thread wait/join (idempotent)
        if isinstance(deadline_seconds, Deadline):
            deadline = deadline_seconds
        elif isinstance(deadline_seconds, (int, float)) and deadline_seconds <= 0:
            deadline = None
        else:
            deadline = Deadline(deadline_seconds, deadline_clock)

        self.risk.kill_requested.set()
        self._replay_stop.set()
        with self.store.transaction():
            self.reliability.safety.set("kill_latched", True)
            self.risk.state = Gate.KILLING
            self.strategies.enabled = False
            self.strategies.invalidate_in_flight()
            self.store.audit("KILL_GATE_CLOSED", {})

        # 2. Join replay stream thread now that admission is closed, bounded by remaining deadline
        thread = self._replay_thread
        if thread and thread is not current_thread():
            join_timeout = min(1.0, deadline.remaining) if deadline is not None else 0.0
            thread.join(timeout=join_timeout)

        def execute(order):
            price = self.ledger.marks.get(order.intent.symbol, Decimal("100"))
            if order.status != "REJECTED":
                trade_side = Side(order.intent.side)
                charges_calc = calculate_indian_charges(
                    order.remaining_quantity,
                    price,
                    trade_side,
                )
                self.ingest(
                    self.broker_calls.call(
                        "execute",
                        order.order_id,
                        order.remaining_quantity,
                        price,
                        self.clock(),
                        charges_calc.total_charges,
                        timeout=(
                            self.reliability.kill_deadline.remaining
                            if hasattr(self.reliability, "kill_deadline")
                            and self.reliability.kill_deadline is not None
                            else 0.0
                        ),
                    )
                )

        return self.reliability.kill(
            execute,
            deadline_seconds=deadline.remaining if deadline is not None else 0.0,
            deadline_clock=deadline_clock,
            deadline=deadline,
        )

    def strategy_readiness(self, strategy_id: str):
        return self.strategies.readiness_for(strategy_id)

    def market_data_evidence(self, account_id: str | None = None):
        market_data = self.candles.stats()
        if self.external_market_data is not None:
            market_data.update(self.external_market_data.telemetry())
            source = market_data.get("source") or "UNKNOWN"
            quotes = list(market_data.get("latest_quotes") or [])
        else:
            source = "MOCK_REPLAY"
            quotes = list(self._market_observations.values())
            if account_id is not None:
                # Replay observations are shared process state, but account
                # responses may only expose instruments subscribed by that account.
                visible_symbols = {
                    row["symbol"]
                    for row in self.store.rows(
                        "SELECT DISTINCT symbol FROM subscriptions WHERE account=?",
                        (account_id,),
                    )
                }
                quotes = [
                    quote for quote in quotes if quote.get("symbol") in visible_symbols
                ]
            market_data.update(
                {
                    "provider": "MOCK_REPLAY",
                    "source": source,
                    "label": "MOCK / REPLAY",
                    "volume_available": True,
                    "connected": bool(
                        self._replay_thread and self._replay_thread.is_alive()
                    ),
                }
            )
        now = self.clock()
        enriched_quotes = []
        for quote in quotes:
            item = dict(quote)
            received_at = item.get("received_at")
            age = (
                max(0.0, now - float(received_at)) if received_at is not None else None
            )
            item["age_seconds"] = age
            item["stale"] = age is not None and age > 15
            enriched_quotes.append(item)
        market_data["latest_quotes"] = enriched_quotes
        market_data["rejected_observations"] = self._market_rejected
        forming_candles = [
            _contract_dict(candle)
            for candle in sorted(
                self.candles.active.values(),
                key=lambda candle: (candle.symbol, candle.interval),
            )
        ]
        if self.external_market_data is None and account_id is not None:
            visible_symbols = {
                row["symbol"]
                for row in self.store.rows(
                    "SELECT DISTINCT symbol FROM subscriptions WHERE account=?",
                    (account_id,),
                )
            }
            forming_candles = [
                candle
                for candle in forming_candles
                if candle["symbol"] in visible_symbols
            ]
        market_data["forming_candles"] = forming_candles
        provider_key = (
            market_data.get("provider")
            if self.external_market_data is not None
            else "replay"
        )
        cached_count = self._candle_count_cache.get(provider_key)
        if cached_count is None or now - cached_count[0] > 2:
            cached_count = (now, self.store.candle_count(provider_key))
            self._candle_count_cache[provider_key] = cached_count
        market_data["closed_candles_available"] = cached_count[1]
        received_times = [
            float(item["received_at"])
            for item in enriched_quotes
            if item.get("received_at") is not None
        ]
        if not received_times and market_data.get("last_received_at") is not None:
            received_times.append(float(market_data["last_received_at"]))
        feed_age = max(0.0, now - max(received_times)) if received_times else None
        market_data["feed_age_seconds"] = feed_age
        connected = bool(market_data.get("connected"))
        if self.external_market_data is None:
            market_data["feed_status"] = "MOCK_REPLAY" if enriched_quotes else "NO_DATA"
            market_data["stale"] = False
        elif not connected:
            market_data["feed_status"] = "DISCONNECTED"
            market_data["stale"] = False
        elif not enriched_quotes:
            market_data["feed_status"] = "CONNECTED_NO_EVENTS"
            market_data["stale"] = False
        else:
            market_data["stale"] = feed_age is not None and feed_age > 15
            market_data["feed_status"] = "STALE" if market_data["stale"] else "LIVE"
        if market_data["closed_candles_available"]:
            market_data["chart_data_status"] = "HISTORY_AVAILABLE"
            market_data["chart_data_reason"] = None
        elif market_data["forming_candles"]:
            market_data["chart_data_status"] = "FORMING"
            market_data["chart_data_reason"] = "WAITING_FOR_NEXT_BUCKET_OBSERVATION"
        elif enriched_quotes:
            market_data["chart_data_status"] = "QUOTE_ONLY"
            market_data["chart_data_reason"] = "NO_CLOSED_CANDLE_YET"
        else:
            market_data["chart_data_status"] = "UNAVAILABLE"
            market_data["chart_data_reason"] = (
                "PROVIDER_DISCONNECTED"
                if self.external_market_data is not None and not connected
                else "NO_VALID_OBSERVATIONS"
            )
        return market_data

    def provider_readiness(self, account_id: str, market_data=None):
        """Return account-scoped provider evidence without changing authority."""
        adapter = getattr(self.broker_calls, "adapter", self.broker)
        return self.reliability.readiness_projection(
            account_id=account_id,
            market_data=market_data or self.market_data_evidence(),
            external_market_data=self.external_market_data is not None,
            broker_connected=getattr(adapter, "connected", None),
            supports_virtual_closes=bool(
                getattr(adapter, "supports_virtual_closes", False)
            ),
        )

    def snapshot(self, account_id: str | None = None):
        with self.store.lock:
            if account_id is not None:
                sub_rows = self.store.rows(
                    "SELECT * FROM subscriptions WHERE account=?", (account_id,)
                )
                user_strat_ids = {r["id"] for r in sub_rows}
            else:
                sub_rows = self.store.rows("SELECT * FROM subscriptions")
                user_strat_ids = None

            subscriptions = [
                dict(r)
                | {
                    "running": self.strategies.state_for(r) == "RUNNING"
                    and self.risk.strategy_state(r["id"]) == "RUNNING",
                    "state": (
                        "HALTED"
                        if str(self.risk.strategy_state(r["id"])).endswith("HALTED")
                        else self.strategies.state_for(r)
                    ),
                    "strategy_state": self.risk.strategy_state(r["id"]),
                    "readiness": self.strategies.readiness_for(r["id"]),
                }
                for r in sub_rows
            ]

            if account_id is not None:
                positions = [
                    _contract_dict(p) | {"account_id": a}
                    for (a, _, _), p in self.ledger.positions().items()
                    if a == account_id
                ]
            else:
                positions = [
                    _contract_dict(p) | {"account_id": a}
                    for (a, _, _), p in self.ledger.positions().items()
                ]

            risk_budgets = [
                self.risk.budget(r["account"], r["id"], r["symbol"]) for r in sub_rows
            ]

            orders = list(
                reversed(self.history("orders", account_id=account_id)["items"])
            )
            fills = list(
                reversed(self.history("fills", account_id=account_id)["items"])
            )
            counts = {
                "orders": self.history_count("orders", account_id=account_id),
                "fills": self.history_count("fills", account_id=account_id),
            }

            if account_id is not None:
                signals = [
                    s
                    for s in self.strategies.signals
                    if s.get("account") == account_id
                    or (user_strat_ids and s.get("strategy") in user_strat_ids)
                ]
                strategy_errors = [
                    e
                    for e in self.strategies.errors
                    if e.get("account") == account_id
                    or (user_strat_ids and e.get("strategy") in user_strat_ids)
                ]
                audit_rows = []
                for r in self.store.rows(
                    "SELECT * FROM audit ORDER BY sequence DESC LIMIT 100"
                ):
                    try:
                        p = (
                            json.loads(r["payload"])
                            if isinstance(r["payload"], str)
                            else r["payload"]
                        )
                        if isinstance(p, dict):
                            if (
                                p.get("account") == account_id
                                or p.get("account_id") == account_id
                                or (
                                    user_strat_ids
                                    and p.get("strategy") in user_strat_ids
                                )
                            ):
                                audit_rows.append(dict(r))
                    except Exception:
                        pass
                    if len(audit_rows) >= 30:
                        break
            else:
                signals = list(self.strategies.signals)
                strategy_errors = list(self.strategies.errors)
                audit_rows = [
                    dict(r)
                    for r in self.store.rows(
                        "SELECT * FROM audit ORDER BY sequence DESC LIMIT 30"
                    )
                ]

            raw_safety = self.reliability.evidence()
            if account_id is not None:
                safety = json.loads(json.dumps(raw_safety, default=str))
                pos_comp = safety.get("position_comparison", {})
                if "virtual" in pos_comp and isinstance(pos_comp["virtual"], list):
                    pos_comp["virtual"] = [
                        v
                        for v in pos_comp["virtual"]
                        if v.get("account_id") == account_id
                    ]
                if "broker" in pos_comp and isinstance(pos_comp["broker"], list):
                    pos_comp["broker"] = [
                        b
                        for b in pos_comp["broker"]
                        if b.get("account_id") == account_id
                    ]
                user_virt = {
                    (v.get("account_id"), v.get("symbol")): v.get("quantity")
                    for v in (pos_comp.get("virtual") or [])
                }
                user_brok = {
                    (b.get("account_id"), b.get("symbol")): b.get("quantity")
                    for b in (pos_comp.get("broker") or [])
                }
                raw_status = raw_safety.get("position_comparison", {}).get(
                    "status", "UNKNOWN"
                )
                if raw_status in {"UNKNOWN", "FAILED"}:
                    pos_comp["status"] = raw_status
                elif raw_status == "VERIFIED":
                    pos_comp["status"] = (
                        "VERIFIED" if user_virt == user_brok else "FAILED"
                    )
                else:
                    pos_comp["status"] = raw_status

                reconc = safety.get("reconciliation", {})
                if reconc:
                    if isinstance(reconc.get("broker_positions"), list):
                        reconc["broker_positions"] = [
                            b
                            for b in reconc["broker_positions"]
                            if b.get("account_id") == account_id
                        ]
                    if isinstance(reconc.get("unexplained_positions"), list):
                        reconc["unexplained_positions"] = [
                            b
                            for b in reconc["unexplained_positions"]
                            if b.get("account_id") == account_id
                        ]
                    accounts = reconc.pop("accounts", None)
                    if (
                        accounts
                        and account_id in accounts
                        and reconc.get("verified") is True
                    ):
                        acc_data = accounts[account_id]
                        reconc["orders"] = acc_data.get("orders")
                        reconc["unique_fills"] = acc_data.get("unique_fills")
                        reconc["open_orders"] = acc_data.get("open_orders")
                        reconc["duplicate_snapshot_fills"] = acc_data.get(
                            "duplicate_snapshot_fills"
                        )
                        reconc["unattributed_fills"] = acc_data.get(
                            "unattributed_fills"
                        )
                    else:
                        reconc["orders"] = None
                        reconc["unique_fills"] = None
                        reconc["open_orders"] = None
                        reconc["duplicate_snapshot_fills"] = None
                        reconc["unattributed_fills"] = None

                if "unknown_orders" in safety:
                    safety["unknown_orders"] = [
                        r["id"]
                        for r in self.store.rows(
                            "SELECT id FROM orders WHERE status=? AND account=?",
                            (OrderStatus.UNKNOWN, account_id),
                        )
                    ]

                if "fills" in safety and isinstance(safety["fills"], dict):
                    safety["fills"]["unique_applied"] = counts["fills"]
                    user_dups = 0
                    for r in self.store.rows(
                        "SELECT payload FROM audit WHERE type='DUPLICATE_FILL_IGNORED'"
                    ):
                        try:
                            p = (
                                json.loads(r["payload"])
                                if isinstance(r["payload"], str)
                                else r["payload"]
                            )
                            if (
                                p.get("account_id") == account_id
                                or p.get("account") == account_id
                            ):
                                user_dups += 1
                        except Exception:
                            pass
                    safety["fills"]["duplicates_ignored"] = user_dups

                    user_rejections = 0
                    for r in self.store.rows(
                        "SELECT payload FROM audit WHERE type='SAFETY_RESTRICTED' AND payload LIKE '%FILL_EVENT_REJECTED%'"
                    ):
                        try:
                            p = (
                                json.loads(r["payload"])
                                if isinstance(r["payload"], str)
                                else r["payload"]
                            )
                            if (
                                p.get("account_id") == account_id
                                or p.get("account") == account_id
                            ):
                                user_rejections += 1
                        except Exception:
                            pass
                    safety["fills"]["rejected_events"] = user_rejections

                    trusted = (
                        self.reliability.health == "HEALTHY"
                        and not self.broker_calls.uncertain
                        and self.risk.state != Gate.UNCERTAIN
                        and self.reliability.report.get("verified", False)
                        and not self.broker_calls.unsettled
                    )
                    if (
                        trusted
                        and reconc
                        and reconc.get("verified") is True
                        and reconc.get("unattributed_fills") == 0
                    ):
                        safety["fills"]["unattributed_in_last_verified_snapshot"] = 0
                    elif (
                        trusted
                        and reconc
                        and reconc.get("unattributed_fills") is not None
                    ):
                        safety["fills"]["unattributed_in_last_verified_snapshot"] = (
                            reconc.get("unattributed_fills")
                        )
                    else:
                        safety["fills"]["unattributed_in_last_verified_snapshot"] = None
            else:
                safety = raw_safety

            decisions = [
                json.loads(row["payload"])
                for row in reversed(
                    self.store.rows(
                        "SELECT payload FROM audit WHERE type='RISK_DECISION' "
                        "ORDER BY sequence DESC LIMIT 100"
                    )
                )
            ]
            if account_id is not None:
                decisions = [
                    decision
                    for decision in decisions
                    if decision.get("details", {}).get("account_id") == account_id
                ]

            if account_id is not None and self.reliability.certificate:
                kill_cert = asdict(self.reliability.certificate)
                if isinstance(kill_cert.get("broker_positions"), dict):
                    kill_cert["broker_positions"] = {
                        k: v
                        for k, v in kill_cert["broker_positions"].items()
                        if k.startswith(f"{account_id}/")
                    }
                kill_data = kill_cert
            else:
                kill_data = (
                    asdict(self.reliability.certificate)
                    if self.reliability.certificate
                    else None
                )

            market_data = self.market_data_evidence(account_id)
            result = {
                "demo_enabled": self.demo_enabled,
                "failure_lab_enabled": True,
                "mode": (
                    self.external_market_data.telemetry().get(
                        "label", "EXTERNAL MARKET DATA"
                    )
                    if self.external_market_data is not None
                    else (
                        "MOCK / REPLAY"
                        if self.demo_enabled
                        else (
                            "MOCK / PERSISTENT STORE"
                            if isinstance(self.broker, MockBrokerAdapter)
                            else "BROKER ADAPTER / LIVE"
                        )
                    )
                ),
                "storage": self.store.backend_name,
                "health": self.reliability.health,
                "gate": self.risk.state,
                "safety": safety,
                "safety_proof": self.safety_proof.build(),
                "metrics": self.metrics.snapshot(),
                "reconciliation_center": self.reliability.reconciliation_center(),
                "traces": self.traces.recent_traces(10, account_id),
                "safety_bench": self.safety_bench.latest(),
                "subscriptions": subscriptions,
                "positions": positions,
                "risk_budgets": risk_budgets,
                "account_risk": [
                    self.risk.account_budget(row["account"], row["symbol"])
                    for row in self.store.rows(
                        "SELECT DISTINCT account,symbol FROM subscriptions WHERE account=?"
                        if account_id is not None
                        else "SELECT DISTINCT account,symbol FROM subscriptions",
                        (account_id,) if account_id is not None else (),
                    )
                ],
                "risk_decisions": decisions[-20:],
                "orders": orders,
                "fills": fills,
                "counts": counts,
                "candles": [
                    _contract_dict(c)
                    for c in list(self.closed_candles)[-20:]
                    if account_id is None
                    or self.external_market_data is not None
                    or any(row["symbol"] == c.symbol for row in sub_rows)
                ][-20:],
                "signals": signals,
                "strategy_errors": strategy_errors,
                "market_data": market_data,
                "auto_mode": (
                    self.auto_mode.evidence(account_id)
                    if account_id is not None
                    else None
                ),
                "provider_readiness": (
                    self.provider_readiness(account_id, market_data)
                    if account_id is not None
                    else None
                ),
                "market_session": self.market_session.to_dict(self.clock()),
                "audit": audit_rows,
                "kill": kill_data,
            }

            if account_id is not None:
                from backend.shared.presentation import AccountResponseScope

                return AccountResponseScope(self.store, account_id).project(result)
            return result

    def history_count(self, table, account_id: str | None = None):
        if table not in {"orders", "fills"}:
            raise ValueError("unsupported history")
        if account_id is not None:
            return self.store.rows(
                f"SELECT COUNT(*) AS n FROM {table} WHERE account=?", (account_id,)
            )[0]["n"]
        return self.store.rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def history(self, table, limit=200, offset=0, account_id: str | None = None):
        if table not in {"orders", "fills"} or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid history query")
        ordering = "created,id" if table == "orders" else "timestamp,id"
        # Fixed allowlist; parameters bind pagination, never table/order input.
        keys = ordering.replace(",", " DESC,") + " DESC"
        with self.store.lock:
            if account_id is not None:
                return {
                    "items": [
                        dict(r)
                        for r in self.store.rows(
                            f"SELECT * FROM {table} WHERE account=? ORDER BY {keys} LIMIT ? OFFSET ?",
                            (account_id, limit, offset),
                        )
                    ],
                    "total": self.history_count(table, account_id=account_id),
                    "limit": limit,
                    "offset": offset,
                }
            return {
                "items": [
                    dict(r)
                    for r in self.store.rows(
                        f"SELECT * FROM {table} ORDER BY {keys} LIMIT ? OFFSET ?",
                        (limit, offset),
                    )
                ],
                "total": self.history_count(table),
                "limit": limit,
                "offset": offset,
            }

    def close(self):
        """Shut down the platform, strategy runtime executor, and store cleanly."""
        self.stop_replay_stream()
        self.stop_external_market_data()
        self.strategies.close()
        self.store.close()

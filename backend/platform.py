import time
from collections import deque
from collections.abc import Iterable
from threading import Event, Lock, Thread, current_thread
from dataclasses import asdict
from decimal import Decimal

from backend.accounting.charges import calculate_indian_charges
from backend.accounting.ledger import Ledger
from backend.broker.adapters import MockBrokerAdapter
from backend.broker.http_adapter import HTTPMockBrokerAdapter
from backend.execution.orders import OrderManager
from backend.market_data.candles import CandleBuilder
from backend.market_data.session import MarketSession
from backend.reliability.control import Reliability
from backend.reliability.broker_calls import BrokerSession, Deadline
from backend.risk.gateway import RiskGateway
from backend.shared.auth import AuthService
from backend.shared.contracts import GlobalTradingState as Gate, Side, Tick
from backend.shared.store import Store
from backend.strategies.runtime import StrategyRuntime


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
        self.broker_calls = BrokerSession(self.broker)
        self.orders = OrderManager(self.store, self.broker_calls, self.ledger)
        self.risk = RiskGateway(self.store, self.ledger, self.orders, clock)
        self.strategies = StrategyRuntime(self.store)
        self.strategies.may_run = lambda strategy: (
            not self.risk.kill_requested.is_set()
            and self.risk.strategy_state(strategy) == "RUNNING"
        )
        self.market_session = MarketSession()
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
        self.candles = CandleBuilder()
        self.strategies.on_interval_registered = self.candles.add_interval
        for meta in self.strategies.registry.values():
            self.candles.add_interval(meta["interval"])
        self.closed_candles = deque(maxlen=128)
        self.auth = AuthService(self.store)
        self.demo_count = 0
        self._simulation_cursor = {}
        self._simulation_seq = 0
        self._replay_lock = Lock()
        self._replay_stop = Event()
        self._replay_thread = None

    def account(self, account_id):
        if not account_id:
            raise ValueError("account ID required")
        with self.store.transaction() as db:
            db.execute("INSERT INTO accounts VALUES (?)", (account_id,))
            self.store.audit("ACCOUNT_CREATED", {"account_id": account_id})

    def ingest(self, fill):
        with self.store.lock:
            try:
                return self.orders.ingest(fill)
            except Exception:
                self.reliability.fail_closed("FILL_EVENT_REJECTED")
                raise

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
        for upd in updates:
            results.append(self.process_broker_update(upd))
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
        if replay:
            self.require_replay_demo()
        with self.store.lock:
            try:
                accepted, closed = self.candles.ingest_event(tick)
            except ValueError as exc:
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
            self._simulation_cursor[tick.symbol] = max(
                self._simulation_cursor.get(tick.symbol, 0),
                getattr(tick, "event_timestamp", 0),
            )
            self.ledger.marks[tick.symbol] = tick.price
            self.reliability.observe_tick(tick, replay=replay)
            for candle in closed:
                self.closed_candles.append(candle)
        intents = []
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

    def demo(self):
        with self.store.lock:
            if not self.demo_enabled:
                raise ValueError("replay demo is disabled for this database")
            self.require_replay_demo()
            if not self.store.rows("SELECT id FROM accounts WHERE id='demo'"):
                self.account("demo")
            for kind in ("momentum", "mean_reversion", "breakout"):
                if not self.store.rows(
                    "SELECT id FROM subscriptions WHERE id=?", (kind,)
                ):
                    self.strategies.subscribe("demo", kind, kind, "DEMO")
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
        return self.snapshot()

    def start_replay_stream(self, interval=0.75):
        """Continue local mock ticks after an explicit replay action.

        This is intentionally available only for the HTTP mock adapter. It is
        a deterministic local simulator, not a live market-data connection.
        """
        if not isinstance(self.broker, HTTPMockBrokerAdapter):
            return False
        if not self.demo_enabled:
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
                "demo/failure injection requires offline mock storage; production database is protected"
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
            thread.join(timeout=min(1.0, deadline.remaining))

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
                        timeout=self.reliability.kill_deadline.remaining,
                    )
                )

        return self.reliability.kill(
            execute,
            deadline_seconds=deadline.remaining,
            deadline_clock=deadline_clock,
        )

    def strategy_readiness(self, strategy_id: str):
        return self.strategies.readiness_for(strategy_id)

    def snapshot(self):
        with self.store.lock:
            return {
                "mode": (
                    "MOCK / REPLAY"
                    if self.demo_enabled
                    else (
                        "MOCK / PERSISTENT STORE"
                        if isinstance(self.broker, MockBrokerAdapter)
                        else "BROKER ADAPTER / LIVE"
                    )
                ),
                "storage": self.store.backend_name,
                "health": self.reliability.health,
                "gate": self.risk.state,
                "safety": self.reliability.evidence(),
                "subscriptions": [
                    dict(r)
                    | {
                        "running": self.strategies.state_for(r) == "RUNNING"
                        and self.risk.strategy_state(r["id"]) == "RUNNING",
                        "state": self.strategies.state_for(r),
                        "strategy_state": self.risk.strategy_state(r["id"]),
                        "readiness": self.strategies.readiness_for(r["id"]),
                    }
                    for r in self.store.rows("SELECT * FROM subscriptions")
                ],
                "positions": [
                    _contract_dict(p) | {"account_id": a}
                    for (a, _, _), p in self.ledger.positions().items()
                ],
                "risk_budgets": [
                    self.risk.budget(r["account"], r["id"], r["symbol"])
                    for r in self.store.rows("SELECT * FROM subscriptions")
                ],
                "orders": list(reversed(self.history("orders")["items"])),
                "fills": list(reversed(self.history("fills")["items"])),
                "counts": {
                    "orders": self.history_count("orders"),
                    "fills": self.history_count("fills"),
                },
                "candles": [_contract_dict(c) for c in list(self.closed_candles)[-20:]],
                "signals": list(self.strategies.signals),
                "strategy_errors": list(self.strategies.errors),
                "market_data": self.candles.stats(),
                "market_session": self.market_session.to_dict(self.clock()),
                "audit": [
                    dict(r)
                    for r in self.store.rows(
                        "SELECT * FROM audit ORDER BY sequence DESC LIMIT 30"
                    )
                ],
                "kill": asdict(self.reliability.certificate)
                if self.reliability.certificate
                else None,
            }

    def history_count(self, table):
        if table not in {"orders", "fills"}:
            raise ValueError("unsupported history")
        return self.store.rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def history(self, table, limit=200, offset=0):
        if table not in {"orders", "fills"} or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("invalid history query")
        ordering = "created,id" if table == "orders" else "timestamp,id"
        # Fixed allowlist; parameters bind pagination, never table/order input.
        keys = ordering.replace(",", " DESC,") + " DESC"
        with self.store.lock:
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
        self.strategies.close()
        self.store.close()

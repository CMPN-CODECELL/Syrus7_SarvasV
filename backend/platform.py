import time
from dataclasses import asdict
from decimal import Decimal

from backend.accounting.ledger import Ledger
from backend.broker.adapters import MockBrokerAdapter
from backend.execution.orders import OrderManager
from backend.market_data.candles import CandleBuilder, ReplayMarketDataProvider
from backend.reliability.control import Reliability
from backend.risk.gateway import RiskGateway
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
        self.broker = broker if broker is not None else MockBrokerAdapter()
        self.ledger = Ledger(self.store)
        self.orders = OrderManager(self.store, self.broker, self.ledger)
        self.risk = RiskGateway(self.store, self.ledger, self.orders, clock)
        self.strategies = StrategyRuntime(self.store)
        self.reliability = Reliability(
            self.store,
            self.broker,
            self.ledger,
            self.orders,
            self.risk,
            self.strategies,
            clock,
        )
        self.candles = CandleBuilder()
        self.closed_candles = []
        self.demo_count = 0

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
                self.risk.state = "UNCERTAIN"
                self.strategies.enabled = False
                raise

    def tick(self, tick):
        with self.store.lock:
            try:
                accepted, closed = self.candles.ingest_event(tick)
            except ValueError as exc:
                self.risk.state = "UNCERTAIN"
                self.strategies.enabled = False
                with self.store.transaction():
                    self.store.audit(
                        "MARKET_DATA_REJECTED",
                        {
                            "symbol": getattr(tick, "symbol", ""),
                            "event_id": getattr(tick, "event_id", ""),
                            "reason": (
                                "LATE_TICK"
                                if str(exc).startswith("late tick")
                                else "INVALID_TICK"
                            ),
                        },
                    )
                raise
            if not accepted:
                return
            self.ledger.marks[tick.symbol] = tick.price
            for candle in closed:
                self.closed_candles.append(candle)
                for intent in self.strategies.on_candle(candle, self.clock()):
                    decision = self.risk.submit(intent)
                    if decision.allowed and self.risk.state == "RUNNING":
                        order = self.broker.orders[intent.intent_id]
                        if order.remaining_quantity and order.status != "REJECTED":
                            self.ingest(
                                self.broker.execute(
                                    order.order_id,
                                    order.remaining_quantity,
                                    tick.price,
                                    self.clock(),
                                    Decimal("0.01"),
                                )
                            )

    def demo(self):
        with self.store.lock:
            if not self.demo_enabled:
                raise ValueError("replay demo is disabled for this database")
            if not self.store.rows("SELECT id FROM accounts WHERE id='demo'"):
                self.account("demo")
            for kind in ("momentum", "mean_reversion", "breakout"):
                if not self.store.rows(
                    "SELECT id FROM subscriptions WHERE id=?", (kind,)
                ):
                    self.strategies.subscribe("demo", kind, kind, "DEMO")
            self.reliability.resume()
            start = 1_700_000_100 + self.demo_count * 900
            self.demo_count += 1
            for tick in ReplayMarketDataProvider.demo(start).ticks():
                self.tick(tick)
            self.reliability.reconcile()
            # Demo stops safely after replay; subscriptions remain visible.
            return self.snapshot()

    def kill(self):
        def execute(order):
            price = self.ledger.marks.get(order.intent.symbol, Decimal("100"))
            if order.status != "REJECTED":
                self.ingest(
                    self.broker.execute(
                        order.order_id,
                        order.remaining_quantity,
                        price,
                        self.clock(),
                        Decimal("0.01"),
                    )
                )

        return self.reliability.kill(execute)

    def snapshot(self):
        with self.store.lock:
            return {
                "mode": (
                    "MOCK / REPLAY" if self.demo_enabled else "MOCK / PERSISTENT STORE"
                ),
                "health": self.reliability.health,
                "gate": self.risk.state,
                "subscriptions": [
                    dict(r)
                    | {
                        "running": self.strategies.state_for(r) == "RUNNING",
                        "state": self.strategies.state_for(r),
                    }
                    for r in self.store.rows("SELECT * FROM subscriptions")
                ],
                "positions": [
                    _contract_dict(p) | {"account_id": a}
                    for (a, _, _), p in self.ledger.positions().items()
                ],
                "orders": [dict(r) for r in self.store.rows("SELECT * FROM orders")],
                "fills": [dict(r) for r in self.store.rows("SELECT * FROM fills")],
                "candles": [_contract_dict(c) for c in self.closed_candles[-20:]],
                "signals": list(self.strategies.signals),
                "strategy_errors": list(self.strategies.errors),
                "market_data": self.candles.stats(),
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

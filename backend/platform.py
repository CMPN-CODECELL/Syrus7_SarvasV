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


class Platform:
    def __init__(self, path=":memory:", broker=None, clock=time.time, store=None):
        self.clock = clock
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
                self.reliability.fail_closed("FILL_EVENT_REJECTED")
                raise

    def tick(self, tick, *, replay=False):
        if replay:
            self.require_offline_demo()
        with self.store.lock:
            try:
                closed = self.candles.ingest(tick)
            except ValueError:
                self.reliability.fail_closed("MARKET_EVENT_REJECTED")
                raise
            self.reliability.observe_tick(tick, replay=replay)
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
            self.require_offline_demo()
            if not self.store.rows("SELECT id FROM accounts WHERE id='demo'"):
                self.account("demo")
                for kind in ("momentum", "mean_reversion", "breakout"):
                    self.strategies.subscribe("demo", kind, kind, "DEMO")
            previous = self.store.rows(
                "SELECT id FROM orders WHERE strategy IN ('momentum','mean_reversion','breakout')"
            )
            starts = [
                int(r["id"].rsplit(":", 1)[1])
                for r in previous
                if r["id"].rsplit(":", 1)[1].isdigit()
            ]
            start = max(starts, default=1_700_000_100) + 900
            self.demo_count += 1
            events = iter(ReplayMarketDataProvider.demo(start).ticks())
            self.tick(next(events), replay=True)
            self.reliability.resume()
            for tick in events:
                self.tick(tick, replay=True)
            self.reliability.reconcile()
            # Demo stops safely after replay; subscriptions remain visible.
            return self.snapshot()

    def require_offline_demo(self):
        from backend.shared.postgres import PostgresStore

        if isinstance(self.store, PostgresStore) or not isinstance(
            self.broker, MockBrokerAdapter
        ):
            raise ValueError(
                "demo/failure injection requires offline mock storage; production database is protected"
            )

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
                "mode": "MOCK / REPLAY",
                "health": self.reliability.health,
                "gate": self.risk.state,
                "safety": self.reliability.evidence(),
                "subscriptions": [
                    dict(r)
                    | {
                        "running": self.strategies.enabled
                        and self.risk.strategy_state(r["id"]) == "RUNNING",
                        "strategy_state": self.risk.strategy_state(r["id"]),
                    }
                    for r in self.store.rows("SELECT * FROM subscriptions")
                ],
                "positions": [
                    asdict(p) | {"account_id": a}
                    for (a, _, _), p in self.ledger.positions().items()
                ],
                "risk_budgets": [
                    self.risk.budget(r["account"], r["id"], r["symbol"])
                    for r in self.store.rows("SELECT * FROM subscriptions")
                ],
                "orders": [dict(r) for r in self.store.rows("SELECT * FROM orders")],
                "fills": [dict(r) for r in self.store.rows("SELECT * FROM fills")],
                "candles": [asdict(c) for c in self.closed_candles[-20:]],
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

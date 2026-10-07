from decimal import Decimal

from backend.shared.contracts import Fill, Side, StrategyPosition


class Ledger:
    def __init__(self, store):
        self.store = store
        self.marks = {}

    def apply(self, fill: Fill):
        if fill.quantity <= 0 or fill.price <= 0 or fill.charges < 0:
            raise ValueError("invalid fill economics")
        with self.store.transaction() as db:
            previous = db.execute(
                "SELECT * FROM fills WHERE id=?", (fill.fill_id,)
            ).fetchone()
            values = (
                fill.fill_id,
                fill.broker_order_id,
                fill.strategy_instance_id,
                fill.account_id,
                fill.symbol,
                fill.side.value,
                fill.quantity,
                str(fill.price),
                fill.timestamp,
                str(fill.charges),
            )
            if previous:
                if (
                    tuple(
                        previous[k]
                        for k in (
                            "id",
                            "order_id",
                            "strategy",
                            "account",
                            "symbol",
                            "side",
                            "quantity",
                            "price",
                            "timestamp",
                            "charges",
                        )
                    )
                    != values
                ):
                    raise ValueError("conflicting duplicate fill")
                return False
            db.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?)", values)
            self.store.audit("FILL_APPLIED", {"fill_id": fill.fill_id})
            return True

    def _calculate(self, now=None):
        state = {}
        daily = {}
        for f in self.store.rows("SELECT * FROM fills ORDER BY timestamp,id"):
            key = (f["account"], f["strategy"], f["symbol"])
            q, avg, realized, charges = state.get(
                key, (0, Decimal(0), Decimal(0), Decimal(0))
            )
            delta = f["quantity"] * Side(f["side"]).sign
            price = Decimal(f["price"])
            before_realized = realized
            if not q or q * delta > 0:
                avg = (abs(q) * avg + abs(delta) * price) / abs(q + delta)
            else:
                realized += (
                    min(abs(q), abs(delta)) * (price - avg) * (1 if q > 0 else -1)
                )
                if abs(delta) > abs(q):
                    avg = price
                elif delta == -q:
                    avg = Decimal(0)
            state[key] = (q + delta, avg, realized, charges + Decimal(f["charges"]))
            if now is not None and int((f["timestamp"] + 19800) // 86400) == int(
                (now + 19800) // 86400
            ):
                daily[key] = (
                    daily.get(key, Decimal(0))
                    + realized
                    - before_realized
                    - Decimal(f["charges"])
                )
        result = {}
        for (account, strategy, symbol), (q, avg, realized, charges) in state.items():
            unrealized = q * (self.marks.get(symbol, avg) - avg)
            result[(account, strategy, symbol)] = StrategyPosition(
                strategy,
                symbol,
                q,
                avg,
                realized,
                unrealized,
                charges,
                realized + unrealized - charges,
            )
        return result, daily

    def positions(self):
        return self._calculate()[0]

    def quantity(self, account, strategy, symbol):
        p = self.positions().get((account, strategy, symbol))
        return p.net_quantity if p else 0

    def aggregate(self):
        result = {}
        for (account, _, symbol), p in self.positions().items():
            key = (account, symbol)
            result[key] = result.get(key, 0) + p.net_quantity
        return {k: v for k, v in result.items() if v}

    def daily_net(self, account, strategy, now):
        positions, daily = self._calculate(now)
        # Design decision: current unrealized P&L + session realized P&L - session charges.
        # Midnight Asia/Kolkata defines the bootstrap session; sponsor semantics remain open.
        return sum(
            (
                daily.get(key, Decimal(0)) + p.unrealized_pnl
                for key, p in positions.items()
                if key[0] == account and key[1] == strategy
            ),
            Decimal(0),
        )

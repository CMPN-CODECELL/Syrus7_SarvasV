from backend.shared.contracts import OrderIntent, Side


KINDS = {"momentum", "mean_reversion", "breakout"}


class StrategyRuntime:
    """Built-in callbacks receive candles only; broker authority is never passed in."""

    def __init__(self, store):
        self.store = store
        self.enabled = False
        self.last_close = {}

    def subscribe(self, account, strategy, kind, symbol):
        if kind not in KINDS:
            raise ValueError("unknown strategy")
        with self.store.transaction() as db:
            if not db.execute(
                "SELECT id FROM accounts WHERE id=?", (account,)
            ).fetchone():
                raise ValueError("account does not exist")
            db.execute(
                "INSERT INTO subscriptions VALUES (?,?,?,?)",
                (strategy, account, kind, symbol),
            )
            self.store.audit("SUBSCRIBED", {"strategy": strategy, "account": account})

    def on_candle(self, candle, now):
        if not self.enabled or candle.interval != 60 or not candle.is_closed:
            return []
        intents = []
        for sub in self.store.rows(
            "SELECT * FROM subscriptions WHERE symbol=?", (candle.symbol,)
        ):
            previous = self.last_close.get(sub["id"])
            self.last_close[sub["id"]] = candle.close
            if sub["kind"] == "momentum":
                side = Side.BUY if candle.close > candle.open else Side.SELL
            elif sub["kind"] == "mean_reversion":
                side = Side.SELL if candle.close > candle.open else Side.BUY
            else:
                if previous is None or candle.close <= previous:
                    continue
                side = Side.BUY
            intents.append(
                OrderIntent(
                    f"{sub['id']}:{candle.start_time}",
                    sub["id"],
                    sub["account"],
                    candle.symbol,
                    side,
                    1,
                    now,
                    reason=f"{sub['kind']} closed 1m candle",
                )
            )
        return intents

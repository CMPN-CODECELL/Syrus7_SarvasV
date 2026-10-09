import json


class TraceService:
    def __init__(self, store, ledger=None):
        self.store = store
        self.ledger = ledger

    def trace(self, trace_id, account_id=None):
        rows = self.store.rows(
            "SELECT sequence,type,payload,recorded_at,correlation_id FROM audit "
            "WHERE correlation_id=? ORDER BY sequence",
            (trace_id,),
        )
        events = []
        strategy = None
        account = None
        symbol = None
        for row in rows:
            payload = json.loads(row["payload"])
            strategy = (
                strategy
                or payload.get("strategy")
                or payload.get("strategy_instance_id")
            )
            account = (
                account
                or payload.get("account")
                or payload.get("account_id")
                or payload.get("details", {}).get("account_id")
            )
            symbol = symbol or payload.get("symbol")
            events.append(
                {
                    "sequence": row["sequence"],
                    "type": row["type"],
                    "recorded_at": row["recorded_at"],
                    "payload": payload,
                }
            )
        order_rows = self.store.rows("SELECT * FROM orders WHERE id=?", (trace_id,))
        order_info = None
        if order_rows:
            o = order_rows[0]
            account = account or o["account"]
            strategy = strategy or o["strategy"]
            symbol = symbol or o["symbol"]
            order_info = {
                "order_id": o["id"],
                "strategy_instance_id": o["strategy"],
                "account_id": o["account"],
                "symbol": o["symbol"],
                "side": o["side"],
                "quantity": o["quantity"],
                "status": o["status"],
                "filled_quantity": o["filled"],
                "created_at": o["created"],
            }
        if account_id and account != account_id:
            raise PermissionError("trace belongs to another account")

        fill_rows = self.store.rows(
            "SELECT * FROM fills WHERE order_id=? ORDER BY timestamp, id", (trace_id,)
        )
        fills = [
            {
                "fill_id": f["id"],
                "order_id": f["order_id"],
                "strategy_instance_id": f["strategy"],
                "account_id": f["account"],
                "symbol": f["symbol"],
                "side": f["side"],
                "quantity": f["quantity"],
                "price": str(f["price"]),
                "charges": str(f["charges"]),
                "timestamp": f["timestamp"],
            }
            for f in fill_rows
        ]

        financial_outcome = None
        if self.ledger and account and strategy and symbol:
            pos = self.ledger.positions().get((account, strategy, symbol))
            if pos:
                financial_outcome = {
                    "strategy_instance_id": pos.strategy_instance_id,
                    "symbol": pos.symbol,
                    "net_quantity": pos.net_quantity,
                    "average_price": str(pos.average_price),
                    "realized_pnl": str(pos.realized_pnl),
                    "unrealized_pnl": str(pos.unrealized_pnl),
                    "gross_pnl": str(pos.gross_pnl),
                    "charges": str(pos.charges),
                    "net_pnl": str(pos.net_pnl),
                }

        return {
            "trace_id": trace_id,
            "strategy_instance_id": strategy,
            "account_id": account,
            "events": events,
            "order": order_info,
            "fills": fills,
            "financial_outcome": financial_outcome,
        }

    def recent_traces(self, limit=20, account_id=None):
        if account_id:
            rows = self.store.rows(
                "SELECT a.correlation_id, MAX(a.sequence) AS latest_sequence "
                "FROM audit a LEFT JOIN orders o ON o.id=a.correlation_id "
                "WHERE o.account=? AND a.correlation_id IS NOT NULL "
                "GROUP BY a.correlation_id ORDER BY latest_sequence DESC LIMIT ?",
                (account_id, limit),
            )
        else:
            rows = self.store.rows(
                "SELECT correlation_id, MAX(sequence) AS latest_sequence "
                "FROM audit WHERE correlation_id IS NOT NULL "
                "GROUP BY correlation_id ORDER BY latest_sequence DESC LIMIT ?",
                (limit,),
            )
        return [self.trace(row["correlation_id"], account_id) for row in rows]

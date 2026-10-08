import json


class TraceService:
    def __init__(self, store):
        self.store = store

    def trace(self, trace_id, account_id=None):
        rows = self.store.rows(
            "SELECT sequence,type,payload,recorded_at,correlation_id FROM audit "
            "WHERE correlation_id=? ORDER BY sequence",
            (trace_id,),
        )
        events = []
        strategy = None
        account = None
        for row in rows:
            payload = json.loads(row["payload"])
            strategy = (
                strategy
                or payload.get("strategy")
                or payload.get("strategy_instance_id")
            )
            account = account or payload.get("account") or payload.get("account_id")
            events.append(
                {
                    "sequence": row["sequence"],
                    "type": row["type"],
                    "recorded_at": row["recorded_at"],
                    "payload": payload,
                }
            )
        order = self.store.rows(
            "SELECT account,strategy FROM orders WHERE id=?", (trace_id,)
        )
        if order:
            account = account or order[0]["account"]
            strategy = strategy or order[0]["strategy"]
        if account_id and account and account != account_id:
            raise PermissionError("trace belongs to another account")
        return {
            "trace_id": trace_id,
            "strategy_instance_id": strategy,
            "account_id": account,
            "events": events,
        }

    def recent_traces(self, limit=20, account_id=None):
        args = (account_id, limit) if account_id else (limit,)
        where = "WHERE o.account=?" if account_id else ""
        rows = self.store.rows(
            "SELECT DISTINCT a.correlation_id FROM audit a "
            "LEFT JOIN orders o ON o.id=a.correlation_id "
            f"{where} AND a.correlation_id IS NOT NULL "
            "ORDER BY a.sequence DESC LIMIT ?"
            if where
            else "SELECT DISTINCT correlation_id FROM audit "
            "WHERE correlation_id IS NOT NULL ORDER BY sequence DESC LIMIT ?",
            args,
        )
        return [self.trace(row["correlation_id"], account_id) for row in rows]

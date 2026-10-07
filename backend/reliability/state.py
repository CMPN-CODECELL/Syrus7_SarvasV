import json


class SafetyRepository:
    """Risk/reliability owned durable state; values are never broker credentials."""

    def __init__(self, store):
        self.store = store

    def get(self, key, default=None):
        rows = self.store.rows("SELECT value FROM safety_values WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key, value):
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO safety_values VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, default=str)),
            )

    def mark(self, tick, received_at, source):
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO risk_marks VALUES (?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET price=excluded.price,event_timestamp=excluded.event_timestamp,received_at=excluded.received_at,source=excluded.source",
                (
                    tick.symbol,
                    str(tick.price),
                    tick.event_timestamp,
                    received_at,
                    source,
                ),
            )

"""Durable external mock fixture, independent of the platform execution ledger."""

import json
import os
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from backend.shared.contracts import (
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    Side,
)


class MockPersistence:
    def __init__(self, path):
        self.path = Path(path) if path else None

    def load(self):
        if self.path is None or not self.path.exists():
            return {}, {}, {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data["version"] != 1:
                raise ValueError("unsupported mock state version")
            orders = {}
            for row in data["orders"]:
                i = row["intent"]
                i["side"] = Side(i["side"])
                if i["limit_price"] is not None:
                    i["limit_price"] = Decimal(i["limit_price"])
                order = CanonicalOrder(
                    row["order_id"],
                    OrderIntent(**i),
                    OrderStatus(row["status"]),
                    row["filled_quantity"],
                )
                orders[order.order_id] = order
            fills = {}
            for row in data["fills"]:
                row["side"] = Side(row["side"])
                row["price"], row["charges"] = (
                    Decimal(row["price"]),
                    Decimal(row["charges"]),
                )
                fill = Fill(**row)
                fills[fill.fill_id] = fill
            external = {(a, s): q for a, s, q in data["external_positions"]}
            return orders, fills, external
        except Exception:
            raise ValueError(
                "external mock state unreadable; recovery requires intact broker evidence"
            ) from None

    def save(self, orders, fills, external):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "orders": [asdict(o) for o in orders.values()],
            "fills": [asdict(f) for f in fills.values()],
            "external_positions": [(a, s, q) for (a, s), q in external.items()],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

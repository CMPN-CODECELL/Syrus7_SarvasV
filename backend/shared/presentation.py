"""Account response boundary, independent of authoritative financial calculations."""

import json
import re
from dataclasses import asdict, is_dataclass


_OMIT = object()
_GLOBAL_STATES = {
    "RUNNING",
    "STOPPED",
    "RECOVERING",
    "REDUCE_ONLY",
    "KILLING",
    "KILLED",
    "UNCERTAIN",
    "HEALTHY",
    "DEGRADED",
    "DRIFTED",
    "SUCCESS",
    "SAFE_LATE",
    "FAILED",
    "UNKNOWN",
    "VERIFIED",
    "NOT_APPLICABLE",
    "UNSAFE",
    "VERIFIED_SAFE",
}


class AccountResponseScope:
    """Project nested domain evidence using durable ownership, never caller IDs.

    Global gate/verdict/timing and aggregate diagnostics retain their meaning.
    Foreign attributed records and references are omitted, including JSON audit
    payloads. This operates on copies only, after internal calculations finish.
    """

    def __init__(self, store, account_id):
        self.account_id = account_id
        self.owners = {}
        for table in ("subscriptions", "orders", "fills"):
            for row in store.rows(f"SELECT id,account FROM {table}"):
                self._remember(row["id"], row["account"])
        for row in store.rows("SELECT id FROM accounts"):
            self._remember(row["id"], row["id"])
        self.symbols = {
            row["symbol"]
            for row in store.rows(
                "SELECT symbol FROM subscriptions WHERE account=?", (account_id,)
            )
        }
        foreign = [key for key, owner in self.owners.items() if owner != account_id]
        self.foreign_pattern = (
            re.compile(
                r"(?<![\w])(?:"
                + "|".join(re.escape(k) for k in sorted(foreign, key=len, reverse=True))
                + r")(?![\w])"
            )
            if foreign
            else None
        )

    def _remember(self, identity, owner):
        # Namespace collisions cannot grant access to an identifier owned by B.
        if identity in self.owners and self.owners[identity] != owner:
            self.owners[identity] = None
        else:
            self.owners[identity] = owner

    def project(self, value):
        result = self._project(value)
        return None if result is _OMIT else result

    def _project(self, value, field=""):
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            attributed = (
                value.get("account") == self.account_id
                or value.get("account_id") == self.account_id
                or value.get("details", {}).get("account_id") == self.account_id
                or any(
                    isinstance(value.get(key), str)
                    and self.owners.get(value[key]) == self.account_id
                    for key in ("strategy", "strategy_instance_id")
                )
            )
            if (
                field != "invariants"
                and value.get("id") in self.owners
                and self.owners[value["id"]] != self.account_id
            ):
                return _OMIT
            for key in ("account", "account_id"):
                if isinstance(value.get(key), str) and value[key] != self.account_id:
                    return _OMIT
            for key in (
                "strategy",
                "strategy_instance_id",
                "order_id",
                "broker_order_id",
                "fill_id",
                "intent_id",
                "trace_id",
                "correlation_id",
            ):
                identity = value.get(key)
                if (
                    isinstance(identity, str)
                    and self.owners.get(
                        identity, self.account_id if attributed else None
                    )
                    != self.account_id
                ):
                    return _OMIT
            result = {}
            for key, item in value.items():
                if field == "last_event_timestamp" and key not in self.symbols:
                    continue
                if (
                    field in {"accounts", "broker_positions"}
                    and key in self.owners
                    and self.owners[key] != self.account_id
                ):
                    continue
                if "/" in key and key.split("/", 1)[0] != self.account_id:
                    continue
                projected = self._project(item, key)
                if key == "payload" and projected is _OMIT:
                    return _OMIT
                if projected is not _OMIT:
                    result[key] = projected
            if result.get("provider") == "MOCK_REPLAY":
                for key in ("latest_quotes", "forming_candles"):
                    if isinstance(result.get(key), list):
                        result[key] = [
                            item
                            for item in result[key]
                            if isinstance(item, dict)
                            and item.get("symbol") in self.symbols
                        ]
            if "accounts" in value and "verified" in value:
                breakdown = (
                    value["accounts"].get(self.account_id, {})
                    if value["verified"]
                    else {}
                )
                for key in (
                    "orders",
                    "unique_fills",
                    "open_orders",
                    "duplicate_snapshot_fills",
                    "unattributed_fills",
                ):
                    result[key] = breakdown.get(key)
                result.pop("accounts", None)
            if "recovered_fill_ids" in result:
                result["recovered_fill_count"] = len(result["recovered_fill_ids"])
            return result
        if isinstance(value, (list, tuple)):
            result = []
            for item in value:
                if field in {"feeds", "candles", "stale_feeds"}:
                    symbol = item.get("symbol") if isinstance(item, dict) else item
                    if symbol not in self.symbols:
                        continue
                projected = self._project(item, field)
                if projected is not _OMIT:
                    result.append(projected)
            return result
        if isinstance(value, str):
            if (
                field in {"status", "gate", "health", "verdict"}
                and value in _GLOBAL_STATES
            ):
                return value
            if field == "id" and value in {f"I{i}" for i in range(1, 11)}:
                return value
            if field == "payload":
                try:
                    payload = self._project(json.loads(value))
                    return json.dumps(payload) if payload is not _OMIT else _OMIT
                except (ValueError, TypeError):
                    return _OMIT
            if field in {"unknown_orders", "recovered_fill_ids"}:
                return value if self.owners.get(value) == self.account_id else _OMIT
            if self.owners.get(value, self.account_id) != self.account_id:
                return _OMIT
            if self.foreign_pattern and self.foreign_pattern.search(value):
                return "[redacted]"
        return value

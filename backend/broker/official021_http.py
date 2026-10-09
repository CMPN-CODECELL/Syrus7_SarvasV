"""Authenticated REST transport for the documented 021 developer API.

The transport owns provider-specific HTTP, paise conversion, instrument lookup,
and provider-order mapping.  Domain modules see only canonical AlgoShield
contracts.  No credentials are read from tracked files; callers pass them from
process configuration or an ignored local environment file.
"""

from __future__ import annotations

import csv
import gzip
import io
import os
import time
from decimal import Decimal
from typing import Any

import httpx

from backend.broker.official021 import (
    CODE_TO_EXCHANGE,
    EXCHANGE_TO_CODE,
    REQUEST_EXCHANGE,
    Instrument021,
    Provider021Blocked,
    Provider021Error,
    Provider021ProtocolError,
    Provider021WriteUncertain,
    classify_http_error,
    paise_to_rupees,
    parse_envelope,
    parse_plain_list,
)
from backend.shared.contracts import (
    BrokerSnapshot,
    BrokerUpdate,
    BrokerUpdateType,
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    Side,
)


STATUS_MAP = {
    "Received": OrderStatus.OPEN,
    "Placed": OrderStatus.OPEN,
    "Pending": OrderStatus.OPEN,
    "Executed": OrderStatus.FILLED,
    "Rejected": OrderStatus.REJECTED,
    "Cancelled": OrderStatus.CANCELLED,
    "Frozen": OrderStatus.UNKNOWN,
    "SentForModification": OrderStatus.OPEN,
    "SentForCancellation": OrderStatus.OPEN,
    "AcceptedForAMO": OrderStatus.OPEN,
}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _signed_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise Provider021ProtocolError("021 quantity is not an integer") from exc


def _paise(value: Any) -> Decimal:
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise Provider021ProtocolError("021 price is not an integer") from exc
    if integer <= 0:
        raise Provider021ProtocolError("021 price must be positive for an execution")
    return paise_to_rupees(integer)


def _request_exchange(exchange: str) -> str:
    try:
        return REQUEST_EXCHANGE[exchange]
    except KeyError as exc:
        raise Provider021ProtocolError(f"unsupported 021 exchange {exchange}") from exc


class Official021RESTAdapter:
    """Live REST implementation of the canonical broker adapter protocol."""

    supports_virtual_closes = False
    provider = "021"

    def __init__(
        self,
        store,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
        product: str = "INTRADAY",
        timeout: float = 8.0,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        instrument_cache: str | None = None,
    ):
        self.store = store
        self.base_url = (
            base_url or os.getenv(
                "ALGOSHIELD_021_BASE_URL",
                "https://devapi.021.trade/api/developer-api/v1",
            )
        ).rstrip("/")
        self.username = username or os.getenv("ALGOSHIELD_021_USERNAME")
        self.password = password or os.getenv("ALGOSHIELD_021_PASSWORD")
        self.access_token = access_token or os.getenv("ALGOSHIELD_021_TOKEN")
        self.product = product
        self.timeout = timeout
        self.instrument_cache = instrument_cache or os.getenv(
            "ALGOSHIELD_021_INSTRUMENT_CACHE"
        )
        self.instruments: dict[str, Instrument021] = {}
        self._provider_orders: dict[str, str] = {}
        self._seen_trade_ids: set[str] = set()
        self.connected = False
        self.updates: list[BrokerUpdate] = []
        self.client = client or httpx.Client(timeout=timeout, transport=transport)
        self._owns_client = client is None

    def close(self):
        if self._owns_client:
            self.client.close()

    def _auth(self) -> str:
        if self.access_token:
            return self.access_token
        if not self.username or not self.password:
            raise Provider021Blocked(
                "021 credentials are not configured; set ALGOSHIELD_021_USERNAME and ALGOSHIELD_021_PASSWORD"
            )
        response = self.client.post(
            f"{self.base_url}/auth/token",
            json={"username": self.username, "password": self.password},
        )
        if response.status_code >= 400:
            self._raise_http(response, write=False)
        data = parse_envelope(response.json())
        token = data.get("accessToken") if isinstance(data, dict) else None
        if not token:
            raise Provider021ProtocolError("021 token response omitted accessToken")
        self.access_token = str(token)
        return self.access_token

    def _raise_http(self, response: httpx.Response, *, write: bool):
        error_type = classify_http_error(response.status_code, write=write)
        detail = "021 request failed"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("error") or payload.get("detail") or detail)
        except Exception:
            pass
        raise error_type(f"HTTP {response.status_code}: {detail}")

    def _request(self, method: str, path: str, *, json: dict | None = None, write=False):
        token = self._auth()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = self.client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json,
            )
        except httpx.TimeoutException as exc:
            if write:
                raise Provider021WriteUncertain("021 write timed out") from exc
            raise Provider021Error("021 request timed out") from exc
        except httpx.HTTPError as exc:
            raise Provider021Error("021 transport failure") from exc
        if response.status_code == 401 and self.username and self.password:
            # The provider revokes the previous token on login; refresh once,
            # never retry a write after an uncertain 401 response.
            if write:
                self._raise_http(response, write=True)
            self.access_token = None
            token = self._auth()
            response = self.client.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )
        if response.status_code >= 400:
            self._raise_http(response, write=write)
        self.connected = True
        return response

    def _load_instruments(self):
        if self.instrument_cache and os.path.isfile(self.instrument_cache):
            with open(self.instrument_cache, "rb") as stream:
                payload = stream.read()
        else:
            response = self._request("GET", "/instruments")
            payload = response.content
            if self.instrument_cache:
                with open(self.instrument_cache, "wb") as stream:
                    stream.write(payload)
        if payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
        try:
            rows = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
            loaded: dict[str, Instrument021] = {}
            for row in rows:
                exchange = row.get("exchange", "").strip()
                if exchange not in EXCHANGE_TO_CODE:
                    continue
                symbol = row.get("symbol", "").strip().upper()
                if not symbol or row.get("instrument_type") not in {"STK", "FUTSTK", "FUTIDX", "OPTSTK", "OPTIDX", "IDX"}:
                    continue
                try:
                    token = int(row["token"])
                    lot = max(1, int(row.get("board_lot_quantity") or 1))
                    freeze = int(row["freeze_quantity"] or 0) or None
                    tick = max(1, int(row.get("ticksize") or 1))
                except (TypeError, ValueError, KeyError):
                    continue
                loaded.setdefault(
                    symbol,
                    Instrument021(
                        EXCHANGE_TO_CODE[exchange],
                        token,
                        symbol,
                        product=self.product,
                        lot_size=lot,
                        freeze_quantity=freeze,
                        tick_size_paise=tick,
                    ),
                )
            if not loaded:
                raise Provider021ProtocolError("021 instruments response contained no usable rows")
            self.instruments = loaded
        except UnicodeDecodeError as exc:
            raise Provider021ProtocolError("021 instruments response is not UTF-8 CSV") from exc

    def _instrument(self, symbol: str) -> Instrument021:
        if not self.instruments:
            self._load_instruments()
        try:
            return self.instruments[symbol.upper()]
        except KeyError as exc:
            raise Provider021Blocked(f"no 021 instrument mapping for {symbol}") from exc

    def _mapping(self, platform_order_id: str):
        rows = self.store.rows(
            "SELECT * FROM broker_order_mappings WHERE platform_order_id=? AND provider=?",
            (platform_order_id, self.provider),
        )
        if not rows:
            raise Provider021Blocked("021 order mapping is unavailable; reconcile before mutation")
        return rows[0]

    def submit(self, intent: OrderIntent) -> CanonicalOrder:
        instrument = self._instrument(intent.symbol)
        price = 0 if intent.order_type == "MARKET" else int(intent.limit_price * 100)
        if price and price % instrument.tick_size_paise:
            raise Provider021Blocked("limit price is not aligned to 021 tick size")
        payload = {
            "exchange": _request_exchange(CODE_TO_EXCHANGE[instrument.exchange]),
            "token": instrument.token,
            "qty": intent.quantity * intent.side.sign,
            "price": price,
            "book": "RL",
            "trigger": 0,
            "discQuantity": 0,
            "product": instrument.product,
            "validity": "Day",
            "amo": False,
        }
        response = self._request("POST", "/orders", json=payload, write=True)
        data = parse_envelope(response.json())
        if not isinstance(data, dict) or not data.get("orderId"):
            raise Provider021ProtocolError("021 order response omitted orderId")
        provider_order_id = str(data["orderId"])
        try:
            with self.store.transaction() as db:
                db.execute(
                    "INSERT INTO broker_order_mappings(platform_order_id,provider,provider_order_id,account,exchange,token,product,symbol,created) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        intent.intent_id,
                        self.provider,
                        provider_order_id,
                        intent.account_id,
                        CODE_TO_EXCHANGE[instrument.exchange],
                        instrument.token,
                        instrument.product,
                        intent.symbol,
                        time.time(),
                    ),
                )
                self.store.audit(
                    "021_ORDER_MAPPED",
                    {"order_id": intent.intent_id, "provider_order_id": provider_order_id},
                )
        except Exception as exc:
            raise Provider021WriteUncertain("021 order accepted but mapping was not durably recorded") from exc
        self._provider_orders[intent.intent_id] = provider_order_id
        return CanonicalOrder(intent.intent_id, intent, OrderStatus.OPEN)

    def cancel(self, order_id: str, timeout: float | None = None) -> None:
        mapping = self._mapping(order_id)
        self._request(
            "DELETE",
            f"/orders/{mapping['provider_order_id']}",
            json={
                "exchange": _request_exchange(mapping["exchange"]),
                "token": mapping["token"],
                "product": mapping["product"],
            },
            write=True,
        )
        deadline = time.monotonic() + min(timeout or self.timeout, self.timeout)
        while time.monotonic() < deadline:
            rows = parse_plain_list(
                self._request("GET", f"/orders/{mapping['provider_order_id']}").json()
            )
            if rows:
                status = STATUS_MAP.get(_text(rows[0].get("status")), OrderStatus.UNKNOWN)
                if status in {OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED}:
                    return
            time.sleep(0.05)
        raise Provider021WriteUncertain("021 cancellation remains pending; reconciliation required")

    def _local_intent(self, row):
        order = self.store.rows("SELECT * FROM orders WHERE id=?", (row["platform_order_id"],))
        if not order:
            raise Provider021ProtocolError("mapped 021 order has no local intent")
        local = order[0]
        return OrderIntent(
            local["id"],
            local["strategy"],
            local["account"],
            local["symbol"],
            Side(local["side"]),
            local["quantity"],
            local["created"],
        )

    def _orders(self):
        return parse_plain_list(self._request("GET", "/orders").json())

    def _trades(self):
        return parse_plain_list(self._request("GET", "/trades").json())

    def _mapped_trades(self, mapped):
        """Fetch trades per mapped order because the aggregate response has no order ID."""
        trades = []
        for provider_order_id in mapped:
            rows = parse_plain_list(
                self._request("GET", f"/orders/{provider_order_id}/trades").json()
            )
            for row in rows:
                trades.append({**row, "orderId": provider_order_id})
        return trades

    def snapshot(self) -> BrokerSnapshot:
        orders = self._orders()
        trades = self._mapped_trades(
            {row["provider_order_id"]: row for row in self.store.rows("SELECT * FROM broker_order_mappings WHERE provider=?", (self.provider,))}
        )
        positions = parse_plain_list(self._request("GET", "/portfolio/positions").json())
        mapped = {row["provider_order_id"]: row for row in self.store.rows("SELECT * FROM broker_order_mappings WHERE provider=?", (self.provider,))}
        canonical_orders = []
        complete = True
        for row in orders:
            mapping = mapped.get(_text(row.get("orderId")))
            if mapping is None:
                complete = False
                continue
            intent = self._local_intent(mapping)
            status = STATUS_MAP.get(_text(row.get("status")), OrderStatus.UNKNOWN)
            filled = abs(_signed_int(row.get("qtyTraded", 0)))
            if filled > intent.quantity:
                raise Provider021ProtocolError("021 order reports overfill")
            canonical_orders.append(CanonicalOrder(intent.intent_id, intent, status, filled))
        fills = self._fills_from_trades(trades, mapped)
        position_map = {}
        accounts = {row["account"] for row in mapped.values()}
        account_id = next(iter(accounts)) if len(accounts) == 1 else None
        if positions and account_id is None:
            complete = False
        for row in positions:
            exchange = row.get("exchange")
            token = row.get("token")
            symbol = _text(row.get("symbol")) or self._symbol_for_token(exchange, token)
            if symbol and account_id:
                position_map[(account_id, symbol)] = _signed_int(row.get("netQuantity", 0))
        return BrokerSnapshot(tuple(canonical_orders), tuple(fills), position_map, complete, time.time())

    def _symbol_for_token(self, exchange, token):
        for instrument in self.instruments.values():
            if instrument.token == int(token or 0) and CODE_TO_EXCHANGE.get(instrument.exchange) == exchange:
                return instrument.symbol
        return None

    def _fills_from_trades(self, trades, mapped):
        fills = []
        for trade in trades:
            provider_order_id = _text(trade.get("orderId"))
            mapping = mapped.get(provider_order_id)
            if mapping is None:
                continue
            trade_id = _text(trade.get("tradeId"))
            if not trade_id:
                raise Provider021ProtocolError(
                    f"021 trade for order {provider_order_id} has no tradeId"
                )
            intent = self._local_intent(mapping)
            signed = _signed_int(trade.get("quantity"))
            if signed == 0 or (signed > 0) != (intent.side == Side.BUY):
                raise Provider021ProtocolError("021 trade side does not match mapped intent")
            fills.append(
                Fill(
                    f"021:{trade_id}",
                    intent.intent_id,
                    intent.strategy_instance_id,
                    intent.account_id,
                    intent.symbol,
                    intent.side,
                    abs(signed),
                    _paise(trade.get("price")),
                    float(trade.get("tradeTime", time.time())),
                    Decimal("0"),
                )
            )
        return fills

    def drain_updates(self) -> list[BrokerUpdate]:
        orders = self._orders()
        mapped = {row["provider_order_id"]: row for row in self.store.rows("SELECT * FROM broker_order_mappings WHERE provider=?", (self.provider,))}
        trades = self._mapped_trades(mapped)
        updates = []
        for row in orders:
            mapping = mapped.get(_text(row.get("orderId")))
            if mapping is None:
                continue
            intent = self._local_intent(mapping)
            status = STATUS_MAP.get(_text(row.get("status")), OrderStatus.UNKNOWN)
            update_type = {
                OrderStatus.REJECTED: BrokerUpdateType.ORDER_REJECTED,
                OrderStatus.CANCELLED: BrokerUpdateType.ORDER_CANCELLED,
                OrderStatus.OPEN: BrokerUpdateType.ORDER_ACCEPTED,
            }.get(status, BrokerUpdateType.ORDER_STATUS)
            updates.append(BrokerUpdate(f"021:status:{mapping['provider_order_id']}:{status.value}", intent.intent_id, update_type, status, timestamp=float(row.get("lastActivity", time.time()))))
        for fill in self._fills_from_trades(trades, mapped):
            if fill.fill_id in self._seen_trade_ids:
                continue
            self._seen_trade_ids.add(fill.fill_id)
            updates.append(BrokerUpdate(f"021:fill:{fill.fill_id}", fill.broker_order_id, BrokerUpdateType.FILL, OrderStatus.PARTIALLY_FILLED, fill, fill.timestamp))
        self.updates = updates
        return list(updates)

    def disconnect(self):
        self.connected = False

    def reconnect(self):
        self._auth()
        self.connected = True

    def ephemeral_key(self) -> str:
        self._require_enabled()
        data = parse_envelope(self._request("GET", "/websocket/ephemeral-key").json())
        if not isinstance(data, dict) or not data.get("token"):
            raise Provider021ProtocolError("021 ephemeral-key response omitted token")
        return str(data["token"])

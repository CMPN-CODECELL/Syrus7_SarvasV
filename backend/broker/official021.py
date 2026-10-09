"""Official 021 wire normalization.

This module contains no network client and is safe to exercise with fixtures.  Live
writes remain disabled until a caller supplies an explicitly enabled transport and
the unresolved trade/order identity evidence is confirmed.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import struct
from typing import Any

from backend.shared.contracts import OrderStatus, Side


class Provider021Error(RuntimeError):
    pass


class Provider021ProtocolError(Provider021Error):
    pass


class Provider021WriteUncertain(Provider021Error):
    """A write may have reached 021 and must be reconciled, never retried blindly."""


class Provider021Blocked(Provider021Error):
    pass


class ObservationKind(StrEnum):
    LTP = "LTP"
    FULL = "FULL"
    HEARTBEAT = "HEARTBEAT"


EXCHANGE_TO_CODE = {
    "NSECM": 1,
    "NSEFO": 2,
    "NSEIDX": 3,
    "BSEEQ": 4,
    "BSEEQD": 5,
    "BSEIDX": 6,
}
CODE_TO_EXCHANGE = {value: key for key, value in EXCHANGE_TO_CODE.items()}
REQUEST_EXCHANGE = {
    "NSECM": "NSE",
    "NSEFO": "NSEFO",
    "BSEEQ": "BSE",
    "BSEEQD": "BSEFO",
}


@dataclass(frozen=True)
class Instrument021:
    exchange: int
    token: int
    symbol: str
    product: str = "INTRADAY"
    lot_size: int = 1
    freeze_quantity: int | None = None
    tick_size_paise: int = 1

    def __post_init__(self):
        if self.exchange not in {1, 2, 3, 4, 5, 6}:
            raise ValueError("unsupported 021 exchange")
        if self.token <= 0 or not self.symbol.strip():
            raise ValueError("positive token and symbol required")
        if self.product not in {"INTRADAY", "CNC", "NRML"}:
            raise ValueError("unsupported 021 product")
        if self.product == "CNC" and self.exchange not in {1, 4}:
            raise ValueError("CNC is cash-only")
        if self.product == "NRML" and self.exchange not in {2, 5}:
            raise ValueError("NRML is derivatives-only")
        if self.lot_size <= 0 or self.tick_size_paise <= 0:
            raise ValueError("positive lot and tick sizes required")
        if self.freeze_quantity is not None and self.freeze_quantity <= 0:
            raise ValueError("freeze quantity must be positive")

    def validate_quantity(self, quantity: int) -> None:
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if quantity % self.lot_size:
            raise ValueError("quantity is not a whole number of lots")
        if self.freeze_quantity is not None and quantity > self.freeze_quantity:
            raise ValueError("quantity exceeds instrument freeze quantity")


@dataclass(frozen=True)
class MarketObservation021:
    exchange: int
    token: int
    kind: ObservationKind
    ltp: Decimal | None = None
    official_open: Decimal | None = None
    last_trade_quantity: int | None = None
    cumulative_volume: int | None = None
    exchange_timestamp: int | None = None


@dataclass(frozen=True)
class OrderEvent021:
    exchange: int
    order_id: str
    status_code: int
    signed_quantity: int
    price: Decimal
    ucc: str
    symbol: str | None = None
    token: int | None = None
    error: str | None = None

    @property
    def is_trade_without_identity(self) -> bool:
        return self.status_code == 1


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


def rupees_to_paise(value: Decimal) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("price must be a positive finite Decimal")
    paise = value * 100
    if paise != paise.to_integral_value():
        raise ValueError("021 prices cannot represent fractions of one paise")
    return int(paise)


def paise_to_rupees(value: int) -> Decimal:
    if type(value) is not int or value <= 0:
        raise ValueError("paise price must be a positive integer")
    return Decimal(value) / Decimal(100)


def encode_order_payload(
    *,
    instrument: Instrument021,
    side: Side,
    quantity: int,
    order_type: str,
    limit_price: Decimal | None,
) -> dict[str, Any]:
    instrument.validate_quantity(quantity)
    if not isinstance(side, Side):
        raise ValueError("canonical side required")
    if order_type not in {"MARKET", "LIMIT"}:
        raise ValueError("unsupported order type")
    if order_type == "LIMIT" and limit_price is None:
        raise ValueError("limit price required")
    price = 0 if order_type == "MARKET" else rupees_to_paise(limit_price)
    if price and price % instrument.tick_size_paise:
        raise ValueError("limit price is not aligned to instrument tick size")
    return {
        "exchange": instrument.exchange,
        "token": instrument.token,
        "product": instrument.product,
        "quantity": quantity * side.sign,
        "orderType": order_type,
        "price": price,
    }


def parse_envelope(payload: Any) -> Any:
    if not isinstance(payload, dict) or set(payload) < {"data", "success", "error"}:
        raise Provider021ProtocolError("invalid 021 response envelope")
    if payload["success"] is not True:
        raise Provider021Error(str(payload.get("error") or "021 request failed"))
    return payload["data"]


def parse_plain_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or any(not isinstance(v, dict) for v in payload):
        raise Provider021ProtocolError("021 list endpoint did not return an array")
    return payload


def classify_http_error(status: int, *, write: bool) -> type[Provider021Error]:
    if write and status in {500, 503}:
        return Provider021WriteUncertain
    if status in {401, 403, 421, 422}:
        return Provider021Blocked
    return Provider021Error


def _u16(frame: bytes, offset: int) -> int:
    return struct.unpack_from(">H", frame, offset)[0]


def _u32(frame: bytes, offset: int) -> int:
    return struct.unpack_from(">I", frame, offset)[0]


def _i32(frame: bytes, offset: int) -> int:
    return struct.unpack_from(">i", frame, offset)[0]


def parse_market_frame(frame: bytes) -> MarketObservation021:
    if len(frame) < 2:
        raise Provider021ProtocolError("truncated 021 market frame")
    tc = _u16(frame, 0)
    if tc == 10:
        if len(frame) != 2:
            raise Provider021ProtocolError("invalid heartbeat length")
        return MarketObservation021(0, 0, ObservationKind.HEARTBEAT)
    if tc == 1:
        if len(frame) not in {12, 17}:
            raise Provider021ProtocolError("invalid TC1 length")
        exchange, token, price = _u16(frame, 2), _u32(frame, 4), _u32(frame, 8)
        opening = None
        if len(frame) == 17:
            if frame[12:13] != b"o":
                raise Provider021ProtocolError("unsupported TC1 snapshot suffix")
            opening = paise_to_rupees(_u32(frame, 13))
        return MarketObservation021(
            exchange, token, ObservationKind.LTP, paise_to_rupees(price), opening
        )
    if tc != 3:
        raise Provider021ProtocolError(f"unsupported market transaction code {tc}")
    exchange = _u16(frame, 2)
    expected = {1: 220, 2: 234, 3: 36, 4: 262, 5: 262, 6: 262}.get(exchange)
    if expected is None or len(frame) != expected:
        raise Provider021ProtocolError("invalid TC3 exchange or frame length")
    if exchange == 2:
        (
            token_offset,
            ltp_offset,
            qty_offset,
            volume_offset,
            open_offset,
            time_offset,
        ) = 6, 10, 14, 22, 50, 230
    elif exchange == 3:
        (
            token_offset,
            ltp_offset,
            qty_offset,
            volume_offset,
            open_offset,
            time_offset,
        ) = 4, 8, None, None, 16, 28
    elif exchange in {4, 5, 6}:
        (
            token_offset,
            ltp_offset,
            qty_offset,
            volume_offset,
            open_offset,
            time_offset,
        ) = 4, 8, None, 24, 52, 244
    else:
        (
            token_offset,
            ltp_offset,
            qty_offset,
            volume_offset,
            open_offset,
            time_offset,
        ) = 4, 8, 12, 20, 48, 216
    return MarketObservation021(
        exchange,
        _u32(frame, token_offset),
        ObservationKind.FULL,
        paise_to_rupees(_u32(frame, ltp_offset)),
        paise_to_rupees(_u32(frame, open_offset)),
        _u32(frame, qty_offset) if qty_offset is not None else None,
        _u32(frame, volume_offset) if volume_offset is not None else None,
        _u32(frame, time_offset) + 315513000,
    )


def parse_market_frames(frame: bytes) -> list[MarketObservation021]:
    """Decode a WebSocket frame containing one or more documented packets."""
    observations = []
    offset = 0
    while offset < len(frame):
        if len(frame) - offset < 2:
            raise Provider021ProtocolError("truncated 021 packet sequence")
        tc = _u16(frame, offset)
        if tc == 1:
            if len(frame) - offset < 12:
                raise Provider021ProtocolError("truncated TC1 packet")
            # A snapshot LTPO packet has the documented 5-byte open suffix.
            length = 17 if len(frame) - offset >= 17 and frame[offset + 12 : offset + 13] == b"o" else 12
        elif tc == 3:
            if len(frame) - offset < 4:
                raise Provider021ProtocolError("truncated TC3 packet")
            length = {1: 220, 2: 234, 3: 36, 4: 262, 5: 262, 6: 262}.get(
                _u16(frame, offset + 2)
            )
            if length is None:
                raise Provider021ProtocolError("unsupported TC3 exchange")
        elif tc == 10:
            length = 2
        else:
            raise Provider021ProtocolError(f"unsupported market transaction code {tc}")
        packet = frame[offset : offset + length]
        if len(packet) != length:
            raise Provider021ProtocolError("truncated 021 packet")
        observations.append(parse_market_frame(packet))
        offset += length
    return observations


def parse_order_frame(frame: bytes) -> OrderEvent021:
    if len(frame) < 4:
        raise Provider021ProtocolError("truncated 021 order frame")
    tc, status = _u16(frame, 0), _u16(frame, 2)
    if status not in range(1, 10):
        raise Provider021ProtocolError("unknown 021 order status")
    if tc == 4:
        if len(frame) < 46:
            raise Provider021ProtocolError("truncated NSE TC4 frame")
        ucc = frame[4:14].rstrip(b"\x00 ").decode("ascii")
        symbol = frame[14:34].rstrip(b"\x00 ").decode("ascii") or None
        event = OrderEvent021(
            1,
            str(_u32(frame, 34)),
            status,
            _i32(frame, 38),
            paise_to_rupees(_u32(frame, 42)),
            ucc,
            symbol=symbol,
        )
        suffix = frame[46:]
    elif tc == 8:
        if len(frame) < 32:
            raise Provider021ProtocolError("truncated BSE TC8 frame")
        ucc = frame[4:14].rstrip(b"\x00 ").decode("ascii")
        exchange = _u16(frame, 14)
        event = OrderEvent021(
            exchange,
            str(_u32(frame, 20)),
            status,
            _i32(frame, 24),
            paise_to_rupees(_u32(frame, 28)),
            ucc,
            token=_u32(frame, 16),
        )
        suffix = frame[32:]
    else:
        raise Provider021ProtocolError(f"unsupported order transaction code {tc}")
    if suffix:
        try:
            error = suffix.rstrip(b"\x00").decode("ascii") or None
        except UnicodeDecodeError as exc:
            raise Provider021ProtocolError("invalid order error suffix") from exc
        event = OrderEvent021(**{**event.__dict__, "error": error})
    return event

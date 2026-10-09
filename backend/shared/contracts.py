"""Canonical domain contracts. Money is Decimal; timestamps are UTC epoch seconds."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from math import isfinite


class GlobalTradingState(StrEnum):
    RECOVERING = "RECOVERING"
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    REDUCE_ONLY = "REDUCE_ONLY"
    KILLING = "KILLING"
    KILLED = "KILLED"
    UNCERTAIN = "UNCERTAIN"


class StrategyState(StrEnum):
    RUNNING = "RUNNING"
    HALTED = "HALTED"
    LOSS_HALTED = "LOSS_HALTED"


class ReconciliationState(StrEnum):
    RECOVERING = "RECOVERING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DRIFTED = "DRIFTED"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self):
        return 1 if self == Side.BUY else -1


class OrderStatus(StrEnum):
    RESERVED = "RESERVED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}


@dataclass(frozen=True)
class Tick:
    symbol: str
    event_timestamp: int
    price: Decimal
    quantity: int
    event_id: str
    raw_event_timestamp: str | None = None
    volume_available: bool = True
    data_source: str = "UNSPECIFIED"
    received_at: float | None = None
    event_time_status: str = "VERIFIED"

    def __post_init__(self):
        if (
            not isinstance(self.price, Decimal)
            or not self.price.is_finite()
            or self.price <= 0
            or type(self.quantity) is not int
            or self.quantity < 0
        ):
            raise ValueError("invalid tick economics")
        if (
            type(self.event_timestamp) is not int
            or not self.symbol
            or not self.event_id
            or (
                self.raw_event_timestamp is not None
                and not isinstance(self.raw_event_timestamp, str)
            )
            or type(self.volume_available) is not bool
            or not self.data_source
            or (
                self.received_at is not None
                and (
                    not isinstance(self.received_at, (int, float))
                    or not isfinite(self.received_at)
                )
            )
            or self.event_time_status
            not in {
                "VERIFIED",
                "MISSING_FALLBACK",
                "FUTURE_FALLBACK",
                "PAST_FALLBACK",
                "REORDER_FALLBACK",
            }
        ):
            raise ValueError("invalid tick identity/timestamp")


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: int
    start_time: int
    end_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_closed: bool = True
    volume_available: bool = True
    data_source: str = "UNSPECIFIED"


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    strategy_instance_id: str
    account_id: str
    symbol: str
    side: Side
    quantity: int
    created_at: float
    order_type: str = "MARKET"
    limit_price: Decimal | None = None
    reason: str = ""

    def __post_init__(self):
        if (
            type(self.quantity) is not int
            or self.quantity <= 0
            or not all(
                isinstance(v, str) and v.strip()
                for v in (
                    self.symbol,
                    self.intent_id,
                    self.strategy_instance_id,
                    self.account_id,
                )
            )
            or not isfinite(self.created_at)
        ):
            raise ValueError("positive quantity, symbol and intent ID required")
        if self.order_type not in {"MARKET", "LIMIT"}:
            raise ValueError("order_type must be MARKET or LIMIT")
        if self.order_type == "LIMIT":
            if (
                self.limit_price is None
                or not isinstance(self.limit_price, Decimal)
                or self.limit_price <= 0
            ):
                raise ValueError("LIMIT order requires positive limit_price Decimal")
        elif self.limit_price is not None:
            raise ValueError("MARKET order must not specify limit_price")
        if not isinstance(self.side, Side):
            raise ValueError("side must be canonical Side")


@dataclass(frozen=True)
class RiskDecision:
    intent_id: str
    allowed: bool
    reason_code: str
    projected_position: int | None = None
    reason_text: str = ""
    rule_results: tuple[str, ...] = ()
    created_at: float = 0
    reservation_id: str | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalOrder:
    order_id: str
    intent: OrderIntent
    status: OrderStatus
    filled_quantity: int = 0

    def __post_init__(self):
        if type(self.filled_quantity) is not int or self.filled_quantity < 0:
            raise ValueError("filled_quantity must be a non-negative integer")
        if self.filled_quantity > self.intent.quantity:
            raise ValueError("filled_quantity cannot exceed requested quantity")
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must be a non-empty string")

    @property
    def remaining_quantity(self):
        return self.intent.quantity - self.filled_quantity


@dataclass(frozen=True)
class Fill:
    fill_id: str
    broker_order_id: str
    strategy_instance_id: str
    account_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: float
    charges: Decimal = Decimal("0")

    def __post_init__(self):
        if (
            type(self.quantity) is not int
            or self.quantity <= 0
            or not isinstance(self.side, Side)
        ):
            raise ValueError("invalid fill quantity/side")
        if (
            not isinstance(self.price, Decimal)
            or not self.price.is_finite()
            or self.price <= 0
            or not isinstance(self.charges, Decimal)
            or not self.charges.is_finite()
            or self.charges < 0
        ):
            raise ValueError("invalid fill economics")
        if not isfinite(self.timestamp) or not all(
            (
                self.fill_id,
                self.broker_order_id,
                self.strategy_instance_id,
                self.account_id,
                self.symbol,
            )
        ):
            raise ValueError("invalid fill attribution/timestamp")


@dataclass(frozen=True)
class StrategyPosition:
    strategy_instance_id: str
    symbol: str
    net_quantity: int
    average_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    gross_pnl: Decimal
    charges: Decimal
    net_pnl: Decimal

    def __post_init__(self):
        if type(self.net_quantity) is not int:
            raise ValueError("net_quantity must be an integer")
        for name, value in (
            ("average_price", self.average_price),
            ("realized_pnl", self.realized_pnl),
            ("unrealized_pnl", self.unrealized_pnl),
            ("gross_pnl", self.gross_pnl),
            ("charges", self.charges),
            ("net_pnl", self.net_pnl),
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.charges < 0:
            raise ValueError("charges cannot be negative")
        if self.average_price < 0:
            raise ValueError("average_price cannot be negative")
        if (
            not isinstance(self.strategy_instance_id, str)
            or not self.strategy_instance_id
        ):
            raise ValueError("strategy_instance_id must be non-empty")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be non-empty")


@dataclass(frozen=True)
class RiskPolicy:
    max_daily_loss: Decimal = Decimal("1000")
    max_position: int = 100
    max_orders_per_minute: int = 10
    max_price_deviation_bps: int = 500

    def __post_init__(self):
        if (
            not isinstance(self.max_daily_loss, Decimal)
            or not self.max_daily_loss.is_finite()
            or self.max_daily_loss <= 0
        ):
            raise ValueError("max_daily_loss must be a finite positive Decimal")
        if type(self.max_position) is not int or self.max_position <= 0:
            raise ValueError("max_position must be a positive integer")
        if (
            type(self.max_orders_per_minute) is not int
            or self.max_orders_per_minute <= 0
        ):
            raise ValueError("max_orders_per_minute must be a positive integer")
        if (
            type(self.max_price_deviation_bps) is not int
            or self.max_price_deviation_bps <= 0
        ):
            raise ValueError("max_price_deviation_bps must be a positive integer")


@dataclass(frozen=True)
class AccountRiskPolicy:
    max_net_position_per_symbol: int | None = None
    max_gross_virtual_position_per_symbol: int | None = None

    def __post_init__(self):
        for name, value in (
            ("max_net_position_per_symbol", self.max_net_position_per_symbol),
            (
                "max_gross_virtual_position_per_symbol",
                self.max_gross_virtual_position_per_symbol,
            ),
        ):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer or null")


@dataclass(frozen=True)
class BrokerSnapshot:
    orders: tuple[CanonicalOrder, ...]
    fills: tuple[Fill, ...]
    positions: dict[tuple[str, str], int]
    is_complete: bool = False
    observed_at: float | None = None


@dataclass(frozen=True)
class KillCertificate:
    status: str
    elapsed_seconds: float
    open_orders: int
    broker_positions: dict[str, int]
    virtual_positions_flat: bool
    reason: str
    target_seconds: float = 10.0
    started_at: float | None = None
    completed_at: float | None = None
    stage_durations_ms: dict = field(default_factory=dict)
    final_evidence: dict = field(default_factory=dict)


class BrokerUpdateType(StrEnum):
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_STATUS = "ORDER_STATUS"
    FILL = "FILL"


@dataclass(frozen=True)
class BrokerUpdate:
    update_id: str
    order_id: str
    update_type: BrokerUpdateType
    status: OrderStatus | None = None
    fill: Fill | None = None
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.update_id or not isinstance(self.update_id, str):
            raise ValueError("invalid update_id")
        if not self.order_id or not isinstance(self.order_id, str):
            raise ValueError("invalid order_id")
        if not isinstance(self.update_type, BrokerUpdateType):
            raise ValueError("invalid update_type")
        if self.update_type == BrokerUpdateType.FILL and self.fill is None:
            raise ValueError("fill required for FILL update")
        if self.fill is not None and self.fill.broker_order_id != self.order_id:
            raise ValueError("fill broker_order_id must match update order_id")

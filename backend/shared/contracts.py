"""Canonical domain contracts. Money is Decimal; timestamps are UTC epoch seconds."""

from dataclasses import dataclass
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
        if self.order_type != "MARKET" or self.limit_price is not None:
            raise ValueError("bootstrap supports MARKET orders only")
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


@dataclass(frozen=True)
class CanonicalOrder:
    order_id: str
    intent: OrderIntent
    status: OrderStatus
    filled_quantity: int = 0

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
    charges: Decimal
    net_pnl: Decimal


@dataclass(frozen=True)
class RiskPolicy:
    max_daily_loss: Decimal = Decimal("1000")
    max_position: int = 100
    max_orders_per_minute: int = 10

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

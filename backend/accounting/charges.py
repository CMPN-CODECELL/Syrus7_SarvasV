"""Indian regulatory and statutory charges calculator for equity trading (cash / intraday).

Follows standard Indian equity market rate schedules:
- Brokerage: flat or percentage (e.g. 0.03% or flat Rs 20, defaults to 0.03% capped at Rs 20)
- STT (Securities Transaction Tax):
    - Intraday equity: 0.025% on SELL only
    - Delivery equity: 0.1% on BUY and SELL
- Exchange Turnover Charges: NSE 0.00297%, BSE 0.00375% (default NSE)
- SEBI Turnover Charges: Rs 10 per crore (0.0001%)
- Stamp Duty: 0.015% on BUY (intraday: 0.003% on BUY)
- GST: 18% on (Brokerage + Exchange Turnover Charges + SEBI Charges)
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from backend.shared.contracts import Side


@dataclass(frozen=True)
class ChargeBreakdown:
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    sebi_charges: Decimal
    stamp_duty: Decimal
    gst: Decimal
    total_charges: Decimal
    turnover: Decimal = Decimal("0.00")

    @property
    def exchange_fee(self) -> Decimal:
        return self.exchange_charges

    @property
    def sebi_fee(self) -> Decimal:
        return self.sebi_charges

    @property
    def total(self) -> Decimal:
        return self.total_charges

    def to_dict(self) -> dict:
        return {
            "turnover": str(self.turnover),
            "brokerage": str(self.brokerage),
            "stt": str(self.stt),
            "exchange_charges": str(self.exchange_charges),
            "sebi_charges": str(self.sebi_charges),
            "stamp_duty": str(self.stamp_duty),
            "gst": str(self.gst),
            "total_charges": str(self.total_charges),
        }


def round_cur(val: Decimal) -> Decimal:
    """Round to 2 decimal places using standard financial round half up."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_indian_charges(
    quantity: int,
    price: Decimal,
    side: Side,
    *,
    is_intraday: bool = True,
    is_delivery: bool | None = None,
    brokerage_rate: Decimal = Decimal("0.0003"),  # 0.03%
    max_brokerage_per_order: Decimal = Decimal("20.00"),
) -> ChargeBreakdown:
    """Calculate exact statutory and regulatory charges for a trade in INR."""
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be positive")

    if is_delivery is not None:
        is_intraday = not is_delivery

    side = Side(side)
    turnover = round_cur(Decimal(quantity) * price)

    # 1. Brokerage: min(turnover * rate, max_per_order)
    raw_brokerage = turnover * brokerage_rate
    brokerage = min(raw_brokerage, max_brokerage_per_order)
    brokerage = round_cur(brokerage)

    # 2. STT (Securities Transaction Tax)
    if is_intraday:
        # Intraday: 0.025% on SELL only
        stt = turnover * Decimal("0.00025") if side == Side.SELL else Decimal("0")
    else:
        # Delivery: 0.1% on both BUY and SELL
        stt = turnover * Decimal("0.001")
    stt = round_cur(stt)

    # 3. Exchange Turnover Charges (NSE: ~0.00345%)
    exchange_charges = round_cur(turnover * Decimal("0.0000345"))

    # 4. SEBI Turnover Charges (Rs 10 per crore = 0.0001%)
    sebi_charges = round_cur(turnover * Decimal("0.000001"))

    # 5. Stamp Duty (0.003% on BUY for intraday, 0.015% for delivery)
    if side == Side.BUY:
        stamp_rate = Decimal("0.00003") if is_intraday else Decimal("0.00015")
        stamp_duty = round_cur(turnover * stamp_rate)
    else:
        stamp_duty = Decimal("0")

    # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
    gst_base = brokerage + exchange_charges + sebi_charges
    gst = round_cur(gst_base * Decimal("0.18"))

    # Total
    total = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst

    return ChargeBreakdown(
        turnover=turnover,
        brokerage=brokerage,
        stt=stt,
        exchange_charges=exchange_charges,
        sebi_charges=sebi_charges,
        stamp_duty=stamp_duty,
        gst=gst,
        total_charges=round_cur(total),
    )

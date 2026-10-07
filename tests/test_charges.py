from decimal import Decimal
import pytest

from backend.accounting.charges import calculate_indian_charges
from backend.shared.contracts import Side


def test_calculate_indian_charges_buy_intraday():
    # 10 shares @ 1000 = 10,000 turnover
    charges = calculate_indian_charges(
        side=Side.BUY,
        price=Decimal("1000"),
        quantity=10,
        is_delivery=False,
    )
    assert charges.turnover == Decimal("10000.00")
    # For intraday equity BUY:
    # STT = 0
    assert charges.stt == Decimal("0.00")
    # Stamp duty = 0.003% of 10000 = 0.30
    assert charges.stamp_duty == Decimal("0.30")
    # Exchange fee = 0.00345% of 10000 = 0.35
    assert charges.exchange_fee == Decimal("0.35")
    # Brokerage = min(20, 10000 * 0.0003) = 3.00
    assert charges.brokerage == Decimal("3.00")
    # SEBI turnover fee = 10000 * 0.000001 = 0.01
    assert charges.sebi_fee == Decimal("0.01")
    # GST = 18% of (3.00 + 0.35 + 0.01) = 18% of 3.36 = 0.60
    assert charges.gst == Decimal("0.60")
    # Total = 0 + 0.30 + 0.35 + 3.00 + 0.01 + 0.60 = 4.26
    assert charges.total == Decimal("4.26")
    assert charges.total == (
        charges.stt
        + charges.stamp_duty
        + charges.exchange_fee
        + charges.brokerage
        + charges.sebi_fee
        + charges.gst
    )


def test_calculate_indian_charges_sell_intraday():
    # 10 shares @ 1000 = 10,000 turnover
    charges = calculate_indian_charges(
        side=Side.SELL,
        price=Decimal("1000"),
        quantity=10,
        is_delivery=False,
    )
    assert charges.turnover == Decimal("10000.00")
    # For intraday equity SELL:
    # STT = 0.025% of 10000 = 2.50
    assert charges.stt == Decimal("2.50")
    # Stamp duty on SELL = 0
    assert charges.stamp_duty == Decimal("0.00")
    # Exchange fee = 0.35
    assert charges.exchange_fee == Decimal("0.35")
    # Brokerage = 3.00
    assert charges.brokerage == Decimal("3.00")
    assert charges.total > Decimal("0")


def test_brokerage_cap_at_twenty():
    # Large trade: 1000 shares @ 3000 = 3,000,000 turnover
    # 0.03% of 3,000,000 = 900, but cap is 20
    charges = calculate_indian_charges(
        side=Side.BUY,
        price=Decimal("3000"),
        quantity=1000,
    )
    assert charges.brokerage == Decimal("20.00")


def test_invalid_price_or_quantity():
    with pytest.raises(ValueError):
        calculate_indian_charges(
            side=Side.BUY,
            price=Decimal("0"),
            quantity=10,
        )
    with pytest.raises(ValueError):
        calculate_indian_charges(
            side=Side.BUY,
            price=Decimal("100"),
            quantity=0,
        )

from decimal import Decimal

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, RiskPolicy, Side, Tick


def test_limit_order_uses_decimal_mark_guard_but_market_order_does_not_invent_price():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    platform.risk.policies["s"] = RiskPolicy(max_price_deviation_bps=100)
    rejected = platform.risk.submit(
        OrderIntent(
            "limit",
            "s",
            "a",
            "X",
            Side.BUY,
            1,
            platform.clock(),
            order_type="LIMIT",
            limit_price=Decimal("102"),
        )
    )
    assert rejected.reason_code == "RISK_PRICE_REASONABILITY"
    assert rejected.details["deviation_bps"] == "200.00"
    assert platform.risk.submit(
        OrderIntent("market", "s", "a", "X", Side.BUY, 1, platform.clock())
    ).allowed
    platform.close()

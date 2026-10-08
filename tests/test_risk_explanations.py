from decimal import Decimal

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, RiskPolicy, Side, Tick


def test_numeric_rejection_has_structured_rule_evidence():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    platform.risk.policies["s"] = RiskPolicy(max_position=2)
    decision = platform.risk.submit(
        OrderIntent("too-large", "s", "a", "X", Side.BUY, 3, platform.clock())
    )
    assert decision.reason_code == "RISK_MAX_POSITION"
    assert decision.reason_text.startswith("REJECTED — POSITION LIMIT")
    assert decision.rule_results[-1] == "MAX_POSITION:FAIL"
    assert decision.details["requested_quantity"] == 3
    assert decision.details["projected"] == 3
    assert decision.details["limit"] == 2
    assert platform.snapshot()["risk_decisions"][-1]["details"]["limit"] == 2
    platform.close()

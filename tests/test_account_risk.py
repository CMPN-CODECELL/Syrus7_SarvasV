from decimal import Decimal

from backend.platform import Platform
from backend.shared.contracts import (
    AccountRiskPolicy,
    OrderIntent,
    RiskPolicy,
    Side,
    Tick,
)


def _platform():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    for strategy in ("A", "B", "C"):
        platform.strategies.subscribe("a", strategy, "momentum", "X")
        platform.risk.policies[strategy] = RiskPolicy(max_position=200)
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    return platform


def _intent(platform, key, strategy, quantity, side=Side.BUY):
    return OrderIntent(key, strategy, "a", "X", side, quantity, platform.clock())


def test_account_gross_counts_opposing_and_cross_strategy_pending_exposure():
    platform = _platform()
    platform.risk.account_policies.set("a", AccountRiskPolicy(300, 150))
    assert platform.risk.submit(_intent(platform, "a-buy", "A", 100)).allowed
    decision = platform.risk.submit(_intent(platform, "b-sell", "B", 100, Side.SELL))
    assert decision.reason_code == "RISK_ACCOUNT_GROSS_POSITION"
    assert decision.details["gross_projected"] == 200
    platform.close()


def test_racing_account_reservations_are_atomic():
    from concurrent.futures import ThreadPoolExecutor

    platform = _platform()
    platform.risk.account_policies.set("a", AccountRiskPolicy(100, 500))
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(
            pool.map(
                lambda args: platform.risk.submit(_intent(platform, *args)),
                [("one", "A", 60), ("two", "B", 60)],
            )
        )
    assert sum(decision.allowed for decision in decisions) == 1
    platform.close()

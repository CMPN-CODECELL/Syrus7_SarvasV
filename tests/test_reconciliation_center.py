from decimal import Decimal

from backend.platform import Platform
from backend.shared.contracts import Tick


def test_reconciliation_center_exposes_position_delta_without_synthetic_fill():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.broker.external_positions[("a", "X")] = 7
    assert platform.reliability.reconcile() is False
    center = platform.reliability.reconciliation_center()
    assert center["report"]["position_diff"] == [
        {"account_id": "a", "symbol": "X", "local": 0, "broker": 7, "delta": 7}
    ]
    assert platform.store.rows("SELECT COUNT(*) AS n FROM fills")[0]["n"] == 0
    platform.close()

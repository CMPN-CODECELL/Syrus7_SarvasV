import pytest

from backend.platform import Platform
from backend.reliability.failure_lab import FailureLab


@pytest.mark.parametrize(
    "scenario",
    [
        "concurrent_position_race",
        "account_risk",
        "opposing_gross_exposure",
        "limit_lowered_below_position",
        "daily_loss_mark_breach",
        "late_fill_after_cancel",
        "kill_late_fill",
        "restart_fail_closed",
        "stale_broker_evidence",
        "invalid_price",
    ],
)
def test_v2_scenarios_have_real_explicit_pass_criteria(scenario):
    platform = Platform()
    result = FailureLab(platform).run(scenario)
    assert result["status"] == "PASS"
    assert result["duration_ms"] >= 0
    assert result["expected"]
    assert result["invariants"]["invariants"]
    platform.close()

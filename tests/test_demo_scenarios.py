"""Tests for deterministic demo scenarios and rehearsal runner (Task 7).

Verifies all seven required scenario capabilities:
1. Exact 1m/5m candles and strategy entries (including opposing positions).
2. Separate strategy positions/P&L (long and short on one symbol).
3. Partial fill, rejection and duplicate fill via mock facilities.
4. Risk-limit rejection with backend reason.
5. Missed attributed fill recovered through reconciliation.
6. Platform restart remains RECOVERING until reconcile/explicit resume.
7. Kill with pending orders/exposure: zero open orders, zero broker & virtual positions.
"""

from decimal import Decimal
import pytest

from backend.demo_scenarios import RehearsalRunner, generate_deterministic_ticks
from backend.shared.contracts import (
    GlobalTradingState as Gate,
    OrderStatus,
    ReconciliationState as Health,
)


@pytest.fixture
def runner():
    r = RehearsalRunner()
    yield r
    r.close()


def test_deterministic_tick_sequence():
    ticks = generate_deterministic_ticks("TCS", 1_700_000_100)
    assert len(ticks) >= 36
    # Ascending timestamps
    for i in range(1, len(ticks)):
        assert ticks[i].event_timestamp >= ticks[i - 1].event_timestamp
        assert ticks[i].price > Decimal(0)
        assert ticks[i].symbol == "TCS"


def test_exact_1m_5m_candles_and_opposing_strategy_entries(runner):
    """Scenario 1 & 2: 1m/5m candles, warmup, simultaneous opposing positions, separate P&L."""
    res = runner.run_candles_and_opposing_strategies()
    assert res.passed is True
    p = runner.platform
    acc = runner.account_id

    # 1. Check candles
    candles = list(p.closed_candles)
    assert len(candles) >= 10
    one_m = [c for c in candles if c.interval == 60]
    five_m = [c for c in candles if c.interval == 300]
    assert len(one_m) >= 9
    assert len(five_m) >= 2

    # 2. Check opposing strategy positions on TCS for the same account
    positions = p.ledger.positions()
    mom_pos = positions[(acc, "strat_mom", "TCS")]
    mr_pos = positions[(acc, "strat_mr", "TCS")]
    bo_pos = positions[(acc, "strat_bo", "TCS")]

    assert mom_pos.net_quantity > 0, "Momentum must be LONG"
    assert mr_pos.net_quantity < 0, "Mean Reversion must be SHORT"
    assert bo_pos.net_quantity > 0, "Breakout must be LONG"

    # Separate virtual positions & P&L
    assert mom_pos.net_quantity != mr_pos.net_quantity
    assert mom_pos.realized_pnl is not None
    assert mr_pos.realized_pnl is not None
    assert bo_pos.realized_pnl is not None

    # Broker net position matches sum of strategy positions
    broker_positions = p.broker.snapshot().positions
    expected_net = mom_pos.net_quantity + mr_pos.net_quantity + bo_pos.net_quantity
    assert broker_positions.get((acc, "TCS"), 0) == expected_net

    # User-scoped state reflects isolated subscriptions and positions
    snap = p.snapshot(account_id=acc)
    assert len(snap["subscriptions"]) == 3
    assert len(snap["positions"]) == 3
    assert sorted([pos["strategy_instance_id"] for pos in snap["positions"]]) == [
        "strat_bo",
        "strat_mom",
        "strat_mr",
    ]


def test_partial_fill_rejection_and_duplicate_fill(runner):
    """Scenario 3: Partial fill, duplicate fill ignored, order rejection."""
    # First establish positions
    runner.run_candles_and_opposing_strategies()
    res = runner.run_partial_rejection_duplicate()
    assert res.passed is True
    assert res.details["partial_order_status"] == OrderStatus.PARTIALLY_FILLED.value
    assert res.details["partial_filled_quantity"] == 10
    assert res.details["duplicate_fill_ignored"] is True
    assert res.details["rejected_order_status"] == OrderStatus.REJECTED.value

    # Verify duplicate fill audit in store
    dups = runner.platform.store.rows(
        "SELECT * FROM audit WHERE type='DUPLICATE_FILL_IGNORED'"
    )
    assert len(dups) >= 1


def test_risk_limit_rejection_with_backend_reason(runner):
    """Scenario 4: Risk limit rejection with specific backend reason code."""
    runner.run_candles_and_opposing_strategies()
    res = runner.run_risk_limit_rejection()
    assert res.passed is True
    assert res.details["allowed"] is False
    assert res.details["reason_code"] == "RISK_MAX_POSITION"

    # Verify audit event
    audits = runner.platform.store.rows(
        "SELECT payload FROM audit WHERE type='RISK_DECISION' AND payload LIKE '%RISK_MAX_POSITION%'"
    )
    assert len(audits) >= 1


def test_missed_fill_recovery_through_reconciliation(runner):
    """Scenario 5: Missed broker fill recovered through reconciliation."""
    runner.run_candles_and_opposing_strategies()
    res = runner.run_missed_fill_recovery()
    assert res.passed is True
    assert res.details["status_before"] == OrderStatus.OPEN.value
    assert res.details["filled_before"] == 0
    assert res.details["status_after"] == OrderStatus.FILLED.value
    assert res.details["filled_after"] == 5
    assert res.details["ledger_quantity_recovered"] == 5


def test_restart_recovery_invariants(runner):
    """Scenario 6: Process restart begins in RECOVERING; resume requires reconciliation."""
    runner.run_candles_and_opposing_strategies()
    res = runner.run_restart_recovery()
    assert res.passed is True
    assert res.details["initial_health"] == "RECOVERING"
    assert res.details["initial_gate"] == "RECOVERING"
    assert res.details["retained_fills"] > 0
    assert len(res.details["retained_positions"]) > 0
    assert res.details["reconciliation_verified"] is True
    assert res.details["resumed_gate"] == Gate.RUNNING.value
    assert res.details["resumed_health"] == Health.HEALTHY.value


def test_kill_switch_with_exposure(runner):
    """Scenario 7: Kill switch flattens all exposure and cancels open orders."""
    runner.run_candles_and_opposing_strategies()
    res = runner.run_kill_switch_with_exposure()
    assert res.passed is True
    assert res.details["certificate_status"] == "SUCCESS"
    assert res.details["open_orders"] == 0
    assert res.details["virtual_positions_flat"] is True
    assert res.details["virtual_positions_remaining"] == {}
    assert res.details["broker_positions_remaining"] == {}
    assert res.details["elapsed_seconds"] < 10.0


def test_unexplained_drift_remains_blocked(runner):
    """Scenario 8: Unexplained external drift fails closed and refuses auto-fix."""
    runner.run_candles_and_opposing_strategies()
    runner.run_kill_switch_with_exposure()
    res = runner.run_unexplained_drift_blocked()
    assert res.passed is True
    assert res.details["reconciliation_verified"] is False
    assert res.details["failure_reason"] in {
        "UNEXPLAINED_EXTERNAL_POSITION",
        "VIRTUAL_POSITION_DRIFT",
    }
    assert res.details["gate_state"] == Gate.UNCERTAIN.value
    assert res.details["health_state"] == Health.DRIFTED.value
    assert res.details["resume_blocked"] is True


def test_comprehensive_rehearsal_suite(runner):
    """Run full sequential rehearsal suite and verify all scenarios pass."""
    results = runner.run_all()
    assert len(results) == 7
    for r in results:
        assert r.passed is True, f"Scenario {r.scenario} failed: {r.summary}"

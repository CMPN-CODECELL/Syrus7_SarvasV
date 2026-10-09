from dataclasses import replace
from decimal import Decimal
import pytest

from backend.platform import Platform
from backend.shared.contracts import (
    GlobalTradingState as Gate,
    OrderIntent,
    OrderStatus,
    RiskPolicy,
    Side,
    Tick,
)
from backend.execution.orders import SubmissionBlocked


class ControllableClock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class MockConnectedExternalProvider:
    supports_live_broker = True

    def stop(self):
        return True

    def telemetry(self):
        return {
            "provider": "021",
            "source": "021_LIVE",
            "connected": True,
            "last_received_at": None,
        }


def make_test_platform(*, external=False):
    clock = ControllableClock()
    platform = Platform(clock=clock)
    platform.account("acc_a")
    platform.strategies.subscribe("acc_a", "strat_a", "momentum", "TCS")
    if external:
        platform.configure_external_market_data(MockConnectedExternalProvider())
        source = "021_LIVE"
    else:
        source = "MOCK_REPLAY"
    platform.tick(
        Tick("TCS", int(clock()), Decimal("100.0"), 10, "init-mark", data_source=source),
        replay=not external,
    )
    return platform, clock


def make_intent(
    platform,
    intent_id="intent_1",
    account="acc_a",
    strategy="strat_a",
    symbol="TCS",
    side=Side.BUY,
    qty=10,
):
    return OrderIntent(
        intent_id=intent_id,
        strategy_instance_id=strategy,
        account_id=account,
        symbol=symbol,
        side=side,
        quantity=qty,
        created_at=platform.clock(),
    )


# -----------------------------------------------------------------------------
# 1. Connected-but-unverified provider, stale feed/broker, incomplete snapshot
# -----------------------------------------------------------------------------
def test_connected_unverified_provider_blocks_admission_and_resume():
    platform, clock = make_test_platform(external=True)
    # External provider has no authenticated subscription ACK
    # 1. Resume must be rejected
    with pytest.raises(ValueError, match="provider subscription evidence unavailable"):
        platform.reliability.resume()
    assert platform.risk.state != Gate.RUNNING

    # 2. Admission under RUNNING gate must be rejected with RISK_PROVIDER_SUBSCRIPTION_UNAVAILABLE
    platform.risk.state = Gate.RUNNING
    intent = make_intent(platform, "ext_order_1")
    decision = platform.risk.submit(intent)
    assert decision.allowed is False
    assert decision.reason_code == "RISK_PROVIDER_SUBSCRIPTION_UNAVAILABLE"

    # Zero orders inserted in orders table
    assert not platform.store.rows("SELECT id FROM orders WHERE id='ext_order_1'")
    platform.close()


def test_stale_feed_and_broker_block_admission_with_proper_codes():
    platform, clock = make_test_platform()
    assert platform.reliability.reconcile() is True
    platform.reliability.resume()
    assert platform.risk.state == Gate.RUNNING

    # 1. Reconcile broker to keep broker fresh, set gate RUNNING, advance clock past feed age
    clock.advance(16)
    assert platform.reliability.reconcile() is True
    platform.risk.state = Gate.RUNNING
    intent = make_intent(platform, "stale_feed_ord")
    decision = platform.risk.submit(intent)
    assert decision.allowed is False
    assert decision.reason_code == "RISK_STALE_MARKET_DATA"

    # Feed a fresh mark
    platform.tick(
        Tick("TCS", int(clock()), Decimal("101.0"), 10, "fresh-tick", data_source="MOCK_REPLAY"),
        replay=True,
    )
    assert platform.reliability.reconcile() is True
    platform.risk.state = Gate.RUNNING

    # 2. Advance broker past max_broker_age (5s) without reconciling
    clock.advance(6)
    intent2 = make_intent(platform, "stale_broker_ord")
    decision2 = platform.risk.submit(intent2)
    assert decision2.allowed is False
    assert decision2.reason_code == "RISK_STALE_BROKER_STATE"
    platform.close()


def test_incomplete_reconciliation_blocks_admission_and_resume(monkeypatch):
    platform, clock = make_test_platform()
    # Incomplete snapshot
    snapshot = replace(platform.broker.snapshot(), is_complete=False)
    monkeypatch.setattr(platform.broker_calls, "snapshot", lambda timeout=None: snapshot)

    assert platform.reliability.reconcile() is False
    assert platform.reliability.report["reason"] == "SNAPSHOT_INCOMPLETE"

    # Resume must be rejected
    with pytest.raises(ValueError, match="reconciliation required"):
        platform.reliability.resume()

    # Admission under RUNNING gate must be rejected with RISK_RECONCILIATION_REQUIRED
    platform.risk.state = Gate.RUNNING
    intent = make_intent(platform, "incomp_ord")
    decision = platform.risk.submit(intent)
    assert decision.allowed is False
    assert decision.reason_code == "RISK_RECONCILIATION_REQUIRED"
    platform.close()


# -----------------------------------------------------------------------------
# 2. Evidence invalidates between reservation and dispatch: zero broker calls
# -----------------------------------------------------------------------------
def test_evidence_invalidates_between_reservation_and_dispatch_zero_broker_calls(monkeypatch):
    platform, clock = make_test_platform()
    platform.reliability.resume()
    assert platform.risk.state == Gate.RUNNING

    broker_calls = []
    original_submit = platform.broker.submit

    def recording_submit(intent):
        broker_calls.append(intent.intent_id)
        return original_submit(intent)

    monkeypatch.setattr(platform.broker, "submit", recording_submit)

    # Invalidate feed right before dispatch (e.g. simulate clock jumping between reservation and dispatch)
    intent = make_intent(platform, "race_ord_1")

    original_start_reserved = platform.orders._start_reserved

    def invalidate_and_start(ord_intent):
        # Invalidate clock/feed age right before serialized dispatch start
        clock.advance(20)
        return original_start_reserved(ord_intent)

    monkeypatch.setattr(platform.orders, "_start_reserved", invalidate_and_start)

    # Submit the order: admission passes and reserves, but pre-dispatch revalidation blocks!
    decision = platform.risk.submit(intent)
    assert decision.allowed is True  # Reserved at admission

    # Order in database must be REJECTED, not UNKNOWN or OPEN
    rows = platform.store.rows("SELECT * FROM orders WHERE id='race_ord_1'")
    assert len(rows) == 1
    assert rows[0]["status"] == OrderStatus.REJECTED.value
    assert rows[0]["dispatch_started"] == 0

    # Broker submit was NEVER called
    assert len(broker_calls) == 0

    # DISPATCH_BLOCKED audit was recorded
    audits = platform.store.rows("SELECT * FROM audit WHERE type='DISPATCH_BLOCKED'")
    assert any("race_ord_1" in a["payload"] for a in audits)

    # Reservation was safely released from budget
    budget = platform.risk.budget("acc_a", "strat_a", "TCS")
    assert budget["position"]["reserved_buy"] == 0
    platform.close()


# -----------------------------------------------------------------------------
# 3. Once-dispatched uncertainty retains exposure without retries
# -----------------------------------------------------------------------------
def test_once_dispatched_uncertainty_retains_exposure_without_retries(monkeypatch):
    platform, clock = make_test_platform()
    platform.reliability.resume()

    # Simulate broker timeout during wait on broker_calls
    def failing_wait(call, timeout=None):
        raise TimeoutError("broker HTTP submit timed out after dispatch started")

    monkeypatch.setattr(platform.broker_calls, "wait", failing_wait)

    intent = make_intent(platform, "timeout_ord_1", qty=15)
    platform.risk.submit(intent)

    # Order must remain UNKNOWN with dispatch_started=1
    rows = platform.store.rows("SELECT * FROM orders WHERE id='timeout_ord_1'")
    assert len(rows) == 1
    assert rows[0]["status"] == OrderStatus.UNKNOWN.value
    assert rows[0]["dispatch_started"] == 1

    # Platform must have failed closed
    assert platform.risk.state == Gate.UNCERTAIN

    # Reservation remains retained in both strategy and account budgets
    budget = platform.risk.budget("acc_a", "strat_a", "TCS")
    assert budget["position"]["reserved_buy"] == 15
    acc_budget = platform.risk.account_budget("acc_a", "TCS")
    assert acc_budget["net_projected"] == 15

    # SUBMISSION_UNKNOWN audit event exists
    audits = platform.store.rows("SELECT * FROM audit WHERE type='SUBMISSION_UNKNOWN'")
    assert any("timeout_ord_1" in a["payload"] for a in audits)
    platform.close()


# -----------------------------------------------------------------------------
# 4. Concurrent directional reservations remain effective
# -----------------------------------------------------------------------------
def test_directional_reservations_track_both_sides_and_account_limits():
    platform, clock = make_test_platform()
    platform.reliability.resume()

    # Policy limit: 20 per strategy
    platform.risk.policies["strat_a"] = RiskPolicy(max_position=20)

    # Submit BUY 15 -> allowed
    i_buy = make_intent(platform, "dir_buy_1", qty=15, side=Side.BUY)
    assert platform.risk.submit(i_buy).allowed is True

    # Submit SELL 10 -> allowed (directional capacity tracked separately, not offset)
    i_sell = make_intent(platform, "dir_sell_1", qty=10, side=Side.SELL)
    assert platform.risk.submit(i_sell).allowed is True

    # Try BUY 10 more -> exceeds max_position (15 + 10 = 25 > 20) -> rejected
    i_buy_excess = make_intent(platform, "dir_buy_2", qty=10, side=Side.BUY)
    dec = platform.risk.submit(i_buy_excess)
    assert dec.allowed is False
    assert dec.reason_code == "RISK_MAX_POSITION"

    # Try SELL 15 more -> exceeds max_position (10 + 15 = 25 > 20) -> rejected
    i_sell_excess = make_intent(platform, "dir_sell_2", qty=15, side=Side.SELL)
    dec_sell = platform.risk.submit(i_sell_excess)
    assert dec_sell.allowed is False
    assert dec_sell.reason_code == "RISK_MAX_POSITION"
    platform.close()


# -----------------------------------------------------------------------------
# 5. Restart and reconnect stay closed
# -----------------------------------------------------------------------------
def test_reconnect_and_restart_never_auto_resume(tmp_path):
    db_file = str(tmp_path / "persist_test.db")
    clock = ControllableClock()
    platform = Platform(path=db_file, clock=clock)
    platform.account("acc_a")
    platform.strategies.subscribe("acc_a", "strat_a", "momentum", "TCS")
    platform.tick(Tick("TCS", int(clock()), Decimal("100.0"), 10, "init-mark"), replay=True)
    platform.reliability.resume()
    assert platform.risk.state == Gate.RUNNING

    # 1. Disconnect broker
    platform.disconnect_broker()
    assert platform.risk.state == Gate.UNCERTAIN

    # 2. Reconnect broker: calls reconcile(), which leaves gate in STOPPED
    reconnect_res = platform.reconnect_broker()
    assert reconnect_res["connected"] is True
    assert reconnect_res["reconciled"] is True
    assert platform.risk.state == Gate.STOPPED
    assert platform.strategies.enabled is False

    # 3. Simulate process restart: fresh platform instance starts in RECOVERING
    platform.close()
    restarted = Platform(path=db_file, clock=clock)
    assert restarted.risk.state == Gate.RECOVERING
    assert restarted.reliability.health.value == "RECOVERING"
    assert restarted.strategies.enabled is False
    restarted.close()


# -----------------------------------------------------------------------------
# 6. Resume evaluates evidence across accounts and independently of gate
# -----------------------------------------------------------------------------
def test_resume_evaluates_evidence_across_all_accounts(monkeypatch):
    platform, clock = make_test_platform()
    # Add account B
    platform.account("acc_b")
    platform.strategies.subscribe("acc_b", "strat_b", "momentum", "INFY")
    assert platform.reliability.reconcile() is True

    # Ingest UNKNOWN order on acc_b
    with platform.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) "
            "VALUES ('unk_b','strat_b','acc_b','INFY','BUY',5,?, 'UNKNOWN',0,0,1)",
            (clock(),),
        )

    # When reconcile is bypassed or reports the unknown order still active
    monkeypatch.setattr(platform.reliability, "reconcile", lambda timeout=None: True)

    # Resume must be blocked because an UNKNOWN order exists on acc_b
    with pytest.raises(ValueError, match="unresolved unknown orders"):
        platform.reliability.resume()
    assert platform.risk.state == Gate.STOPPED

    # Resolve the unknown order
    with platform.store.transaction() as db:
        db.execute("UPDATE orders SET status='REJECTED' WHERE id='unk_b'")

    # Resume now succeeds independently of gate state
    platform.reliability.resume()
    assert platform.risk.state == Gate.RUNNING
    assert platform.strategies.enabled is True
    platform.close()


# -----------------------------------------------------------------------------
# 7. Kill and disconnect during resume/dispatch prevent unauthorized state
# -----------------------------------------------------------------------------
def test_kill_and_disconnect_during_resume_prevent_gate_opening():
    platform, clock = make_test_platform()
    assert platform.reliability.reconcile() is True

    # 1. Kill latched before resume
    platform.risk.kill_requested.set()
    with pytest.raises(ValueError, match="latched"):
        platform.reliability.resume()
    assert platform.risk.state == Gate.STOPPED

    platform.risk.kill_requested.clear()

    # 2. Broker disconnected before resume
    platform.broker.connected = False
    with pytest.raises(ValueError, match="broker evidence not ready|reconciliation required"):
        platform.reliability.resume()
    assert platform.risk.state != Gate.RUNNING
    platform.close()


# -----------------------------------------------------------------------------
# 8. Emergency reducing exits and mock/replay contracts preserved
# -----------------------------------------------------------------------------
def test_emergency_exit_and_mock_replay_contracts_preserved():
    platform, clock = make_test_platform()
    platform.reliability.resume()

    # Ingest a fill to create a position: LONG 10 TCS
    intent_norm = make_intent(platform, "fill_norm_1", qty=10)
    platform.risk.submit(intent_norm)
    fill = platform.broker.execute("fill_norm_1", 10, Decimal("100.0"), clock())
    platform.ingest(fill)
    assert platform.ledger.quantity("acc_a", "strat_a", "TCS") == 10

    # Latch kill gate manually to test emergency exit authorization
    platform.risk.state = Gate.KILLING
    platform.reliability.safety.set("kill_latched", True)

    # Emergency exit requires reducing intent under KILLING gate
    exit_intent = make_intent(platform, "emerg_exit_1", side=Side.SELL, qty=10)
    emerg_decision = platform.risk.authorize_emergency(exit_intent)
    assert emerg_decision.allowed is True
    assert emerg_decision.reason_code == "EMERGENCY_REDUCING_EXIT"

    # Emergency order dispatches safely
    platform.orders.submit_reserved(exit_intent)
    rows = platform.store.rows("SELECT * FROM orders WHERE id='emerg_exit_1'")
    assert rows[0]["status"] in {OrderStatus.OPEN.value, OrderStatus.FILLED.value}
    assert rows[0]["emergency"] == 1
    platform.close()


def test_emergency_dispatch_rechecks_residual_after_late_cancelled_exit_fill(
    monkeypatch,
):
    platform, clock = make_test_platform()
    platform.reliability.resume()

    entry = make_intent(platform, "entry_for_emergency_race", qty=10)
    platform.risk.submit(entry)
    platform.ingest(
        platform.broker.execute(entry.intent_id, 10, Decimal("100.0"), clock())
    )

    # A previously cancelled reducing order is terminal locally, but may still
    # receive a late provider fill while the emergency reservation waits.
    prior_exit = make_intent(
        platform, "cancelled_exit_for_emergency_race", side=Side.SELL, qty=5
    )
    platform.risk.submit(prior_exit)
    platform.cancel(prior_exit.intent_id)

    platform.risk.state = Gate.KILLING
    platform.reliability.safety.set("kill_latched", True)
    emergency = make_intent(platform, "emergency_race_exit", side=Side.SELL, qty=10)
    platform.risk.authorize_emergency(emergency)

    broker_submits = []
    original_submit = platform.broker.submit

    def recording_submit(intent):
        broker_submits.append(intent.intent_id)
        return original_submit(intent)

    monkeypatch.setattr(platform.broker, "submit", recording_submit)
    original_start = platform.orders._start_reserved

    def late_fill_then_start(intent):
        platform.ingest(
            platform.broker.execute(
                prior_exit.intent_id,
                5,
                Decimal("100.0"),
                clock(),
                allow_late=True,
            )
        )
        return original_start(intent)

    monkeypatch.setattr(platform.orders, "_start_reserved", late_fill_then_start)
    with pytest.raises(SubmissionBlocked):
        platform.orders.submit_reserved(emergency)

    row = platform.store.rows(
        "SELECT status,dispatch_started FROM orders WHERE id=?",
        (emergency.intent_id,),
    )[0]
    assert row["status"] == OrderStatus.REJECTED.value
    assert row["dispatch_started"] == 0
    assert broker_submits == []
    assert platform.ledger.quantity("acc_a", "strat_a", "TCS") == 5
    audit = platform.store.rows(
        "SELECT payload FROM audit WHERE type='EMERGENCY_DISPATCH_BLOCKED'"
    )
    assert any("EMERGENCY_RESIDUAL_INSUFFICIENT" in row["payload"] for row in audit)
    platform.close()

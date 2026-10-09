from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest

from backend.execution.orders import (
    IllegalOrderTransition,
    validate_order_transition,
)
from backend.platform import Platform
from backend.shared.contracts import (
    CanonicalOrder,
    Fill,
    OrderIntent,
    OrderStatus,
    Side,
)
from test_recovery import ready, intent, Clock


def test_reserved_to_unknown_to_open_lifecycle():
    p = ready()
    i = intent(p, "ord-1", 100)
    decision = p.risk.submit(i)
    assert decision.allowed

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-1'")
    assert len(rows) == 1
    assert rows[0]["status"] == OrderStatus.OPEN.value
    assert rows[0]["filled"] == 0
    assert rows[0]["quantity"] == 100
    assert rows[0]["dispatch_started"] == 1

    # Ledger remains 0 until fills arrive
    assert p.ledger.quantity("a", "A", "X") == 0

    audits = [
        r["type"]
        for r in p.store.rows("SELECT type FROM audit WHERE payload LIKE '%ord-1%'")
    ]
    assert "RISK_DECISION" in audits
    assert "ORDER_SUBMITTED" in audits
    assert "ORDER_STATUS_CHANGED" in audits
    p.store.close()


def test_unknown_to_rejected_on_submission_rejection():
    p = ready()
    p.broker.reject_next = True
    i = intent(p, "ord-reject", 50)
    decision = p.risk.submit(i)
    assert decision.allowed  # Risk approved admission

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-reject'")
    assert len(rows) == 1
    assert rows[0]["status"] == OrderStatus.REJECTED.value
    assert rows[0]["filled"] == 0

    # Ensure no fills can ever be accepted on this rejected order
    fake_fill = Fill(
        "f-rej",
        "ord-reject",
        "A",
        "a",
        "X",
        Side.BUY,
        10,
        Decimal("100"),
        p.clock(),
    )
    with pytest.raises(ValueError, match="cannot ingest fill for rejected order"):
        p.ingest(fake_fill)

    assert p.risk.state == "UNCERTAIN"
    p.store.close()


def test_open_to_partially_filled():
    p = ready()
    i = intent(p, "ord-part", 100)
    p.risk.submit(i)

    f = p.broker.execute("ord-part", 40, Decimal("100"), p.clock())
    applied = p.ingest(f)
    assert applied

    rows = p.store.rows("SELECT * FROM orders WHERE id='ord-part'")
    assert rows[0]["status"] == OrderStatus.PARTIALLY_FILLED.value
    assert rows[0]["filled"] == 40
    assert rows[0]["quantity"] - rows[0]["filled"] == 60
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def order_status_filled(p, order_id):
    row = p.store.rows("SELECT status, filled FROM orders WHERE id=?", (order_id,))[0]
    return row["status"], row["filled"]


def test_repeated_partial_fills_and_full_fill():
    p = ready()
    p.risk.submit(intent(p, "ord-multi", 100))

    # Fill 1: 30
    f1 = p.broker.execute("ord-multi", 30, Decimal("100"), p.clock())
    p.ingest(f1)
    assert order_status_filled(p, "ord-multi") == ("PARTIALLY_FILLED", 30)
    assert p.ledger.quantity("a", "A", "X") == 30

    # Fill 2: 30
    f2 = p.broker.execute("ord-multi", 30, Decimal("101"), p.clock())
    p.ingest(f2)
    assert order_status_filled(p, "ord-multi") == ("PARTIALLY_FILLED", 60)
    assert p.ledger.quantity("a", "A", "X") == 60

    # Fill 3: 20
    f3 = p.broker.execute("ord-multi", 20, Decimal("102"), p.clock())
    p.ingest(f3)
    assert order_status_filled(p, "ord-multi") == ("PARTIALLY_FILLED", 80)
    assert p.ledger.quantity("a", "A", "X") == 80

    # Fill 4: 20 (completes order)
    f4 = p.broker.execute("ord-multi", 20, Decimal("103"), p.clock())
    p.ingest(f4)
    assert order_status_filled(p, "ord-multi") == ("FILLED", 100)
    assert p.ledger.quantity("a", "A", "X") == 100
    p.store.close()


def test_duplicate_identical_fill_ignored():
    p = ready()
    p.risk.submit(intent(p, "ord-dup", 100))
    f = p.broker.execute("ord-dup", 40, Decimal("100"), p.clock())

    assert p.ingest(f) is True
    assert p.ledger.quantity("a", "A", "X") == 40

    # Duplicate submission of the identical fill
    assert p.ingest(f) is False
    assert p.ledger.quantity("a", "A", "X") == 40
    assert (
        p.store.rows("SELECT filled FROM orders WHERE id='ord-dup'")[0]["filled"] == 40
    )

    dup_audits = p.store.rows("SELECT * FROM audit WHERE type='DUPLICATE_FILL_IGNORED'")
    assert len(dup_audits) == 1
    p.store.close()


def test_concurrent_duplicate_fill_has_one_financial_effect():
    p = ready()
    p.risk.submit(intent(p, "ord-concurrent-dup", 100))
    fill = p.broker.execute("ord-concurrent-dup", 40, Decimal("100"), p.clock())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: p.ingest(fill), range(2)))

    assert sorted(results) == [False, True]
    assert p.ledger.quantity("a", "A", "X") == 40
    row = p.store.rows(
        "SELECT status,filled FROM orders WHERE id='ord-concurrent-dup'"
    )[0]
    assert (row["status"], row["filled"]) == ("PARTIALLY_FILLED", 40)
    assert len(p.store.rows("SELECT id FROM fills WHERE id=?", (fill.fill_id,))) == 1
    p.store.close()


def test_fill_and_order_state_roll_back_together_on_audit_failure():
    p = ready()
    p.risk.submit(intent(p, "ord-fill-rollback", 100))
    fill = p.broker.execute("ord-fill-rollback", 40, Decimal("100"), p.clock())
    original_audit = p.store.audit
    failed = False

    def fail_order_transition_audit(event_type, payload, correlation_id=None):
        nonlocal failed
        if event_type == "ORDER_STATUS_CHANGED" and not failed:
            failed = True
            raise RuntimeError("injected audit persistence failure")
        return original_audit(event_type, payload, correlation_id)

    p.store.audit = fail_order_transition_audit
    with pytest.raises(RuntimeError, match="injected audit persistence failure"):
        p.ingest(fill)
    p.store.audit = original_audit

    order = p.store.rows(
        "SELECT status,filled FROM orders WHERE id='ord-fill-rollback'"
    )[0]
    assert (order["status"], order["filled"]) == ("OPEN", 0)
    assert p.store.rows("SELECT id FROM fills WHERE id=?", (fill.fill_id,)) == []
    assert p.ledger.quantity("a", "A", "X") == 0
    assert p.risk.state == "UNCERTAIN"
    p.store.close()


def test_conflicting_duplicate_fill_fails_safely():
    p = ready()
    p.risk.submit(intent(p, "ord-conflict", 100))
    f = p.broker.execute("ord-conflict", 40, Decimal("100"), p.clock())
    assert p.ingest(f) is True

    # Same fill ID, but conflicting price
    conflicting = replace(f, price=Decimal("105"))
    with pytest.raises(ValueError, match="conflicting duplicate fill"):
        p.ingest(conflicting)

    assert p.risk.state == "UNCERTAIN"
    assert p.ledger.quantity("a", "A", "X") == 40
    p.store.close()


def test_overfill_attempt_rejected():
    p = ready()
    p.risk.submit(intent(p, "ord-overfill", 50))
    f1 = p.broker.execute("ord-overfill", 30, Decimal("100"), p.clock())
    p.ingest(f1)

    # Attempting to ingest a fill of 30 when only 20 remain
    overfill = Fill(
        "f-over",
        "ord-overfill",
        "A",
        "a",
        "X",
        Side.BUY,
        30,
        Decimal("100"),
        p.clock(),
    )
    with pytest.raises(ValueError, match="overfill"):
        p.ingest(overfill)

    assert p.risk.state == "UNCERTAIN"
    assert (
        p.store.rows("SELECT filled FROM orders WHERE id='ord-overfill'")[0]["filled"]
        == 30
    )
    p.store.close()


def test_fill_attribution_mismatches():
    p = ready()
    p.risk.submit(intent(p, "ord-attr", 50, side=Side.BUY))

    # Wrong strategy
    with pytest.raises(ValueError, match="fill attribution mismatch"):
        p.ingest(
            Fill(
                "f1",
                "ord-attr",
                "WRONG_STRAT",
                "a",
                "X",
                Side.BUY,
                10,
                Decimal("100"),
                p.clock(),
            )
        )

    # Wrong account
    with pytest.raises(ValueError, match="fill attribution mismatch"):
        p.ingest(
            Fill(
                "f2",
                "ord-attr",
                "A",
                "WRONG_ACC",
                "X",
                Side.BUY,
                10,
                Decimal("100"),
                p.clock(),
            )
        )

    # Wrong symbol
    with pytest.raises(ValueError, match="fill attribution mismatch"):
        p.ingest(
            Fill(
                "f3",
                "ord-attr",
                "A",
                "a",
                "WRONG_SYM",
                Side.BUY,
                10,
                Decimal("100"),
                p.clock(),
            )
        )

    # Wrong side
    with pytest.raises(ValueError, match="fill attribution mismatch"):
        p.ingest(
            Fill(
                "f4",
                "ord-attr",
                "A",
                "a",
                "X",
                Side.SELL,
                10,
                Decimal("100"),
                p.clock(),
            )
        )

    p.store.close()


def test_fill_for_unknown_order():
    p = ready()
    unattributed = Fill(
        "f-orphan",
        "non-existent-order",
        "A",
        "a",
        "X",
        Side.BUY,
        10,
        Decimal("100"),
        p.clock(),
    )
    with pytest.raises(ValueError, match="unattributed execution"):
        p.ingest(unattributed)

    assert p.risk.state == "UNCERTAIN"
    p.store.close()


def test_fill_on_undispatched_order_rejected():
    p = ready()
    # Create an order in RESERVED state without dispatching it
    with p.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) VALUES (?,?,?,?,?,?,?,?,0,0,0)",
            ("ord-undispatched", "A", "a", "X", "BUY", 50, p.clock(), "RESERVED"),
        )

    fill_attempt = Fill(
        "f-undisp",
        "ord-undispatched",
        "A",
        "a",
        "X",
        Side.BUY,
        10,
        Decimal("100"),
        p.clock(),
    )
    with pytest.raises(ValueError, match="cannot ingest fill for undispatched order"):
        p.ingest(fill_attempt)

    p.store.close()


def test_illegal_terminal_state_regressions():
    # FILLED regressions
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(OrderStatus.FILLED, OrderStatus.OPEN, 100, 0, 100)
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(
            OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, 100, 50, 100
        )
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(OrderStatus.FILLED, OrderStatus.REJECTED, 100, 0, 100)
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(
            OrderStatus.FILLED, OrderStatus.CANCELLED, 100, 100, 100
        )

    # REJECTED regressions
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(OrderStatus.REJECTED, OrderStatus.OPEN, 0, 0, 100)
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(
            OrderStatus.REJECTED, OrderStatus.PARTIALLY_FILLED, 0, 50, 100
        )
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(OrderStatus.REJECTED, OrderStatus.FILLED, 0, 100, 100)

    # CANCELLED regressions
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(OrderStatus.CANCELLED, OrderStatus.OPEN, 50, 0, 100)
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(
            OrderStatus.CANCELLED, OrderStatus.PARTIALLY_FILLED, 50, 60, 100
        )
    with pytest.raises(IllegalOrderTransition, match="illegal order state transition"):
        validate_order_transition(
            OrderStatus.CANCELLED, OrderStatus.REJECTED, 50, 0, 100
        )

    # Decreasing filled quantity
    with pytest.raises(IllegalOrderTransition, match="cannot decrease"):
        validate_order_transition(
            OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED, 50, 40, 100
        )

    # Inconsistent filled quantity for target status
    with pytest.raises(IllegalOrderTransition, match="FILLED status requires"):
        validate_order_transition(OrderStatus.OPEN, OrderStatus.FILLED, 0, 80, 100)
    with pytest.raises(IllegalOrderTransition, match="requires filled_quantity == 0"):
        validate_order_transition(
            OrderStatus.RESERVED, OrderStatus.REJECTED, 0, 10, 100
        )


def test_canonical_order_invariants():
    i = OrderIntent("intent-1", "A", "a", "X", Side.BUY, 100, 1_700_000_000.0)

    # Valid
    o = CanonicalOrder("ord-1", i, OrderStatus.OPEN, 0)
    assert o.remaining_quantity == 100

    o_part = CanonicalOrder("ord-1", i, OrderStatus.PARTIALLY_FILLED, 40)
    assert o_part.remaining_quantity == 60

    o_full = CanonicalOrder("ord-1", i, OrderStatus.FILLED, 100)
    assert o_full.remaining_quantity == 0

    # Negative filled quantity
    with pytest.raises(ValueError, match="non-negative integer"):
        CanonicalOrder("ord-1", i, OrderStatus.PARTIALLY_FILLED, -1)

    # Exceeding quantity
    with pytest.raises(ValueError, match="cannot exceed requested quantity"):
        CanonicalOrder("ord-1", i, OrderStatus.FILLED, 101)

    # Empty order ID
    with pytest.raises(ValueError, match="order_id must be a non-empty string"):
        CanonicalOrder("", i, OrderStatus.OPEN, 0)


def test_timeout_after_accept_remains_unknown_until_reconciled():
    p = ready()
    p.broker.timeout_after_accept = True
    p.risk.submit(intent(p, "ord-timeout", 20))

    assert p.risk.state == "UNCERTAIN"
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-timeout'")[0]
    assert row["status"] == OrderStatus.UNKNOWN.value
    assert row["filled"] == 0
    assert row["dispatch_started"] == 1

    # Broker actually accepted it
    assert "ord-timeout" in p.broker.orders

    # Reconciliation resolves UNKNOWN to OPEN
    assert p.reliability.reconcile()
    assert p.risk.state == "STOPPED"
    row_after = p.store.rows("SELECT * FROM orders WHERE id='ord-timeout'")[0]
    assert row_after["status"] == OrderStatus.OPEN.value
    p.store.close()


def test_complete_snapshot_resolves_absent_unknown_to_rejected():
    p = ready()
    # Simulate an order that started dispatch (UNKNOWN) but was never recorded at broker
    with p.store.transaction() as db:
        db.execute(
            "INSERT INTO orders (id,strategy,account,symbol,side,quantity,created,status,filled,emergency,dispatch_started) VALUES (?,?,?,?,?,?,?,?,0,0,1)",
            ("ord-lost", "A", "a", "X", "BUY", 10, p.clock(), "UNKNOWN"),
        )

    assert p.reliability.reconcile()
    row = p.store.rows("SELECT * FROM orders WHERE id='ord-lost'")[0]
    assert row["status"] == OrderStatus.REJECTED.value
    assert row["dispatch_started"] == 0

    audits = p.store.rows("SELECT * FROM audit WHERE type='ABSENT_SUBMISSION_RESOLVED'")
    assert any("ord-lost" in r["payload"] for r in audits)
    p.store.close()


def test_incomplete_snapshot_not_falsely_resolving_unknown(monkeypatch):
    p = ready()
    p.broker.timeout_after_accept = True
    p.risk.submit(intent(p, "ord-incomplete", 10))

    incomplete = replace(p.broker.snapshot(), is_complete=False)
    monkeypatch.setattr(p.broker, "snapshot", lambda: incomplete)

    assert not p.reliability.reconcile()
    assert p.reliability.report["reason"] == "SNAPSHOT_INCOMPLETE"
    assert (
        p.store.rows("SELECT status FROM orders WHERE id='ord-incomplete'")[0]["status"]
        == OrderStatus.UNKNOWN.value
    )
    p.store.close()


def test_late_fill_after_cancellation():
    p = ready()
    p.risk.submit(intent(p, "ord-cancel-fill", 100))

    # Partial fill of 40
    f1 = p.broker.execute("ord-cancel-fill", 40, Decimal("100"), p.clock())
    p.ingest(f1)
    assert order_status_filled(p, "ord-cancel-fill") == ("PARTIALLY_FILLED", 40)

    # Cancel order at broker and update local status to CANCELLED
    p.broker.cancel("ord-cancel-fill")
    p.orders.transition_status("ord-cancel-fill", OrderStatus.CANCELLED)
    assert order_status_filled(p, "ord-cancel-fill") == ("CANCELLED", 40)

    # Late execution 1 of 30 arrives: status stays CANCELLED, filled updates to 70
    f2 = p.broker.execute(
        "ord-cancel-fill", 30, Decimal("100"), p.clock(), allow_late=True
    )
    assert p.ingest(f2) is True
    assert order_status_filled(p, "ord-cancel-fill") == ("CANCELLED", 70)
    assert p.ledger.quantity("a", "A", "X") == 70

    # Late execution 2 of 30 arrives: completes the 100 requested quantity
    f3 = p.broker.execute(
        "ord-cancel-fill", 30, Decimal("100"), p.clock(), allow_late=True
    )
    assert p.ingest(f3) is True
    # Now order transitioned from CANCELLED to FILLED
    assert order_status_filled(p, "ord-cancel-fill") == ("FILLED", 100)
    assert p.ledger.quantity("a", "A", "X") == 100

    late_audits = p.store.rows(
        "SELECT * FROM audit WHERE type='LATE_FILL_ON_CANCELLED'"
    )
    assert len(late_audits) == 2
    p.store.close()


def test_cancel_fill_race():
    p = ready()
    p.risk.submit(intent(p, "ord-race", 50))

    # Broker executed full fill
    f = p.broker.execute("ord-race", 50, Decimal("100"), p.clock())

    # Locally, order was marked CANCELLED before fill arrived
    p.orders.transition_status("ord-race", OrderStatus.CANCELLED)
    assert order_status_filled(p, "ord-race") == ("CANCELLED", 0)

    # Now the racing fill arrives
    assert p.ingest(f) is True
    assert order_status_filled(p, "ord-race") == ("FILLED", 50)
    assert p.ledger.quantity("a", "A", "X") == 50
    p.store.close()


def test_out_of_order_unique_fills_converge():
    p = ready()
    p.risk.submit(intent(p, "ord-ooo", 100))

    # Broker generates two fills
    f1 = Fill(
        "f-ooo-1",
        "ord-ooo",
        "A",
        "a",
        "X",
        Side.BUY,
        30,
        Decimal("100"),
        p.clock() + 1,
    )
    f2 = Fill(
        "f-ooo-2",
        "ord-ooo",
        "A",
        "a",
        "X",
        Side.BUY,
        40,
        Decimal("100"),
        p.clock() + 2,
    )

    # Ingest f2 before f1
    assert p.ingest(f2) is True
    assert order_status_filled(p, "ord-ooo") == ("PARTIALLY_FILLED", 40)
    assert p.ledger.quantity("a", "A", "X") == 40

    # Now ingest f1
    assert p.ingest(f1) is True
    assert order_status_filled(p, "ord-ooo") == ("PARTIALLY_FILLED", 70)
    assert p.ledger.quantity("a", "A", "X") == 70
    p.store.close()


def test_restart_reconciliation_preserves_valid_execution_state(tmp_path):
    path = str(tmp_path / "exec_state.db")
    first = ready(path)
    first.risk.submit(intent(first, "ord-persist", 100))
    first.ingest(first.broker.execute("ord-persist", 45, Decimal("100"), first.clock()))
    first.store.close()

    # Reopen Platform
    second = Platform(path, clock=Clock())
    assert second.risk.state == "RECOVERING"
    assert second.ledger.quantity("a", "A", "X") == 45
    assert order_status_filled(second, "ord-persist") == ("PARTIALLY_FILLED", 45)

    # Reconcile successfully verifies against preserved mock external evidence
    assert second.reliability.reconcile()
    assert second.risk.state == "STOPPED"
    assert order_status_filled(second, "ord-persist") == ("PARTIALLY_FILLED", 45)
    second.store.close()

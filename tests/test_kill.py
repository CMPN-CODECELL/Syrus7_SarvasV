from decimal import Decimal
from threading import Event, Thread
import time

from test_recovery import ready, intent
from backend.shared.contracts import OrderStatus


def test_hung_submission_does_not_hold_gate_or_database(monkeypatch):
    p = ready()
    entered, release = Event(), Event()
    original = p.broker.submit

    def hung(i):
        entered.set()
        assert release.wait(3)
        return original(i)

    monkeypatch.setattr(p.broker, "submit", hung)
    p.broker_calls.call_timeout = 0.05
    thread = Thread(target=lambda: p.risk.submit(intent(p)))
    thread.start()
    assert entered.wait(1)
    started = time.monotonic()
    certificate = p.kill()
    assert time.monotonic() - started < 1
    assert certificate.status == "FAILED"
    assert p.risk.kill_requested.is_set()
    assert not p.risk.submit(intent(p, "blocked")).allowed
    assert p.store.rows("SELECT status FROM orders")[0][0] == "UNKNOWN"
    release.set()
    thread.join(1)
    assert not thread.is_alive()
    assert p.kill().status == "SUCCESS"
    p.store.close()


def test_cancel_fill_race_uses_actual_residual(monkeypatch):
    p = ready()
    p.risk.submit(intent(p))
    original = p.broker.cancel

    def racing(oid):
        p.broker.execute(oid, 4, Decimal("100"), p.clock())
        original(oid)

    monkeypatch.setattr(p.broker, "cancel", racing)
    assert p.kill().status == "SUCCESS"
    exits = [o for o in p.broker.orders.values() if o.order_id.startswith("kill:")]
    assert len(exits) == 1 and exits[0].intent.quantity == 4
    assert not p.ledger.quantity("a", "A", "X")
    p.store.close()


def test_delayed_cancel_requires_observation(monkeypatch):
    p = ready()
    p.risk.submit(intent(p))
    original = p.broker.cancel
    attempts = []

    def delayed(oid):
        attempts.append(oid)
        if len(attempts) == 2:
            original(oid)

    monkeypatch.setattr(p.broker, "cancel", delayed)
    assert p.kill().status == "SUCCESS"
    assert len(attempts) == 2
    assert len(p.broker.orders) == 1
    p.store.close()


def test_partial_exit_converges_without_duplicate_orders():
    p = ready()
    p.risk.submit(intent(p))
    p.ingest(p.broker.execute("one", 10, Decimal("100"), p.clock()))

    def partial(o):
        p.ingest(
            p.broker_calls.call(
                "execute",
                o.order_id,
                min(3, o.remaining_quantity),
                Decimal("100"),
                p.clock(),
            )
        )

    assert p.reliability.kill(partial).status == "SUCCESS"
    assert len(p.broker.orders) == 2
    assert not p.ledger.quantity("a", "A", "X")
    p.store.close()


def test_safe_late_is_not_sla_success(monkeypatch):
    p = ready()
    clock = [0]
    original = p.broker.snapshot

    def late():
        clock[0] = 11
        return original()

    monkeypatch.setattr(p.broker, "snapshot", late)
    c = p.reliability.kill(deadline_seconds=12, deadline_clock=lambda: clock[0])
    assert c.status == "SAFE_LATE" and c.elapsed_seconds == 11
    p.store.close()


def test_hung_snapshot_has_bounded_deadline(monkeypatch):
    p = ready()
    release = Event()
    original = p.broker.snapshot

    def hung():
        assert release.wait(3)
        return original()

    monkeypatch.setattr(p.broker, "snapshot", hung)
    c = p.reliability.kill(deadline_seconds=0.03)
    assert c.status == "FAILED" and c.elapsed_seconds < 1
    release.set()
    assert p.broker_calls.active.done.wait(1)
    assert p.reliability.kill_latched
    p.store.close()


def test_gate_closes_between_reservation_and_dispatch(monkeypatch):
    p = ready()
    original = p.orders.submit_reserved

    def close_first(i):
        p.risk.kill_requested.set()
        return original(i)

    monkeypatch.setattr(p.orders, "submit_reserved", close_first)
    p.risk.submit(intent(p))
    assert not p.broker.orders
    assert (
        p.store.rows("SELECT status,dispatch_started FROM orders")[0][0]
        == OrderStatus.REJECTED
    )
    assert p.reliability.reconcile()
    p.store.close()


def test_complete_snapshot_resolves_never_accepted_unknown(monkeypatch):
    p = ready()

    def unavailable(i):
        raise ConnectionError()

    monkeypatch.setattr(p.broker, "submit", unavailable)
    p.risk.submit(intent(p))
    assert p.reliability.reconcile()
    row = p.store.rows("SELECT * FROM orders")[0]
    assert row["status"] == "REJECTED" and row["dispatch_started"] == 0
    p.store.close()

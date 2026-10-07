import json
import random
from decimal import Decimal
from threading import Event, Thread

import pytest

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, RiskPolicy, Side
from test_recovery import ready, Clock


@pytest.mark.parametrize("seed", [7, 19, 43])
def test_mixed_execution_state_machine_retains_safety(seed):
    p = ready()
    for strategy in ("B", "C"):
        p.strategies.subscribe("a", strategy, "momentum", "X")
    for strategy in ("A", "B", "C"):
        p.risk.policies[strategy] = RiskPolicy(
            max_position=30, max_orders_per_minute=1000
        )
    rng = random.Random(seed)
    for n in range(40):
        action = rng.choice(
            ("submit", "fill", "missed", "duplicate", "cancel", "reject", "unknown")
        )
        active = [
            o
            for o in p.broker.orders.values()
            if o.status not in {"FILLED", "CANCELLED", "REJECTED"}
        ]
        if action in {"submit", "reject", "unknown"}:
            strategy = rng.choice(("A", "B", "C"))
            before = p.ledger.quantity("a", strategy, "X")
            p.broker.reject_next = action == "reject"
            p.broker.timeout_after_accept = action == "unknown"
            p.risk.submit(
                OrderIntent(
                    f"{seed}:{n}",
                    strategy,
                    "a",
                    "X",
                    rng.choice((Side.BUY, Side.SELL)),
                    rng.randint(1, 12),
                    p.clock(),
                )
            )
            assert p.ledger.quantity("a", strategy, "X") == before
            p.broker.reject_next = p.broker.timeout_after_accept = False
        elif active and action in {"fill", "missed", "cancel"}:
            order = rng.choice(active)
            if action == "cancel":
                p.broker.cancel(order.order_id)
            else:
                f = p.broker.execute(
                    order.order_id,
                    rng.randint(1, order.remaining_quantity),
                    Decimal("100"),
                    p.clock(),
                )
                if action == "fill":
                    p.ingest(f)
        elif action == "duplicate" and p.broker.fills:
            f = rng.choice(list(p.broker.fills.values()))
            assert not p.ingest(f)
        assert p.reliability.reconcile()
        expected = {}
        for f in p.broker.fills.values():
            expected[f.strategy_instance_id] = (
                expected.get(f.strategy_instance_id, 0) + f.side.sign * f.quantity
            )
        for strategy in ("A", "B", "C"):
            assert p.ledger.quantity("a", strategy, "X") == expected.get(strategy, 0)
            assert p.risk.budget("a", strategy, "X")["position"]["used"] <= 30
        assert p.ledger.aggregate() == p.broker.snapshot().positions
        p.reliability.resume()
    assert p.kill().status == "SUCCESS"
    approvals = {
        json.loads(r["payload"])["intent_id"]
        for r in p.store.rows("SELECT payload FROM audit WHERE type='RISK_DECISION'")
        if json.loads(r["payload"])["allowed"]
    }
    assert set(p.broker.orders) <= approvals
    p.store.close()


def test_resume_cannot_reopen_while_kill_waits_for_controller(monkeypatch):
    p = ready()
    entered, release = Event(), Event()
    original = p.broker.snapshot
    errors = []

    def blocked():
        entered.set()
        assert release.wait(2)
        return original()

    monkeypatch.setattr(p.broker, "snapshot", blocked)

    def resume():
        try:
            p.reliability.resume()
        except ValueError as exc:
            errors.append(str(exc))

    thread = Thread(target=resume)
    thread.start()
    assert entered.wait(1)
    c = p.reliability.kill(deadline_seconds=0.03)
    assert c.status == "FAILED" and c.reason == "KILL_CONTROLLER_BUSY"
    release.set()
    thread.join(1)
    assert not thread.is_alive() and errors
    assert p.reliability.kill_latched and p.risk.state != "RUNNING"
    p.store.close()


def test_disconnect_during_cancel_stays_latched_and_can_recover(monkeypatch):
    p = ready()
    p.risk.submit(OrderIntent("one", "A", "a", "X", Side.BUY, 10, p.clock()))
    original = p.broker.cancel

    def disconnect(oid):
        p.broker.connected = False
        original(oid)

    monkeypatch.setattr(p.broker, "cancel", disconnect)
    assert p.kill().status == "FAILED"
    assert p.reliability.kill_latched
    monkeypatch.setattr(p.broker, "cancel", original)
    p.broker.connected = True
    assert p.kill().status == "SUCCESS"
    p.store.close()


def test_restart_unknown_submission_uses_external_evidence_without_retry(tmp_path):
    path = str(tmp_path / "unknown.db")
    p = ready(path)
    p.broker.timeout_after_accept = True
    p.risk.submit(OrderIntent("ambiguous", "A", "a", "X", Side.BUY, 10, p.clock()))
    p.store.close()
    p = Platform(path, clock=Clock())
    assert p.risk.state == "RECOVERING" and not p.strategies.enabled
    assert p.reliability.reconcile()
    assert p.risk.state == "STOPPED" and len(p.broker.orders) == 1
    assert p.store.rows("SELECT status FROM orders")[0][0] == "OPEN"
    p.store.close()

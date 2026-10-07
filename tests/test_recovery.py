from dataclasses import replace
from decimal import Decimal

import pytest

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


def ready(path=":memory:"):
    p = Platform(path, clock=Clock())
    if not p.store.rows("SELECT id FROM accounts WHERE id='a'"):
        p.account("a")
        p.strategies.subscribe("a", "A", "momentum", "X")
    p.tick(Tick("X", int(p.clock()), Decimal("100"), 0, "fresh"))
    p.reliability.resume()
    return p


def intent(p, key="one", qty=10, side=Side.BUY):
    return OrderIntent(key, "A", "a", "X", side, qty, p.clock())


def test_incomplete_snapshot_cannot_import_fills(monkeypatch):
    p = ready()
    p.risk.submit(intent(p))
    p.broker.execute("one", 4, Decimal("100"), p.clock())
    snapshot = replace(p.broker.snapshot(), is_complete=False)
    monkeypatch.setattr(p.broker, "snapshot", lambda: snapshot)
    assert not p.reliability.reconcile()
    assert p.reliability.report["reason"] == "SNAPSHOT_INCOMPLETE"
    assert p.ledger.quantity("a", "A", "X") == 0
    assert not p.risk.submit(intent(p, "blocked")).allowed
    p.store.close()


def test_fill_history_compared_even_when_account_net_is_zero(monkeypatch):
    p = ready()
    for key, side in (("1-buy", Side.BUY), ("2-sell", Side.SELL)):
        p.risk.submit(intent(p, key, side=side))
        p.ingest(p.broker.execute(key, 10, Decimal("100"), p.clock()))
    snapshot = p.broker.snapshot()
    empty = replace(
        snapshot,
        fills=(),
        orders=tuple(
            replace(o, filled_quantity=0, status="OPEN") for o in snapshot.orders
        ),
    )
    monkeypatch.setattr(p.broker, "snapshot", lambda: empty)
    assert not p.reliability.reconcile()
    assert not p.reliability.report["verified"]
    assert not p.broker.snapshot().positions
    p.store.close()


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda s: replace(s, observed_at=1_699_999_990), "SNAPSHOT_STALE"),
        (lambda s: replace(s, orders=s.orders + s.orders), "DUPLICATE_BROKER_ORDER"),
        (
            lambda s: replace(
                s, fills=s.fills + (replace(s.fills[0], price=Decimal("101")),)
            ),
            "CONFLICTING_BROKER_FILL",
        ),
        (
            lambda s: replace(s, orders=(replace(s.orders[0], filled_quantity=5),)),
            "CUMULATIVE_FILL_MISMATCH",
        ),
        (
            lambda s: replace(s, positions={("a", "X"): 8}),
            "UNEXPLAINED_EXTERNAL_POSITION",
        ),
    ],
)
def test_independent_evidence_failures(monkeypatch, mutation, expected):
    p = ready()
    p.risk.submit(intent(p))
    p.ingest(p.broker.execute("one", 4, Decimal("100"), p.clock()))
    broken = mutation(p.broker.snapshot())
    monkeypatch.setattr(p.broker, "snapshot", lambda: broken)
    assert not p.reliability.reconcile()
    assert p.reliability.report["reason"] == expected
    assert p.risk.state == "UNCERTAIN"
    p.store.close()


def test_reordered_missing_and_duplicate_fills_replay_once(monkeypatch):
    p = ready()
    p.risk.submit(intent(p))
    first = p.broker.execute("one", 4, Decimal("100"), p.clock())
    p.clock.now += 1
    second = p.broker.execute("one", 6, Decimal("110"), p.clock())
    snapshot = replace(p.broker.snapshot(), fills=(second, first, first))
    monkeypatch.setattr(p.broker, "snapshot", lambda: snapshot)
    assert p.reliability.reconcile()
    assert p.reliability.reconcile()
    assert p.ledger.quantity("a", "A", "X") == 10
    assert p.ledger.positions()[("a", "A", "X")].average_price == Decimal("106")
    assert p.reliability.report["duplicate_snapshot_fills"] == 1
    p.store.close()


def test_stale_feed_and_broker_evidence_block_exposure():
    p = ready()
    p.clock.now += 16
    p.reliability.resume()
    assert p.risk.submit(intent(p)).reason_code == "RISK_STALE_MARKET_DATA"
    assert not p.strategies.enabled
    p.tick(Tick("X", int(p.clock()), Decimal("100"), 0, "fresh-again"))
    p.reliability.resume()
    p.clock.now += 6
    assert p.risk.submit(intent(p, "two")).reason_code == "RISK_STALE_BROKER_STATE"
    p.store.close()


def test_old_live_event_does_not_become_fresh_by_arriving_now():
    p = ready()
    p.clock.now += 20
    p.tick(Tick("X", int(p.clock()) - 19, Decimal("100"), 0, "late-feed"))
    p.reliability.resume()
    assert p.risk.submit(intent(p)).reason_code == "RISK_STALE_MARKET_DATA"
    p.store.close()


def test_unrealized_loss_and_kill_latch_survive_restart(tmp_path):
    path = str(tmp_path / "state.db")
    p = ready(path)
    p.risk.submit(intent(p))
    p.ingest(p.broker.execute("one", 10, Decimal("100"), p.clock()))
    p.tick(Tick("X", int(p.clock()), Decimal("90"), 0, "loss-mark"))
    assert p.ledger.daily_net("a", "A", p.clock()) == Decimal("-100")
    assert p.kill().status == "SUCCESS"
    certificate = p.reliability.certificate
    p.store.close()
    restarted = Platform(path, clock=Clock())
    assert restarted.reliability.certificate == certificate
    assert restarted.reliability.kill_latched
    assert restarted.risk.state == "RECOVERING"
    with pytest.raises(ValueError, match="latched"):
        restarted.reliability.resume()
    restarted.reliability.reset_kill()
    assert restarted.risk.state == "STOPPED"
    restarted.reliability.resume()
    restarted.store.close()


def test_reset_refuses_residual_positions():
    p = ready()
    p.risk.submit(intent(p))
    p.ingest(p.broker.execute("one", 4, Decimal("100"), p.clock()))
    p.reliability.kill(flatten_executor=None)
    with pytest.raises(ValueError, match="requires verified"):
        p.reliability.reset_kill()
    assert p.reliability.kill_latched
    p.store.close()


def test_reduce_only_cannot_reverse_or_offset_pending_orders():
    p = ready()
    p.risk.submit(intent(p))
    p.ingest(p.broker.execute("one", 10, Decimal("100"), p.clock()))
    p.reliability.resume(reduce_only=True)
    assert p.risk.submit(intent(p, "increase", 1)).reason_code == "RISK_NOT_REDUCING"
    assert (
        p.risk.submit(intent(p, "reverse", 11, Side.SELL)).reason_code
        == "RISK_NOT_REDUCING"
    )
    assert p.risk.submit(intent(p, "exit", 5, Side.SELL)).allowed
    assert (
        p.risk.submit(intent(p, "competing-exit", 5, Side.SELL)).reason_code
        == "RISK_NOT_REDUCING"
    )
    p.store.close()

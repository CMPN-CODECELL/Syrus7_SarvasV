from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.broker.adapters import MockBrokerAdapter
from backend.market_data.candles import CandleBuilder
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, RiskPolicy, Side, Tick


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def p():
    engine = Platform(clock=Clock())
    engine.account("a")
    for name, kind in (("A", "momentum"), ("B", "mean_reversion"), ("C", "breakout")):
        engine.strategies.subscribe("a", name, kind, "X")
    engine.tick(Tick("X", int(engine.clock()), D("100"), 0, "fresh-mark"))
    engine.reliability.resume()
    yield engine
    engine.store.close()


def intent(p, key, quantity, strategy="A", side=Side.BUY):
    return OrderIntent(key, strategy, "a", "X", side, quantity, p.clock())


def fill(p, key, quantity, price="100", charges="0"):
    f = p.broker.execute(key, quantity, D(price), p.clock(), D(charges))
    p.ingest(f)
    return f


def test_partial_fill(p):
    assert p.risk.submit(intent(p, "one", 100)).allowed
    fill(p, "one", 40)
    assert p.ledger.quantity("a", "A", "X") == 40
    assert p.store.rows("SELECT status FROM orders")[0][0] == "PARTIALLY_FILLED"


def test_opposing_strategies(p):
    for key, strategy, qty, side in (
        ("1", "A", 100, Side.BUY),
        ("2", "B", 60, Side.SELL),
        ("3", "C", 20, Side.BUY),
    ):
        assert p.risk.submit(intent(p, key, qty, strategy, side)).allowed
        fill(p, key, qty)
    assert [p.ledger.quantity("a", s, "X") for s in "ABC"] == [100, -60, 20]
    assert p.broker.snapshot().positions == {("a", "X"): 60}
    assert p.reliability.reconcile()


def test_pending_exposure(p):
    p.risk.submit(intent(p, "80", 80))
    fill(p, "80", 80)
    p.risk.submit(intent(p, "20", 20))
    assert p.risk.submit(intent(p, "10", 10)).reason_code == "RISK_MAX_POSITION"


def test_duplicate_fill(p):
    p.risk.submit(intent(p, "one", 100))
    f = fill(p, "one", 40)
    assert not p.ingest(f)
    assert p.ledger.quantity("a", "A", "X") == 40
    with pytest.raises(ValueError, match="conflicting"):
        p.ingest(replace(f, price=D("101")))
    assert p.risk.state == "UNCERTAIN"


def test_drift_blocks(p):
    p.risk.submit(intent(p, "one", 60))
    fill(p, "one", 60)
    p.broker.external_positions[("a", "X")] = 20
    assert not p.reliability.reconcile()
    assert p.reliability.health == "DRIFTED"
    assert not p.risk.submit(intent(p, "blocked", 1)).allowed


def test_kill_during_partial_fill(p):
    p.risk.submit(intent(p, "one", 100))
    fill(p, "one", 40)
    certificate = p.kill()
    assert certificate.status == "SUCCESS"
    assert not p.broker.snapshot().positions
    assert p.ledger.quantity("a", "A", "X") == 0
    events = [r[0] for r in p.store.rows("SELECT type FROM audit ORDER BY sequence")]
    assert events.index("KILL_GATE_CLOSED") < events.index("EMERGENCY_AUTHORIZED")
    assert not p.risk.submit(intent(p, "after", 1)).allowed
    with pytest.raises(ValueError, match="latched"):
        p.reliability.resume()


def test_restart_loads_and_reconciles(tmp_path):
    path = str(tmp_path / "state.db")
    old = Platform(path, clock=Clock())
    old.account("a")
    old.strategies.subscribe("a", "A", "momentum", "X")
    old.tick(Tick("X", int(old.clock()), D("100"), 0, "fresh-mark"))
    old.reliability.resume()
    old.risk.submit(intent(old, "one", 100))
    old.ingest(old.broker.execute("one", 40, D("100"), old.clock(), D("0.5")))
    broker = old.broker
    old.store.close()
    new = Platform(path, broker, Clock())
    assert new.risk.state == "RECOVERING"
    assert new.ledger.quantity("a", "A", "X") == 40
    assert not new.risk.submit(intent(new, "blocked", 1)).allowed
    assert new.reliability.reconcile()
    assert new.risk.state == "STOPPED"
    new.reliability.resume()
    assert new.risk.state == "RUNNING"
    assert new.ledger.positions()[("a", "A", "X")].charges == D("0.5")
    new.store.close()


def test_fresh_mock_after_restart_cannot_fake_recovery(tmp_path):
    path = str(tmp_path / "state.db")
    old = Platform(path, clock=Clock())
    old.account("a")
    old.strategies.subscribe("a", "A", "momentum", "X")
    old.tick(Tick("X", int(old.clock()), D("100"), 0, "fresh-mark"))
    old.reliability.resume()
    old.risk.submit(intent(old, "one", 1))
    old.store.close()
    new = Platform(path, broker=MockBrokerAdapter())
    assert not new.reliability.reconcile()
    new.store.close()


def test_concurrent_reservations(p):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda key: p.risk.submit(intent(p, key, 60)), ["one", "two"])
        )
    assert sum(d.allowed for d in results) == 1


def test_opposing_pending_does_not_offset(p):
    p.risk.submit(intent(p, "buy", 100))
    p.risk.submit(intent(p, "sell", 100, side=Side.SELL))
    assert not p.risk.submit(intent(p, "extra", 1)).allowed


def test_ambiguous_timeout_reconciles_without_retry(p):
    p.broker.timeout_after_accept = True
    p.risk.submit(intent(p, "one", 100))
    assert p.risk.state == "UNCERTAIN"
    assert p.store.rows("SELECT status FROM orders")[0][0] == "UNKNOWN"
    assert p.reliability.reconcile()
    assert len(p.broker.orders) == 1
    assert p.store.rows("SELECT status FROM orders")[0][0] == "OPEN"


def test_missing_fill_recovery(p):
    p.risk.submit(intent(p, "one", 100))
    p.broker.execute("one", 40, D("100"), p.clock())
    assert p.ledger.quantity("a", "A", "X") == 0
    assert p.reliability.reconcile()
    assert p.ledger.quantity("a", "A", "X") == 40
    assert p.reliability.reconcile()
    assert len(p.store.rows("SELECT * FROM fills")) == 1


def test_rate_limit_and_boundary(p):
    p.risk.policies["A"] = RiskPolicy(max_orders_per_minute=1)
    p.risk.submit(intent(p, "one", 1))
    assert p.risk.submit(intent(p, "two", 1)).reason_code == "RISK_RATE_LIMIT"
    p.clock.now += 60
    p.tick(Tick("X", int(p.clock()), D("100"), 0, "fresh-rate-mark"))
    p.reliability.resume()
    assert p.risk.submit(intent(p, "three", 1)).allowed


def test_daily_loss_and_charges(p):
    p.risk.policies["A"] = RiskPolicy(max_daily_loss=D("5"))
    p.risk.submit(intent(p, "buy", 1))
    fill(p, "buy", 1, "100", "1")
    p.ledger.marks["X"] = D("95")
    assert p.risk.submit(intent(p, "blocked", 1)).reason_code == "RISK_MAX_DAILY_LOSS"


def test_long_short_reversal_accounting(p):
    for key, qty, side, price, charges in (
        ("buy", 10, Side.BUY, "100", "1"),
        ("sell", 15, Side.SELL, "110", "2"),
    ):
        p.risk.submit(intent(p, key, qty, side=side))
        fill(p, key, qty, price, charges)
    p.ledger.marks["X"] = D("105")
    pos = p.ledger.positions()[("a", "A", "X")]
    assert (
        pos.net_quantity,
        pos.average_price,
        pos.realized_pnl,
        pos.unrealized_pnl,
        pos.net_pnl,
    ) == (-5, D("110"), D("100"), D("25"), D("122"))


def test_rejection_releases_reservation(p):
    p.broker.reject_next = True
    p.risk.submit(intent(p, "rejected", 100))
    assert p.ledger.quantity("a", "A", "X") == 0
    assert p.risk.submit(intent(p, "next", 100)).allowed


def test_disconnect_kill_never_success(p):
    p.broker.connected = False
    assert p.kill().status == "FAILED"
    assert p.risk.state == "UNCERTAIN"


def test_opposing_virtual_positions_kill(p):
    for key, strategy, side in (("buy", "A", Side.BUY), ("sell", "B", Side.SELL)):
        p.risk.submit(intent(p, key, 10, strategy, side))
        fill(p, key, 10)
    assert not p.broker.snapshot().positions
    assert p.kill().status == "SUCCESS"
    assert all(pos.net_quantity == 0 for pos in p.ledger.positions().values())


def test_candles_boundary_duplicate_late():
    b = CandleBuilder()
    ticks = [
        Tick("X", t, D(price), qty, str(t))
        for t, price, qty in [
            (0, "100", 2),
            (59, "102", 3),
            (60, "101", 4),
            (300, "103", 1),
        ]
    ]
    assert b.ingest(ticks[0]) == []
    assert b.ingest(ticks[0]) == []
    b.ingest(ticks[1])
    first = b.ingest(ticks[2])[0]
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        D("100"),
        D("102"),
        D("100"),
        D("102"),
        5,
    )
    five = next(c for c in b.ingest(ticks[3]) if c.interval == 300)
    assert (five.start_time, five.end_time, five.volume) == (0, 300, 9)
    with pytest.raises(ValueError, match="late"):
        b.ingest(Tick("X", 299, D("100"), 1, "late"))


def test_api_vertical_slice():
    p = Platform()
    with TestClient(create_app(p)) as client:
        assert client.get("/health").json()["trading"] == "RECOVERING"
        assert client.get("/").status_code == 200
        response = client.post("/api/demo")
        assert response.status_code == 200
        state = response.json()
        assert len(state["subscriptions"]) == 3
        assert {f["strategy"] for f in state["fills"]} == {
            "momentum",
            "mean_reversion",
            "breakout",
        }
        assert {c["interval"] for c in state["candles"]} == {60, 300}
        assert state["health"] == "HEALTHY"
        assert client.post("/api/kill").json()["status"] == "SUCCESS"
    p.store.close()

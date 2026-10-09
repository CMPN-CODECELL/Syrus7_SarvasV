from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backend.market_data.session import MarketSession
from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side


class Clock:
    def __init__(self, initial_time: float = 1_700_000_000.0):
        self.now = initial_time

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


def test_market_session_ist_conversion_and_boundaries():
    """
    Continuous trading hours: 09:15:00 to 15:30:00 Asia/Kolkata.
    Boundary is half-open: [09:15:00, 15:30:00).
    At 09:15:00 IST -> OPEN.
    At 15:30:00 IST -> CLOSED.
    """
    session = MarketSession(enforce_hours=True)
    ist = ZoneInfo("Asia/Kolkata")

    # Day 2026-04-10
    # 09:14:59 IST (before open)
    dt_before = datetime(2026, 4, 10, 9, 14, 59, tzinfo=ist)
    ts_before = dt_before.timestamp()
    assert not session.is_open(ts_before)
    assert session.status_at(ts_before) == "CLOSED"

    # 09:15:00 IST (exact open boundary)
    dt_open = datetime(2026, 4, 10, 9, 15, 0, tzinfo=ist)
    ts_open = dt_open.timestamp()
    assert session.is_open(ts_open)
    assert session.status_at(ts_open) == "OPEN"

    # 12:30:00 IST (mid-session)
    dt_mid = datetime(2026, 4, 10, 12, 30, 0, tzinfo=ist)
    ts_mid = dt_mid.timestamp()
    assert session.is_open(ts_mid)
    assert session.status_at(ts_mid) == "OPEN"

    # 15:29:59 IST (last open second)
    dt_last = datetime(2026, 4, 10, 15, 29, 59, tzinfo=ist)
    ts_last = dt_last.timestamp()
    assert session.is_open(ts_last)
    assert session.status_at(ts_last) == "OPEN"

    # 15:30:00 IST (exact close boundary -> closed)
    dt_close = datetime(2026, 4, 10, 15, 30, 0, tzinfo=ist)
    ts_close = dt_close.timestamp()
    assert not session.is_open(ts_close)
    assert session.status_at(ts_close) == "CLOSED"

    # 15:30:01 IST (after close)
    dt_after = datetime(2026, 4, 10, 15, 30, 1, tzinfo=ist)
    ts_after = dt_after.timestamp()
    assert not session.is_open(ts_after)
    assert session.status_at(ts_after) == "CLOSED"


def test_market_session_utc_date_boundary_crossing():
    """
    Verify UTC timestamps crossing midnight or differing calendar dates are converted correctly.
    Asia/Kolkata is UTC+05:30.
    For 2026-04-10:
    03:45:00 UTC = 09:15:00 IST (OPEN)
    10:00:00 UTC = 15:30:00 IST (CLOSED)
    23:45:00 UTC on 2026-04-09 = 05:15:00 IST on 2026-04-10 (CLOSED, morning before open)
    18:30:00 UTC on 2026-04-09 = 00:00:00 IST on 2026-04-10 (CLOSED, midnight)
    """
    session = MarketSession(enforce_hours=True)

    # 03:45:00 UTC -> 09:15:00 IST
    dt_utc_open = datetime(2026, 4, 10, 3, 45, 0, tzinfo=timezone.utc)
    assert session.is_open(dt_utc_open.timestamp())
    assert session.status_at(dt_utc_open.timestamp()) == "OPEN"

    # 03:44:59 UTC -> 09:14:59 IST
    dt_utc_before = datetime(2026, 4, 10, 3, 44, 59, tzinfo=timezone.utc)
    assert not session.is_open(dt_utc_before.timestamp())
    assert session.status_at(dt_utc_before.timestamp()) == "CLOSED"

    # 10:00:00 UTC -> 15:30:00 IST
    dt_utc_close = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    assert not session.is_open(dt_utc_close.timestamp())
    assert session.status_at(dt_utc_close.timestamp()) == "CLOSED"

    # Previous UTC date: 2026-04-09 23:45:00 UTC -> 2026-04-10 05:15:00 IST
    dt_prev_utc = datetime(2026, 4, 9, 23, 45, 0, tzinfo=timezone.utc)
    assert not session.is_open(dt_prev_utc.timestamp())
    assert session.status_at(dt_prev_utc.timestamp()) == "CLOSED"


def test_market_session_missing_timestamp_fails_closed_when_enforced():
    """
    When hours are enforced, a missing timestamp (None) and no clock must fail closed (False / CLOSED).
    When hours are unenforced (mock replay default), missing timestamp remains open.
    """
    # Enforced session without clock
    session_enforced = MarketSession(enforce_hours=True, clock=None)
    assert not session_enforced.is_open(None)
    assert session_enforced.status_at(None) == "CLOSED"
    snap_enforced = session_enforced.to_dict(None)
    assert snap_enforced["status"] == "CLOSED"
    assert snap_enforced["is_open"] is False

    # Unenforced session (default)
    session_default = MarketSession(enforce_hours=False)
    assert session_default.is_open(None)
    assert session_default.status_at(None) == "OPEN"
    snap_default = session_default.to_dict(None)
    assert snap_default["status"] == "OPEN"
    assert snap_default["is_open"] is True


def test_market_session_clock_fallback():
    """
    When timestamp is None, session falls back to its injected clock if available.
    """
    ist = ZoneInfo("Asia/Kolkata")
    dt_open = datetime(2026, 4, 10, 11, 0, 0, tzinfo=ist)
    clock = Clock(initial_time=dt_open.timestamp())

    session = MarketSession(enforce_hours=True, clock=clock)
    assert session.is_open(None)
    assert session.status_at(None) == "OPEN"

    # Advance clock to after close
    dt_closed = datetime(2026, 4, 10, 16, 0, 0, tzinfo=ist)
    clock.advance(dt_closed.timestamp() - dt_open.timestamp())
    assert not session.is_open(None)
    assert session.status_at(None) == "CLOSED"


def test_market_session_halt_and_manual_overrides_consistency():
    """
    Consistency between is_open(), status_at(), to_dict() and risk checks.
    HALTED takes precedence over manual OPEN.
    Manual CLOSED forces closed even during market hours.
    Manual OPEN cannot bypass enforced live market hours.
    AUTO reverts to schedule.
    """
    ist = ZoneInfo("Asia/Kolkata")
    dt_open = datetime(2026, 4, 10, 11, 0, 0, tzinfo=ist)
    ts_open = dt_open.timestamp()

    dt_closed = datetime(2026, 4, 10, 18, 0, 0, tzinfo=ist)
    ts_closed = dt_closed.timestamp()

    session = MarketSession(enforce_hours=True)

    # 1. During open hours, normal AUTO
    assert session.is_open(ts_open)
    assert session.status_at(ts_open) == "OPEN"
    assert session.to_dict(ts_open)["status"] == "OPEN"

    # 2. Halt while open
    session.halt("Exchange circuit breaker")
    assert not session.is_open(ts_open)
    assert session.status_at(ts_open) == "HALTED"
    snap = session.to_dict(ts_open)
    assert snap["is_open"] is False
    assert snap["status"] == "HALTED"
    assert snap["halt_reason"] == "Exchange circuit breaker"

    # 3. Resume from halt -> back to AUTO
    session.resume()
    assert session.is_open(ts_open)
    assert session.status_at(ts_open) == "OPEN"

    # 4. Manual CLOSED during open hours
    session.set_status("CLOSED")
    assert not session.is_open(ts_open)
    assert session.status_at(ts_open) == "CLOSED"
    assert session.to_dict(ts_open)["status"] == "CLOSED"

    # 5. Halt while manual CLOSED
    session.halt("Emergency halt")
    assert session.status_at(ts_open) == "HALTED"
    session.resume()
    assert session.status_at(ts_open) == "CLOSED"  # returns to manual CLOSED

    # 6. Manual OPEN outside live market hours remains closed
    session.set_status("OPEN")
    assert not session.is_open(ts_closed)
    assert session.status_at(ts_closed) == "CLOSED"
    assert session.to_dict(ts_closed)["status"] == "CLOSED"

    # 7. Halt overrides manual OPEN outside market hours
    session.halt("Maintenance halt")
    assert not session.is_open(ts_closed)
    assert session.status_at(ts_closed) == "HALTED"
    session.resume()
    assert not session.is_open(ts_closed)

    # 8. Reset to AUTO
    session.set_status("AUTO")
    assert not session.is_open(ts_closed)
    assert session.status_at(ts_closed) == "CLOSED"


def test_reliability_risk_evidence_integration_with_market_session(tmp_path):
    """
    Reliability.check_evidence verifies HALTED -> RISK_MARKET_HALTED
    and session closed -> RISK_MARKET_CLOSED.
    """
    ist = ZoneInfo("Asia/Kolkata")
    dt_closed = datetime(2026, 4, 10, 18, 0, 0, tzinfo=ist)
    clock = Clock(initial_time=dt_closed.timestamp())

    platform = Platform(path=str(tmp_path / "test.db"), clock=clock)
    platform.market_session.enforce_hours = True
    session = platform.market_session
    reliability = platform.reliability
    reliability.reconcile()
    reliability.last_broker_at = clock()

    intent = OrderIntent(
        intent_id="intent_1",
        strategy_instance_id="strat_1",
        account_id="client_1",
        symbol="RELIANCE",
        side=Side.BUY,
        quantity=10,
        created_at=clock(),
    )

    # Outside market hours -> RISK_MARKET_CLOSED
    res = reliability.check_evidence(intent)
    assert res == "RISK_MARKET_CLOSED"

    # Halt during closed hours -> RISK_MARKET_HALTED has precedence
    session.halt("Market halted")
    res_halt = reliability.check_evidence(intent)
    assert res_halt == "RISK_MARKET_HALTED"

    # Resume, set manual OPEN: enforced live hours still remain closed.
    session.resume()
    session.set_status("OPEN")
    # Need broker mark so it doesn't fail on market data
    with platform.store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO risk_marks (symbol, price, event_timestamp, received_at, source) VALUES (?, ?, ?, ?, ?)",
            ("RELIANCE", "100.0", int(clock()), clock(), "REPLAY"),
        )
    platform.reliability.last_broker_at = clock()
    res_open = reliability.check_evidence(intent)
    assert res_open == "RISK_MARKET_CLOSED"

    # Explicit offline replay preserves the historical operator OPEN behavior.
    platform.market_session.enforce_hours = False
    assert reliability.check_evidence(intent) == ""


def test_kill_certificate_elapsed_time_and_exhausted_deadline(tmp_path):
    """
    Task 4 follow-up 2 verification:
    1. Exhausted budget returns a truthful failure certificate (KILL_DEADLINE_EXPIRED),
       not an unhandled ValueError from Deadline.
    2. Kill certificate elapsed time includes replay join and admission closure.
    """
    clock = Clock(initial_time=1000.0)
    platform = Platform(path=str(tmp_path / "test.db"), clock=clock)

    # Test 1: deadline_seconds <= 0 passed directly returns truthful FAILED certificate
    cert = platform.kill(deadline_seconds=0.0)
    assert cert.status == "FAILED"
    assert cert.reason == "KILL_DEADLINE_EXPIRED"
    assert cert.elapsed_seconds >= 0.0

    # Test 2: Negative deadline
    cert_neg = platform.kill(deadline_seconds=-1.0)
    assert cert_neg.status == "FAILED"
    assert cert_neg.reason == "KILL_DEADLINE_EXPIRED"

    # Test 3: Normal kill with valid deadline succeeds and measures elapsed time accurately
    cert_valid = platform.kill(deadline_seconds=5.0)
    assert cert_valid.status == "SUCCESS"
    assert cert_valid.elapsed_seconds >= 0.0

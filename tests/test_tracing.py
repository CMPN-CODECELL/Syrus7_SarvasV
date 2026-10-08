from decimal import Decimal

import pytest

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick


def test_order_trace_is_durable_ordered_and_account_scoped():
    platform = Platform(clock=lambda: 1_700_000_000)
    platform.account("a")
    platform.strategies.subscribe("a", "s", "momentum", "X")
    platform.tick(Tick("X", 1_700_000_000, Decimal("100"), 0, "mark"))
    platform.reliability.resume()
    platform.risk.submit(
        OrderIntent("trace-1", "s", "a", "X", Side.BUY, 2, platform.clock())
    )
    platform.ingest(
        platform.broker.execute("trace-1", 2, Decimal("100"), platform.clock())
    )
    trace = platform.traces.trace("trace-1", "a")
    assert [event["sequence"] for event in trace["events"]] == sorted(
        event["sequence"] for event in trace["events"]
    )
    assert {event["type"] for event in trace["events"]} >= {
        "RISK_DECISION",
        "ORDER_SUBMITTED",
        "ORDER_STATUS_CHANGED",
    }
    with pytest.raises(PermissionError):
        platform.traces.trace("trace-1", "other")
    platform.close()

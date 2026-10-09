from datetime import datetime
from decimal import Decimal
import struct
from zoneinfo import ZoneInfo

import pytest

from backend.broker.official021 import (
    Instrument021,
    Provider021ProtocolError,
    Provider021WriteUncertain,
    classify_http_error,
    encode_order_payload,
    parse_market_frame,
    parse_order_frame,
)
from backend.shared.contracts import Side
from backend.shared.store import Store
from backend.strategies.official021 import (
    OpenBreakoutStrategy,
    StrategyContext,
    Time0915Strategy,
)

IST = ZoneInfo("Asia/Kolkata")


def epoch(day, hh, mm):
    return datetime(2026, 10, day, hh, mm, tzinfo=IST).timestamp()


def context(now, **changes):
    values = dict(
        strategy_instance_id="s",
        account_id="a",
        symbol="RELIANCE",
        now=now,
        feed_fresh=True,
        broker_evidence_fresh=True,
        gate_running=True,
        session_open=True,
    )
    values.update(changes)
    return StrategyContext(**values)


def test_order_encoding_uses_signed_quantity_paise_and_validates_tick():
    inst = Instrument021(1, 2885, "RELIANCE", tick_size_paise=5)
    assert encode_order_payload(
        instrument=inst,
        side=Side.SELL,
        quantity=2,
        order_type="LIMIT",
        limit_price=Decimal("10.05"),
    ) == {
        "exchange": 1,
        "token": 2885,
        "product": "INTRADAY",
        "quantity": -2,
        "orderType": "LIMIT",
        "price": 1005,
    }
    with pytest.raises(ValueError, match="tick size"):
        encode_order_payload(
            instrument=inst,
            side=Side.BUY,
            quantity=1,
            order_type="LIMIT",
            limit_price=Decimal("10.01"),
        )
    assert classify_http_error(503, write=True) is Provider021WriteUncertain


def test_tc1_ltpo_and_strict_unknown_or_truncated_frames():
    parsed = parse_market_frame(struct.pack(">HHIIcI", 1, 1, 2885, 12345, b"o", 12000))
    assert parsed.ltp == Decimal("123.45")
    assert parsed.official_open == Decimal("120")
    with pytest.raises(Provider021ProtocolError):
        parse_market_frame(b"\x00\x01")
    with pytest.raises(Provider021ProtocolError):
        parse_market_frame(struct.pack(">H", 99))


def test_tc3_offsets_and_order_trade_event_remain_unidentified():
    frame = bytearray(220)
    struct.pack_into(">HHI", frame, 0, 3, 1, 2885)
    struct.pack_into(">I", frame, 8, 10100)
    struct.pack_into(">I", frame, 12, 3)
    struct.pack_into(">I", frame, 20, 99)
    struct.pack_into(">I", frame, 48, 10000)
    struct.pack_into(">I", frame, 216, 10)
    observation = parse_market_frame(bytes(frame))
    assert observation.official_open == Decimal("100")
    assert observation.exchange_timestamp == 315513010

    order = bytearray(46)
    struct.pack_into(">HH", order, 0, 4, 1)
    order[4:14] = b"UCC123    "
    order[14:34] = b"RELIANCE            "
    struct.pack_into(">IiI", order, 34, 42, 1, 10100)
    event = parse_order_frame(bytes(order))
    assert event.order_id == "42"
    assert event.is_trade_without_identity is True


def test_time_strategy_persists_once_per_session_and_bounds_exit():
    store = Store()
    store.db.execute("INSERT INTO accounts VALUES ('a')")
    store.db.execute(
        "INSERT INTO subscriptions VALUES ('s','a','time_0915_1515','RELIANCE',1)"
    )
    strategy = Time0915Strategy(store)
    now = epoch(9, 9, 15)
    first = strategy.evaluate_entry(context(now))
    assert first is not None and first.side == Side.BUY
    assert strategy.evaluate_entry(context(now)) is None
    assert Time0915Strategy(store).evaluate_entry(context(now)) is None
    assert strategy.evaluate_entry(context(epoch(10, 9, 16))) is None
    assert (
        strategy.evaluate_exit(
            context(epoch(9, 15, 15)),
            residual_quantity=2,
            attributed_side=Side.BUY,
            account_square_off_quantity=1,
        )
        is None
    )
    exit_intent = strategy.evaluate_exit(
        context(epoch(9, 15, 15)),
        residual_quantity=2,
        attributed_side=Side.BUY,
        account_square_off_quantity=2,
    )
    assert exit_intent.side == Side.SELL and exit_intent.quantity == 2


def test_breakout_requires_official_open_and_fill_wap_for_residual_exit():
    store = Store()
    strategy = OpenBreakoutStrategy(store)
    now = epoch(9, 10, 0)
    assert (
        strategy.evaluate_entry(context(now), ltp=Decimal("101"), official_open=None)
        is None
    )
    entry = strategy.evaluate_entry(
        context(now), ltp=Decimal("101"), official_open=Decimal("100")
    )
    assert entry is not None
    assert (
        strategy.evaluate_entry(
            context(now), ltp=Decimal("102"), official_open=Decimal("100")
        )
        is None
    )
    assert (
        strategy.evaluate_exit(
            context(now),
            ltp=Decimal("105"),
            fill_wap=None,
            residual_quantity=1,
            attributed_side=Side.BUY,
            entry_order_open=False,
        )
        is None
    )
    exit_intent = strategy.evaluate_exit(
        context(now),
        ltp=Decimal("105"),
        fill_wap=Decimal("100"),
        residual_quantity=1,
        attributed_side=Side.BUY,
        entry_order_open=False,
    )
    assert exit_intent.side == Side.SELL
    assert (
        strategy.evaluate_exit(
            context(now),
            ltp=Decimal("94"),
            fill_wap=Decimal("100"),
            residual_quantity=1,
            attributed_side=Side.BUY,
            entry_order_open=False,
        )
        is None
    )

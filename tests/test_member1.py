from decimal import Decimal
import pytest

from backend.accounting.ledger import Ledger
from backend.platform import Platform
from backend.shared.contracts import Fill, OrderIntent, Side, StrategyPosition, Tick
from backend.shared.store import Store


class MockClock:
    def __init__(self, start=1_700_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def ledger(store):
    return Ledger(store)


def make_fill(
    fill_id: str = "f1",
    broker_order_id: str = "ord1",
    strategy_instance_id: str = "stratA",
    account_id: str = "acc1",
    symbol: str = "RELIANCE",
    side: Side = Side.BUY,
    quantity: int = 10,
    price: str = "100.00",
    timestamp: float = 1_700_000_000.0,
    charges: str = "0.01",
) -> Fill:
    return Fill(
        fill_id=fill_id,
        broker_order_id=broker_order_id,
        strategy_instance_id=strategy_instance_id,
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=Decimal(price),
        timestamp=timestamp,
        charges=Decimal(charges),
    )


def test_isolated_ledger_empty(ledger):
    assert ledger.positions() == {}
    assert ledger.quantity("acc1", "stratA", "RELIANCE") == 0
    assert ledger.aggregate() == {}
    assert ledger.daily_net("acc1", "stratA", 1_700_000_000.0) == Decimal(0)


def test_isolated_ledger_single_buy_fill(ledger):
    f = make_fill(quantity=50, price="100.00", charges="0.50")
    assert ledger.apply(f) is True
    ledger.marks["RELIANCE"] = Decimal("105.00")

    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos.strategy_instance_id == "stratA"
    assert pos.symbol == "RELIANCE"
    assert pos.net_quantity == 50
    assert pos.average_price == Decimal("100.00")
    assert pos.realized_pnl == Decimal("0")
    assert pos.unrealized_pnl == Decimal("250.00")  # 50 * (105 - 100)
    assert pos.gross_pnl == Decimal("250.00")  # realized + unrealized
    assert pos.charges == Decimal("0.50")
    assert pos.net_pnl == Decimal("249.50")  # gross_pnl - charges
    assert ledger.quantity("acc1", "stratA", "RELIANCE") == 50


def test_isolated_ledger_single_sell_fill_short(ledger):
    f = make_fill(side=Side.SELL, quantity=40, price="200.00", charges="1.00")
    assert ledger.apply(f) is True
    ledger.marks["RELIANCE"] = Decimal("190.00")

    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos.net_quantity == -40
    assert pos.average_price == Decimal("200.00")
    assert pos.realized_pnl == Decimal("0")
    assert pos.unrealized_pnl == Decimal("400.00")  # -40 * (190 - 200) = +400
    assert pos.gross_pnl == Decimal("400.00")
    assert pos.charges == Decimal("1.00")
    assert pos.net_pnl == Decimal("399.00")


def test_partial_fills_and_weighted_average_entry(ledger):
    # Buy 30 @ 100, then Buy 20 @ 110, then Buy 50 @ 104
    # Total qty: 100
    # Expected avg: (30*100 + 20*110 + 50*104) / 100 = (3000 + 2200 + 5200) / 100 = 104
    assert ledger.apply(
        make_fill(fill_id="f1", quantity=30, price="100.00", charges="0.10")
    )
    assert ledger.apply(
        make_fill(fill_id="f2", quantity=20, price="110.00", charges="0.10")
    )
    assert ledger.apply(
        make_fill(fill_id="f3", quantity=50, price="104.00", charges="0.20")
    )

    ledger.marks["RELIANCE"] = Decimal("114.00")
    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]

    assert pos.net_quantity == 100
    assert pos.average_price == Decimal("104.00")
    assert pos.realized_pnl == Decimal("0")
    assert pos.unrealized_pnl == Decimal("1000.00")  # 100 * (114 - 104)
    assert pos.gross_pnl == Decimal("1000.00")
    assert pos.charges == Decimal("0.40")
    assert pos.net_pnl == Decimal("999.60")


def test_partial_and_full_closing_trades(ledger):
    # Buy 100 @ 100
    assert ledger.apply(
        make_fill(
            fill_id="f1", side=Side.BUY, quantity=100, price="100.00", charges="0.10"
        )
    )

    # Partial exit: Sell 40 @ 120 -> Realized P&L = 40 * (120 - 100) = 800
    assert ledger.apply(
        make_fill(
            fill_id="f2", side=Side.SELL, quantity=40, price="120.00", charges="0.10"
        )
    )
    ledger.marks["RELIANCE"] = Decimal("125.00")
    pos1 = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos1.net_quantity == 60
    assert pos1.average_price == Decimal("100.00")
    assert pos1.realized_pnl == Decimal("800.00")
    assert pos1.unrealized_pnl == Decimal("1500.00")  # 60 * (125 - 100)
    assert pos1.gross_pnl == Decimal("2300.00")
    assert pos1.charges == Decimal("0.20")
    assert pos1.net_pnl == Decimal("2299.80")

    # Full exit: Sell remaining 60 @ 115 -> Realized P&L = 800 + 60 * (115 - 100) = 800 + 900 = 1700
    assert ledger.apply(
        make_fill(
            fill_id="f3", side=Side.SELL, quantity=60, price="115.00", charges="0.10"
        )
    )
    pos2 = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos2.net_quantity == 0
    assert pos2.average_price == Decimal("0")
    assert pos2.realized_pnl == Decimal("1700.00")
    assert pos2.unrealized_pnl == Decimal("0")
    assert pos2.gross_pnl == Decimal("1700.00")
    assert pos2.charges == Decimal("0.30")
    assert pos2.net_pnl == Decimal("1699.70")


def test_position_reversal_long_to_short(ledger):
    # Buy 10 @ 100
    assert ledger.apply(
        make_fill(
            fill_id="f1", side=Side.BUY, quantity=10, price="100.00", charges="0.10"
        )
    )

    # Sell 25 @ 120 (reversal: closes 10 long, opens 15 short @ 120)
    assert ledger.apply(
        make_fill(
            fill_id="f2", side=Side.SELL, quantity=25, price="120.00", charges="0.25"
        )
    )
    ledger.marks["RELIANCE"] = Decimal("110.00")
    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]

    assert pos.net_quantity == -15
    assert pos.average_price == Decimal("120.00")  # New short entry avg
    assert pos.realized_pnl == Decimal("200.00")  # 10 * (120 - 100)
    assert pos.unrealized_pnl == Decimal("150.00")  # -15 * (110 - 120) = +150
    assert pos.gross_pnl == Decimal("350.00")
    assert pos.charges == Decimal("0.35")
    assert pos.net_pnl == Decimal("349.65")

    # Cover 15 @ 105 -> realizes 15 * (120 - 105) = 225
    assert ledger.apply(
        make_fill(
            fill_id="f3", side=Side.BUY, quantity=15, price="105.00", charges="0.15"
        )
    )
    pos_flat = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos_flat.net_quantity == 0
    assert pos_flat.average_price == Decimal("0")
    assert pos_flat.realized_pnl == Decimal("425.00")  # 200 + 225
    assert pos_flat.unrealized_pnl == Decimal("0")
    assert pos_flat.gross_pnl == Decimal("425.00")
    assert pos_flat.charges == Decimal("0.50")
    assert pos_flat.net_pnl == Decimal("424.50")


def test_position_reversal_short_to_long(ledger):
    # Sell 20 @ 150
    assert ledger.apply(
        make_fill(
            fill_id="f1", side=Side.SELL, quantity=20, price="150.00", charges="0.20"
        )
    )

    # Buy 30 @ 140 (closes 20 short, opens 10 long @ 140)
    assert ledger.apply(
        make_fill(
            fill_id="f2", side=Side.BUY, quantity=30, price="140.00", charges="0.30"
        )
    )
    ledger.marks["RELIANCE"] = Decimal("145.00")
    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]

    assert pos.net_quantity == 10
    assert pos.average_price == Decimal("140.00")
    assert pos.realized_pnl == Decimal("200.00")  # 20 * (150 - 140)
    assert pos.unrealized_pnl == Decimal("50.00")  # 10 * (145 - 140)
    assert pos.gross_pnl == Decimal("250.00")
    assert pos.charges == Decimal("0.50")
    assert pos.net_pnl == Decimal("249.50")


def test_duplicate_fill_idempotent(ledger, store):
    f = make_fill(fill_id="f1", quantity=10, price="100.00", charges="0.05")
    assert ledger.apply(f) is True
    # Duplicate exact fill must return False and not double-count
    assert ledger.apply(f) is False

    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos.net_quantity == 10
    assert pos.charges == Decimal("0.05")

    # In database, exactly one row exists
    rows = store.rows("SELECT * FROM fills WHERE id='f1'")
    assert len(rows) == 1

    # Exactly one FILL_APPLIED audit event
    audits = store.rows("SELECT * FROM audit WHERE type='FILL_APPLIED'")
    assert len(audits) == 1
    assert "f1" in audits[0]["payload"]


def test_conflicting_duplicate_fill_raises(ledger):
    f1 = make_fill(fill_id="f1", quantity=10, price="100.00")
    assert ledger.apply(f1) is True

    # Same fill_id but different price must raise ValueError
    f1_conflict = make_fill(fill_id="f1", quantity=10, price="105.00")
    with pytest.raises(ValueError, match="conflicting duplicate fill"):
        ledger.apply(f1_conflict)


def test_invalid_fill_economics_validation(ledger):
    with pytest.raises(ValueError, match="invalid fill quantity/side"):
        make_fill(quantity=0)

    with pytest.raises(ValueError, match="invalid fill quantity/side"):
        make_fill(quantity=-5)

    with pytest.raises(ValueError, match="invalid fill economics"):
        make_fill(price="0")

    with pytest.raises(ValueError, match="invalid fill economics"):
        make_fill(charges="-0.01")


def test_opposite_strategy_positions_independence(ledger):
    # Strategy A: BUY 100 @ 100.00
    # Strategy B: SELL 60 @ 102.00
    # Strategy C: BUY 20 @ 101.00
    # All on same account acc1 and symbol TCS
    assert ledger.apply(
        make_fill(
            fill_id="fA",
            strategy_instance_id="A",
            side=Side.BUY,
            quantity=100,
            price="100.00",
            charges="0.10",
            symbol="TCS",
        )
    )
    assert ledger.apply(
        make_fill(
            fill_id="fB",
            strategy_instance_id="B",
            side=Side.SELL,
            quantity=60,
            price="102.00",
            charges="0.06",
            symbol="TCS",
        )
    )
    assert ledger.apply(
        make_fill(
            fill_id="fC",
            strategy_instance_id="C",
            side=Side.BUY,
            quantity=20,
            price="101.00",
            charges="0.02",
            symbol="TCS",
        )
    )

    ledger.marks["TCS"] = Decimal("105.00")
    positions = ledger.positions()

    posA = positions[("acc1", "A", "TCS")]
    posB = positions[("acc1", "B", "TCS")]
    posC = positions[("acc1", "C", "TCS")]

    # Strategy A
    assert posA.net_quantity == 100
    assert posA.average_price == Decimal("100.00")
    assert posA.unrealized_pnl == Decimal("500.00")  # 100 * (105 - 100)
    assert posA.gross_pnl == Decimal("500.00")
    assert posA.charges == Decimal("0.10")
    assert posA.net_pnl == Decimal("499.90")

    # Strategy B (Short position)
    assert posB.net_quantity == -60
    assert posB.average_price == Decimal("102.00")
    assert posB.unrealized_pnl == Decimal("-180.00")  # -60 * (105 - 102)
    assert posB.gross_pnl == Decimal("-180.00")
    assert posB.charges == Decimal("0.06")
    assert posB.net_pnl == Decimal("-180.06")

    # Strategy C
    assert posC.net_quantity == 20
    assert posC.average_price == Decimal("101.00")
    assert posC.unrealized_pnl == Decimal("80.00")  # 20 * (105 - 101)
    assert posC.gross_pnl == Decimal("80.00")
    assert posC.charges == Decimal("0.02")
    assert posC.net_pnl == Decimal("79.98")

    # Account aggregation: net quantity across strategies = 100 - 60 + 20 = 60
    aggregate = ledger.aggregate()
    assert aggregate[("acc1", "TCS")] == 60

    # Ensure aggregate does not overwrite strategy positions
    assert ledger.quantity("acc1", "A", "TCS") == 100
    assert ledger.quantity("acc1", "B", "TCS") == -60
    assert ledger.quantity("acc1", "C", "TCS") == 20


def test_multi_symbol_multi_account_isolation(ledger):
    ledger.apply(
        make_fill(
            fill_id="f1",
            account_id="acc1",
            strategy_instance_id="s1",
            symbol="INFY",
            quantity=10,
            price="1000",
        )
    )
    ledger.apply(
        make_fill(
            fill_id="f2",
            account_id="acc1",
            strategy_instance_id="s1",
            symbol="WIPRO",
            quantity=25,
            price="400",
        )
    )
    ledger.apply(
        make_fill(
            fill_id="f3",
            account_id="acc2",
            strategy_instance_id="s1",
            symbol="INFY",
            quantity=15,
            price="1005",
        )
    )

    assert ledger.quantity("acc1", "s1", "INFY") == 10
    assert ledger.quantity("acc1", "s1", "WIPRO") == 25
    assert ledger.quantity("acc2", "s1", "INFY") == 15

    agg = ledger.aggregate()
    assert agg[("acc1", "INFY")] == 10
    assert agg[("acc1", "WIPRO")] == 25
    assert agg[("acc2", "INFY")] == 15


def test_charges_accumulation_and_synthetic_demo_charges(ledger):
    # Exact Decimal charges including synthetic demo default (0.01) and custom exact values
    fills = [
        make_fill(
            fill_id="f1", quantity=10, price="100", charges="0.01"
        ),  # synthetic demo default
        make_fill(fill_id="f2", quantity=10, price="100", charges="0.05"),
        make_fill(
            fill_id="f3", quantity=10, price="100", charges="0.123456"
        ),  # sub-cent precision
    ]
    for f in fills:
        ledger.apply(f)

    ledger.marks["RELIANCE"] = Decimal("100")
    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]

    expected_charges = Decimal("0.01") + Decimal("0.05") + Decimal("0.123456")
    assert pos.charges == expected_charges
    assert pos.charges == Decimal("0.183456")
    assert pos.gross_pnl == Decimal("0")
    assert pos.net_pnl == -Decimal("0.183456")


def test_mark_price_updates_unrealized_and_gross_pnl_dynamically(ledger):
    ledger.apply(make_fill(fill_id="f1", quantity=10, price="100", charges="0.10"))

    # Initial mark equal to entry price -> unrealized = 0
    ledger.marks["RELIANCE"] = Decimal("100")
    pos = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos.unrealized_pnl == Decimal("0")
    assert pos.gross_pnl == Decimal("0")
    assert pos.net_pnl == Decimal("-0.10")

    # Mark increases -> unrealized increases
    ledger.marks["RELIANCE"] = Decimal("120")
    pos2 = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos2.unrealized_pnl == Decimal("200")
    assert pos2.gross_pnl == Decimal("200")
    assert pos2.net_pnl == Decimal("199.90")

    # Mark drops below entry -> unrealized negative
    ledger.marks["RELIANCE"] = Decimal("85")
    pos3 = ledger.positions()[("acc1", "stratA", "RELIANCE")]
    assert pos3.unrealized_pnl == Decimal("-150")
    assert pos3.gross_pnl == Decimal("-150")
    assert pos3.net_pnl == Decimal("-150.10")


def test_daily_net_pnl_ist_boundary(ledger):
    # Midnight Asia/Kolkata boundary: UTC timestamp + 19800 // 86400
    # Day 1: timestamp = 1_700_000_000 (corresponds to a specific day)
    t_day1 = 1_700_000_000.0
    # Day 2: 86400 seconds later
    t_day2 = t_day1 + 86400.0

    # Trade on Day 1: Buy 10 @ 100, Sell 10 @ 110 -> realized +100, charges 0.20
    ledger.apply(
        make_fill(
            fill_id="d1_buy", timestamp=t_day1, quantity=10, price="100", charges="0.10"
        )
    )
    ledger.apply(
        make_fill(
            fill_id="d1_sell",
            timestamp=t_day1 + 10,
            side=Side.SELL,
            quantity=10,
            price="110",
            charges="0.10",
        )
    )

    # Day 1 daily net must be: realized(100) - charges(0.20) + unrealized(0) = 99.80
    assert ledger.daily_net("acc1", "stratA", t_day1) == Decimal("99.80")

    # Trade on Day 2: Buy 5 @ 100, charges 0.05
    ledger.apply(
        make_fill(
            fill_id="d2_buy", timestamp=t_day2, quantity=5, price="100", charges="0.05"
        )
    )
    ledger.marks["RELIANCE"] = Decimal("102")

    # Day 2 daily net should only consider session trades + current unrealized:
    # Session realized: 0
    # Session charges: 0.05
    # Current unrealized: 5 * (102 - 100) = 10
    # Day 2 daily net = 0 - 0.05 + 10 = 9.95
    assert ledger.daily_net("acc1", "stratA", t_day2) == Decimal("9.95")


def test_orders_do_not_create_positions_or_pnl():
    clock = MockClock()
    platform = Platform(clock=clock)
    platform.account("acc_test")
    platform.strategies.subscribe("acc_test", "strat_test", "momentum", "TESTSYM")
    platform.tick(Tick("TESTSYM", int(clock()), Decimal("100"), 0, "fresh-mark"))
    platform.reliability.resume()

    # Step 1: Submit an order intent
    intent = OrderIntent(
        intent_id="order_intent_1",
        strategy_instance_id="strat_test",
        account_id="acc_test",
        symbol="TESTSYM",
        side=Side.BUY,
        quantity=50,
        created_at=clock(),
    )
    decision = platform.risk.submit(intent)
    assert decision.allowed is True

    # Invariant: An accepted order DOES NOT create a position in the ledger!
    assert platform.ledger.quantity("acc_test", "strat_test", "TESTSYM") == 0
    assert platform.ledger.positions() == {}

    # Step 2: Partial fill (20 out of 50 executed)
    f = platform.broker.execute(
        "order_intent_1", 20, Decimal("100"), clock(), Decimal("0.01")
    )
    platform.ingest(f)

    # Invariant: Position reflects ONLY executed fill quantity (20, not 50)
    assert platform.ledger.quantity("acc_test", "strat_test", "TESTSYM") == 20
    pos = platform.ledger.positions()[("acc_test", "strat_test", "TESTSYM")]
    assert pos.net_quantity == 20
    assert pos.average_price == Decimal("100")

    # Step 3: Cancel unexecuted remainder (30)
    cancelled_order = platform.orders.cancel("order_intent_1", clock())
    assert cancelled_order.status.value == "CANCELLED"
    assert cancelled_order.remaining_quantity == 30

    # Invariant: Cancellation of remaining quantity has ZERO effect on position
    assert platform.ledger.quantity("acc_test", "strat_test", "TESTSYM") == 20
    platform.store.close()


def test_strategy_position_contract_validation():
    # Valid position construction
    pos = StrategyPosition(
        strategy_instance_id="s1",
        symbol="X",
        net_quantity=10,
        average_price=Decimal("100.5"),
        realized_pnl=Decimal("50"),
        unrealized_pnl=Decimal("20"),
        gross_pnl=Decimal("70"),
        charges=Decimal("0.5"),
        net_pnl=Decimal("69.5"),
    )
    assert pos.gross_pnl == Decimal("70")
    assert pos.net_pnl == Decimal("69.5")

    # Non-integer net_quantity must raise ValueError
    with pytest.raises(ValueError, match="net_quantity must be an integer"):
        StrategyPosition(
            "s1",
            "X",
            10.5,
            Decimal("100"),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
        )  # type: ignore

    # Non-finite decimal must raise ValueError
    with pytest.raises(ValueError, match="must be a finite Decimal"):
        StrategyPosition(
            "s1",
            "X",
            10,
            Decimal("NaN"),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
        )

    # Negative charges must raise ValueError
    with pytest.raises(ValueError, match="charges cannot be negative"):
        StrategyPosition(
            "s1",
            "X",
            10,
            Decimal("100"),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal("-1"),
            Decimal(0),
        )

    # Negative average price must raise ValueError
    with pytest.raises(ValueError, match="average_price cannot be negative"):
        StrategyPosition(
            "s1",
            "X",
            10,
            Decimal("-10"),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
        )

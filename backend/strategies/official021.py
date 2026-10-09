"""Conservative 021-03 reference strategy decision policies.

These policies never receive broker authority.  Their outputs are canonical
OrderIntent objects which still require RiskGateway admission and reservation.
"""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

from backend.shared.contracts import OrderIntent, Side

IST = ZoneInfo("Asia/Kolkata")


def _session_key(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, IST).date().isoformat()


def _already_recorded(store, event_type: str, strategy: str, session: str) -> bool:
    for row in store.rows("SELECT payload FROM audit WHERE type=?", (event_type,)):
        payload = json.loads(row["payload"])
        if payload.get("strategy") == strategy and payload.get("session") == session:
            return True
    return False


def _record_trigger(store, event_type: str, strategy: str, session: str) -> None:
    with store.transaction():
        store.audit(event_type, {"strategy": strategy, "session": session})


@dataclass(frozen=True)
class StrategyContext:
    strategy_instance_id: str
    account_id: str
    symbol: str
    now: float
    feed_fresh: bool
    broker_evidence_fresh: bool
    gate_running: bool
    session_open: bool

    @property
    def safe_for_entry(self) -> bool:
        return all(
            (
                self.feed_fresh,
                self.broker_evidence_fresh,
                self.gate_running,
                self.session_open,
            )
        )


class Time0915Strategy:
    """One 09:15 INTRADAY entry and an attributed-residual 15:15 exit."""

    kind = "time_0915_1515"

    def __init__(self, store, *, side=Side.BUY, quantity=1):
        self.store = store
        self.side = side
        self.quantity = quantity

    def evaluate_entry(self, context: StrategyContext) -> OrderIntent | None:
        local = datetime.fromtimestamp(context.now, IST)
        session = _session_key(context.now)
        # No late catch-up: only observations in the 09:15 minute may enter.
        if not (time(9, 15) <= local.time() < time(9, 16)):
            return None
        if not context.safe_for_entry or _already_recorded(
            self.store,
            "OFFICIAL_TIME_ENTRY_TRIGGERED",
            context.strategy_instance_id,
            session,
        ):
            return None
        _record_trigger(
            self.store,
            "OFFICIAL_TIME_ENTRY_TRIGGERED",
            context.strategy_instance_id,
            session,
        )
        return OrderIntent(
            f"{context.strategy_instance_id}:{session}:0915-entry",
            context.strategy_instance_id,
            context.account_id,
            context.symbol,
            self.side,
            self.quantity,
            context.now,
            reason="021-03 09:15 INTRADAY entry",
        )

    def evaluate_exit(
        self,
        context: StrategyContext,
        *,
        residual_quantity: int,
        attributed_side: Side,
        account_square_off_quantity: int | None,
    ) -> OrderIntent | None:
        local = datetime.fromtimestamp(context.now, IST)
        session = _session_key(context.now)
        if local.time() < time(15, 15) or residual_quantity <= 0:
            return None
        if not (context.feed_fresh and context.broker_evidence_fresh):
            return None
        if (
            account_square_off_quantity is None
            or abs(account_square_off_quantity) < residual_quantity
        ):
            return None
        if _already_recorded(
            self.store,
            "OFFICIAL_TIME_EXIT_TRIGGERED",
            context.strategy_instance_id,
            session,
        ):
            return None
        _record_trigger(
            self.store,
            "OFFICIAL_TIME_EXIT_TRIGGERED",
            context.strategy_instance_id,
            session,
        )
        return OrderIntent(
            f"{context.strategy_instance_id}:{session}:1515-exit",
            context.strategy_instance_id,
            context.account_id,
            context.symbol,
            Side.SELL if attributed_side == Side.BUY else Side.BUY,
            residual_quantity,
            context.now,
            reason="021-03 15:15 attributed residual exit",
        )


class OpenBreakoutStrategy:
    """One 1%-from-official-open entry with application-managed 5% exits."""

    kind = "open_1pct_tp5_sl5"

    def __init__(self, store, *, side=Side.BUY, quantity=1):
        self.store = store
        self.side = side
        self.quantity = quantity

    def evaluate_entry(
        self, context: StrategyContext, *, ltp: Decimal, official_open: Decimal | None
    ) -> OrderIntent | None:
        session = _session_key(context.now)
        if official_open is None or official_open <= 0 or ltp <= 0:
            return None
        crossed = (
            ltp >= official_open * Decimal("1.01")
            if self.side == Side.BUY
            else ltp <= official_open * Decimal("0.99")
        )
        if not crossed or not context.safe_for_entry:
            return None
        if _already_recorded(
            self.store,
            "OFFICIAL_BREAKOUT_ENTRY_TRIGGERED",
            context.strategy_instance_id,
            session,
        ):
            return None
        _record_trigger(
            self.store,
            "OFFICIAL_BREAKOUT_ENTRY_TRIGGERED",
            context.strategy_instance_id,
            session,
        )
        return OrderIntent(
            f"{context.strategy_instance_id}:{session}:open-breakout-entry",
            context.strategy_instance_id,
            context.account_id,
            context.symbol,
            self.side,
            self.quantity,
            context.now,
            reason="021-03 1% move from verified official open",
        )

    def evaluate_exit(
        self,
        context: StrategyContext,
        *,
        ltp: Decimal,
        fill_wap: Decimal | None,
        residual_quantity: int,
        attributed_side: Side,
        entry_order_open: bool,
    ) -> OrderIntent | None:
        session = _session_key(context.now)
        if (
            fill_wap is None
            or fill_wap <= 0
            or residual_quantity <= 0
            or entry_order_open
            or not context.feed_fresh
            or not context.broker_evidence_fresh
        ):
            return None
        if attributed_side == Side.BUY:
            triggered = ltp >= fill_wap * Decimal("1.05") or ltp <= fill_wap * Decimal(
                "0.95"
            )
            exit_side = Side.SELL
        else:
            triggered = ltp <= fill_wap * Decimal("0.95") or ltp >= fill_wap * Decimal(
                "1.05"
            )
            exit_side = Side.BUY
        generation = str(residual_quantity)
        event_type = f"OFFICIAL_BREAKOUT_EXIT_TRIGGERED:{generation}"
        if not triggered or _already_recorded(
            self.store, event_type, context.strategy_instance_id, session
        ):
            return None
        _record_trigger(self.store, event_type, context.strategy_instance_id, session)
        return OrderIntent(
            f"{context.strategy_instance_id}:{session}:tp-sl-exit:{generation}",
            context.strategy_instance_id,
            context.account_id,
            context.symbol,
            exit_side,
            residual_quantity,
            context.now,
            reason="021-03 application-managed 5% TP/SL from fill WAP",
        )

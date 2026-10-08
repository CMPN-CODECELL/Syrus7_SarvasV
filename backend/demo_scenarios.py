"""Deterministic mock demo scenarios and rehearsal runner.

Generates reproducible rising/falling/reversal tick sequences, executes authentic
order intents through platform risk -> mock broker -> fills -> ledger, and exercises
all platform reliability and safety invariants on isolated temporary storage.
"""

from dataclasses import dataclass
from decimal import Decimal
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from backend.accounting.charges import calculate_indian_charges
from backend.broker.adapters import MockBrokerAdapter
from backend.platform import Platform
from backend.shared.contracts import (
    Candle,
    GlobalTradingState as Gate,
    OrderIntent,
    OrderStatus,
    ReconciliationState as Health,
    RiskPolicy,
    Side,
    Tick,
)


class ControllableClock:
    """Deterministic monotonic clock for accelerated mock and replay scenarios."""

    def __init__(self, start_time: float = 1_700_000_100.0):
        self._current_time = float(start_time)

    def __call__(self) -> float:
        return self._current_time

    def advance(self, seconds: float) -> float:
        self._current_time += float(seconds)
        return self._current_time

    def set(self, timestamp: float) -> float:
        self._current_time = float(timestamp)
        return self._current_time


def generate_deterministic_ticks(
    symbol: str = "TCS",
    start_time: int = 1_700_000_100,
) -> list[Tick]:
    """Build deterministic rising/falling/reversal tick sequence across 12 minutes (720s).

    Interval structure (aligned to 300s 5-minute boundaries):
    - Minutes 0-2 (t0 to t0+120): Flat baseline at 100.0
    - Minutes 3-4 (t0+180 to t0+240): Rising ticks from 101.0 to 106.0
    - Minute 5 (t0+300): Closes 1m candle 4 at 106.0 and closes 5m candle 0 [t0, t0+300)
      -> 5 1m closes: [100, 100, 100, 101, 106]
      -> Momentum: 5-period EMA bullish crossover -> BUY intent
      -> Mean Reversion: 106 is +4.5% above mean (101.4) -> SELL intent
      -> Opposing entries on TCS on the same account!
    - Minutes 6-9 (t0+360 to t0+540): Price continues rising to 112.0
    - Minute 10 (t0+600): Closes 5m candle 1 [t0+300, t0+600) with close 112.0 > 106.0
      -> Breakout: 5m close breaks previous 5m high (106.0) -> BUY intent
    - Minutes 11-12 (t0+660 to t0+720): Sharp reversal down to 95.0
    """
    ticks: list[Tick] = []
    # Minute-by-minute prices:
    # m0: 100, m1: 100, m2: 100, m3: 101, m4: 106, m5: 108,
    # m6: 110, m7: 112, m8: 113, m9: 114, m10: 115, m11: 95
    minute_prices = [
        (0, Decimal("100.0")),
        (1, Decimal("100.0")),
        (2, Decimal("100.0")),
        (3, Decimal("101.0")),
        (4, Decimal("106.0")),
        (5, Decimal("108.0")),
        (6, Decimal("110.0")),
        (7, Decimal("112.0")),
        (8, Decimal("113.0")),
        (9, Decimal("114.0")),
        (10, Decimal("115.0")),
        (11, Decimal("95.0")),
    ]

    for m, p in minute_prices:
        base_ts = start_time + m * 60
        # 3 ticks per minute at offsets 0, 20, 40 seconds
        for offset in (0, 20, 40):
            ts = base_ts + offset
            ticks.append(
                Tick(
                    symbol=symbol,
                    event_timestamp=ts,
                    price=p,
                    quantity=10,
                    event_id=f"det:{symbol}:{ts}:{offset}",
                )
            )
    # Final tick at t0 + 720 to cleanly close minute 11
    ticks.append(
        Tick(
            symbol=symbol,
            event_timestamp=start_time + 720,
            price=Decimal("95.0"),
            quantity=10,
            event_id=f"det:{symbol}:{start_time + 720}:final",
        )
    )
    return ticks


@dataclass
class ScenarioResult:
    scenario: str
    passed: bool
    summary: str
    details: dict[str, Any]


class RehearsalRunner:
    """Clean-start mock rehearsal runner using isolated storage and injected clocks."""

    def __init__(
        self,
        db_path: str | None = None,
        start_time: float = 1_700_000_100.0,
        account_id: str = "acc_demo",
        username: str = "demo_user",
        password: str = "password123",
    ):
        self._temp_dir = None
        if db_path is None:
            self._temp_dir = tempfile.mkdtemp(prefix="algoshield_rehearsal_")
            self.db_path = os.path.join(self._temp_dir, "rehearsal.db")
        else:
            self.db_path = db_path

        self.start_time = float(start_time)
        self.clock = ControllableClock(self.start_time)
        self.account_id = account_id
        self.username = username
        self.password = password
        self.token = ""

        # Initialize platform with isolated storage and mock adapter
        self.platform = self._create_platform()
        self._init_account()

    def _create_platform(self) -> Platform:
        broker = MockBrokerAdapter(f"{self.db_path}.broker.json")
        return Platform(
            path=self.db_path,
            broker=broker,
            clock=self.clock,
            demo_enabled=True,
        )

    def _init_account(self):
        user = self.platform.auth.register(
            self.username, self.password, account_id=self.account_id
        )
        self.token = user["token"]

    def close(self):
        if hasattr(self, "platform") and self.platform:
            try:
                self.platform.close()
            except Exception:
                pass
        if self._temp_dir and Path(self._temp_dir).exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Scenario 1: Exact 1m/5m Candles & Opposing Strategy Entries
    # -------------------------------------------------------------------------
    def run_candles_and_opposing_strategies(self) -> ScenarioResult:
        """Exercise 1m/5m candles with warmup and simultaneous opposing positions on TCS."""
        p = self.platform
        acc = self.account_id

        # 1. Subscribe three strategies on the same account
        p.strategies.subscribe(acc, "strat_mom", "momentum", "TCS")
        p.strategies.subscribe(acc, "strat_mr", "mean_reversion", "TCS")
        p.strategies.subscribe(acc, "strat_bo", "breakout", "TCS")

        # 2. Feed initial mark and resume trading gate
        initial_tick = Tick("TCS", int(self.clock()), Decimal("100.0"), 10, "init:mark")
        p.tick(initial_tick, replay=True)
        p.reliability.resume()
        assert p.risk.state == Gate.RUNNING

        # 3. Feed deterministic rising ticks across 10 minutes
        ticks = generate_deterministic_ticks("TCS", int(self.start_time))
        # Feed up to minute 10 (t0 + 600)
        ten_min_ticks = [
            t for t in ticks if t.event_timestamp <= int(self.start_time) + 600
        ]

        last_min = -1
        for tick in ten_min_ticks:
            cur_min = (tick.event_timestamp - int(self.start_time)) // 60
            if cur_min != last_min:
                # Advance simulated clock with the ticks
                self.clock.set(tick.event_timestamp)
                # Rehearsal step: In accelerated simulated replay, advancing simulated time
                # jumps past real wall-clock seconds. Ram's Reliability.check_evidence() enforces
                # max_broker_age = 5s (now - last_broker_at <= 5). In live operation, periodic
                # background health loops run continuously. For accelerated replay, calling
                # resume() at simulated minute intervals is an explicit rehearsal step
                # to refresh evidence, NOT proof of uninterrupted trading or automatic broker refresh.
                p.reliability.resume()
                last_min = cur_min
            p.tick(tick, replay=True)

        # 4. Assert strategy entries and positions
        positions = p.ledger.positions()
        mom_pos = positions.get((acc, "strat_mom", "TCS"))
        mr_pos = positions.get((acc, "strat_mr", "TCS"))
        bo_pos = positions.get((acc, "strat_bo", "TCS"))

        assert mom_pos is not None and mom_pos.net_quantity > 0, (
            "Momentum strategy must establish a LONG position"
        )
        assert mr_pos is not None and mr_pos.net_quantity < 0, (
            "Mean reversion strategy must establish an opposing SHORT position"
        )
        assert bo_pos is not None and bo_pos.net_quantity > 0, (
            "Breakout strategy must establish a LONG position after 5m candle close"
        )

        # Assert candles built
        assert len(p.closed_candles) >= 10
        one_m_candles = [c for c in p.closed_candles if c.interval == 60]
        five_m_candles = [c for c in p.closed_candles if c.interval == 300]
        assert len(one_m_candles) >= 9
        assert len(five_m_candles) >= 2

        # Assert signals emitted
        signals = list(p.strategies.signals)
        mom_signals = [s for s in signals if s["strategy"] == "strat_mom"]
        mr_signals = [s for s in signals if s["strategy"] == "strat_mr"]
        bo_signals = [s for s in signals if s["strategy"] == "strat_bo"]

        assert len(mom_signals) >= 1 and mom_signals[0]["side"] == "BUY"
        assert len(mr_signals) >= 1 and mr_signals[0]["side"] == "SELL"
        assert len(bo_signals) >= 1 and bo_signals[0]["side"] == "BUY"

        # Assert broker snapshot reflects aggregate net position
        broker_positions = p.broker.snapshot().positions
        expected_net = mom_pos.net_quantity + mr_pos.net_quantity + bo_pos.net_quantity
        assert broker_positions.get((acc, "TCS"), 0) == expected_net

        return ScenarioResult(
            scenario="candles_and_opposing_strategies",
            passed=True,
            summary=(
                f"1m/5m candles verified; opposing positions on TCS: "
                f"strat_mom={mom_pos.net_quantity} (LONG), strat_mr={mr_pos.net_quantity} (SHORT), "
                f"strat_bo={bo_pos.net_quantity} (LONG); net broker={expected_net}"
            ),
            details={
                "closed_1m_candles": len(one_m_candles),
                "closed_5m_candles": len(five_m_candles),
                "mom_position": mom_pos.net_quantity,
                "mr_position": mr_pos.net_quantity,
                "bo_position": bo_pos.net_quantity,
                "broker_net_position": expected_net,
                "signals_count": len(signals),
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 2: Partial Fill, Rejection, and Duplicate Fill
    # -------------------------------------------------------------------------
    def run_partial_rejection_duplicate(self) -> ScenarioResult:
        """Exercise partial fill, duplicate fill deduplication, and broker rejection."""
        p = self.platform
        acc = self.account_id

        # 1. Partial fill: submit order for 20, broker executes 10
        intent_partial = OrderIntent(
            "intent_partial_1",
            "strat_mom",
            acc,
            "TCS",
            Side.BUY,
            20,
            self.clock(),
        )
        dec_partial = p.risk.submit(intent_partial)
        assert dec_partial.allowed, (
            f"Partial intent rejected: {dec_partial.reason_code}"
        )

        price = Decimal("115.0")
        charges = calculate_indian_charges(10, price, Side.BUY).total_charges
        fill_partial = p.broker_calls.call(
            "execute", "intent_partial_1", 10, price, self.clock(), charges
        )
        p.ingest(fill_partial)

        order_row = p.store.rows("SELECT * FROM orders WHERE id='intent_partial_1'")[0]
        assert order_row["status"] == OrderStatus.PARTIALLY_FILLED.value
        assert order_row["filled"] == 10

        # 2. Duplicate fill: ingesting identical fill again is safely ignored
        pos_before_dup = p.ledger.quantity(acc, "strat_mom", "TCS")
        applied_again = p.ingest(fill_partial)
        assert applied_again is False, "Duplicate fill must return False"
        pos_after_dup = p.ledger.quantity(acc, "strat_mom", "TCS")
        assert pos_before_dup == pos_after_dup, "Duplicate fill must not alter position"

        # Check audit for DUPLICATE_FILL_IGNORED
        dup_audits = p.store.rows(
            "SELECT * FROM audit WHERE type='DUPLICATE_FILL_IGNORED'"
        )
        assert len(dup_audits) >= 1

        # 3. Order rejection: set broker.reject_next = True
        p.broker.reject_next = True
        intent_rej = OrderIntent(
            "intent_rej_1",
            "strat_mom",
            acc,
            "TCS",
            Side.BUY,
            5,
            self.clock(),
        )
        p.risk.submit(intent_rej)
        rej_order_row = p.store.rows("SELECT * FROM orders WHERE id='intent_rej_1'")[0]
        assert rej_order_row["status"] == OrderStatus.REJECTED.value

        return ScenarioResult(
            scenario="partial_rejection_duplicate",
            passed=True,
            summary="Partial fill (10/20), duplicate fill safely ignored, broker rejection handled",
            details={
                "partial_order_status": order_row["status"],
                "partial_filled_quantity": order_row["filled"],
                "duplicate_fill_ignored": True,
                "rejected_order_status": rej_order_row["status"],
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 3: Risk-Limit Rejection with Backend Reason
    # -------------------------------------------------------------------------
    def run_risk_limit_rejection(self) -> ScenarioResult:
        """Exercise risk-gateway position limit rejection with auditable backend reason."""
        p = self.platform
        acc = self.account_id

        # Set tight position limit of 5 on strat_bo (which currently has position ~1)
        p.risk.policies["strat_bo"] = RiskPolicy(max_position=5)

        # Attempt to buy 10 more (projected: 10 + 10 = 20 > 15)
        intent_blocked = OrderIntent(
            "intent_risk_blocked_1",
            "strat_bo",
            acc,
            "TCS",
            Side.BUY,
            10,
            self.clock(),
        )
        decision = p.risk.submit(intent_blocked)

        assert decision.allowed is False, "Order exceeding limit must be blocked"
        assert decision.reason_code == "RISK_MAX_POSITION", (
            f"Expected RISK_MAX_POSITION, got {decision.reason_code}"
        )

        # Assert no order was inserted in open/reserved status
        order_rows = p.store.rows(
            "SELECT * FROM orders WHERE id='intent_risk_blocked_1'"
        )
        assert len(order_rows) == 0

        # Assert audit record exists
        audit_rows = p.store.rows(
            "SELECT * FROM audit WHERE type='RISK_DECISION' AND payload LIKE '%intent_risk_blocked_1%'"
        )
        assert len(audit_rows) >= 1

        # Restore normal policy
        p.risk.policies["strat_bo"] = RiskPolicy(max_position=100)

        return ScenarioResult(
            scenario="risk_limit_rejection",
            passed=True,
            summary=f"Risk gateway rejected excess order with reason: {decision.reason_code}",
            details={
                "allowed": decision.allowed,
                "reason_code": decision.reason_code,
                "reason_text": decision.reason_text,
                "rules_triggered": decision.rule_results,
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 4: Missed Attributed Fill Recovered Through Reconciliation
    # -------------------------------------------------------------------------
    def run_missed_fill_recovery(self) -> ScenarioResult:
        """Simulate dropped execution event; verify recovery via reconciliation."""
        p = self.platform
        acc = self.account_id

        # Submit an order that remains OPEN locally
        intent_missed = OrderIntent(
            "intent_missed_1",
            "strat_mom",
            acc,
            "TCS",
            Side.BUY,
            5,
            self.clock(),
        )
        decision = p.risk.submit(intent_missed)
        assert decision.allowed

        # Simulate execution at broker without local ingest (e.g. dropped network callback)
        price = Decimal("115.0")
        p.broker.execute_external(
            "intent_missed_1",
            5,
            price,
            self.clock(),
            calculate_indian_charges(5, price, Side.BUY).total_charges,
        )

        # Verify local state is still OPEN with 0 filled
        local_before = p.store.rows(
            "SELECT status, filled FROM orders WHERE id='intent_missed_1'"
        )[0]
        assert local_before["status"] == OrderStatus.OPEN.value
        assert local_before["filled"] == 0
        qty_before = p.ledger.quantity(acc, "strat_mom", "TCS")

        # Reconcile local state against broker truth
        reconciled = p.reliability.reconcile()
        assert reconciled is True, f"Reconciliation failed: {p.reliability.report}"

        # Verify order updated to FILLED and ledger position updated
        local_after = p.store.rows(
            "SELECT status, filled FROM orders WHERE id='intent_missed_1'"
        )[0]
        assert local_after["status"] == OrderStatus.FILLED.value
        assert local_after["filled"] == 5
        qty_after = p.ledger.quantity(acc, "strat_mom", "TCS")
        assert qty_after == qty_before + 5

        return ScenarioResult(
            scenario="missed_fill_recovery",
            passed=True,
            summary="Missed broker fill recovered via reconciliation; order marked FILLED and ledger synced",
            details={
                "status_before": local_before["status"],
                "filled_before": local_before["filled"],
                "status_after": local_after["status"],
                "filled_after": local_after["filled"],
                "ledger_quantity_recovered": qty_after - qty_before,
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 5: Platform Restart Remains RECOVERING Until Reconcile/Resume
    # -------------------------------------------------------------------------
    def run_restart_recovery(self) -> ScenarioResult:
        """Simulate platform process restart; verify recovery gate, retained history, and safe resume."""
        # 1. Capture durable pre-close state: executed fills, virtual positions, and broker snapshot
        fills_before = self.platform.store.rows("SELECT * FROM fills")
        positions_before = {
            k: p.net_quantity
            for k, p in self.platform.ledger.positions().items()
            if p.net_quantity != 0
        }
        broker_positions_before = {
            k: q for k, q in self.platform.broker.snapshot().positions.items() if q != 0
        }
        assert len(fills_before) > 0, (
            "Restart scenario requires executed fills in history"
        )
        assert len(positions_before) > 0, (
            "Restart scenario requires active virtual positions"
        )
        assert len(broker_positions_before) > 0, (
            "Restart scenario requires active broker positions"
        )

        # 2. Close current platform instance (simulating process exit/crash)
        self.platform.close()

        # 3. Restart with fresh Platform instance on the SAME durable SQLite file
        #    and independent mock broker persistence file.
        restarted = self._create_platform()
        self.platform = restarted

        # 4. Assert startup invariants BEFORE reconciliation or resume:
        #    - Health is RECOVERING
        #    - Gate is RECOVERING (admission closed)
        #    - Strategies are disabled (runtime.enabled == False)
        assert restarted.reliability.health == Health.RECOVERING
        assert restarted.risk.state == Gate.RECOVERING
        assert restarted.strategies.enabled is False

        # Assert durable SQLite retained positions and fill history without data loss:
        fills_after = restarted.store.rows("SELECT * FROM fills")
        positions_after = {
            k: p.net_quantity
            for k, p in restarted.ledger.positions().items()
            if p.net_quantity != 0
        }
        assert len(fills_after) == len(fills_before), (
            "Durable fill history must be preserved across restart"
        )
        assert positions_after == positions_before, (
            "Durable virtual positions must be preserved across restart"
        )

        # Assert independent broker evidence retains actual external positions:
        broker_positions_after = {
            k: q for k, q in restarted.broker.snapshot().positions.items() if q != 0
        }
        assert broker_positions_after == broker_positions_before, (
            "Independent broker snapshot must be preserved across restart"
        )

        # Strategies must not emit orders while in RECOVERING:
        now_ts = int(self.clock())
        test_candle = Candle(
            "TCS",
            60,
            now_ts,
            now_ts + 60,
            Decimal("110.0"),
            Decimal("112.0"),
            Decimal("108.0"),
            Decimal("111.0"),
            100,
        )
        intents = restarted.strategies.on_candle(test_candle, self.clock())
        assert intents == [], "Strategies must not execute while gate is RECOVERING"

        # 5. Authoritative broker reconciliation: local ledger is reconciled against
        #    observed external broker truth (never replacing broker truth with ledger reconstruction).
        reconciled = restarted.reliability.reconcile()
        assert reconciled is True, (
            "Authoritative reconciliation must verify matching state"
        )

        # 6. Explicit operator resume: restores trading gate to RUNNING and health to HEALTHY
        restarted.reliability.resume()
        assert restarted.risk.state == Gate.RUNNING
        assert restarted.reliability.health == Health.HEALTHY
        assert restarted.strategies.enabled is True

        return ScenarioResult(
            scenario="restart_recovery",
            passed=True,
            summary="Restart began safely in RECOVERING; retained durable history, reconciled against broker truth, and resumed to RUNNING",
            details={
                "initial_health": "RECOVERING",
                "initial_gate": "RECOVERING",
                "retained_fills": len(fills_after),
                "retained_positions": positions_after,
                "reconciliation_verified": True,
                "resumed_gate": restarted.risk.state.value,
                "resumed_health": restarted.reliability.health.value,
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 6: Kill with Pending Orders/Exposure
    # -------------------------------------------------------------------------
    def run_kill_switch_with_exposure(self) -> ScenarioResult:
        """Execute platform kill switch: cancel open orders, flatten all positions."""
        p = self.platform
        acc = self.account_id

        # Verify there is active exposure before kill
        virt_before = p.ledger.aggregate()
        assert len(virt_before) > 0, (
            "Kill scenario requires active positions to flatten"
        )

        # Submit an open order to verify cancellation
        intent_open = OrderIntent(
            "intent_kill_open_1",
            "strat_mom",
            acc,
            "TCS",
            Side.BUY,
            5,
            self.clock(),
        )
        dec_open = p.risk.submit(intent_open)
        assert dec_open.allowed

        # Trigger kill switch via Platform.kill()
        cert = p.kill(deadline_seconds=9)

        # Assert kill certificate invariants against KillCertificate contract
        assert cert.status == "SUCCESS", (
            f"Kill failed with status {cert.status}: {cert.reason}"
        )
        assert cert.elapsed_seconds < 10.0, (
            f"Kill deadline exceeded: {cert.elapsed_seconds}s >= 10s"
        )
        assert cert.open_orders == 0, f"Expected 0 open orders, got {cert.open_orders}"
        assert cert.virtual_positions_flat is True, (
            "Certificate indicates virtual positions not flat"
        )

        # Assert all local and broker positions are completely flat
        virt_after = {k: q for k, q in p.ledger.aggregate().items() if q}
        broker_after = {k: q for k, q in p.broker.snapshot().positions.items() if q}
        assert virt_after == {}, f"Virtual aggregate positions not flat: {virt_after}"
        assert broker_after == {}, f"Broker positions not flat: {broker_after}"
        assert all(pos.net_quantity == 0 for pos in p.ledger.positions().values()), (
            "Every virtual strategy position must be flat (net_quantity == 0)"
        )

        # Assert gate is KILLED and admission is latched
        assert p.risk.state == Gate.KILLED or p.reliability.kill_latched

        return ScenarioResult(
            scenario="kill_switch_with_exposure",
            passed=True,
            summary=(
                f"Verified kill certificate SUCCESS in {cert.elapsed_seconds:.2f}s; "
                f"0 open orders, 0 broker positions, all virtual positions flat"
            ),
            details={
                "certificate_status": cert.status,
                "elapsed_seconds": cert.elapsed_seconds,
                "open_orders": cert.open_orders,
                "virtual_positions_flat": cert.virtual_positions_flat,
                "reason": cert.reason,
                "virtual_positions_remaining": virt_after,
                "broker_positions_remaining": broker_after,
            },
        )

    # -------------------------------------------------------------------------
    # Scenario 7: Unexplained Drift Remains Blocked
    # -------------------------------------------------------------------------
    def run_unexplained_drift_blocked(self) -> ScenarioResult:
        """Inject unverified external position drift; verify platform fails closed without auto-fixing."""
        p = self.platform
        acc = self.account_id

        # Inject foreign external position at mock broker
        p.broker.external_positions[(acc, "UNEXPLAINED_DRIFT")] = 50
        p.broker.persist()

        # Reconcile must detect position drift and fail closed
        reconciled = p.reliability.reconcile()
        assert reconciled is False, "Reconciliation must fail on unexplained drift"
        assert p.reliability.report["verified"] is False
        assert p.reliability.report["reason"] in {
            "UNEXPLAINED_EXTERNAL_POSITION",
            "VIRTUAL_POSITION_DRIFT",
        }

        # Risk gate must be UNCERTAIN and health DRIFTED
        assert p.risk.state == Gate.UNCERTAIN
        assert p.reliability.health == Health.DRIFTED

        # Platform must refuse to resume while drifted
        try:
            p.reliability.resume()
            resumed = True
        except ValueError:
            resumed = False
        assert resumed is False, "Platform must not auto-resume while drifted"

        # Verify platform did not auto-fix or clear the drift
        assert (acc, "UNEXPLAINED_DRIFT") in p.broker.external_positions

        return ScenarioResult(
            scenario="unexplained_drift_blocked",
            passed=True,
            summary="Unexplained broker drift triggered fail-closed UNCERTAIN/DRIFTED; auto-fix correctly blocked",
            details={
                "reconciliation_verified": False,
                "failure_reason": p.reliability.report["reason"],
                "gate_state": p.risk.state.value,
                "health_state": p.reliability.health.value,
                "resume_blocked": True,
            },
        )

    # -------------------------------------------------------------------------
    # Comprehensive Scenario Suite Runner
    # -------------------------------------------------------------------------
    def run_all(self) -> list[ScenarioResult]:
        """Execute all rehearsal scenarios sequentially."""
        results: list[ScenarioResult] = []
        try:
            results.append(self.run_candles_and_opposing_strategies())
            results.append(self.run_partial_rejection_duplicate())
            results.append(self.run_risk_limit_rejection())
            results.append(self.run_missed_fill_recovery())
            results.append(self.run_restart_recovery())
            results.append(self.run_kill_switch_with_exposure())
            results.append(self.run_unexplained_drift_blocked())
        finally:
            self.close()
        return results

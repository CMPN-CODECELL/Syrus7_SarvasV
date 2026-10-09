"""Offline fault scenarios; all ordinary intents enter through platform risk."""

from dataclasses import replace
from decimal import Decimal
from tempfile import TemporaryDirectory
from time import perf_counter
from backend.shared.contracts import (
    AccountRiskPolicy,
    OrderIntent,
    Side,
    Tick,
    RiskPolicy,
)
from backend.reliability.failure_lab_meta import (
    SCENARIO_METADATA,
    build_simple_explanation,
)

SCENARIOS = {
    "partial",
    "rejection",
    "position_limit",
    "duplicate_fill",
    "conflicting_fill",
    "missed_fill",
    "unknown_submission",
    "disconnect",
    "reconnect",
    "spam",
    "stale_feed",
    "drift",
    "clear_drift",
    "kill_partial",
    "broker_update",
    "disconnect_recovery",
    "concurrent_position_race",
    "account_risk",
    "opposing_gross_exposure",
    "limit_lowered_below_position",
    "daily_loss_mark_breach",
    "late_fill_after_cancel",
    "kill_late_fill",
    "broker_failure_during_kill",
    "restart_fail_closed",
    "stale_broker_evidence",
    "invalid_price",
}


class FailureLab:
    def __init__(self, platform):
        self.platform = platform

    def _cleanup_previous_faults(self, scenario):
        p = self.platform
        if scenario != "reconnect":
            p.broker.connected = True
            adapter = getattr(p.broker_calls, "adapter", p.broker)
            adapter.connected = True

        if scenario != "clear_drift":
            p.broker.external_positions.pop(("failure-lab", "INJECTED"), None)
            p.broker.persist()

        p.broker.reject_next = False
        p.broker.timeout_after_accept = False
        if hasattr(p.broker, "updates"):
            p.broker.updates.clear()

        with p.store.transaction() as db:
            db.execute("DELETE FROM account_risk_policies WHERE account='failure-lab'")

        p.reliability.safety.set("kill_latched", False)
        p.risk.kill_requested.clear()

        if scenario not in {"reconnect", "clear_drift", "disconnect"}:
            try:
                p.reliability.reconcile()
                p.reliability.resume()
            except Exception:
                pass

    def run(self, scenario, params=None):
        started_at = self.platform.clock()
        timer = perf_counter()
        params = params or {}
        p = self.platform
        p.require_offline_demo()
        if scenario not in SCENARIOS:
            raise ValueError("unknown failure scenario")
        self._cleanup_previous_faults(scenario)
        decisions, evidence = [], {}
        if scenario == "disconnect":
            p.disconnect_broker()
            p.reliability.reconcile()
        elif scenario == "reconnect":
            p.reconnect_broker()

        elif scenario == "clear_drift":
            p.broker.external_positions.pop(("failure-lab", "INJECTED"), None)
            p.broker.persist()
            p.reliability.reconcile()
        elif scenario == "drift":
            injected_qty = int(params.get("injected_quantity", 7))
            p.broker.external_positions[("failure-lab", "INJECTED")] = injected_qty
            p.broker.persist()
            p.reliability.reconcile()
        else:
            with p.store.lock:
                if not p.store.rows("SELECT id FROM accounts WHERE id='failure-lab'"):
                    p.account("failure-lab")
                counter = len(
                    p.store.rows(
                        "SELECT id FROM subscriptions WHERE account='failure-lab'"
                    )
                )
                strategy = f"lab-{scenario}-{counter}"
                p.strategies.subscribe("failure-lab", strategy, "momentum", "LAB")
            p.tick(Tick("LAB", int(p.clock()), Decimal("100"), 0, strategy + ":mark"))
            p.reliability.resume()

            def submit(suffix, quantity):
                i = OrderIntent(
                    f"{strategy}:{suffix}",
                    strategy,
                    "failure-lab",
                    "LAB",
                    Side.BUY,
                    quantity,
                    p.clock(),
                )
                decisions.append(p.risk.submit(i))
                return i

            def execute(i, quantity):
                return p.broker_calls.call(
                    "execute", i.intent_id, quantity, Decimal("100"), p.clock()
                )

            if scenario in {"partial", "kill_partial"}:
                order_qty = int(params.get("order_quantity", 100))
                fill_qty = int(params.get("fill_quantity", 40))
                i = submit("partial", order_qty)
                p.ingest(execute(i, fill_qty))
                evidence["order_quantity"] = order_qty
                evidence["filled"] = fill_qty
                if scenario == "kill_partial":
                    evidence["kill"] = p.kill()
            elif scenario == "rejection":
                order_qty = int(params.get("order_quantity", 5))
                p.broker.reject_next = True
                submit("reject", order_qty)
            elif scenario == "position_limit":
                init_fill = int(params.get("initial_fill", 80))
                pend_qty = int(params.get("pending_quantity", 20))
                block_qty = int(params.get("blocked_quantity", 10))
                i = submit("filled", init_fill)
                p.ingest(execute(i, init_fill))
                submit("pending", pend_qty)
                submit("blocked", block_qty)
            elif scenario in {"duplicate_fill", "conflicting_fill", "missed_fill"}:
                order_qty = int(params.get("order_quantity", 10))
                fill_qty = int(params.get("fill_quantity", 4))
                i = submit("fill", order_qty)
                f = execute(i, fill_qty)
                if scenario == "missed_fill":
                    evidence["quantity_before_recovery"] = p.ledger.quantity(
                        "failure-lab", strategy, "LAB"
                    )
                    evidence["recovered"] = p.reliability.reconcile()
                    evidence["quantity_after_recovery"] = p.ledger.quantity(
                        "failure-lab", strategy, "LAB"
                    )
                else:
                    p.ingest(f)
                    if scenario == "duplicate_fill":
                        evidence["applied_again"] = p.ingest(f)
                    else:
                        try:
                            p.ingest(replace(f, price=Decimal("101")))
                        except Exception:
                            evidence["conflict_rejected"] = True
            elif scenario == "unknown_submission":
                order_qty = int(params.get("order_quantity", 10))
                p.broker.timeout_after_accept = True
                i = submit("unknown", order_qty)
                evidence["order_id"] = i.intent_id
            elif scenario == "spam":
                max_opm = int(params.get("max_orders_per_minute", 2))
                num_orders = int(params.get("orders_sent", 4))
                p.risk.policies[strategy] = RiskPolicy(max_orders_per_minute=max_opm)
                for n in range(num_orders):
                    submit(str(n), 1)
            elif scenario == "account_risk":
                acc_net = int(params.get("account_net_limit", 1))
                order_qty = int(params.get("order_quantity", 2))
                p.risk.account_policies.set(
                    "failure-lab", AccountRiskPolicy(acc_net, 100)
                )
                submit("account-net", order_qty)
                evidence["blocked"] = decisions[-1].reason_code
            elif scenario == "opposing_gross_exposure":
                acc_gross = int(params.get("account_gross_limit", 1))
                order_qty = int(params.get("order_quantity", 2))
                p.risk.account_policies.set(
                    "failure-lab", AccountRiskPolicy(100, acc_gross)
                )
                submit("account-gross", order_qty)
                evidence["blocked"] = decisions[-1].reason_code
            elif scenario == "concurrent_position_race":
                from concurrent.futures import ThreadPoolExecutor

                max_pos = int(params.get("max_position", 100))
                order_sz = int(params.get("order_size", 60))
                p.risk.policies[strategy] = RiskPolicy(max_position=max_pos)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [
                        pool.submit(submit, f"race-{n}", order_sz) for n in range(2)
                    ]
                    for future in futures:
                        future.result()
                evidence["allowed"] = sum(decision.allowed for decision in decisions)
            elif scenario == "stale_broker_evidence":
                p.reliability.last_broker_at = (
                    p.clock() - p.reliability.max_broker_age - 1
                )
                submit("stale-broker", 1)
                evidence["blocked"] = decisions[-1].reason_code
            elif scenario == "invalid_price":
                limit_p = Decimal(str(params.get("limit_price", 10000)))
                intent = OrderIntent(
                    f"{strategy}:invalid-price",
                    strategy,
                    "failure-lab",
                    "LAB",
                    Side.BUY,
                    1,
                    p.clock(),
                    order_type="LIMIT",
                    limit_price=limit_p,
                )
                decisions.append(p.risk.submit(intent))
                evidence["blocked"] = decisions[-1].reason_code
            elif scenario == "limit_lowered_below_position":
                cur_pos = int(params.get("current_position", 80))
                lowered = int(params.get("lowered_limit", 50))
                filled_intent = submit("existing", cur_pos)
                p.ingest(execute(filled_intent, cur_pos))
                p.risk.policies[strategy] = RiskPolicy(max_position=lowered)
                submit("increase", 1)
                reducing_intent = OrderIntent(
                    f"{strategy}:reduce",
                    strategy,
                    "failure-lab",
                    "LAB",
                    Side.SELL,
                    1,
                    p.clock(),
                )
                decisions.append(p.risk.submit(reducing_intent))
                evidence["increase_blocked"] = decisions[-2].reason_code
                evidence["reduce_allowed"] = decisions[-1].allowed
            elif scenario == "daily_loss_mark_breach":
                loss_lim = Decimal(str(params.get("daily_loss_limit", 1)))
                drop_p = Decimal(str(params.get("drop_price", 90)))
                filled_intent = submit("loss-position", 1)
                p.ingest(execute(filled_intent, 1))
                p.risk.policies[strategy] = RiskPolicy(max_daily_loss=loss_lim)
                p.tick(
                    Tick(
                        "LAB",
                        int(p.clock()) + 1,
                        drop_p,
                        0,
                        strategy + ":loss-mark",
                    )
                )
                submit("loss-blocked", 1)
                evidence["blocked"] = decisions[-1].reason_code
            elif scenario == "late_fill_after_cancel":
                init_fill = int(params.get("initial_fill", 4))
                late_fill = int(params.get("late_fill", 2))
                order_intent = submit("late", init_fill + late_fill + 4)
                p.ingest(execute(order_intent, init_fill))
                p.cancel(order_intent.intent_id)
                late = p.broker.execute(
                    order_intent.intent_id,
                    late_fill,
                    Decimal("100"),
                    p.clock(),
                    allow_late=True,
                )
                p.ingest(late)
                evidence["filled"] = p.store.rows(
                    "SELECT filled FROM orders WHERE id=?", (order_intent.intent_id,)
                )[0]["filled"]
            elif scenario == "kill_late_fill":
                order_qty = int(params.get("order_quantity", 10))
                fill_qty = int(params.get("fill_quantity", 4))
                order_intent = submit("kill-late", order_qty)
                p.ingest(execute(order_intent, fill_qty))
                evidence["kill"] = p.kill()
            elif scenario == "broker_failure_during_kill":
                p.broker.connected = False
                evidence["kill"] = p.kill()
            elif scenario == "restart_fail_closed":
                from backend.platform import Platform

                with TemporaryDirectory(prefix="algoshield-restart-") as directory:
                    path = directory + "/restart.sqlite3"
                    before = Platform(path)
                    try:
                        before.account("restart-account")
                        before.strategies.subscribe(
                            "restart-account", "restart-strategy", "momentum", "RST"
                        )
                        before.tick(
                            Tick("RST", 1_700_000_000, Decimal("100"), 1, "restart:1"),
                            replay=True,
                        )
                        before.reliability.resume()
                        evidence["before_restart_gate"] = before.risk.state
                    finally:
                        before.close()
                    after = Platform(path)
                    try:
                        evidence["gate"] = after.risk.state
                        evidence["runtime_enabled"] = after.strategies.enabled
                    finally:
                        after.close()
            elif scenario == "stale_feed":
                # Explicit mock fixture time; never alters process clocks or financial events.
                with p.store.transaction() as db:
                    db.execute(
                        "UPDATE risk_marks SET received_at=? WHERE symbol='LAB'",
                        (p.clock() - p.reliability.max_feed_age - 1,),
                    )
                    p.store.audit("FAILURE_LAB_STALE_FEED", {"symbol": "LAB"})
                submit("stale", 1)
            elif scenario == "drift":
                injected_qty = int(params.get("injected_quantity", 7))
                p.broker.external_positions[("failure-lab", "INJECTED")] = injected_qty
                p.broker.persist()
                p.reliability.reconcile()
            elif scenario == "broker_update":
                order_qty = int(params.get("order_quantity", 100))
                fill_qty = int(params.get("fill_quantity", 40))
                i = submit("broker-upd", order_qty)
                p.sync_broker_updates()
                execute(i, fill_qty)
                synced = p.sync_broker_updates()
                evidence["order_id"] = i.intent_id
                evidence["synced_updates_count"] = len(synced)
                evidence["executed_quantity"] = p.ledger.quantity(
                    "failure-lab", strategy, "LAB"
                )
            elif scenario == "disconnect_recovery":
                order_qty = int(params.get("order_quantity", 100))
                fill_qty = int(params.get("fill_quantity", 40))
                i = submit("disc-rec", order_qty)
                evidence["before_disconnect"] = {
                    "order_id": i.intent_id,
                    "status": "OPEN",
                    "filled": 0,
                }
                p.disconnect_broker()
                evidence["during_disconnect"] = {
                    "connected": False,
                    "platform_state": p.risk.state.value,
                }
                adapter = getattr(p.broker_calls, "adapter", p.broker)
                adapter.connected = True
                adapter.execute(i.intent_id, fill_qty, Decimal("100"), p.clock())
                adapter.connected = False
                evidence["broker_truth"] = {
                    "order_id": i.intent_id,
                    "status": "PARTIALLY_FILLED",
                    "filled": fill_qty,
                }
                rec = p.reconnect_broker()
                evidence["reconciliation_result"] = rec["reconciled"]
                row = p.store.rows("SELECT * FROM orders WHERE id=?", (i.intent_id,))[0]
                evidence["after_reconciliation"] = {
                    "order_id": i.intent_id,
                    "status": row["status"],
                    "filled": row["filled"],
                }
                evidence["recovered_fill_quantity"] = row["filled"]
                evidence["position"] = p.ledger.quantity("failure-lab", strategy, "LAB")

            if scenario in {
                "partial",
                "rejection",
                "position_limit",
                "duplicate_fill",
                "spam",
                "broker_update",
            }:
                p.reliability.reconcile()
        with p.store.transaction() as db:
            db.execute("DELETE FROM account_risk_policies WHERE account='failure-lab'")
            p.store.audit("FAILURE_LAB", {"scenario": scenario, "evidence": evidence})
        proof = p.safety_proof.build()
        passed = self._passed(scenario, decisions, evidence, p, params=params)
        p._metric_counter("failure_lab_runs")
        p._metric_counter("failure_lab_passes" if passed else "failure_lab_failures")
        meta = SCENARIO_METADATA.get(scenario, {})
        explanation_data = build_simple_explanation(
            scenario, passed, evidence, decisions, params, p
        )
        return {
            "scenario": scenario,
            "status": "PASS" if passed else "FAIL",
            "started_at": started_at,
            "duration_ms": (perf_counter() - timer) * 1000,
            "title": meta.get("title", scenario.replace("_", " ").title()),
            "summary": explanation_data["summary"],
            "what_it_does": meta.get("what_it_does", ""),
            "steps": meta.get("steps", []),
            "explanation": explanation_data["explanation"],
            "simple_evidence": explanation_data["simple_evidence"],
            "parameters_used": params,
            "expected": [
                "Platform contains the injected failure without bypassing risk."
            ],
            "observed": evidence,
            "decisions": decisions,
            "evidence": evidence,
            "invariants": proof,
            "state": p.snapshot(),
        }

    @staticmethod
    def _passed(scenario, decisions, evidence, platform, params=None):
        params = params or {}
        latest_orders = platform.store.rows(
            "SELECT status,filled FROM orders ORDER BY created DESC,id DESC LIMIT 3"
        )
        fill_qty_default_40 = int(params.get("fill_quantity", 40))
        checks = {
            "partial": lambda: (
                bool(latest_orders)
                and latest_orders[0]["filled"] == fill_qty_default_40
            ),
            "kill_partial": lambda: (
                getattr(evidence.get("kill"), "status", None)
                in {"SUCCESS", "SAFE_LATE"}
            ),
            "rejection": lambda: (
                bool(latest_orders) and latest_orders[0]["status"] == "REJECTED"
            ),
            "position_limit": lambda: (
                bool(decisions) and decisions[-1].reason_code == "RISK_MAX_POSITION"
            ),
            "duplicate_fill": lambda: evidence.get("applied_again") is False,
            "conflicting_fill": lambda: (
                evidence.get("conflict_rejected") is True
                and platform.risk.state == "UNCERTAIN"
            ),
            "missed_fill": lambda: (
                evidence.get("quantity_before_recovery") == 0
                and evidence.get("quantity_after_recovery")
                == int(params.get("fill_quantity", 4))
            ),
            "unknown_submission": lambda: (
                bool(latest_orders) and latest_orders[0]["status"] == "UNKNOWN"
            ),
            "spam": lambda: (
                [decision.reason_code for decision in decisions]
                == ["ALLOWED", "ALLOWED", "RISK_RATE_LIMIT", "RISK_RATE_LIMIT"]
                if not params
                else any(d.reason_code == "RISK_RATE_LIMIT" for d in decisions)
            ),
            "account_risk": lambda: (
                evidence.get("blocked") == "RISK_ACCOUNT_NET_POSITION"
            ),
            "opposing_gross_exposure": lambda: (
                evidence.get("blocked") == "RISK_ACCOUNT_GROSS_POSITION"
            ),
            "concurrent_position_race": lambda: evidence.get("allowed") == 1,
            "stale_broker_evidence": lambda: (
                evidence.get("blocked") == "RISK_STALE_BROKER_STATE"
            ),
            "invalid_price": lambda: (
                evidence.get("blocked") == "RISK_PRICE_REASONABILITY"
            ),
            "limit_lowered_below_position": lambda: (
                evidence.get("increase_blocked") == "RISK_MAX_POSITION"
                and evidence.get("reduce_allowed") is True
            ),
            "daily_loss_mark_breach": lambda: (
                evidence.get("blocked") == "RISK_MAX_DAILY_LOSS"
            ),
            "late_fill_after_cancel": lambda: (
                evidence.get("filled")
                == int(params.get("initial_fill", 4)) + int(params.get("late_fill", 2))
            ),
            "kill_late_fill": lambda: (
                getattr(evidence.get("kill"), "status", None)
                in {"SUCCESS", "SAFE_LATE"}
            ),
            "broker_failure_during_kill": lambda: (
                getattr(evidence.get("kill"), "status", None) == "FAILED"
                and platform.risk.state == "UNCERTAIN"
            ),
            "restart_fail_closed": lambda: (
                evidence.get("gate") == "RECOVERING"
                and evidence.get("runtime_enabled") is False
            ),
            "stale_feed": lambda: (
                bool(decisions)
                and decisions[-1].reason_code == "RISK_STALE_MARKET_DATA"
            ),
            "disconnect": lambda: platform.risk.state == "UNCERTAIN",
            "reconnect": lambda: (
                platform.risk.state == "STOPPED"
                and platform.reliability.report.get("verified") is True
            ),
            "drift": lambda: platform.reliability.report.get("verified") is False,
            "clear_drift": lambda: platform.reliability.report.get("verified") is True,
            "broker_update": lambda: (
                evidence.get("executed_quantity") == fill_qty_default_40
            ),
            "disconnect_recovery": lambda: (
                evidence.get("recovered_fill_quantity") == fill_qty_default_40
            ),
        }
        check = checks.get(scenario)
        return bool(check()) if check else False

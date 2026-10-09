"""Metadata, plain-English explanations, and parameter schemas for Failure Lab scenarios."""

SCENARIO_METADATA = {
    "partial": {
        "id": "partial",
        "title": "Partial order fill",
        "summary": "The broker fills only part of an order.",
        "what_it_does": "Submits a buy order, but the broker executes only a fraction of requested shares. Verifies that the platform records only real fills and never counts unfilled quantity.",
        "steps": [
            "Emit order intent for requested quantity",
            "Pass non-bypassable platform risk checks",
            "Broker executes a partial fill",
            "Platform updates position by executed quantity only",
            "Reconciliation confirms position matches broker truth exactly",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 100,
                "min": 10,
                "max": 1000,
                "description": "Total shares requested by the strategy",
            },
            {
                "name": "fill_quantity",
                "label": "Executed fill quantity",
                "type": "number",
                "default": 40,
                "min": 1,
                "max": 999,
                "description": "Partial shares actually executed by the broker",
            },
        ],
    },
    "rejection": {
        "id": "rejection",
        "title": "Broker rejection",
        "summary": "The broker refuses an approved order.",
        "what_it_does": "Sends an approved order to the broker, but the broker rejects it. Verifies that rejected orders create no fills and zero position.",
        "steps": [
            "Submit order intent approved by platform risk",
            "Broker returns rejection response",
            "Platform transitions order to REJECTED status",
            "Verify strategy position remains zero with no phantom trades",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 5,
                "min": 1,
                "max": 100,
                "description": "Shares in the rejected order",
            }
        ],
    },
    "position_limit": {
        "id": "position_limit",
        "title": "Position limit breach",
        "summary": "A new order would exceed the strategy's size limit.",
        "what_it_does": "Fills a strategy close to its position limit, then submits an order that would breach the limit. Verifies that the platform risk gateway blocks the order before it reaches the broker.",
        "steps": [
            "Fill initial position up to safe capacity",
            "Attempt additional order exceeding max position",
            "Platform risk gateway intercepts order and blocks with RISK_MAX_POSITION",
            "Verify broker receives zero excess orders",
        ],
        "parameters": [
            {
                "name": "initial_fill",
                "label": "Initial filled position",
                "type": "number",
                "default": 80,
                "min": 10,
                "max": 90,
                "description": "Existing position already held",
            },
            {
                "name": "pending_quantity",
                "label": "Allowed pending quantity",
                "type": "number",
                "default": 20,
                "min": 1,
                "max": 50,
                "description": "Order that fits within remaining limit",
            },
            {
                "name": "blocked_quantity",
                "label": "Excess quantity to block",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 50,
                "description": "Order that pushes past position limit",
            },
        ],
    },
    "duplicate_fill": {
        "id": "duplicate_fill",
        "title": "Duplicate fill deduplication",
        "summary": "The broker sends the same trade confirmation twice.",
        "what_it_does": "Simulates a broker network replay sending the exact same fill ID twice. Verifies that the platform's fill idempotency engine discards the duplicate without double-counting position or P&L.",
        "steps": [
            "Execute order at broker and receive trade fill",
            "Ingest first fill and increment strategy position",
            "Ingest duplicate fill with same fill ID",
            "Platform detects identical fill ID and discards it safely",
            "Verify position and P&L were not doubled",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "Order quantity",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 4,
                "min": 1,
                "max": 100,
                "description": "Quantity in duplicate fill event",
            },
        ],
    },
    "conflicting_fill": {
        "id": "conflicting_fill",
        "title": "Conflicting fill rejection",
        "summary": "The same fill ID arrives with different trade details.",
        "what_it_does": "Simulates receiving an event reusing an existing fill ID but with conflicting price or quantity. Verifies that the platform refuses ambiguous financial records and halts the trading gate for safety.",
        "steps": [
            "Ingest valid execution fill",
            "Receive conflicting fill reusing same fill ID with altered price",
            "Platform rejects corrupt event",
            "Trading gate automatically transitions to UNCERTAIN (fail-closed)",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "Order quantity",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 4,
                "min": 1,
                "max": 100,
                "description": "Quantity in conflicting fill",
            },
        ],
    },
    "missed_fill": {
        "id": "missed_fill",
        "title": "Missed fill reconciliation recovery",
        "summary": "A broker fill is initially missing from local records.",
        "what_it_does": "Broker executes a fill that fails to reach local event streams. When reconciliation runs, it queries broker trade truth, detects the missing fill, and repairs local state.",
        "steps": [
            "Broker executes trade while local platform misses event",
            "Local ledger shows 0 position",
            "Reconciliation center queries authoritative broker ledger",
            "Discrepancy detected and local fill ledger is repaired",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "Order quantity",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 4,
                "min": 1,
                "max": 100,
                "description": "Quantity executed at broker",
            },
        ],
    },
    "unknown_submission": {
        "id": "unknown_submission",
        "title": "Unknown order outcome containment",
        "summary": "The broker accepts an order but the response times out.",
        "what_it_does": "Simulates a network timeout right after submitting an order. Verifies that the platform marks the order UNKNOWN and never blindly resubmits (preventing duplicate market orders).",
        "steps": [
            "Submit order intent to broker",
            "Broker accepts order but network response drops",
            "Platform marks order UNKNOWN and reserves risk capacity",
            "Reconciliation resolves order truth without blindly re-ordering",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "Order quantity",
            }
        ],
    },
    "disconnect": {
        "id": "disconnect",
        "title": "Broker disconnect fail-closed",
        "summary": "The broker connection drops.",
        "what_it_does": "Drops broker connectivity. Verifies that the platform halts new risk immediately and locks the trading gate to UNCERTAIN.",
        "steps": [
            "Drop broker network connection",
            "Platform detects broker disconnection",
            "Trading gate moves to UNCERTAIN",
            "All new strategy order intents are blocked",
        ],
        "parameters": [],
    },
    "reconnect": {
        "id": "reconnect",
        "title": "Broker reconnect safe gate",
        "summary": "The broker connection becomes available again.",
        "what_it_does": "Restores broker connection after an outage. Verifies that the platform reconciles first and leaves the gate in STOPPED (not blindly resuming trading).",
        "steps": [
            "Restore broker connection",
            "Platform initiates full broker state reconciliation",
            "Reconciliation verified successfully",
            "Gate set to STOPPED for operator review before trading",
        ],
        "parameters": [],
    },
    "spam": {
        "id": "spam",
        "title": "Order rate limit enforcement",
        "summary": "A strategy sends orders faster than its rate limit.",
        "what_it_does": "Configures a strict order rate limit and fires a rapid burst of orders. Verifies that orders exceeding the per-minute limit are rejected by the platform.",
        "steps": [
            "Set strategy rate limit to max allowed orders/minute",
            "Strategy emits rapid order burst",
            "First orders approved within rate limit",
            "Subsequent orders blocked with RISK_RATE_LIMIT",
        ],
        "parameters": [
            {
                "name": "max_orders_per_minute",
                "label": "Max orders / min",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 10,
                "description": "Allowed orders per minute",
            },
            {
                "name": "orders_sent",
                "label": "Orders burst count",
                "type": "number",
                "default": 4,
                "min": 2,
                "max": 20,
                "description": "Rapid orders sent",
            },
        ],
    },
    "stale_feed": {
        "id": "stale_feed",
        "title": "Stale market feed protection",
        "summary": "The latest market price becomes too old to trust.",
        "what_it_does": "Simulates a price feed outage where tick data is older than the max freshness threshold. Verifies that orders are blocked rather than traded on old prices.",
        "steps": [
            "Artificially age market tick timestamp past freshness threshold",
            "Strategy emits order intent based on market mark",
            "Risk gateway detects stale market mark and blocks order with RISK_STALE_MARKET_DATA",
        ],
        "parameters": [
            {
                "name": "symbol",
                "label": "Symbol",
                "type": "text",
                "default": "LAB",
                "description": "Trading symbol",
            }
        ],
    },
    "drift": {
        "id": "drift",
        "title": "Position drift detection",
        "summary": "The broker reports a position AlgoShield cannot explain.",
        "what_it_does": "Injects an unexplained phantom position directly into broker records. Verifies that reconciliation flags the mismatch and halts the trading gate to UNCERTAIN.",
        "steps": [
            "Inject unexplained shares into broker account",
            "Run reconciliation comparison against local fill ledger",
            "Drift detected and verified status set to FAILED",
            "Platform fails closed to prevent trading on corrupted inventory",
        ],
        "parameters": [
            {
                "name": "injected_quantity",
                "label": "Drift shares",
                "type": "number",
                "default": 7,
                "min": 1,
                "max": 100,
                "description": "Unexplained shares to inject",
            }
        ],
    },
    "clear_drift": {
        "id": "clear_drift",
        "title": "Clear position drift",
        "summary": "The injected broker mismatch is removed and checked again.",
        "what_it_does": "Removes previously injected broker discrepancies and re-reconciles to confirm clean operational status.",
        "steps": [
            "Remove injected discrepancy from broker",
            "Run reconciliation against broker positions",
            "Verify all differences resolved to zero and gate restored to STOPPED",
        ],
        "parameters": [],
    },
    "kill_partial": {
        "id": "kill_partial",
        "title": "Kill switch after partial fill",
        "summary": "The kill switch runs while an order is partly filled.",
        "what_it_does": "Partially fills an order, then triggers the platform kill switch. Verifies that open orders are cancelled, remaining positions are flattened, and safe state is verified within 10 seconds.",
        "steps": [
            "Execute partial fill on an open order",
            "Trigger emergency kill switch",
            "Close execution gate and cancel remaining unfilled shares",
            "Flatten filled shares at broker",
            "Issue verified kill certificate within 10s SLA",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 100,
                "min": 10,
                "max": 1000,
                "description": "Order size",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 40,
                "min": 1,
                "max": 999,
                "description": "Executed shares before kill",
            },
        ],
    },
    "broker_update": {
        "id": "broker_update",
        "title": "Broker update event stream",
        "summary": "A partial fill arrives as a broker event.",
        "what_it_does": "Submits an order and syncs incoming asynchronous broker events. Verifies that trade confirmations update order status and positions correctly.",
        "steps": [
            "Submit order intent",
            "Broker executes trade and emits event",
            "Platform syncs broker event stream",
            "Order and position updated from fill evidence",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 100,
                "min": 10,
                "max": 1000,
                "description": "Order quantity",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 40,
                "min": 1,
                "max": 999,
                "description": "Executed quantity",
            },
        ],
    },
    "disconnect_recovery": {
        "id": "disconnect_recovery",
        "title": "Recovery after disconnect",
        "summary": "A fill happens while the platform is disconnected.",
        "what_it_does": "Disconnects platform while an order is in flight, executes a trade on the broker, then reconnects. Verifies that reconnect reconciliation recovers the fill without loss.",
        "steps": [
            "Submit order and disconnect platform",
            "Broker executes trade while platform is offline",
            "Reconnect broker connection",
            "Reconciliation detects offline execution and recovers missing fill",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 100,
                "min": 10,
                "max": 1000,
                "description": "Order quantity",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 40,
                "min": 1,
                "max": 999,
                "description": "Executed quantity",
            },
        ],
    },
    "concurrent_position_race": {
        "id": "concurrent_position_race",
        "title": "Concurrent order race condition",
        "summary": "Two orders try to use the same position capacity at once.",
        "what_it_does": "Fires two simultaneous orders in parallel threads that together exceed the position limit. Verifies atomic locking allows only one order through.",
        "steps": [
            "Set max position to limit",
            "Two worker threads concurrently submit orders exceeding limit",
            "Platform lock ensures serialized atomic evaluation",
            "First order approved; second order blocked safely",
        ],
        "parameters": [
            {
                "name": "max_position",
                "label": "Max position limit",
                "type": "number",
                "default": 100,
                "min": 20,
                "max": 500,
                "description": "Position limit",
            },
            {
                "name": "order_size",
                "label": "Concurrent order size",
                "type": "number",
                "default": 60,
                "min": 10,
                "max": 300,
                "description": "Size of each competing order",
            },
        ],
    },
    "account_risk": {
        "id": "account_risk",
        "title": "Account-level net exposure limit",
        "summary": "A trade would push the whole account beyond its net limit.",
        "what_it_does": "Enforces platform-level risk limits independent of strategy code. Verifies that an order exceeding the account net position limit is blocked.",
        "steps": [
            "Set account net position limit",
            "Strategy submits order exceeding limit",
            "Account risk policy intercepts intent",
            "Blocked by RISK_ACCOUNT_NET_POSITION",
        ],
        "parameters": [
            {
                "name": "account_net_limit",
                "label": "Account net limit",
                "type": "number",
                "default": 1,
                "min": 1,
                "max": 50,
                "description": "Net position cap for account",
            },
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 100,
                "description": "Order size to test",
            },
        ],
    },
    "opposing_gross_exposure": {
        "id": "opposing_gross_exposure",
        "title": "Opposing gross exposure containment",
        "summary": "Opposing trades hide risk when only net position is viewed.",
        "what_it_does": "Tests gross exposure limits across strategies. Prevents opposing strategies from accumulating large gross exposure even if net is near zero.",
        "steps": [
            "Set account gross limit",
            "Strategy submits order that exceeds gross capacity",
            "Platform calculates gross exposure across all strategies",
            "Blocked by RISK_ACCOUNT_GROSS_POSITION",
        ],
        "parameters": [
            {
                "name": "account_gross_limit",
                "label": "Account gross limit",
                "type": "number",
                "default": 1,
                "min": 1,
                "max": 50,
                "description": "Gross exposure cap",
            },
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 100,
                "description": "Order size to test",
            },
        ],
    },
    "limit_lowered_below_position": {
        "id": "limit_lowered_below_position",
        "title": "Risk limit lowered below existing position",
        "summary": "A position is already larger than a newly lowered limit.",
        "what_it_does": "Reduces a position limit below currently open inventory. Verifies that risk-increasing orders are blocked, but risk-reducing orders remain permitted.",
        "steps": [
            "Open initial position",
            "Admin reduces max position limit below current position",
            "Attempt BUY (risk-increasing) -> Blocked by RISK_MAX_POSITION",
            "Attempt SELL (risk-reducing) -> Approved",
        ],
        "parameters": [
            {
                "name": "current_position",
                "label": "Existing position",
                "type": "number",
                "default": 80,
                "min": 10,
                "max": 200,
                "description": "Current open shares",
            },
            {
                "name": "lowered_limit",
                "label": "Lowered limit",
                "type": "number",
                "default": 50,
                "min": 5,
                "max": 150,
                "description": "Newly lowered limit",
            },
        ],
    },
    "daily_loss_mark_breach": {
        "id": "daily_loss_mark_breach",
        "title": "Daily loss limit breach",
        "summary": "A price move takes the strategy beyond its daily loss limit.",
        "what_it_does": "Opens a position and simulates an adverse market tick breaching the daily loss limit. Verifies that new orders are immediately blocked.",
        "steps": [
            "Open position at current market price",
            "Market drops, breaching max daily loss limit",
            "Strategy attempts new buy order",
            "Risk gateway blocks order with RISK_MAX_DAILY_LOSS",
        ],
        "parameters": [
            {
                "name": "daily_loss_limit",
                "label": "Daily loss limit",
                "type": "number",
                "default": 1,
                "min": 1,
                "max": 100,
                "description": "Max allowed loss",
            },
            {
                "name": "drop_price",
                "label": "Drop price",
                "type": "number",
                "default": 90,
                "min": 10,
                "max": 99,
                "description": "Adverse market price",
            },
        ],
    },
    "late_fill_after_cancel": {
        "id": "late_fill_after_cancel",
        "title": "Late fill after cancellation",
        "summary": "A fill arrives after cancellation was requested.",
        "what_it_does": "Cancels an open order, but broker executes a late fill before processing the cancel. Verifies that the platform honors the fill because broker executions are financial truth.",
        "steps": [
            "Partially fill shares on order",
            "Send cancel request for remaining shares",
            "Broker executes shares late before cancel takes effect",
            "Platform updates total filled quantity accurately",
        ],
        "parameters": [
            {
                "name": "initial_fill",
                "label": "Initial fill",
                "type": "number",
                "default": 4,
                "min": 1,
                "max": 50,
                "description": "Initial executed shares",
            },
            {
                "name": "late_fill",
                "label": "Late fill",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 50,
                "description": "Late executed shares",
            },
        ],
    },
    "kill_late_fill": {
        "id": "kill_late_fill",
        "title": "Late fill during kill switch",
        "summary": "An execution arrives while the kill switch is closing exposure.",
        "what_it_does": "Simulates an execution arriving in the middle of emergency kill shutdown. Verifies that the kill routine absorbs the execution and still flattens everything.",
        "steps": [
            "Trigger kill switch while order is outstanding",
            "Broker reports late fill during cancellation",
            "Kill routine incorporates late fill into flattening cycle",
            "Verifies zero remaining open orders and flat position",
        ],
        "parameters": [
            {
                "name": "order_quantity",
                "label": "Order quantity",
                "type": "number",
                "default": 10,
                "min": 2,
                "max": 100,
                "description": "Order size",
            },
            {
                "name": "fill_quantity",
                "label": "Fill quantity",
                "type": "number",
                "default": 4,
                "min": 1,
                "max": 50,
                "description": "Executed size",
            },
        ],
    },
    "broker_failure_during_kill": {
        "id": "broker_failure_during_kill",
        "title": "Broker failure during kill shutdown",
        "summary": "The broker becomes unavailable during the kill process.",
        "what_it_does": "Broker drops while kill switch is attempting to flatten positions. Verifies that the platform never claims success and marks state as UNCERTAIN.",
        "steps": [
            "Trigger kill switch",
            "Broker connection drops during order cancellation",
            "Platform records FAILED kill certificate due to broker error",
            "Trading gate set to UNCERTAIN for manual operator review",
        ],
        "parameters": [],
    },
    "restart_fail_closed": {
        "id": "restart_fail_closed",
        "title": "Crash/restart fail-closed recovery",
        "summary": "The platform restarts after trading activity.",
        "what_it_does": "Simulates a sudden power outage or reboot. Verifies that upon reboot, trading starts disabled in RECOVERING state until reconciliation completes.",
        "steps": [
            "Simulate active trading and sudden platform restart",
            "Inspect initial boot state of fresh engine instance",
            "Verify gate starts in RECOVERING and runtime is disabled",
            "No orders are placed before reconciliation verifies truth",
        ],
        "parameters": [],
    },
    "stale_broker_evidence": {
        "id": "stale_broker_evidence",
        "title": "Stale broker snapshot evidence",
        "summary": "The last broker snapshot is too old to trust.",
        "what_it_does": "Simulates broker snapshot timestamp exceeding maximum age. Verifies that risk gateway blocks new orders until fresh broker truth is verified.",
        "steps": [
            "Age broker snapshot timestamp past freshness limit",
            "Strategy submits order intent",
            "Platform blocks order with RISK_STALE_BROKER_STATE",
        ],
        "parameters": [],
    },
    "invalid_price": {
        "id": "invalid_price",
        "title": "Unreasonable limit price check",
        "summary": "A limit order price is far from the trusted market mark.",
        "what_it_does": "Strategy submits a BUY limit order priced dramatically higher than current market mark. Verifies price reasonability rules block fat-finger errors.",
        "steps": [
            "Market mark is at reference price",
            "Strategy submits BUY limit order far outside threshold",
            "Risk gateway detects price deviation exceeding threshold",
            "Blocked with RISK_PRICE_REASONABILITY",
        ],
        "parameters": [
            {
                "name": "market_price",
                "label": "Market price",
                "type": "number",
                "default": 100,
                "min": 1,
                "max": 1000,
                "description": "Prevailing market price",
            },
            {
                "name": "limit_price",
                "label": "Limit order price",
                "type": "number",
                "default": 10000,
                "min": 100,
                "max": 100000,
                "description": "Limit order price",
            },
        ],
    },
}


def build_simple_explanation(
    scenario: str, passed: bool, evidence: dict, decisions: list, params: dict, platform
) -> dict:
    meta = SCENARIO_METADATA.get(scenario, {})
    title = meta.get("title", scenario.replace("_", " ").title())

    if not passed:
        return {
            "summary": f"{title} did not pass the required safety checks.",
            "explanation": "The backend did not observe the expected safe response. Review technical evidence for details.",
            "simple_evidence": {
                "Safety Verdict": "FAIL",
                "Reason": "Invariant expectation violated",
            },
        }

    # Custom plain explanations for passed tests
    if scenario == "partial":
        order_qty = int(params.get("order_quantity", 100))
        fill_qty = int(params.get("fill_quantity", 40))
        phantom = max(0, order_qty - fill_qty)
        return {
            "summary": f"Only executed quantity ({fill_qty}) was counted; unfilled quantity ({phantom}) did not become a position.",
            "explanation": f"Safe: Strategy requested {order_qty} shares, but the broker executed only {fill_qty}. AlgoShield updated your inventory by exactly {fill_qty} shares, preventing {phantom} unexecuted phantom shares from entering your account.",
            "simple_evidence": {
                "Requested Shares": order_qty,
                "Executed Fill": fill_qty,
                "Verified Position": fill_qty,
                "Phantom Shares Blocked": phantom,
            },
        }

    if scenario == "rejection":
        order_qty = int(params.get("order_quantity", 5))
        return {
            "summary": "The rejected order created no fill and no trading position.",
            "explanation": f"Safe: The broker rejected your {order_qty}-share order. AlgoShield recorded the REJECTED status and ensured zero position and zero financial liability was created.",
            "simple_evidence": {
                "Requested Shares": order_qty,
                "Broker Status": "REJECTED",
                "Position Created": 0,
            },
        }

    if scenario == "position_limit":
        init_fill = int(params.get("initial_fill", 80))
        block_qty = int(params.get("blocked_quantity", 10))
        return {
            "summary": "AlgoShield blocked the extra order before it reached the broker.",
            "explanation": f"Safe: With {init_fill} shares already held, an additional {block_qty}-share order exceeded the position limit. The risk gateway blocked it immediately.",
            "simple_evidence": {
                "Holding Position": init_fill,
                "Excess Blocked": block_qty,
                "Risk Decision": "RISK_MAX_POSITION",
                "Orders Sent to Broker": 0,
            },
        }

    if scenario == "duplicate_fill":
        fill_qty = int(params.get("fill_quantity", 4))
        return {
            "summary": "The duplicate was ignored, so position and P&L were not counted twice.",
            "explanation": f"Safe: The broker sent the same {fill_qty}-share fill confirmation twice. AlgoShield detected the existing fill ID and safely discarded the duplicate.",
            "simple_evidence": {
                "First Fill Accepted": f"{fill_qty} shares",
                "Duplicate Event": "Safely Discarded",
                "Double-Counting Prevented": "Yes",
                "Net Position": fill_qty,
            },
        }

    if scenario == "conflicting_fill":
        return {
            "summary": "AlgoShield rejected the conflict and closed the trading gate for review.",
            "explanation": "Safe: An incoming fill event attempted to reuse a fill ID with contradictory pricing. AlgoShield rejected the corrupt event and set the gate to UNCERTAIN.",
            "simple_evidence": {
                "Conflict Detected": "Yes",
                "Corrupt Record Allowed": "No",
                "Trading Gate": "UNCERTAIN (Halted)",
            },
        }

    if scenario == "missed_fill":
        fill_qty = int(params.get("fill_quantity", 4))
        return {
            "summary": "Reconciliation found the real fill and repaired local state from broker evidence.",
            "explanation": f"Safe: A {fill_qty}-share execution was missed by local feeds. Scheduled reconciliation queried broker records and restored the missing position.",
            "simple_evidence": {
                "Position Before Reconcile": 0,
                "Position After Reconcile": fill_qty,
                "Broker Fill Recovered": "Yes",
            },
        }

    if scenario == "unknown_submission":
        return {
            "summary": "The order stayed UNKNOWN and AlgoShield did not blindly submit it again.",
            "explanation": "Safe: Order acknowledgement timed out. Instead of placing a duplicate order that could double your risk, the order was marked UNKNOWN until verified.",
            "simple_evidence": {
                "Order Status": "UNKNOWN",
                "Duplicate Re-orders Placed": 0,
                "Risk Reserved": "Yes",
            },
        }

    if scenario == "disconnect":
        return {
            "summary": "AlgoShield stopped trusting broker state and blocked new risk.",
            "explanation": "Safe: Connection to the broker was lost. AlgoShield immediately set the trading gate to UNCERTAIN and blocked all new orders.",
            "simple_evidence": {
                "Broker Connection": "DISCONNECTED",
                "Trading Gate": "UNCERTAIN",
                "New Trades Blocked": "Yes",
            },
        }

    if scenario == "reconnect":
        return {
            "summary": "Connectivity returned without silently declaring trading safe.",
            "explanation": "Safe: Reconnection succeeded and reconciled broker state. Trading gate was set to STOPPED for operator review before resuming.",
            "simple_evidence": {
                "Broker Connection": "RESTORED",
                "Reconciliation": "MATCHED",
                "Trading Gate": "STOPPED",
            },
        }

    if scenario == "spam":
        max_opm = int(params.get("max_orders_per_minute", 2))
        num_orders = int(params.get("orders_sent", 4))
        return {
            "summary": "Orders over the allowed rate were blocked by the platform.",
            "explanation": f"Safe: Strategy attempted {num_orders} orders in a burst. Rate limiting approved {max_opm} orders and blocked the remaining {num_orders - max_opm} orders.",
            "simple_evidence": {
                "Rate Limit": f"{max_opm}/min",
                "Orders Attempted": num_orders,
                "Approved": max_opm,
                "Blocked": num_orders - max_opm,
            },
        }

    if scenario == "stale_feed":
        return {
            "summary": "AlgoShield blocked a new order instead of trading on stale data.",
            "explanation": "Safe: The latest market price was older than freshness limits. Risk controls blocked order execution on unreliable pricing.",
            "simple_evidence": {
                "Market Price Age": "Expired / Stale",
                "Order Decision": "RISK_STALE_MARKET_DATA",
                "Stale Trades Placed": 0,
            },
        }

    if scenario == "drift":
        injected_qty = int(params.get("injected_quantity", 7))
        return {
            "summary": "Reconciliation detected the mismatch and failed closed.",
            "explanation": f"Safe: Found {injected_qty} unexplained shares on the broker. Reconciliation failed the verification and set the trading gate to UNCERTAIN.",
            "simple_evidence": {
                "Drift Detected": f"{injected_qty} shares",
                "Reconciliation": "FAILED (Mismatch)",
                "Trading Gate": "UNCERTAIN",
            },
        }

    if scenario == "clear_drift":
        return {
            "summary": "AlgoShield rechecked broker truth instead of clearing the warning blindly.",
            "explanation": "Safe: Discrepancy was resolved and reconciliation confirmed exact agreement between broker truth and local ledgers.",
            "simple_evidence": {
                "Discrepancies": "None",
                "Reconciliation": "VERIFIED",
                "Trading Gate": "STOPPED",
            },
        }

    if scenario == "kill_partial":
        fill_qty = int(params.get("fill_quantity", 40))
        return {
            "summary": "The platform cancelled or closed remaining exposure and verified the result.",
            "explanation": f"Safe: Kill switch activated with {fill_qty} shares filled. Platform cancelled open balance, flattened {fill_qty} shares, and verified flat state within SLA.",
            "simple_evidence": {
                "Kill SLA": "10.0s",
                "Kill Certificate": "SUCCESS",
                "Open Orders": 0,
                "Net Position Flat": "Yes",
            },
        }

    if scenario == "broker_update":
        fill_qty = int(params.get("fill_quantity", 40))
        return {
            "summary": "The event updated the order and position using actual fill evidence.",
            "explanation": f"Safe: Asynchronous broker trade execution of {fill_qty} shares was synced directly into the strategy's attributed ledger.",
            "simple_evidence": {
                "Broker Events Processed": 1,
                "Executed Shares": fill_qty,
                "Strategy Position": fill_qty,
            },
        }

    if scenario == "disconnect_recovery":
        fill_qty = int(params.get("fill_quantity", 40))
        return {
            "summary": "Reconnect reconciliation recovered the missed fill and synchronized local state.",
            "explanation": f"Safe: A {fill_qty}-share trade completed while offline. Upon reconnecting, reconciliation matched broker records and synchronized local position.",
            "simple_evidence": {
                "Offline Trade": f"{fill_qty} shares",
                "Recovered Fill": fill_qty,
                "Synchronized Position": fill_qty,
            },
        }

    if scenario == "concurrent_position_race":
        max_pos = int(params.get("max_position", 100))
        order_sz = int(params.get("order_size", 60))
        return {
            "summary": "Atomic risk checks allowed only the order that fit within the limit.",
            "explanation": f"Safe: Two concurrent orders for {order_sz} shares raced for {max_pos} capacity. Atomic evaluation approved the first and blocked the second.",
            "simple_evidence": {
                "Concurrent Orders": 2,
                "Approved": 1,
                "Blocked (Exceeded Limit)": 1,
                "Overfill Race Prevented": "Yes",
            },
        }

    if scenario == "account_risk":
        acc_net = int(params.get("account_net_limit", 1))
        order_qty = int(params.get("order_quantity", 2))
        return {
            "summary": "The account-level risk rule blocked the trade.",
            "explanation": f"Safe: Order for {order_qty} shares would have exceeded the account net position limit of {acc_net}. Platform risk stopped the trade.",
            "simple_evidence": {
                "Account Net Limit": acc_net,
                "Attempted Shares": order_qty,
                "Decision": "RISK_ACCOUNT_NET_POSITION",
            },
        }

    if scenario == "opposing_gross_exposure":
        acc_gross = int(params.get("account_gross_limit", 1))
        order_qty = int(params.get("order_quantity", 2))
        return {
            "summary": "AlgoShield measured gross strategy exposure and blocked the excess.",
            "explanation": f"Safe: Order for {order_qty} shares exceeded the account gross limit ({acc_gross}). Opposing positions cannot bypass platform gross limits.",
            "simple_evidence": {
                "Account Gross Limit": acc_gross,
                "Attempted Shares": order_qty,
                "Decision": "RISK_ACCOUNT_GROSS_POSITION",
            },
        }

    if scenario == "limit_lowered_below_position":
        cur_pos = int(params.get("current_position", 80))
        lowered = int(params.get("lowered_limit", 50))
        return {
            "summary": "Increasing risk was blocked while a reducing trade remained allowed.",
            "explanation": f"Safe: With {cur_pos} shares open and limit lowered to {lowered}, buy orders were blocked but sell orders (reducing exposure) were permitted.",
            "simple_evidence": {
                "Current Position": cur_pos,
                "Lowered Limit": lowered,
                "Buy (Increase Risk)": "BLOCKED",
                "Sell (Reduce Risk)": "ALLOWED",
            },
        }

    if scenario == "daily_loss_mark_breach":
        return {
            "summary": "AlgoShield blocked further risk after the loss threshold was breached.",
            "explanation": "Safe: An adverse price drop exceeded the daily loss limit. The risk engine immediately blocked new risk-increasing orders.",
            "simple_evidence": {
                "Loss Limit Breached": "Yes",
                "Decision": "RISK_MAX_DAILY_LOSS",
                "New Risk Allowed": "No",
            },
        }

    if scenario == "late_fill_after_cancel":
        init_fill = int(params.get("initial_fill", 4))
        late_fill = int(params.get("late_fill", 2))
        total = init_fill + late_fill
        return {
            "summary": "The late execution was still recorded because fills remain financial truth.",
            "explanation": f"Safe: Broker reported a late fill of {late_fill} shares after cancellation. AlgoShield updated the total to {total} to preserve financial truth.",
            "simple_evidence": {
                "Initial Fill": init_fill,
                "Late Fill": late_fill,
                "Total Verified Fills": total,
            },
        }

    if scenario == "kill_late_fill":
        return {
            "summary": "The kill process included the late fill before verifying the final state.",
            "explanation": "Safe: A late fill occurred during emergency shutdown. The kill routine absorbed the execution into its flattening cycle and verified flat state.",
            "simple_evidence": {
                "Late Fill Absorbed": "Yes",
                "Kill Certificate": "SUCCESS",
                "Final Position": 0,
            },
        }

    if scenario == "broker_failure_during_kill":
        return {
            "summary": "AlgoShield reported uncertainty instead of claiming the account was flat.",
            "explanation": "Safe: Broker failed during kill shutdown. AlgoShield refused to fabricate a flat state, issuing a FAILED certificate and setting gate to UNCERTAIN.",
            "simple_evidence": {
                "Broker Accessible": "No",
                "Kill Certificate": "FAILED",
                "Trading Gate": "UNCERTAIN",
            },
        }

    if scenario == "restart_fail_closed":
        return {
            "summary": "It restarted with trading closed until reconciliation and explicit resume.",
            "explanation": "Safe: After rebooting, the platform started in RECOVERING with trading disabled. No orders could execute until operator reconciliation ran.",
            "simple_evidence": {
                "Boot Gate": "RECOVERING",
                "Trading Enabled": "No (Fail-closed)",
                "Reconciliation Required": "Yes",
            },
        }

    if scenario == "stale_broker_evidence":
        return {
            "summary": "AlgoShield blocked new exposure until fresh broker evidence is available.",
            "explanation": "Safe: Broker snapshot evidence was older than allowed freshness limits. Orders were blocked until fresh broker truth was verified.",
            "simple_evidence": {
                "Broker Snapshot": "Stale",
                "Decision": "RISK_STALE_BROKER_STATE",
                "New Exposure Allowed": "No",
            },
        }

    if scenario == "invalid_price":
        market_p = params.get("market_price", 100)
        limit_p = params.get("limit_price", 10000)
        return {
            "summary": "The price-reasonability rule blocked the order.",
            "explanation": f"Safe: A BUY limit order was priced at {limit_p} against a market mark of {market_p}. Price reasonability blocked the abnormal price.",
            "simple_evidence": {
                "Market Price": str(market_p),
                "Submitted Limit Price": str(limit_p),
                "Decision": "RISK_PRICE_REASONABILITY",
            },
        }

    return {
        "summary": meta.get("summary", "Scenario passed."),
        "explanation": meta.get("what_it_does", "Scenario verified safe operation."),
        "simple_evidence": {"Safety Verdict": "PASS"},
    }

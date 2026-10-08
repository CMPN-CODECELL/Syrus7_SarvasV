PS-06: Algo Trading Platform
Background : An AI can build a trading strategy quickly. The real challenge is handling partial fills, server restarts, order failures, and runaway strategies while enforcing risk limits.
Problem Statement : Build an algo trading platform on the 021 developer APIs where risk limits remain effective even when strategies fail. Evaluation will focus on hidden tests, a live change request, and a technical viva—not strategy profitability.
Objective
Your system should:
Strategy subscription & candle creation: Users can create an account and subscribe to any strategy. The platform must build 1-minute and 5-minute candles from raw ticks and use them in at least one strategy entry condition.
Live trading: Orders are placed against the sandbox, fills are tracked, and partial fills and rejections are handled. The strategy's position must remain in sync with the account, with the exact list of trades and net P&L after charges.
Risk controls: Each strategy must have limits for maximum daily loss, maximum position size and maximum orders per minute. A kill switch must stop all 
strategies, cancel open orders and close positions within 10 seconds. These limits must be enforced by the platform, not the strategy code.
Multiple strategies: At least three strategies must run simultaneously on the same account. Each strategy must maintain its own P&L and position, even when one is long and another is short on the same stock.
Dashboard: Users can see which strategies they are subscribed to and their live P&L.

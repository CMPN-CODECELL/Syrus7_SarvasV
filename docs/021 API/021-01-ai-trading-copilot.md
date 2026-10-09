# Copilot, Not Autopilot; AI Trading Copilot

## The challenge

**Build an AI copilot that lets a trader query and act on their 021 trading account in plain English, and that can never cause a trade the trader did not clearly approve.**

Any team can wire an LLM to an order API in a few hours. That is not what we are scoring. We are scoring what happens when the model misreads a request, the network drops mid-order, the price moves while the user is deciding, or a stock name contains instructions aimed at your model. Real money systems fail at those edges, and so will your copilot unless you design for them.

|                       |                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------- |
| You get               | 021 Developer Sandbox: market data, a simulated account and order APIs, with realistic failures switched on |
| You may use           | Any language, any framework, any LLM provider, and any AI coding tool                                       |
| You will be judged on | Hidden test scenarios, a live change request on the day, and a technical viva, not on the slides            |

## What you're building

The copilot has four levels. Each level builds on the one before it. A rock-solid L2 beats a shaky L4: we score depth before breadth.

1. **L1: Answer questions (read-only).** "What's my P&L today?", "Which positions are down more than 5%?", "What did I pay on average for INFY?", "Show NIFTY options near the money for this expiry."
2. **L2: Place, modify and cancel orders, with confirmation.** "Buy 10 Reliance at market", "Sell half my TCS", "Move my stop-loss on HDFC Bank up to 1640." The copilot turns the request into an exact order, shows it, and sends it only after the trader approves that exact order.
3. **L3: Standing instructions.** "If Reliance drops below 2800, buy 10." "Tell me when any holding falls 3% in a day." These are watched against the live price feed. They must survive your server restarting, and must fire once, not once per price update.
4. **L4: Multi-step plans.** "Exit all my losing intraday positions." "Rebalance so no single stock is more than 20% of my portfolio." The copilot proposes a plan of several orders, the trader approves it, and the copilot reports exactly what happened, including when some orders fill and others are rejected.

The interface should be a web chat.

## The sandbox misbehaves on purpose

The 021 Developer Sandbox behaves like a real broker on a busy day. The full API reference and keys are shared at kickoff. These behaviours are switched on during development and during judging. Expect issues such as rate limits, random server errors where a call returns HTTP 500 or 503, order timeouts, and so on.

## Automatic disqualification
Claims in the README the code does not back up.

---

*Disclaimer: We may make minor changes to this problem statement on the day of the hackathon. Any changes will be communicated to all participating teams.*

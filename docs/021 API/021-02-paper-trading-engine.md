# The Ledger Never Lies; Paper Trading Engine

## The challenge

**Build a paper trading engine that fills simulated orders against live 021 market data, exactly as a real exchange would, and whose money never goes wrong by a single paisa.**

A buy button, a portfolio screen and a balance that goes down are an afternoon's work with an AI assistant. That is not what we are scoring. We are scoring whether a limit order fills at the right moment and at the right price, whether a stop-loss behaves correctly, and whether every rupee can be traced after a crash. Real brokers get these wrong in production, and so will you unless you design for them.

|                       |                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| You get               | 021 Developer Sandbox: a live price and market-depth feed, recorded market days for replay, and an API contract your engine must implement |
| You may use           | Any language, any framework, any database, and any AI coding tool                                                                          |
| You will be judged on | Hidden test scenarios run against your engine, a live change request on the day, and a technical viva, not on the slides                   |

## What you're building

The engine has three levels. Each level builds on the one before it. A rock-solid L2 beats a shaky L3: we score depth before breadth.

1. **L1: Market and limit orders for delivery (CNC) on NSE equities.** Place, modify and cancel orders. Holdings, average buy price, realised and unrealised P&L, and a cash ledger.
2. **L2: Stop-loss orders and realistic fills.** SL and SL-M orders. Fills use market depth: a 5,000-share market order does not fill at the best price if only 200 shares are offered there. Limit orders can fill partly and stay open for the rest.
3. **L3: Intraday (MIS) trading.** Leverage and margin as per the margin table we publish at kickoff. Orders rejected when margin is short. All open MIS positions squared off automatically at 15:20. Charges (brokerage, STT, exchange fees, GST, stamp duty) applied per the published charges table, so every trade's net P&L matches a contract note.


Your engine must implement the API contract we share at kickoff, because our test harness drives it through that API.


## The market feed misbehaves on purpose

The 021 Developer Sandbox streams prices and market depth the way a real feed does on a busy day. The full feed reference is shared at kickoff. These behaviours are switched on during development and during judging. Expect issues such as out-of-order ticks, duplicate ticks, feed drops, tick bursts, and so on.

## Automatic disqualification
Claims in the README the code does not back up.

---

*Disclaimer: We may make minor changes to this problem statement on the day of the hackathon. Any changes will be communicated to all participating teams.*

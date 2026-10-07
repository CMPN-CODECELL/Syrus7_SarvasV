# Finance & Trading Glossary for the Team

Only learn what is needed for PS-06.

| Term | Meaning |
|---|---|
| Broker | Company/API through which orders reach the market/sandbox |
| Exchange | Marketplace where buyers and sellers match |
| OMS | Order Management System; receives/routes/tracks orders |
| RMS | Risk Management System; blocks unsafe orders/exposure |
| Order | Request to buy or sell |
| Fill / Execution | Quantity that actually traded |
| Partial Fill | Only part of an order executed |
| Position | Actual net quantity currently held |
| Long | Positive position, e.g. +100 |
| Short | Negative position, e.g. -60 |
| Market Order | Execute at available market price |
| Limit Order | Execute only at specified price or better |
| Open Order | Submitted but not fully complete/cancelled |
| Rejected Order | Broker/exchange refused the order |
| Cancelled Order | Remaining open quantity was cancelled |
| Tick | One market-data update |
| Candle | Summary of ticks over a time window |
| OHLCV | Open, High, Low, Close, Volume |
| Realized P&L | Profit/loss from closed quantity |
| Unrealized P&L | Current profit/loss on still-open quantity |
| Gross P&L | Realized + unrealized before charges |
| Net P&L | Gross P&L minus charges |
| Average Price | Weighted average entry cost of current position |
| Charges | Brokerage/taxes/exchange/regulatory fees |
| Reconciliation | Comparing our state with broker-observed state |
| Idempotency | Reprocessing same event does not change state twice |

## Golden rules
1. **Order quantity is not position.**
2. **Only fills change financial state.**
3. **Broker account position may be netted; strategy positions must remain separately attributable.**
4. **A successful order API response does not necessarily mean a trade happened.**
5. **After uncertainty/failure, reconcile before resuming.**

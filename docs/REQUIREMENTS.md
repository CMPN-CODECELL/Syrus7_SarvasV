# Requirements

## Official PS-06 requirements

### 1. Account + strategy subscription
- User can create an account.
- User can subscribe to strategies.
- At least 3 strategies must run simultaneously on the same account.

### 2. Market data + candles
- Consume raw ticks.
- Build 1-minute candles.
- Build 5-minute candles.
- At least one strategy must use generated candles in an entry condition.

### 3. Live trading
- Send orders to the 021 sandbox.
- Track order lifecycle.
- Handle fills.
- Handle partial fills.
- Handle rejections.
- Keep strategy position synchronized with account reality.
- Maintain exact trade list.
- Show net P&L after charges.

### 4. Risk controls
Per strategy:
- maximum daily loss;
- maximum position size;
- maximum orders per minute.

Rules must be enforced by the platform, never trusted to strategy code.

### 5. Kill switch
Must:
1. stop all strategies;
2. block new order intents;
3. cancel open orders;
4. close positions;
5. verify safe final state;
6. satisfy the sponsor's 10-second requirement.

Exact interpretation of the 10-second SLA must be confirmed with 021.

### 6. Multiple opposing strategies
Example:
- Strategy A: +100 RELIANCE
- Strategy B: -60 RELIANCE
- Strategy C: +20 RELIANCE

Broker/account net may be +60, while AlgoShield must preserve the independent virtual positions and P&L.

### 7. Dashboard
Must show:
- subscribed strategies;
- running/stopped state;
- live P&L.

## Evaluation implications
Because evaluation includes hidden tests, live change request and technical viva:
- state machines must be explicit;
- business logic must be modular;
- hard-coded one-off behavior is unacceptable;
- every major module must be testable in isolation;
- common changes (new risk rule, new strategy, new candle interval, new broker adapter) should be local.

## Out of scope unless core system is complete
- AI-generated strategies;
- sentiment trading;
- portfolio optimization;
- social trading;
- advanced derivatives;
- complex backtesting studio;
- mobile application;
- profitability optimization.

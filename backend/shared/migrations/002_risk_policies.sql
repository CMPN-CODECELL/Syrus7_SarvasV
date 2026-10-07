CREATE TABLE algoshield.risk_policies (
    strategy TEXT PRIMARY KEY REFERENCES algoshield.subscriptions(id),
    max_daily_loss TEXT NOT NULL CHECK (max_daily_loss::numeric > 0),
    max_position INTEGER NOT NULL CHECK (max_position > 0),
    max_orders_per_minute INTEGER NOT NULL CHECK (max_orders_per_minute > 0));
CREATE TABLE algoshield.strategy_controls (
    strategy TEXT PRIMARY KEY REFERENCES algoshield.subscriptions(id),
    state TEXT NOT NULL CHECK (state IN ('RUNNING','HALTED','LOSS_HALTED')),
    reason TEXT NOT NULL, updated DOUBLE PRECISION NOT NULL);
CREATE INDEX orders_strategy_rate ON algoshield.orders(strategy,account,emergency,created);
CREATE INDEX fills_strategy_projection ON algoshield.fills(account,strategy,timestamp,id);

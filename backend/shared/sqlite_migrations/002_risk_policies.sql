CREATE TABLE risk_policies (
    strategy TEXT PRIMARY KEY REFERENCES subscriptions(id),
    max_daily_loss TEXT NOT NULL CHECK (CAST(max_daily_loss AS REAL) > 0),
    max_position INTEGER NOT NULL CHECK (max_position > 0),
    max_orders_per_minute INTEGER NOT NULL CHECK (max_orders_per_minute > 0));
CREATE TABLE strategy_controls (
    strategy TEXT PRIMARY KEY REFERENCES subscriptions(id),
    state TEXT NOT NULL CHECK (state IN ('RUNNING','HALTED','LOSS_HALTED')),
    reason TEXT NOT NULL, updated REAL NOT NULL);
CREATE INDEX orders_strategy_rate ON orders(strategy,account,emergency,created);
CREATE INDEX fills_strategy_projection ON fills(account,strategy,timestamp,id);

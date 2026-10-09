CREATE TABLE broker_order_mappings (
    platform_order_id TEXT PRIMARY KEY REFERENCES orders(id),
    provider TEXT NOT NULL,
    provider_order_id TEXT NOT NULL,
    account TEXT NOT NULL,
    exchange TEXT NOT NULL,
    token INTEGER NOT NULL,
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    created REAL NOT NULL,
    UNIQUE(provider, account, provider_order_id)
);

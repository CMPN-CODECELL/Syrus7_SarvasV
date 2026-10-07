-- Additive schema, scoped away from existing application/public tables.
CREATE SCHEMA IF NOT EXISTS algoshield;
CREATE TABLE algoshield.accounts (id TEXT PRIMARY KEY);
CREATE TABLE algoshield.subscriptions (
    id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES algoshield.accounts(id),
    kind TEXT NOT NULL, symbol TEXT NOT NULL);
CREATE TABLE algoshield.orders (
    id TEXT PRIMARY KEY, strategy TEXT NOT NULL REFERENCES algoshield.subscriptions(id),
    account TEXT NOT NULL REFERENCES algoshield.accounts(id), symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    quantity INTEGER NOT NULL CHECK (quantity > 0), created DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED','OPEN','PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED','UNKNOWN')),
    filled INTEGER NOT NULL DEFAULT 0 CHECK (filled >= 0 AND filled <= quantity),
    emergency INTEGER NOT NULL DEFAULT 0 CHECK (emergency IN (0,1)));
CREATE TABLE algoshield.fills (
    id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES algoshield.orders(id),
    strategy TEXT NOT NULL REFERENCES algoshield.subscriptions(id),
    account TEXT NOT NULL REFERENCES algoshield.accounts(id), symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')), quantity INTEGER NOT NULL CHECK (quantity > 0),
    price TEXT NOT NULL CHECK (price::numeric > 0), timestamp DOUBLE PRECISION NOT NULL,
    charges TEXT NOT NULL CHECK (charges::numeric >= 0));
CREATE TABLE algoshield.audit (
    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type TEXT NOT NULL, payload TEXT NOT NULL);

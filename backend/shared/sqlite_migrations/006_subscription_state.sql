-- Durable operator control for each strategy subscription.
ALTER TABLE subscriptions ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1
CHECK (enabled IN (0,1));

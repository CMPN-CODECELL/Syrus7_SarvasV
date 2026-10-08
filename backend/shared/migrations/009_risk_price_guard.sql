ALTER TABLE algoshield.risk_policies ADD COLUMN max_price_deviation_bps INTEGER NOT NULL DEFAULT 500 CHECK (max_price_deviation_bps > 0);

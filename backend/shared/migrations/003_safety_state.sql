CREATE TABLE algoshield.safety_values (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE algoshield.risk_marks (
    symbol TEXT PRIMARY KEY, price TEXT NOT NULL CHECK (price::numeric > 0),
    event_timestamp DOUBLE PRECISION NOT NULL, received_at DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('LIVE','REPLAY')));
ALTER TABLE algoshield.audit ADD COLUMN recorded_at DOUBLE PRECISION NOT NULL DEFAULT 0;

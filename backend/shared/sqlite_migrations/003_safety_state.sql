CREATE TABLE safety_values (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE risk_marks (
    symbol TEXT PRIMARY KEY, price TEXT NOT NULL CHECK (CAST(price AS REAL) > 0),
    event_timestamp REAL NOT NULL, received_at REAL NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('LIVE','REPLAY')));
ALTER TABLE audit ADD COLUMN recorded_at REAL NOT NULL DEFAULT 0;

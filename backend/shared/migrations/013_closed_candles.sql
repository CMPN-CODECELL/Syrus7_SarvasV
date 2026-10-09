CREATE TABLE algoshield.closed_candles (
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL,
    start_time BIGINT NOT NULL,
    end_time BIGINT NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume BIGINT NOT NULL,
    is_closed BOOLEAN NOT NULL DEFAULT TRUE,
    volume_available BOOLEAN NOT NULL,
    data_source TEXT NOT NULL,
    PRIMARY KEY(provider, symbol, interval_seconds, start_time)
);
CREATE INDEX closed_candles_lookup ON algoshield.closed_candles(symbol, interval_seconds, start_time DESC);

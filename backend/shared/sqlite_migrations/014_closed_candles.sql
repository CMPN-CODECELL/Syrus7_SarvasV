CREATE TABLE closed_candles (
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    end_time INTEGER NOT NULL,
    open TEXT NOT NULL,
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    volume INTEGER NOT NULL,
    is_closed INTEGER NOT NULL DEFAULT 1,
    volume_available INTEGER NOT NULL,
    data_source TEXT NOT NULL,
    PRIMARY KEY(provider, symbol, interval, start_time)
);
CREATE INDEX closed_candles_lookup ON closed_candles(symbol, interval, start_time DESC);

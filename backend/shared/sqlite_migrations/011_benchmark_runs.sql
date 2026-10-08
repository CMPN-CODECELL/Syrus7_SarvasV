CREATE TABLE benchmark_runs (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    completed_at REAL NOT NULL,
    scenario_count INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    payload_json TEXT NOT NULL);

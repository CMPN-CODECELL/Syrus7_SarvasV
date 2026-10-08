CREATE TABLE algoshield.benchmark_runs (
    id TEXT PRIMARY KEY,
    started_at DOUBLE PRECISION NOT NULL,
    completed_at DOUBLE PRECISION NOT NULL,
    scenario_count INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    payload_json TEXT NOT NULL);

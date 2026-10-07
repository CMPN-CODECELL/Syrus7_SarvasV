-- Add users and tokens tables for algoshield schema
CREATE TABLE IF NOT EXISTS algoshield.users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES algoshield.accounts(id),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS algoshield.user_tokens (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES algoshield.users(username),
    expires_at REAL NOT NULL
);

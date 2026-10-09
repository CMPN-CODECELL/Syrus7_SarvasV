CREATE TABLE algoshield.operator_grants (
    username TEXT PRIMARY KEY REFERENCES algoshield.users(username),
    granted_at DOUBLE PRECISION NOT NULL
);

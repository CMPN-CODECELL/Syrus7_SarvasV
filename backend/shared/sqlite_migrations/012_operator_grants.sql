CREATE TABLE operator_grants (
    username TEXT PRIMARY KEY REFERENCES users(username),
    granted_at REAL NOT NULL
);

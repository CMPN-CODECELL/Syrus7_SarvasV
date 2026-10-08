"""Authentication service: secure user registration, login, and token issuance."""

import hashlib
import secrets
import time


class AuthService:
    def __init__(self, store, token_ttl_seconds: int = 86400):
        self.store = store
        self.token_ttl_seconds = token_ttl_seconds

    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def register(
        self, username: str, password: str, account_id: str | None = None
    ) -> dict:
        username = username.strip().lower()
        if not username or len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if not password or len(password) < 6:
            raise ValueError("password must be at least 6 characters")
        account_id = (account_id or f"acc_{username}").strip()

        with self.store.transaction() as db:
            # Check if user exists
            existing = db.execute(
                "SELECT username FROM users WHERE username=?", (username,)
            ).fetchone()
            if existing:
                raise ValueError("username already exists")

            # Ensure account exists or create it
            acc = db.execute(
                "SELECT id FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if not acc:
                db.execute("INSERT INTO accounts VALUES (?)", (account_id,))
                self.store.audit("ACCOUNT_CREATED", {"account_id": account_id})

            salt = secrets.token_hex(16)
            pwd_hash = self._hash_password(password, salt)
            now = time.time()
            db.execute(
                "INSERT INTO users (username, password_hash, salt, account_id, created_at) VALUES (?,?,?,?,?)",
                (username, pwd_hash, salt, account_id, now),
            )
            self.store.audit(
                "USER_REGISTERED", {"username": username, "account_id": account_id}
            )

        token = self.create_token(username)
        return {
            "username": username,
            "account_id": account_id,
            "token": token,
        }

    def login(self, username: str, password: str) -> dict | None:
        username = username.strip().lower()
        if not username or not password:
            return None

        row = self.store.rows("SELECT * FROM users WHERE username=?", (username,))
        if not row:
            return None
        user = row[0]

        expected_hash = self._hash_password(password, user["salt"])
        if not secrets.compare_digest(expected_hash, user["password_hash"]):
            return None

        token = self.create_token(username)
        return {
            "username": username,
            "account_id": user["account_id"],
            "token": token,
        }

    def create_token(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.token_ttl_seconds
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO user_tokens (token, username, expires_at) VALUES (?,?,?)",
                (token, username, expires_at),
            )
        return token

    def verify_token(self, token: str) -> dict | None:
        if not token:
            return None
        now = time.time()
        rows = self.store.rows(
            """SELECT u.username, u.account_id, t.expires_at,
                      CASE WHEN g.username IS NULL THEN 0 ELSE 1 END AS is_operator
               FROM user_tokens t 
               JOIN users u ON t.username = u.username 
               LEFT JOIN operator_grants g ON g.username = u.username
               WHERE t.token = ? AND t.expires_at > ?""",
            (token, now),
        )
        if not rows:
            return None
        return dict(rows[0])

    def provision_operator(self, username: str, *, granted: bool):
        """Trusted local administration only; never exposed through HTTP."""
        username = username.strip().lower()
        with self.store.transaction() as db:
            if not db.execute(
                "SELECT username FROM users WHERE username=?", (username,)
            ).fetchone():
                raise ValueError("existing registered user required")
            if granted:
                db.execute(
                    "INSERT INTO operator_grants(username,granted_at) VALUES (?,?) "
                    "ON CONFLICT(username) DO NOTHING",
                    (username, time.time()),
                )
            else:
                db.execute("DELETE FROM operator_grants WHERE username=?", (username,))
            self.store.audit(
                "OPERATOR_GRANT_CHANGED", {"username": username, "granted": granted}
            )

    def logout(self, token: str) -> bool:
        if not token:
            return False
        with self.store.transaction() as db:
            db.execute("DELETE FROM user_tokens WHERE token=?", (token,))
        return True

"""Authentication service: secure user registration, login, and token issuance."""

import hashlib
import secrets
import time
import re

PASSWORD_ITERATIONS = 600_000


class AuthService:
    def __init__(self, store, token_ttl_seconds: int = 86400):
        self.store = store
        self.token_ttl_seconds = token_ttl_seconds

    def _hash_password(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PASSWORD_ITERATIONS,
        ).hex()
        return f"pbkdf2-sha256$v1${PASSWORD_ITERATIONS}${digest}"

    def _verify_password(self, password, salt, record):
        if not isinstance(record, str) or not isinstance(salt, str):
            return False
        if not re.fullmatch(r"[0-9a-f]{32}", salt):
            return False
        if re.fullmatch(r"[0-9a-f]{64}", record):
            expected = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        else:
            parts = record.split("$")
            if (
                len(parts) != 4
                or parts[:2] != ["pbkdf2-sha256", "v1"]
                or parts[2] != str(PASSWORD_ITERATIONS)
                or not re.fullmatch(r"[0-9a-f]{64}", parts[3])
            ):
                return False
            expected = self._hash_password(password, salt)
        return secrets.compare_digest(expected, record)

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
            # Equalize the dominant KDF cost for nonexistent usernames.
            self._hash_password(password, "0" * 32)
            return None
        user = row[0]

        if not self._verify_password(password, user["salt"], user["password_hash"]):
            if not user["password_hash"].startswith("pbkdf2-sha256$v1$"):
                self._hash_password(password, "0" * 32)
            return None

        if re.fullmatch(r"[0-9a-f]{64}", user["password_hash"]):
            salt = secrets.token_hex(16)
            upgraded = self._hash_password(password, salt)
            with self.store.transaction() as db:
                # Compare-and-swap protects concurrent upgrade/password changes.
                db.execute(
                    "UPDATE users SET password_hash=?, salt=? "
                    "WHERE username=? AND password_hash=? AND salt=?",
                    (upgraded, salt, username, user["password_hash"], user["salt"]),
                )

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

    def select_demo_role(
        self,
        role: str,
        *,
        username: str,
        account_id: str,
        is_operator: bool,
    ) -> dict:
        """Select one configured demo principal without accepting credentials.

        The principal remains durable and account-scoped.  Its deliberately
        invalid password record cannot authenticate through the normal login
        path, and operator authority is still resolved from operator_grants on
        every request.
        """
        role = role.strip().lower()
        username = username.strip().lower()
        account_id = account_id.strip()
        if role not in {"trader", "operator"}:
            raise ValueError("demo role must be Trader or Operator")
        if not username or not account_id:
            raise ValueError("demo role identity is incomplete")

        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO accounts(id) VALUES (?) ON CONFLICT(id) DO NOTHING",
                (account_id,),
            )
            existing = db.execute(
                "SELECT account_id,password_hash FROM users WHERE username=?",
                (username,),
            ).fetchone()
            if existing and (
                existing["account_id"] != account_id
                or existing["password_hash"] != "demo-role-disabled"
            ):
                raise ValueError(
                    "configured demo identity collides with an existing user"
                )
            if not existing:
                db.execute(
                    "INSERT INTO users "
                    "(username,password_hash,salt,account_id,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (username, "demo-role-disabled", "0" * 32, account_id, time.time()),
                )
            grant = db.execute(
                "SELECT username FROM operator_grants WHERE username=?", (username,)
            ).fetchone()
            if is_operator:
                db.execute(
                    "INSERT INTO operator_grants(username,granted_at) VALUES (?,?) "
                    "ON CONFLICT(username) DO NOTHING",
                    (username, time.time()),
                )
            elif grant:
                raise ValueError(
                    "configured Trader unexpectedly has operator authority"
                )
            self.store.audit(
                "DEMO_ROLE_SELECTED",
                {"role": role, "username": username, "account_id": account_id},
            )

        token = self.create_token(username)
        user = self.verify_token(token)
        if not user or bool(user["is_operator"]) != bool(is_operator):
            self.logout(token)
            raise ValueError("demo role authority could not be verified")
        return {"user": user, "token": token, "role": role}

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

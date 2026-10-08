"""Explicit offline administration; run with backend stopped, never against Neon."""

import argparse

from backend.shared.auth import AuthService
from backend.shared.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    # This command deliberately does not load environment/database URL settings.
    from pathlib import Path

    if not Path(args.sqlite_path).is_file():
        parser.error("an existing offline SQLite database is required")
    store = Store(args.sqlite_path)
    try:
        AuthService(store).provision_operator(args.username, granted=not args.revoke)
        print("Operator grant revoked" if args.revoke else "Operator grant provisioned")
    finally:
        store.close()


if __name__ == "__main__":
    main()

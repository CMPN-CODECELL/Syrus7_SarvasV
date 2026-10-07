import os
from dotenv import dotenv_values


def settings():
    # Environment wins; ignored files never enter frontend state or diagnostics.
    values = dict(dotenv_values(".env")) | dict(dotenv_values(".env.local"))
    return {
        "database_url": os.getenv("DATABASE_URL", values.get("DATABASE_URL")) or "",
        "sqlite_path": os.getenv("ALGOSHIELD_DB", values.get("ALGOSHIELD_DB"))
        or "data/platform.db",
    }

import os
from dotenv import dotenv_values


def settings():
    # Environment wins; ignored files never enter frontend state or diagnostics.
    values = dict(dotenv_values(".env")) | dict(dotenv_values(".env.local"))
    result = {
        "database_url": os.getenv("DATABASE_URL", values.get("DATABASE_URL")) or "",
        "sqlite_path": os.getenv("ALGOSHIELD_DB", values.get("ALGOSHIELD_DB"))
        or "data/platform.db",
    }
    # The HTTP mock is an explicit local integration dependency.  Keep this
    # optional so existing callers/config tests remain backwards compatible.
    mock_broker_url = os.getenv("MOCK_BROKER_URL", values.get("MOCK_BROKER_URL"))
    if mock_broker_url:
        result["mock_broker_url"] = mock_broker_url
    trusted_origins = os.getenv(
        "ALGOSHIELD_TRUSTED_ORIGINS", values.get("ALGOSHIELD_TRUSTED_ORIGINS")
    )
    if trusted_origins is not None:
        result["trusted_origins"] = trusted_origins
    return result

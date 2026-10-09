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
    provider = os.getenv(
        "ALGOSHIELD_MARKET_DATA_PROVIDER",
        values.get("ALGOSHIELD_MARKET_DATA_PROVIDER"),
    )
    if provider:
        provider = provider.strip().lower()
        if provider not in {"replay", "yahoo"}:
            raise ValueError("market-data provider must be replay or yahoo")
        result["market_data_provider"] = provider
    symbols = os.getenv(
        "ALGOSHIELD_YAHOO_SYMBOLS", values.get("ALGOSHIELD_YAHOO_SYMBOLS")
    )
    if symbols:
        result["yahoo_symbols"] = tuple(
            symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()
        )
    return result

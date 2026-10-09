import os
from dotenv import dotenv_values


def settings():
    # Environment wins; ignored files never enter frontend state or diagnostics.
    values = dict(dotenv_values(".env")) | dict(dotenv_values(".env.local"))
    result = {
        "database_url": os.getenv("DATABASE_URL", values.get("DATABASE_URL")) or "",
        "sqlite_path": os.getenv("ALGOSHIELD_DB", values.get("ALGOSHIELD_DB"))
        or "data/platform.db",
        "021_enabled": False,
    }
    enabled_021 = (
        os.getenv(
            "ALGOSHIELD_021_ENABLED", values.get("ALGOSHIELD_021_ENABLED", "false")
        )
        .strip()
        .lower()
    )
    if enabled_021 not in {"true", "false"}:
        raise ValueError("ALGOSHIELD_021_ENABLED must be true or false")
    result["021_enabled"] = enabled_021 == "true"
    for key, env_name in (
        ("021_base_url", "ALGOSHIELD_021_BASE_URL"),
        ("021_username", "ALGOSHIELD_021_USERNAME"),
        ("021_password", "ALGOSHIELD_021_PASSWORD"),
        ("021_token", "ALGOSHIELD_021_TOKEN"),
        ("021_instrument_cache", "ALGOSHIELD_021_INSTRUMENT_CACHE"),
    ):
        value = os.getenv(env_name, values.get(env_name))
        if value:
            result[key] = value.strip()
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
        if provider not in {"replay", "yahoo", "021"}:
            raise ValueError("market-data provider must be replay, 021 or yahoo")
        result["market_data_provider"] = provider
    symbols = os.getenv(
        "ALGOSHIELD_YAHOO_SYMBOLS", values.get("ALGOSHIELD_YAHOO_SYMBOLS")
    )
    if symbols:
        result["yahoo_symbols"] = tuple(
            symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()
        )
    live_symbols = os.getenv("ALGOSHIELD_021_SYMBOLS", values.get("ALGOSHIELD_021_SYMBOLS"))
    if live_symbols:
        result["021_symbols"] = tuple(
            symbol.strip().upper() for symbol in live_symbols.split(",") if symbol.strip()
        )
    trusted_origins = os.getenv(
        "ALGOSHIELD_TRUSTED_ORIGINS", values.get("ALGOSHIELD_TRUSTED_ORIGINS")
    )
    if trusted_origins is not None:
        result["trusted_origins"] = trusted_origins
    return result

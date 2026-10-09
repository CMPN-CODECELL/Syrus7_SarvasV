import os
from dotenv import dotenv_values


def _positive_float(values, name: str, default: float) -> float:
    raw = os.getenv(name, values.get(name, str(default)))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _bounded_int(values, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, values.get(name, str(default)))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


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
    if result["021_enabled"] and not result["database_url"]:
        # A live-provider accounting timeline must never share the offline
        # mock/replay order and fill ledger. Preserve ALGOSHIELD_DB as the mock
        # store and use an independently configurable 021 store.
        result["sqlite_path"] = os.getenv(
            "ALGOSHIELD_021_DB",
            values.get("ALGOSHIELD_021_DB", "data/platform-021.db"),
        )
    # 021 is primary when explicitly enabled; offline installs retain replay.
    # Provider changes are startup configuration, never an implicit fallback.
    result["market_data_provider"] = "021" if result["021_enabled"] else "replay"
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
    product = (
        os.getenv(
            "ALGOSHIELD_021_PRODUCT", values.get("ALGOSHIELD_021_PRODUCT", "INTRADAY")
        )
        .strip()
        .upper()
    )
    if product not in {"INTRADAY", "CNC", "NRML"}:
        raise ValueError("ALGOSHIELD_021_PRODUCT must be INTRADAY, CNC or NRML")
    result["021_product"] = product
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
    if result["021_enabled"] and result["market_data_provider"] != "021":
        raise ValueError(
            "021 live mode requires 021 market data; disable "
            "ALGOSHIELD_021_ENABLED before selecting Yahoo fallback or replay"
        )
    if not result["021_enabled"] and result["market_data_provider"] == "021":
        raise ValueError("021 market data requires ALGOSHIELD_021_ENABLED=true")
    symbols = os.getenv(
        "ALGOSHIELD_YAHOO_SYMBOLS", values.get("ALGOSHIELD_YAHOO_SYMBOLS")
    )
    if symbols:
        result["yahoo_symbols"] = tuple(
            symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()
        )
    live_symbols = os.getenv(
        "ALGOSHIELD_021_SYMBOLS", values.get("ALGOSHIELD_021_SYMBOLS")
    )
    if live_symbols:
        result["021_symbols"] = tuple(
            symbol.strip().upper()
            for symbol in live_symbols.split(",")
            if symbol.strip()
        )
    auto_symbols = os.getenv(
        "ALGOSHIELD_AUTO_SYMBOLS", values.get("ALGOSHIELD_AUTO_SYMBOLS")
    )
    if auto_symbols:
        result["auto_symbols"] = tuple(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in auto_symbols.split(",")
                if symbol.strip()
            )
        )
    auto_exchange = (
        os.getenv(
            "ALGOSHIELD_AUTO_EXCHANGE",
            values.get("ALGOSHIELD_AUTO_EXCHANGE", "NSECM"),
        )
        .strip()
        .upper()
    )
    if auto_exchange != "NSECM":
        raise ValueError("ALGOSHIELD_AUTO_EXCHANGE must be NSECM")
    result["auto_exchange"] = auto_exchange
    result["021_max_timestamp_skew_seconds"] = _positive_float(
        values, "ALGOSHIELD_021_MAX_TIMESTAMP_SKEW_SECONDS", 10
    )
    result["broker_read_timeout_seconds"] = _positive_float(
        values, "ALGOSHIELD_BROKER_READ_TIMEOUT_SECONDS", 8
    )
    result["broker_write_timeout_seconds"] = _positive_float(
        values, "ALGOSHIELD_BROKER_WRITE_TIMEOUT_SECONDS", 8
    )
    result["reconciliation_timeout_seconds"] = _positive_float(
        values, "ALGOSHIELD_RECONCILIATION_TIMEOUT_SECONDS", 10
    )
    result["auto_scan_limit"] = _bounded_int(
        values, "ALGOSHIELD_AUTO_SCAN_LIMIT", 200, 1, 2000
    )
    result["auto_max_positions"] = _bounded_int(
        values, "ALGOSHIELD_AUTO_MAX_POSITIONS", 3, 1, 20
    )
    result["auto_lookback_updates"] = _bounded_int(
        values, "ALGOSHIELD_AUTO_LOOKBACK_UPDATES", 5, 2, 100
    )
    result["auto_entry_momentum"] = _positive_float(
        values, "ALGOSHIELD_AUTO_ENTRY_MOMENTUM", 0.003
    )
    result["auto_take_profit"] = _positive_float(
        values, "ALGOSHIELD_AUTO_TAKE_PROFIT", 0.01
    )
    result["auto_stop_loss"] = _positive_float(
        values, "ALGOSHIELD_AUTO_STOP_LOSS", 0.005
    )
    result["auto_cooldown_seconds"] = _bounded_int(
        values, "ALGOSHIELD_AUTO_COOLDOWN_SECONDS", 60, 0, 86400
    )
    trusted_origins = os.getenv(
        "ALGOSHIELD_TRUSTED_ORIGINS", values.get("ALGOSHIELD_TRUSTED_ORIGINS")
    )
    if trusted_origins is not None:
        result["trusted_origins"] = trusted_origins
    secure_cookie = (
        os.getenv(
            "ALGOSHIELD_SECURE_COOKIE", values.get("ALGOSHIELD_SECURE_COOKIE", "false")
        )
        .strip()
        .lower()
    )
    if secure_cookie not in {"true", "false"}:
        raise ValueError("ALGOSHIELD_SECURE_COOKIE must be true or false")
    result["secure_cookie"] = secure_cookie == "true"
    return result

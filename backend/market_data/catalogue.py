"""Canonical bounded instrument catalogue for offline demo mode."""

DEMO_INSTRUMENTS = (
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "RELIANCE",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "TCS",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "INFY",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "HDFCBANK",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "ICICIBANK",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
    {
        "exchange": "NSE",
        "token": None,
        "symbol": "SBIN",
        "provider": "replay",
        "source": "DEMO_PAPER",
        "available": True,
    },
)


def demo_instruments(query: str | None = None) -> list[dict]:
    needle = (query or "").strip().upper()
    return [
        row.copy() for row in DEMO_INSTRUMENTS if not needle or needle in row["symbol"]
    ]

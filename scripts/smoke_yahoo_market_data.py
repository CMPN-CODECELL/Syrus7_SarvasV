#!/usr/bin/env python3
"""Bounded Yahoo quote smoke test on disposable SQLite with trading disabled."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from backend.market_data.yahoo import YahooMarketDataProvider
from backend.platform import Platform


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--symbols", nargs="+", default=["TCS.NS", "INFY.NS"])
    args = parser.parse_args()
    if not 1 <= args.duration <= 420:
        parser.error("duration must be between 1 and 420 seconds")
    return args


def main():
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="algoshield-yahoo-smoke-") as directory:
        platform = Platform(path=str(Path(directory) / "smoke.db"), demo_enabled=False)
        provider = YahooMarketDataProvider(platform, symbols=args.symbols)
        platform.configure_external_market_data(provider)
        platform.strategies.enabled = False
        started = time.monotonic()
        try:
            platform.start_external_market_data()
            deadline = started + args.duration
            while time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))
            snapshot = platform.snapshot()
            print(
                json.dumps(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "gate": str(snapshot["gate"]),
                        "strategy_runtime_enabled": platform.strategies.enabled,
                        "orders": snapshot["counts"]["orders"],
                        "market_data": snapshot["market_data"],
                        "closed_candles": snapshot["candles"],
                    },
                    default=str,
                    indent=2,
                    sort_keys=True,
                ),
                flush=True,
            )
        finally:
            platform.close()
        print(
            json.dumps(
                {
                    "clean_shutdown": True,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "worker_alive": bool(
                        provider._process and provider._process.is_alive()
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()

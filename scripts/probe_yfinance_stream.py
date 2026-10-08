#!/usr/bin/env python3
"""Bounded, read-only probe of yfinance's documented AsyncWebSocket API.

Run this from an isolated environment containing yfinance. The probe does not
import AlgoShield, access its database, start strategies, or use REST history.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

DEFAULT_SYMBOLS = ("TCS.NS", "INFY.NS")
DEFAULT_DURATION_SECONDS = 30.0
DEFAULT_MAX_SAMPLES = 10
MAX_DURATION_SECONDS = 300.0
MAX_SAMPLE_COUNT = 100
_SENSITIVE_KEY = re.compile(r"token|secret|password|cookie|authorization", re.I)
_URL_CREDENTIALS = re.compile(r"(wss?://)[^/@\s]+@", re.I)
_URL_QUERY = re.compile(r"(wss?://[^?\s]+)\?[^\s]+", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe yfinance AsyncWebSocket without touching AlgoShield state."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="Yahoo symbols to subscribe to (default: TCS.NS INFY.NS).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help="Probe duration in seconds, greater than 0 and at most 300 (default: 30).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=DEFAULT_MAX_SAMPLES,
        help="Maximum decoded messages retained in output, 0-100 (default: 10).",
    )
    args = parser.parse_args()
    args.symbols = list(dict.fromkeys(symbol.strip() for symbol in args.symbols))
    if not args.symbols or any(not symbol for symbol in args.symbols):
        parser.error("symbols must be non-empty")
    if (
        not math.isfinite(args.duration)
        or not 0 < args.duration <= MAX_DURATION_SECONDS
    ):
        parser.error("duration must be greater than 0 and at most 300 seconds")
    if not 0 <= args.max_samples <= MAX_SAMPLE_COUNT:
        parser.error("max-samples must be between 0 and 100")
    return args


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_error(exc: BaseException) -> dict[str, str]:
    message = " ".join(str(exc).split())[:500]
    message = _URL_CREDENTIALS.sub(r"\1<redacted>@", message)
    message = _URL_QUERY.sub(r"\1?<redacted>", message)
    return {"type": type(exc).__name__, "message": message}


def safe_value(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary decoded values and remove credential-like fields."""
    if depth >= 4:
        return "<depth-limit>"
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:64]:
            key_text = str(key)[:100]
            result[key_text] = (
                "<redacted>"
                if _SENSITIVE_KEY.search(key_text)
                else safe_value(item, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [safe_value(item, depth=depth + 1) for item in value[:64]]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def timestamp_observation(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"value": value, "unit": "not_inferable"}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return result
    magnitude = abs(value)
    if 1_000_000_000 <= magnitude < 10_000_000_000:
        divisor = 1.0
        unit = "seconds"
    elif 1_000_000_000_000 <= magnitude < 10_000_000_000_000:
        divisor = 1_000.0
        unit = "milliseconds"
    elif 1_000_000_000_000_000 <= magnitude < 10_000_000_000_000_000:
        divisor = 1_000_000.0
        unit = "microseconds"
    else:
        return result
    try:
        parsed = datetime.fromtimestamp(value / divisor, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return result
    result.update(
        {
            "unit": unit,
            "utc_if_inferred_unit": parsed.isoformat(),
            "basis": "numeric magnitude and plausible Unix epoch conversion; inference, not provider contract",
        }
    )
    return result


def installed_api_facts(yf: Any) -> dict[str, Any]:
    import yfinance.live as live

    source = inspect.getsource(live.AsyncWebSocket)
    protobuf_fields = []
    protobuf_types = {
        1: "double",
        2: "float",
        5: "int32",
        9: "string",
        18: "uint64",
    }
    for field in live.PricingData.DESCRIPTOR.fields:
        protobuf_fields.append(
            {
                "name": field.name,
                "protobuf_type": protobuf_types.get(field.type, field.type),
            }
        )
    return {
        "yfinance_version": metadata.version("yfinance"),
        "websockets_version": metadata.version("websockets"),
        "class": "yfinance.AsyncWebSocket",
        "constructor_signature": str(inspect.signature(yf.AsyncWebSocket)),
        "method_signatures": {
            name: str(inspect.signature(getattr(yf.AsyncWebSocket, name)))
            for name in ("subscribe", "listen", "close")
        },
        "installed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "decoded_message_format": "dict produced from PricingData protobuf with original field names",
        "protobuf_declared_fields": protobuf_fields,
    }


class Observations:
    def __init__(self, symbols: list[str], max_samples: int, started: float):
        self.symbols = set(symbols)
        self.max_samples = max_samples
        self.started = started
        self.message_count = 0
        self.samples: list[dict[str, Any]] = []
        self.field_counts: Counter[str] = Counter()
        self.symbol_counts: Counter[str] = Counter()
        self.last_receipt: dict[str, float] = {}
        self.intervals: dict[str, list[float]] = defaultdict(list)
        self.timestamps: list[dict[str, Any]] = []
        self.price_values: list[Any] = []
        self.volume_values: dict[str, list[Any]] = defaultdict(list)
        self.non_mapping_messages = 0

    def handle(self, message: Any) -> None:
        received = time.monotonic()
        self.message_count += 1
        if not isinstance(message, dict):
            self.non_mapping_messages += 1
            if len(self.samples) < self.max_samples:
                self.samples.append(
                    {
                        "received_offset_seconds": round(received - self.started, 6),
                        "message": safe_value(message),
                    }
                )
            return

        self.field_counts.update(message.keys())
        symbol = str(message.get("id", "<missing-id>"))
        bucket = symbol if symbol in self.symbols else "<unexpected-or-missing>"
        self.symbol_counts[bucket] += 1
        previous = self.last_receipt.get(bucket)
        if previous is not None and len(self.intervals[bucket]) < 10_000:
            self.intervals[bucket].append(received - previous)
        self.last_receipt[bucket] = received

        if "time" in message and len(self.timestamps) < MAX_SAMPLE_COUNT:
            self.timestamps.append(timestamp_observation(message["time"]))
        if "price" in message and len(self.price_values) < MAX_SAMPLE_COUNT:
            self.price_values.append(message["price"])
        for field in ("day_volume", "last_size", "bid_size", "ask_size"):
            if field in message and len(self.volume_values[field]) < MAX_SAMPLE_COUNT:
                self.volume_values[field].append(message[field])

        if len(self.samples) < self.max_samples:
            self.samples.append(
                {
                    "received_offset_seconds": round(received - self.started, 6),
                    "message": safe_value(message),
                }
            )

    def frequency_report(self, elapsed: float) -> dict[str, Any]:
        report = {}
        for symbol, count in self.symbol_counts.items():
            intervals = self.intervals[symbol]
            report[symbol] = {
                "messages": count,
                "messages_per_second_over_probe": round(count / elapsed, 6)
                if elapsed > 0
                else None,
                "interarrival_seconds": {
                    "count": len(intervals),
                    "min": round(min(intervals), 6) if intervals else None,
                    "median": round(statistics.median(intervals), 6)
                    if intervals
                    else None,
                    "max": round(max(intervals), 6) if intervals else None,
                },
            }
        return report


async def run_probe(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    import yfinance as yf

    started_wall = utc_now()
    started = time.monotonic()
    observations = Observations(args.symbols, args.max_samples, started)
    events: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    client = yf.AsyncWebSocket(verbose=False)
    outcome = "duration_elapsed"
    subscribed = False
    closed = False

    async def subscribe_and_listen() -> None:
        nonlocal subscribed
        await client.subscribe(args.symbols)
        subscribed = True
        events.append(
            {
                "event": "subscribe_returned",
                "offset_seconds": round(time.monotonic() - started, 6),
            }
        )
        await client.listen(observations.handle)
        events.append(
            {
                "event": "listen_returned",
                "offset_seconds": round(time.monotonic() - started, 6),
            }
        )

    activity = asyncio.create_task(subscribe_and_listen())
    try:
        done, pending = await asyncio.wait({activity}, timeout=args.duration)
        if pending:
            events.append(
                {
                    "event": "duration_timeout",
                    "offset_seconds": round(time.monotonic() - started, 6),
                }
            )
            activity.cancel()
            cancelled, still_pending = await asyncio.wait({activity}, timeout=1.0)
            if still_pending:
                events.append(
                    {
                        "event": "listener_cancellation_timeout",
                        "offset_seconds": round(time.monotonic() - started, 6),
                    }
                )
            elif cancelled:
                events.append(
                    {
                        "event": "listener_cancelled",
                        "offset_seconds": round(time.monotonic() - started, 6),
                    }
                )
        elif done:
            activity.result()
            outcome = "listen_returned"
    except Exception as exc:  # Probe must report provider/network failures cleanly.
        outcome = "connection_or_listen_error"
        errors.append(safe_error(exc))
        events.append(
            {
                "event": "error",
                "offset_seconds": round(time.monotonic() - started, 6),
                **safe_error(exc),
            }
        )
    finally:
        close_task = asyncio.create_task(client.close())
        try:
            close_done, close_pending = await asyncio.wait({close_task}, timeout=1.0)
            if close_done:
                close_task.result()
                closed = True
                events.append(
                    {
                        "event": "close_returned",
                        "offset_seconds": round(time.monotonic() - started, 6),
                    }
                )
            elif close_pending:
                close_task.cancel()
                events.append(
                    {
                        "event": "close_timeout_transport_aborted",
                        "offset_seconds": round(time.monotonic() - started, 6),
                    }
                )
                transport = getattr(getattr(client, "_ws", None), "transport", None)
                if transport is not None:
                    transport.abort()
        except Exception as exc:
            errors.append(safe_error(exc))
            events.append(
                {
                    "event": "close_error",
                    "offset_seconds": round(time.monotonic() - started, 6),
                    **safe_error(exc),
                }
            )

    elapsed = time.monotonic() - started
    no_messages = observations.message_count == 0
    report = {
        "probe": {
            "symbols": args.symbols,
            "configured_duration_seconds": args.duration,
            "max_retained_samples": args.max_samples,
            "started_at_utc": started_wall,
            "finished_at_utc": utc_now(),
            "elapsed_seconds": round(elapsed, 6),
            "bounded_exit_target_seconds": args.duration + 2.0,
            "uses_historical_rest": False,
            "accesses_algoshield_application_or_database": False,
        },
        "installed_api_source_facts": installed_api_facts(yf),
        "observed_facts": {
            "outcome": outcome,
            "subscribe_returned": subscribed,
            "close_returned": closed,
            "message_count": observations.message_count,
            "streaming_success": observations.message_count > 0,
            "field_occurrences": dict(sorted(observations.field_counts.items())),
            "timestamp_field_observations": observations.timestamps,
            "price_field_values": observations.price_values,
            "volume_related_field_values": dict(observations.volume_values),
            "update_frequency": observations.frequency_report(elapsed),
            "non_mapping_messages": observations.non_mapping_messages,
            "connection_events": events,
            "errors": errors,
            "retained_samples": observations.samples,
        },
        "assumptions_and_limits": {
            "timestamp_units": (
                "Magnitude-based inferences are labeled in each observation; the installed protobuf schema does not declare a time unit."
            ),
            "volume_semantics": (
                "No observed volume-related field is assumed to be per-trade quantity; day_volume may be cumulative, and last_size/bid_size/ask_size semantics require provider validation."
            ),
            "event_identity": (
                "No unique trade/message ID is assumed. The installed schema has an id field, but observations must not treat it as a unique event ID."
            ),
            "no_messages": (
                "INCONCLUSIVE: a quiet or closed market does not prove that the symbols or streaming feed are unsupported."
                if no_messages
                else "Not applicable; at least one decoded streaming message was observed."
            ),
            "streaming_evidence": (
                "Only decoded AsyncWebSocket messages count as streaming success; historical REST data is neither requested nor considered."
            ),
        },
    }
    return report, 2 if outcome == "connection_or_listen_error" else 0


def main() -> int:
    args = parse_args()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report, exit_code = loop.run_until_complete(run_probe(args))
        finally:
            # Do not let a provider task that ignored cancellation defeat the
            # probe's wall-clock bound. All remaining tasks lose their loop.
            loop.set_exception_handler(lambda _loop, _context: None)
            loop.close()
            asyncio.set_event_loop(None)
    except ImportError as exc:
        report = {
            "probe_error": safe_error(exc),
            "remediation": "Run from an isolated environment with yfinance installed.",
        }
        exit_code = 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

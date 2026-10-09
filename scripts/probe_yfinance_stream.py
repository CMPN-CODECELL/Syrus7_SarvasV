#!/usr/bin/env python3
"""Bounded, read-only yfinance AsyncWebSocket probe.

The public process supervises a worker so provider calls and cleanup cannot
defeat the wall-clock deadline. No AlgoShield modules, databases, orders,
strategies, or REST history are used.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import math
import queue
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

DEFAULT_SYMBOLS = ("TCS.NS", "INFY.NS")
DEFAULT_DURATION_SECONDS = 30.0
DEFAULT_MAX_SAMPLES = 10
MAX_DURATION_SECONDS = 300.0
MAX_SAMPLE_COUNT = 100
SUPERVISOR_GRACE_SECONDS = 2.0
CHILD_STOP_WAIT_SECONDS = 1.0
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
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
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
    if depth >= 8:
        return "<depth-limit>"
    if isinstance(value, dict):
        return {
            str(key)[:100]: (
                "<redacted>"
                if _SENSITIVE_KEY.search(str(key))
                else safe_value(item, depth=depth + 1)
            )
            for key, item in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple)):
        return [safe_value(item, depth=depth + 1) for item in value[:64]]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def timestamp_observation(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"value": value, "unit": "not_inferable"}
    numeric_value = value
    if isinstance(value, str) and value.isdigit():
        numeric_value = int(value)
        result["decoded_representation"] = "decimal string"
    if isinstance(numeric_value, bool) or not isinstance(numeric_value, (int, float)):
        return result
    magnitude = abs(numeric_value)
    if 1_000_000_000 <= magnitude < 10_000_000_000:
        divisor, unit = 1.0, "seconds"
    elif 1_000_000_000_000 <= magnitude < 10_000_000_000_000:
        divisor, unit = 1_000.0, "milliseconds"
    elif 1_000_000_000_000_000 <= magnitude < 10_000_000_000_000_000:
        divisor, unit = 1_000_000.0, "microseconds"
    else:
        return result
    try:
        parsed = datetime.fromtimestamp(numeric_value / divisor, tz=timezone.utc)
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
    protobuf_types = {1: "double", 2: "float", 5: "int32", 9: "string", 18: "uint64"}
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
        "protobuf_declared_fields": [
            {
                "name": field.name,
                "protobuf_type": protobuf_types.get(field.type, field.type),
            }
            for field in live.PricingData.DESCRIPTOR.fields
        ],
    }


class Observations:
    def __init__(
        self,
        symbols: list[str],
        max_samples: int,
        started: float,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.symbols = set(symbols)
        self.max_samples = max_samples
        self.started = started
        self.emit = emit
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
        self._last_count_emit = 0.0

    def _send(self, event: dict[str, Any]) -> None:
        if self.emit is not None:
            self.emit(event)

    def handle(self, message: Any) -> None:
        received = time.monotonic()
        self.message_count += 1
        sample = {
            "received_offset_seconds": round(received - self.started, 6),
            "message": safe_value(message),
        }
        if not isinstance(message, dict):
            self.non_mapping_messages += 1
        else:
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
                if (
                    field in message
                    and len(self.volume_values[field]) < MAX_SAMPLE_COUNT
                ):
                    self.volume_values[field].append(message[field])
        if len(self.samples) < self.max_samples:
            self.samples.append(sample)
            self._send({"event": "sample", "sample": sample})
        if self.message_count == 1 or received - self._last_count_emit >= 0.5:
            self._last_count_emit = received
            self._send(
                {
                    "event": "message_progress",
                    "message_count_lower_bound": self.message_count,
                    "symbol_counts": dict(self.symbol_counts),
                }
            )

    def frequency_report(self, elapsed: float) -> dict[str, Any]:
        return {
            symbol: {
                "messages": count,
                "messages_per_second_over_probe": round(count / elapsed, 6),
                "interarrival_seconds": {
                    "count": len(self.intervals[symbol]),
                    "min": round(min(self.intervals[symbol]), 6)
                    if self.intervals[symbol]
                    else None,
                    "median": round(statistics.median(self.intervals[symbol]), 6)
                    if self.intervals[symbol]
                    else None,
                    "max": round(max(self.intervals[symbol]), 6)
                    if self.intervals[symbol]
                    else None,
                },
            }
            for symbol, count in self.symbol_counts.items()
        }

    def report(self, elapsed: float) -> dict[str, Any]:
        return {
            "message_count": self.message_count,
            "message_count_exact": True,
            "field_occurrences": dict(sorted(self.field_counts.items())),
            "symbol_counts": dict(self.symbol_counts),
            "timestamp_field_observations": self.timestamps,
            "price_field_values": self.price_values,
            "volume_related_field_values": dict(self.volume_values),
            "update_frequency": self.frequency_report(elapsed),
            "non_mapping_messages": self.non_mapping_messages,
            "retained_samples": self.samples,
        }


def emit_worker_event(event: dict[str, Any]) -> None:
    print(json.dumps(safe_value(event), sort_keys=True, allow_nan=False), flush=True)


async def run_worker(args: argparse.Namespace) -> int:
    started = time.monotonic()
    deadline = started + args.duration
    emit_worker_event({"event": "worker_started", "at_utc": utc_now()})
    emit_worker_event({"event": "provider_import_started"})
    import yfinance as yf

    emit_worker_event(
        {"event": "installed_api_source_facts", "facts": installed_api_facts(yf)}
    )
    observations = Observations(
        args.symbols, args.max_samples, started, emit_worker_event
    )
    client = yf.AsyncWebSocket(verbose=False)
    emit_worker_event({"event": "client_created"})
    listen_started = False
    summary_emitted = False
    activity: asyncio.Task[Any] | None = None
    exit_code = 0
    try:
        emit_worker_event({"event": "connection_subscription_started"})
        activity = asyncio.create_task(client.subscribe(args.symbols))
        done, pending = await asyncio.wait(
            {activity}, timeout=max(0.0, deadline - time.monotonic())
        )
        if pending:
            emit_worker_event(
                {"event": "phase_deadline", "phase": "connection_or_subscription"}
            )
            activity.cancel()
            exit_code = 3
        else:
            activity.result()
            emit_worker_event(
                {
                    "event": "subscribe_returned",
                    "offset_seconds": round(time.monotonic() - started, 6),
                }
            )
            listen_started = True
            emit_worker_event({"event": "listening_started"})
            activity = asyncio.create_task(client.listen(observations.handle))
            done, pending = await asyncio.wait(
                {activity}, timeout=max(0.0, deadline - time.monotonic())
            )
            if done:
                activity.result()
                emit_worker_event({"event": "listen_returned"})
            else:
                emit_worker_event({"event": "duration_elapsed"})
                emit_worker_event(
                    {
                        "event": "observation_summary",
                        "observed_facts": observations.report(
                            max(time.monotonic() - started, 0.000001)
                        ),
                    }
                )
                summary_emitted = True
                activity.cancel()
                await asyncio.wait({activity}, timeout=0.25)
    except Exception as exc:
        emit_worker_event({"event": "provider_error", **safe_error(exc)})
        exit_code = 2
    finally:
        if listen_started and not summary_emitted:
            emit_worker_event(
                {
                    "event": "observation_summary",
                    "observed_facts": observations.report(
                        max(time.monotonic() - started, 0.000001)
                    ),
                }
            )
        emit_worker_event({"event": "cleanup_started"})
        close_task = asyncio.create_task(client.close())
        close_done, close_pending = await asyncio.wait({close_task}, timeout=0.75)
        if close_done:
            try:
                close_task.result()
                emit_worker_event({"event": "cleanup_complete"})
            except Exception as exc:
                emit_worker_event({"event": "cleanup_error", **safe_error(exc)})
                exit_code = 2
        elif close_pending:
            close_task.cancel()
            transport = getattr(getattr(client, "_ws", None), "transport", None)
            if transport is not None:
                transport.abort()
            emit_worker_event({"event": "cleanup_timeout_transport_aborted"})
    emit_worker_event({"event": "worker_complete"})
    return exit_code


def worker_main(args: argparse.Namespace) -> int:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_worker(args))
    except Exception as exc:
        emit_worker_event({"event": "worker_error", **safe_error(exc)})
        return 2
    finally:
        loop.set_exception_handler(lambda _loop, _context: None)
        loop.close()
        asyncio.set_event_loop(None)


def _reader(stream: Any, output: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            output.put(line)
    finally:
        output.put(None)


def _terminate_and_reap(process: subprocess.Popen[str]) -> tuple[bool, str]:
    if process.poll() is not None:
        process.wait(timeout=CHILD_STOP_WAIT_SECONDS)
        return True, "already_exited"
    process.terminate()
    try:
        process.wait(timeout=CHILD_STOP_WAIT_SECONDS)
        return True, "terminated"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=CHILD_STOP_WAIT_SECONDS)
            return True, "killed"
        except subprocess.TimeoutExpired:
            return False, "kill_wait_timeout"


def supervise_command(
    command: list[str],
    *,
    symbols: list[str],
    duration: float,
    max_samples: int,
    grace_seconds: float = SUPERVISOR_GRACE_SECONDS,
    emit_progress: bool = True,
) -> tuple[dict[str, Any], int]:
    """Run a JSON-lines worker under an OS-enforced wall-clock deadline."""
    started = time.monotonic()
    started_at = utc_now()
    worker_timeout = duration + grace_seconds
    maximum_elapsed = worker_timeout + (2 * CHILD_STOP_WAIT_SECONDS)
    lines: queue.Queue[str | None] = queue.Queue()
    events: list[dict[str, Any]] = []
    invalid_worker_lines = 0
    deadline_terminated = False
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    reader = threading.Thread(target=_reader, args=(process.stdout, lines), daemon=True)
    reader.start()

    def consume(line: str) -> None:
        nonlocal invalid_worker_lines
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid_worker_lines += 1
            return
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            invalid_worker_lines += 1
            return
        events.append(event)
        if emit_progress:
            print(
                json.dumps(
                    {"record_type": "progress", **event},
                    sort_keys=True,
                    allow_nan=False,
                ),
                flush=True,
            )

    while True:
        remaining = worker_timeout - (time.monotonic() - started)
        if remaining <= 0:
            deadline_terminated = process.poll() is None
            break
        try:
            line = lines.get(timeout=min(0.1, remaining))
        except queue.Empty:
            if process.poll() is not None and not reader.is_alive():
                break
            continue
        if line is None:
            if process.poll() is not None:
                break
            continue
        consume(line)

    child_reaped, stop_method = _terminate_and_reap(process)
    reader.join(timeout=CHILD_STOP_WAIT_SECONDS)
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            break
        if line is not None:
            consume(line)

    elapsed = time.monotonic() - started
    event_names = [event["event"] for event in events]
    api_facts = next(
        (
            event.get("facts", {})
            for event in events
            if event["event"] == "installed_api_source_facts"
        ),
        {},
    )
    summary = next(
        (
            event.get("observed_facts", {})
            for event in reversed(events)
            if event["event"] == "observation_summary"
        ),
        None,
    )
    lower_bound = max(
        (
            int(event.get("message_count_lower_bound", 0))
            for event in events
            if event["event"] == "message_progress"
        ),
        default=0,
    )
    samples = [
        event["sample"]
        for event in events
        if event["event"] == "sample" and "sample" in event
    ][:max_samples]
    if summary is not None:
        samples = summary.get("retained_samples", samples)
        message_count = summary.get("message_count")
        message_count_exact = bool(summary.get("message_count_exact"))
    else:
        message_count = None
        message_count_exact = False
    errors = [
        {
            "type": event.get("type", "ProviderError"),
            "message": event.get("message", ""),
        }
        for event in events
        if event["event"] in {"provider_error", "worker_error", "cleanup_error"}
    ]
    subscribed = "subscribe_returned" in event_names
    normal_completion = "worker_complete" in event_names and process.returncode == 0
    if message_count_exact and message_count > 0:
        classification = "STREAM_CONFIRMED"
        outcome = (
            "stream_confirmed_worker_deadline_terminated"
            if deadline_terminated
            else "normal_completion"
        )
    elif deadline_terminated:
        classification, outcome = "FAILED", "supervisor_deadline_terminated"
    elif (
        errors or "phase_deadline" in event_names or process.returncode not in (0, None)
    ):
        classification, outcome = "FAILED", "provider_or_worker_error"
    elif (
        normal_completion and subscribed and message_count_exact and message_count == 0
    ):
        classification, outcome = "INCONCLUSIVE", "normal_completion_no_messages"
    else:
        classification, outcome = "FAILED", "incomplete_worker_evidence"
    observed = dict(summary or {})
    observed.update(
        {
            "outcome": outcome,
            "classification": classification,
            "subscribe_returned": subscribed,
            "connection_succeeded": True if subscribed else None,
            "message_count": message_count,
            "message_count_exact": message_count_exact,
            "message_count_lower_bound": lower_bound,
            "retained_samples": samples,
            "connection_events": [
                event
                for event in events
                if event["event"]
                not in {
                    "installed_api_source_facts",
                    "sample",
                    "message_progress",
                    "observation_summary",
                }
            ],
            "errors": errors,
        }
    )
    report = {
        "record_type": "final_report",
        "probe": {
            "symbols": symbols,
            "configured_duration_seconds": duration,
            "max_retained_samples": max_samples,
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "elapsed_seconds": round(elapsed, 6),
            "worker_deadline_seconds": worker_timeout,
            "maximum_elapsed_seconds": maximum_elapsed,
            "uses_historical_rest": False,
            "accesses_algoshield_application_or_database": False,
        },
        "installed_api_source_facts": api_facts,
        "observed_facts": observed,
        "supervision": {
            "deadline_terminated": deadline_terminated,
            "child_pid": process.pid,
            "child_exit_code": process.returncode,
            "child_reaped": child_reaped,
            "stop_method": stop_method,
            "reader_finished": not reader.is_alive(),
            "invalid_worker_lines": invalid_worker_lines,
        },
        "assumptions_and_limits": {
            "timestamp_units": "Magnitude-based conversions are labeled as inference; the installed schema does not declare a unit.",
            "volume_semantics": "No volume-related field is assumed to be per-trade quantity.",
            "event_identity": "The schema id field is not assumed to be a unique event or trade ID.",
            "unavailable_counts": "A missing exact observation summary is reported as null, never inferred to mean zero messages.",
            "streaming_evidence": "Only decoded AsyncWebSocket messages count as streaming success; REST history is not requested.",
        },
    }
    operational_failure = deadline_terminated or bool(errors) or not child_reaped
    exit_code = 2 if operational_failure or classification == "FAILED" else 0
    return report, exit_code


def supervisor_main(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--symbols",
        *args.symbols,
        "--duration",
        str(args.duration),
        "--max-samples",
        str(args.max_samples),
        "--_worker",
    ]
    try:
        report, exit_code = supervise_command(
            command,
            symbols=args.symbols,
            duration=args.duration,
            max_samples=args.max_samples,
        )
    except Exception as exc:
        report = {
            "record_type": "final_report",
            "probe": {
                "symbols": args.symbols,
                "configured_duration_seconds": args.duration,
                "max_retained_samples": args.max_samples,
                "finished_at_utc": utc_now(),
                "uses_historical_rest": False,
                "accesses_algoshield_application_or_database": False,
            },
            "observed_facts": {
                "classification": "FAILED",
                "outcome": "supervisor_error",
                "message_count": None,
                "message_count_exact": False,
                "errors": [safe_error(exc)],
                "retained_samples": [],
            },
        }
        exit_code = 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), flush=True)
    return exit_code


def main() -> int:
    args = parse_args()
    return worker_main(args) if args._worker else supervisor_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

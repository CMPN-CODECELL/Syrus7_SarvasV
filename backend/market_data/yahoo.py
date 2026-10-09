"""Optional, supervised Yahoo quote ingestion.

Yahoo messages are sampled external quote evidence, not complete exchange ticks.
The generated event identifier is only a bounded best-effort duplicate key.
"""

import asyncio
import hashlib
import json
import math
import multiprocessing
import os
import queue
import time
from collections import OrderedDict, deque
from decimal import Decimal, InvalidOperation
from threading import Event, Lock, Thread, current_thread

from backend.shared.contracts import Tick


YAHOO_SYMBOLS = {"TCS.NS": "TCS", "INFY.NS": "INFY"}
SOURCE = "YAHOO_EXTERNAL_QUOTES"
_EXIT_QUEUE_OVERFLOW = 73


def normalize_yahoo_message(payload, *, received_at=None, max_clock_skew=120):
    """Validate and normalize one documented yfinance WebSocket message."""
    if not isinstance(payload, dict):
        raise ValueError("Yahoo message must be an object")
    yahoo_symbol = payload.get("id")
    if yahoo_symbol not in YAHOO_SYMBOLS:
        raise ValueError("unsupported Yahoo symbol")
    try:
        price = Decimal(str(payload.get("price")))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid Yahoo price") from None
    if not price.is_finite() or price <= 0:
        raise ValueError("invalid Yahoo price")

    raw_timestamp = str(payload.get("time", ""))
    if not raw_timestamp.isdigit():
        raise ValueError("invalid Yahoo timestamp")
    timestamp_ms = int(raw_timestamp)
    event_timestamp = timestamp_ms // 1000
    now = time.time() if received_at is None else float(received_at)
    if not math.isfinite(now) or abs(now - event_timestamp) > max_clock_skew:
        raise ValueError("implausible Yahoo timestamp")

    # This is deliberately not represented as an exchange trade identifier.
    duplicate_fields = {
        key: payload.get(key)
        for key in ("id", "price", "time", "day_volume", "last_size")
        if key in payload
    }
    digest = hashlib.sha256(
        json.dumps(duplicate_fields, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return Tick(
        symbol=YAHOO_SYMBOLS[yahoo_symbol],
        event_timestamp=event_timestamp,
        price=price,
        quantity=0,
        event_id=f"yahoo-quote:{digest}",
        raw_event_timestamp=raw_timestamp,
        volume_available=False,
        data_source=SOURCE,
    )


def _queue_event(output, event):
    try:
        output.put_nowait(event)
    except queue.Full:
        os._exit(_EXIT_QUEUE_OVERFLOW)


def _worker(symbols, output, stop_requested):
    """Child-process boundary around yfinance cancellation/close behavior."""

    child_started = time.monotonic()

    def lifecycle(phase, **details):
        _queue_event(
            output,
            {
                "type": "lifecycle",
                "phase": phase,
                "child_elapsed_seconds": round(time.monotonic() - child_started, 6),
                **details,
            },
        )

    async def run():
        lifecycle("import_started")
        from yfinance import AsyncWebSocket

        lifecycle("import_complete")
        socket = AsyncWebSocket(verbose=False)
        lifecycle("client_created")

        def on_message(message):
            _queue_event(output, {"type": "message", "payload": message})

        try:
            lifecycle("connection_subscription_started")
            await socket.subscribe(list(symbols))
            lifecycle("subscribed", symbols=list(symbols))
            listener = asyncio.create_task(socket.listen(on_message))
            while not stop_requested.is_set() and not listener.done():
                await asyncio.sleep(0.1)
            if not listener.done():
                listener.cancel()
            try:
                await asyncio.wait_for(listener, timeout=1.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
        except BaseException as exc:
            _queue_event(
                output,
                {"type": "error", "error": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            try:
                await asyncio.wait_for(socket.close(), timeout=1.0)
            except BaseException:
                pass

    asyncio.run(run())


class YahooMarketDataProvider:
    """Bounded process-supervised adapter that only calls ``Platform.tick``."""

    def __init__(
        self,
        platform,
        symbols=("TCS.NS", "INFY.NS"),
        *,
        queue_size=256,
        startup_timeout=8.0,
        stop_timeout=2.0,
        stale_after=15.0,
        reconnect_attempts=2,
        duplicate_capacity=2048,
        clock=time.time,
        process_target=_worker,
    ):
        symbols = tuple(symbols)
        if not symbols or any(symbol not in YAHOO_SYMBOLS for symbol in symbols):
            raise ValueError("Yahoo symbols must use the explicit supported mapping")
        if queue_size < 1 or duplicate_capacity < 1:
            raise ValueError("queue and duplicate capacities must be positive")
        self.platform = platform
        self.symbols = symbols
        self.queue_size = queue_size
        self.startup_timeout = startup_timeout
        self.stop_timeout = stop_timeout
        self.stale_after = stale_after
        self.reconnect_attempts = reconnect_attempts
        self.duplicate_capacity = duplicate_capacity
        self.clock = clock
        self.process_target = process_target
        self._stop = Event()
        self._thread = None
        self._process = None
        self._process_stop = None
        self._events = None
        self._seen = OrderedDict()
        self._lock = Lock()
        self._errors = deque(maxlen=8)
        self._connected = False
        self._last_received_at = None
        self._last_event_timestamp = None
        self._last_raw_event_timestamp = None
        self._received = 0
        self._accepted = 0
        self._duplicates = 0
        self._latest_quotes = {}
        self._deadline_terminations = 0
        self._lifecycle = deque(maxlen=32)

    def start(self):
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = Thread(
            target=self._supervise, daemon=True, name="algoshield-yahoo-supervisor"
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        with self._lock:
            self._connected = False
        if self._process_stop is not None:
            self._process_stop.set()
        thread = self._thread
        if thread and thread is not current_thread():
            thread.join(self.stop_timeout)
        self._stop_process()
        if thread and thread is not current_thread() and thread.is_alive():
            thread.join(self.stop_timeout)
        return not (thread and thread.is_alive())

    def _stop_process(self):
        process = self._process
        if process is None:
            return
        process.join(self.stop_timeout)
        if process.is_alive():
            process.terminate()
            process.join(self.stop_timeout)
            self._deadline_terminations += 1
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(self.stop_timeout)

    def _fail(self, reason, error=None):
        with self._lock:
            self._connected = False
            if error:
                self._errors.append(str(error))
        self.platform.reliability.fail_closed(reason)

    def ingest_payload(self, payload, *, received_at=None):
        """Normalize one worker message; useful for deterministic offline tests."""
        received_at = self.clock() if received_at is None else received_at
        tick = normalize_yahoo_message(payload, received_at=received_at)
        with self._lock:
            self._received += 1
            self._last_received_at = received_at
            self._last_event_timestamp = tick.event_timestamp
            self._last_raw_event_timestamp = tick.raw_event_timestamp
            if tick.event_id in self._seen:
                self._duplicates += 1
                return False
            self._seen[tick.event_id] = None
            if len(self._seen) > self.duplicate_capacity:
                self._seen.popitem(last=False)
        self.platform.tick(tick, replay=False)
        with self._lock:
            self._accepted += 1
            self._latest_quotes[tick.symbol] = {
                "symbol": tick.symbol,
                "provider_symbol": payload["id"],
                "price": str(tick.price),
                "event_timestamp": tick.event_timestamp,
                "raw_event_timestamp": tick.raw_event_timestamp,
                "received_at": received_at,
                "volume_available": False,
                "data_source": SOURCE,
            }
        return True

    def record_disconnect(self, error="Yahoo connection ended"):
        self._fail("YAHOO_FEED_DISCONNECTED", error)

    def record_queue_overflow(self):
        self._fail("YAHOO_FEED_QUEUE_OVERFLOW", "bounded ingestion queue overflow")

    def check_stale(self, now=None):
        now = self.clock() if now is None else now
        with self._lock:
            last = self._last_received_at
            connected = self._connected
        if connected and last is not None and now - last > self.stale_after:
            self._fail("YAHOO_FEED_STALE", "no quote within freshness deadline")
            return True
        return False

    def _supervise(self):
        for attempt in range(self.reconnect_attempts + 1):
            if self._stop.is_set():
                return
            events = multiprocessing.Queue(maxsize=self.queue_size)
            child_stop = multiprocessing.Event()
            process = multiprocessing.Process(
                target=self.process_target,
                args=(self.symbols, events, child_stop),
                daemon=True,
                name="algoshield-yahoo-worker",
            )
            self._events, self._process_stop, self._process = (
                events,
                child_stop,
                process,
            )
            process.start()
            subscribed_at = None
            started = time.monotonic()
            with self._lock:
                self._lifecycle.append(
                    {
                        "phase": "process_started",
                        "attempt": attempt + 1,
                        "parent_elapsed_seconds": 0.0,
                    }
                )
            dead_polls = 0
            while not self._stop.is_set():
                try:
                    event = events.get(timeout=0.1)
                except queue.Empty:
                    if not process.is_alive():
                        dead_polls += 1
                        if dead_polls >= 3:
                            break
                    else:
                        dead_polls = 0
                    if (
                        subscribed_at is None
                        and time.monotonic() - started > self.startup_timeout
                    ):
                        self._fail(
                            "YAHOO_FEED_START_TIMEOUT", "subscription deadline exceeded"
                        )
                        break
                    if self.check_stale():
                        break
                    continue
                dead_polls = 0
                kind = event.get("type")
                if kind == "lifecycle":
                    phase = event.get("phase", "unknown")
                    with self._lock:
                        self._lifecycle.append(
                            {
                                "phase": phase,
                                "attempt": attempt + 1,
                                "parent_elapsed_seconds": round(
                                    time.monotonic() - started, 6
                                ),
                                "child_elapsed_seconds": event.get(
                                    "child_elapsed_seconds"
                                ),
                            }
                        )
                    if phase == "subscribed":
                        subscribed_at = self.clock()
                        with self._lock:
                            self._connected = True
                elif kind == "subscribed":
                    subscribed_at = self.clock()
                    with self._lock:
                        self._connected = True
                elif kind == "message":
                    try:
                        self.ingest_payload(event.get("payload"))
                    except (TypeError, ValueError) as exc:
                        self._fail("YAHOO_MARKET_EVENT_REJECTED", exc)
                elif kind == "error":
                    self._fail("YAHOO_FEED_ERROR", event.get("error"))
                    break
            child_stop.set()
            self._stop_process()
            if self._stop.is_set():
                return
            reason = (
                "YAHOO_FEED_QUEUE_OVERFLOW"
                if process.exitcode == _EXIT_QUEUE_OVERFLOW
                else "YAHOO_FEED_DISCONNECTED"
            )
            if reason == "YAHOO_FEED_QUEUE_OVERFLOW":
                self.record_queue_overflow()
            else:
                self._fail(reason, f"worker exit code {process.exitcode}")
            if attempt < self.reconnect_attempts and self._stop.wait(
                min(2**attempt, 4)
            ):
                return

    def telemetry(self):
        with self._lock:
            return {
                "provider": SOURCE,
                "label": "YAHOO EXTERNAL QUOTES / MOCK EXECUTION",
                "connected": self._connected,
                "symbols": list(self.symbols),
                "canonical_symbols": [YAHOO_SYMBOLS[symbol] for symbol in self.symbols],
                "latest_quotes": [
                    self._latest_quotes.get(
                        YAHOO_SYMBOLS[provider_symbol],
                        {
                            "symbol": YAHOO_SYMBOLS[provider_symbol],
                            "provider_symbol": provider_symbol,
                            "price": None,
                            "event_timestamp": None,
                            "raw_event_timestamp": None,
                            "received_at": None,
                            "volume_available": False,
                            "data_source": SOURCE,
                        },
                    ).copy()
                    for provider_symbol in self.symbols
                ],
                "last_received_at": self._last_received_at,
                "last_event_timestamp": self._last_event_timestamp,
                "last_raw_event_timestamp": self._last_raw_event_timestamp,
                "volume_available": False,
                "received_messages": self._received,
                "accepted_updates": self._accepted,
                "duplicate_updates": self._duplicates,
                "errors": list(self._errors),
                "queue_capacity": self.queue_size,
                "deadline_terminations": self._deadline_terminations,
                "event_id_semantics": "generated best-effort duplicate key; not an exchange trade ID",
                "lifecycle": list(self._lifecycle),
            }

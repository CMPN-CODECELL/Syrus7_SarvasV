"""Documented 021 market WebSocket provider.

The provider emits canonical ``Tick`` values into the existing CandleBuilder
boundary.  It is deliberately opt-in and does not resume trading when a socket
connects or reconnects; the platform's reconciliation/resume controls remain the
authority for risk-increasing execution.
"""

from __future__ import annotations

import time
import json
from threading import Event, Lock, Thread, current_thread

from backend.broker.official021 import ObservationKind, parse_market_frames
from backend.shared.contracts import Tick


class MarketData021Provider:
    supports_live_broker = True

    def __init__(self, platform, adapter, symbols, *, mode="full", socket_factory=None):
        if mode not in {"ltp", "ltpo", "ltpc", "full"}:
            raise ValueError("unsupported 021 market mode")
        self.adapter = adapter
        self.platform = platform
        self.symbols = tuple(
            dict.fromkeys(symbol.upper() for symbol in symbols if symbol)
        )
        if not self.symbols:
            raise ValueError("at least one 021 symbol is required")
        self.mode = mode
        self.socket_factory = socket_factory
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._connected = False
        self._last_volume = {}
        self._latest_quotes = {}
        self._last_received_at = None
        self._last_event_timestamp = None
        self._last_raw_event_timestamp = None
        self.received = 0
        self.normalized = 0
        self.errors = []

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True, name="021-market-data")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not current_thread():
            self._thread.join(timeout=1.0)
        return not (self._thread and self._thread.is_alive())

    def _connect(self):
        token = self.adapter.ephemeral_key()
        instruments = [self.adapter._instrument(symbol) for symbol in self.symbols]
        pairs = [[instrument.exchange, instrument.token] for instrument in instruments]
        url = self.adapter.base_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        url = url.replace("/api/developer-api/v1", "/api/developer/websocket/market")
        url = f"{url}?token={token}"
        factory = self.socket_factory
        if factory is None:
            from websockets.sync.client import connect

            factory = connect
        socket = factory(url)
        socket.send(
            json.dumps({"Task": "subscribe", "Mode": self.mode, "Instruments": pairs})
        )
        return socket

    def _run(self):
        try:
            socket = self._connect()
            with self._lock:
                self._connected = True
            try:
                while not self._stop.is_set():
                    try:
                        frame = socket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if frame is None:
                        break
                    if isinstance(frame, str):
                        continue
                    self.received += 1
                    for observation in parse_market_frames(frame):
                        self._emit(observation)
            finally:
                with self._lock:
                    self._connected = False
                try:
                    socket.close()
                except Exception:
                    pass
            if not self._stop.is_set():
                with self._lock:
                    self.errors.append("CONNECTION_ENDED")
                self.platform.reliability.fail_closed("021_FEED_DISCONNECTED")
        except Exception as exc:
            with self._lock:
                self._connected = False
                self.errors.append(type(exc).__name__)
            try:
                self.platform.reliability.fail_closed("021_FEED_DISCONNECTED")
            except Exception:
                # Small provider test doubles may not expose reliability state.
                pass

    def _emit(self, observation):
        if observation.kind == ObservationKind.HEARTBEAT:
            return
        instrument = next(
            (
                value
                for value in self.adapter.instruments.values()
                if value.exchange == observation.exchange
                and value.token == observation.token
            ),
            None,
        )
        if instrument is None or observation.ltp is None:
            return
        volume_available = False
        quantity = 0
        volume_key = (observation.exchange, observation.token)
        if observation.cumulative_volume is not None:
            prior = self._last_volume.get(volume_key)
            if prior is not None:
                quantity = observation.cumulative_volume - prior
                if quantity < 0:
                    with self._lock:
                        self.errors.append("VOLUME_REGRESSION")
                    self.platform.reliability.fail_closed("021_VOLUME_REGRESSION")
                    return
                volume_available = True
            self._last_volume[volume_key] = observation.cumulative_volume
        received_at = time.time()
        timestamp = observation.exchange_timestamp or int(received_at)
        raw_volume = (
            "na"
            if observation.cumulative_volume is None
            else observation.cumulative_volume
        )
        event_id = (
            f"021:{observation.exchange}:{observation.token}:"
            f"{timestamp}:{observation.ltp}:{raw_volume}"
        )
        tick = Tick(
            instrument.symbol,
            int(timestamp),
            observation.ltp,
            quantity,
            event_id,
            raw_event_timestamp=(
                str(observation.exchange_timestamp)
                if observation.exchange_timestamp is not None
                else None
            ),
            volume_available=volume_available,
            data_source="021_LIVE",
        )
        self.platform.tick(tick, replay=False)
        with self._lock:
            self.normalized += 1
            self._last_received_at = received_at
            self._last_event_timestamp = timestamp
            self._last_raw_event_timestamp = observation.exchange_timestamp
            self._latest_quotes[instrument.symbol] = {
                "symbol": instrument.symbol,
                "provider_symbol": instrument.symbol,
                "price": str(observation.ltp),
                "event_timestamp": timestamp,
                "raw_event_timestamp": observation.exchange_timestamp,
                "received_at": received_at,
                "volume_available": volume_available,
                "data_source": "021_LIVE",
            }

    def telemetry(self):
        with self._lock:
            return {
                "provider": "021",
                "source": "021_LIVE",
                "label": "021 LIVE / REAL MARKET DATA",
                "connected": self._connected,
                "symbols": list(self.symbols),
                "canonical_symbols": list(self.symbols),
                "latest_quotes": [
                    self._latest_quotes[symbol]
                    for symbol in self.symbols
                    if symbol in self._latest_quotes
                ],
                "last_received_at": self._last_received_at,
                "last_event_timestamp": self._last_event_timestamp,
                "last_raw_event_timestamp": self._last_raw_event_timestamp,
                "volume_available": False,
                "received_messages": self.received,
                "accepted_updates": self.normalized,
                "received": self.received,
                "normalized": self.normalized,
                "errors": list(self.errors[-8:]),
                "event_id_semantics": (
                    "generated best-effort observation key; not an exchange trade ID"
                ),
            }

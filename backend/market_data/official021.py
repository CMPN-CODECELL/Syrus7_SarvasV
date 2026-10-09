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

from backend.broker.official021 import ObservationKind, Provider021Error, parse_market_frames
from backend.shared.contracts import Tick


class MarketData021Provider:
    supports_live_broker = True
    MAX_INSTRUMENTS_PER_CONNECTION = 100
    MAX_CONNECTIONS = 20

    def __init__(self, platform, adapter, symbols, *, mode="full", socket_factory=None):
        if mode not in {"ltp", "ltpo", "ltpc", "full"}:
            raise ValueError("unsupported 021 market mode")
        self.adapter = adapter
        self.platform = platform
        requested_symbols = tuple(
            dict.fromkeys(symbol.upper() for symbol in symbols if symbol)
        )
        if not requested_symbols:
            raise ValueError("at least one 021 symbol is required")
        capacity = self.MAX_INSTRUMENTS_PER_CONNECTION * self.MAX_CONNECTIONS
        self.symbols = requested_symbols[:capacity]
        self.mode = mode
        self.socket_factory = socket_factory
        self._stop = Event()
        self._thread: Thread | None = None
        self._threads: list[Thread] = []
        self._ephemeral_key: str | None = None
        self._lock = Lock()
        self._connected = False
        self._connected_count = 0
        self._last_volume = {}
        self._latest_quotes = {}
        self._last_received_at = None
        self._last_event_timestamp = None
        self._last_raw_event_timestamp = None
        self.received = 0
        self.normalized = 0
        self.errors = []
        if len(requested_symbols) > capacity:
            self.errors.append(
                f"UNIVERSE_TRUNCATED_021_LIMIT:{len(requested_symbols)}>{capacity}"
            )

    def start(self):
        if any(thread.is_alive() for thread in self._threads):
            return False
        self._stop.clear()
        self._threads = []
        self._ephemeral_key = self.adapter.ephemeral_key()
        for index in range(0, len(self.symbols), self.MAX_INSTRUMENTS_PER_CONNECTION):
            chunk = self.symbols[index : index + self.MAX_INSTRUMENTS_PER_CONNECTION]
            thread = Thread(
                target=self._run,
                args=(chunk,),
                daemon=True,
                name=f"021-market-data-{index // self.MAX_INSTRUMENTS_PER_CONNECTION + 1}",
            )
            self._threads.append(thread)
            thread.start()
        self._thread = self._threads[0]
        return True

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            if thread is not current_thread():
                thread.join(timeout=1.0)
        return not any(thread.is_alive() for thread in self._threads)

    def _connect(self, symbols):
        token = self._ephemeral_key or self.adapter.ephemeral_key()
        instruments = [self.adapter._instrument(symbol) for symbol in symbols]
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

    def _run(self, symbols):
        try:
            socket = self._connect(symbols)
            with self._lock:
                self._connected_count += 1
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
                    try:
                        observations = parse_market_frames(frame)
                    except Exception as exc:
                        with self._lock:
                            detail = str(exc).strip()
                            self.errors.append(
                                f"{type(exc).__name__}: {detail[:120]}"
                                if detail
                                else type(exc).__name__
                            )
                        self.platform.reliability.fail_closed("021_FEED_PROTOCOL_ERROR")
                        continue
                    for observation in observations:
                        try:
                            self._emit(observation)
                        except (ValueError, Provider021Error) as exc:
                            with self._lock:
                                detail = str(exc).strip()
                                self.errors.append(
                                    f"{type(exc).__name__}: {detail[:120]}"
                                    if detail
                                    else type(exc).__name__
                                )
                            self.platform.reliability.fail_closed("021_FEED_UPDATE_REJECTED")
            finally:
                with self._lock:
                    self._connected_count = max(0, self._connected_count - 1)
                    self._connected = self._connected_count > 0
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
                self._connected_count = max(0, self._connected_count - 1)
                self._connected = self._connected_count > 0
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
        # The documented exchange epoch is not consistently applied by the
        # development feed.  Never place a candle in the future or reorder the
        # stream: use receive-time evidence while retaining the raw timestamp.
        if abs(timestamp - int(received_at)) > 86_400:
            timestamp = int(received_at)
            with self._lock:
                self.errors.append("EXCHANGE_TIMESTAMP_FALLBACK_RECEIVE_TIME")
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
                "connection_count": self._connected_count,
                "connection_limit": self.MAX_CONNECTIONS,
                "instrument_limit_per_connection": self.MAX_INSTRUMENTS_PER_CONNECTION,
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

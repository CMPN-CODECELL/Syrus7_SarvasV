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

from backend.broker.official021 import (
    ObservationKind,
    Provider021Error,
    parse_market_frames,
)
from backend.shared.contracts import Tick


class MarketData021Provider:
    supports_live_broker = True
    MAX_INSTRUMENTS_PER_CONNECTION = 100
    MAX_CONNECTIONS = 20

    def __init__(
        self,
        platform,
        adapter,
        symbols=(),
        *,
        mode="full",
        socket_factory=None,
        max_timestamp_skew_seconds=10,
    ):
        if mode not in {"ltp", "ltpo", "ltpc", "full"}:
            raise ValueError("unsupported 021 market mode")
        self.adapter = adapter
        self.platform = platform
        if max_timestamp_skew_seconds <= 0:
            raise ValueError("max_timestamp_skew_seconds must be positive")
        requested_symbols = tuple(
            dict.fromkeys(symbol.upper() for symbol in symbols if symbol)
        )
        self.pinned_symbols = requested_symbols
        self.symbols = ()
        self.mode = mode
        self.socket_factory = socket_factory
        self.max_timestamp_skew_seconds = int(max_timestamp_skew_seconds)
        self._stop = Event()
        self._thread: Thread | None = None
        self._threads: list[Thread] = []
        self._lock = Lock()
        self._connected = False
        self._connected_count = 0
        self._last_volume = {}
        self._latest_quotes = {}
        self._generation_sequence = 0
        self._symbol_generations = {}
        self._serving_evidence = {}
        self._last_event_by_symbol = {}
        self._observation_fingerprints = {}
        self._last_received_at = None
        self._last_event_timestamp = None
        self._last_raw_event_timestamp = None
        self.timestamp_fallbacks = 0
        self.timestamp_missing_fallbacks = 0
        self.timestamp_future_fallbacks = 0
        self.timestamp_past_fallbacks = 0
        self.timestamp_reorder_fallbacks = 0
        self.provider_duplicates_dropped = 0
        self.reconnect_attempts = 0
        self.last_disconnect_reason = None
        self.last_connected_at = None
        self.last_disconnected_at = None
        self.health = "IDLE"
        self.desired_symbols = requested_symbols
        self.unsupported_symbols = []
        self.received = 0
        self.normalized = 0
        self.errors = []
        self.universe_truncated = None

    def _resolve_universe(self):
        rows = self.platform.store.rows(
            "SELECT DISTINCT symbol FROM subscriptions WHERE enabled=1 ORDER BY symbol"
        )
        desired = tuple(
            dict.fromkeys(
                (
                    *self.pinned_symbols,
                    *(row["symbol"].upper() for row in rows),
                    *(
                        self.platform.required_market_symbols()
                        if hasattr(self.platform, "required_market_symbols")
                        else ()
                    ),
                )
            )
        )
        valid, unsupported = [], []
        for symbol in desired:
            try:
                self.adapter._instrument(symbol)
            except Provider021Error:
                unsupported.append(symbol)
            else:
                valid.append(symbol)
        capacity = self.MAX_INSTRUMENTS_PER_CONNECTION * self.MAX_CONNECTIONS
        self.desired_symbols = desired
        self.unsupported_symbols = unsupported
        self.universe_truncated = (
            f"{len(valid)}>{capacity}" if len(valid) > capacity else None
        )
        return tuple(valid[:capacity])

    def validate_symbols(self, symbols):
        unsupported = []
        for symbol in symbols:
            try:
                self.adapter._instrument(symbol)
            except Provider021Error:
                unsupported.append(str(symbol).upper())
        if unsupported:
            raise Provider021Error(
                "unsupported 021 instrument symbol(s): "
                + ", ".join(sorted(set(unsupported)))
            )

    def start(self):
        if any(thread.is_alive() for thread in self._threads):
            return False
        self._stop.clear()
        self._threads = []
        self.symbols = self._resolve_universe()
        if not self.symbols:
            with self._lock:
                self._connected = False
                self.health = "IDLE"
            return False
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

    def refresh_universe(self):
        """Apply enabled-subscription changes by rebuilding a bounded feed safely."""
        next_symbols = self._resolve_universe()
        if next_symbols == self.symbols:
            return False
        was_running = any(thread.is_alive() for thread in self._threads)
        if was_running:
            self.platform.reliability.fail_closed("021_UNIVERSE_CHANGED")
            self.stop()
        with self._lock:
            self._serving_evidence.clear()
            self._latest_quotes.clear()
            self._symbol_generations.clear()
        self.symbols = next_symbols
        if next_symbols:
            self.start()
        return True

    def _connect(self, symbols):
        token = self.adapter.ephemeral_key()
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

            socket = connect(url, ping_interval=None)
        else:
            socket = factory(url)
        socket.send(
            json.dumps({"Task": "subscribe", "Mode": self.mode, "Instruments": pairs})
        )
        return socket

    def _run(self, symbols):
        backoff = (1, 2, 5, 10, 30)
        attempt = 0
        while not self._stop.is_set():
            socket = None
            connected = False
            try:
                socket = self._connect(symbols)
                connected = True
                with self._lock:
                    self._generation_sequence += 1
                    generation = self._generation_sequence
                    for symbol in symbols:
                        self._symbol_generations[symbol] = generation
                        self._serving_evidence.pop(symbol, None)
                        self._latest_quotes.pop(symbol, None)
                with self._lock:
                    self._connected_count += 1
                    self._connected = True
                    self.health = "CONNECTED"
                    self.last_disconnect_reason = None
                    self.last_connected_at = time.time()
                while not self._stop.is_set():
                    try:
                        frame = socket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if frame is None:
                        raise ConnectionError("market websocket closed")
                    if isinstance(frame, str):
                        continue
                    self.received += 1
                    try:
                        observations = parse_market_frames(frame)
                    except Exception as exc:
                        with self._lock:
                            self.errors.append(
                                f"{type(exc).__name__}: protocol frame rejected"
                            )
                        self.platform.reliability.fail_closed("021_FEED_PROTOCOL_ERROR")
                        continue
                    for observation in observations:
                        try:
                            self._emit(observation, generation=generation)
                        except (ValueError, Provider021Error) as exc:
                            with self._lock:
                                self.errors.append(
                                    f"{type(exc).__name__}: market update rejected"
                                )
                            self.platform.reliability.fail_closed(
                                "021_FEED_UPDATE_REJECTED"
                            )
            except Exception as exc:
                if not self._stop.is_set():
                    with self._lock:
                        self.last_disconnect_reason = type(exc).__name__
                        self.health = "RECONNECTING"
                        self.reconnect_attempts += 1
                        self.last_disconnected_at = time.time()
                    self.platform.reliability.fail_closed("021_FEED_DISCONNECTED")
                    delay = backoff[min(attempt, len(backoff) - 1)]
                    attempt += 1
                    if self._stop.wait(delay):
                        break
            finally:
                if connected:
                    with self._lock:
                        for symbol in symbols:
                            if self._symbol_generations.get(symbol) == generation:
                                self._serving_evidence.pop(symbol, None)
                                self._latest_quotes.pop(symbol, None)
                        self._connected_count = max(0, self._connected_count - 1)
                        self._connected = self._connected_count > 0
                if socket is not None:
                    try:
                        socket.close()
                    except Exception:
                        pass
            if connected:
                attempt = 0

    def _emit(self, observation, *, generation=None):
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
        with self._lock:
            current_generation = self._symbol_generations.get(instrument.symbol)
            if generation is None:
                # Deterministic unit tests can ingest without a socket. Such an
                # observation is never serving proof because connected is false.
                generation = current_generation if current_generation is not None else 0
                self._symbol_generations.setdefault(instrument.symbol, generation)
            elif current_generation != generation:
                return
        fingerprint = (
            observation.exchange,
            observation.token,
            observation.exchange_timestamp,
            str(observation.ltp),
            observation.cumulative_volume,
            str(observation.official_open)
            if observation.official_open is not None
            else None,
        )
        fingerprint_key = (observation.exchange, observation.token)
        if self._observation_fingerprints.get(fingerprint_key) == fingerprint:
            with self._lock:
                self.provider_duplicates_dropped += 1
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
        raw_timestamp = observation.exchange_timestamp
        timestamp = raw_timestamp or int(received_at)
        event_time_status = "VERIFIED"
        # The documented exchange epoch is not consistently applied by the
        # development feed.  Never place a candle in the future or reorder the
        # stream: use receive-time evidence while retaining the raw timestamp.
        skew = timestamp - int(received_at)
        if raw_timestamp is None:
            timestamp = int(received_at)
            event_time_status = "MISSING_FALLBACK"
            with self._lock:
                self.timestamp_fallbacks += 1
                self.timestamp_missing_fallbacks += 1
        elif skew > self.max_timestamp_skew_seconds:
            timestamp = int(received_at)
            event_time_status = "FUTURE_FALLBACK"
            with self._lock:
                self.timestamp_fallbacks += 1
                self.timestamp_future_fallbacks += 1
        elif skew < -self.max_timestamp_skew_seconds:
            timestamp = int(received_at)
            event_time_status = "PAST_FALLBACK"
            with self._lock:
                self.timestamp_fallbacks += 1
                self.timestamp_past_fallbacks += 1
        prior_timestamp = self._last_event_by_symbol.get(instrument.symbol)
        if prior_timestamp is not None and timestamp < prior_timestamp:
            timestamp = max(int(received_at), prior_timestamp + 1)
            event_time_status = "REORDER_FALLBACK"
            with self._lock:
                self.timestamp_fallbacks += 1
                self.timestamp_reorder_fallbacks += 1
        self._last_event_by_symbol[instrument.symbol] = timestamp
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
            received_at=received_at,
            event_time_status=event_time_status,
        )
        with self._lock:
            self._observation_fingerprints[fingerprint_key] = fingerprint
            self._last_received_at = received_at
            self._last_event_timestamp = timestamp
            self._last_raw_event_timestamp = observation.exchange_timestamp
            self._latest_quotes[instrument.symbol] = {
                "symbol": instrument.symbol,
                "provider_symbol": instrument.symbol,
                "price": str(observation.ltp),
                "event_timestamp": observation.exchange_timestamp,
                "normalized_event_timestamp": timestamp,
                "raw_event_timestamp": observation.exchange_timestamp,
                "received_at": received_at,
                "connection_generation": generation,
                "event_time_status": event_time_status,
                "volume_available": volume_available,
                "official_open": str(observation.official_open)
                if observation.official_open is not None
                else None,
                "data_source": "021_LIVE",
            }
        accepted = self.platform.tick(tick, replay=False)
        with self._lock:
            if accepted is not False and event_time_status == "VERIFIED":
                self._serving_evidence[instrument.symbol] = {
                    "symbol": instrument.symbol,
                    "evidence_type": "FRESH_VALID_OBSERVATION",
                    "connection_generation": generation,
                    "observed_at": received_at,
                    "event_timestamp": timestamp,
                }
            else:
                self._serving_evidence.pop(instrument.symbol, None)
            if accepted is not False:
                self.normalized += 1

    def telemetry(self):
        with self._lock:
            return {
                "provider": "021",
                "source": "021_LIVE",
                "label": "021 LIVE / REAL MARKET DATA",
                "instrument_exchange": getattr(
                    self.adapter, "instrument_exchange", None
                ),
                "connected": self._connected,
                "connection_count": self._connected_count,
                "connected_sockets": self._connected_count,
                "expected_sockets": (
                    len(self.symbols) + self.MAX_INSTRUMENTS_PER_CONNECTION - 1
                )
                // self.MAX_INSTRUMENTS_PER_CONNECTION,
                "health": self.health,
                "connection_limit": self.MAX_CONNECTIONS,
                "instrument_limit_per_connection": self.MAX_INSTRUMENTS_PER_CONNECTION,
                "universe_truncated": self.universe_truncated,
                "symbols": list(self.symbols),
                "desired_symbols": list(self.desired_symbols),
                # The reviewed 021 feed contract exposes no subscription ACK.
                # Keep this empty rather than relabeling a local send as proof.
                "subscribed_symbols": [],
                "requested_symbols": list(self.symbols),
                "subscription_evidence_semantics": "OBSERVATION_BASED_NOT_PROVIDER_ACK",
                "symbol_generations": dict(self._symbol_generations),
                "serving_evidence": [
                    self._serving_evidence[symbol]
                    for symbol in sorted(self._serving_evidence)
                    if self._symbol_generations.get(symbol)
                    == self._serving_evidence[symbol]["connection_generation"]
                ],
                "serving_symbols": sorted(
                    symbol
                    for symbol, item in self._serving_evidence.items()
                    if self._symbol_generations.get(symbol)
                    == item["connection_generation"]
                ),
                "unsupported_symbols": list(self.unsupported_symbols),
                "canonical_symbols": list(self.symbols),
                "latest_quotes": [
                    self._latest_quotes[symbol]
                    for symbol in sorted(self._latest_quotes)
                ],
                "last_received_at": self._last_received_at,
                "last_event_timestamp": self._last_event_timestamp,
                "last_raw_event_timestamp": self._last_raw_event_timestamp,
                "timestamp_fallbacks": self.timestamp_fallbacks,
                "timestamp_missing_fallbacks": self.timestamp_missing_fallbacks,
                "timestamp_future_fallbacks": self.timestamp_future_fallbacks,
                "timestamp_past_fallbacks": self.timestamp_past_fallbacks,
                "timestamp_reorder_fallbacks": self.timestamp_reorder_fallbacks,
                "provider_duplicates_dropped": self.provider_duplicates_dropped,
                "reconnect_attempts": self.reconnect_attempts,
                "last_disconnect_reason": self.last_disconnect_reason,
                "last_connected_at": self.last_connected_at,
                "last_disconnected_at": self.last_disconnected_at,
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

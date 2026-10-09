"""Documented 021 market WebSocket provider.

The provider emits canonical ``Tick`` values into the existing CandleBuilder
boundary.  It is deliberately opt-in and does not resume trading when a socket
connects or reconnects; the platform's reconciliation/resume controls remain the
authority for risk-increasing execution.
"""

from __future__ import annotations

import time
import json
from threading import Event, Thread, current_thread

from backend.broker.official021 import ObservationKind, parse_market_frames
from backend.shared.contracts import Tick


class MarketData021Provider:
    supports_live_broker = True
    def __init__(self, platform, adapter, symbols, *, mode="full", socket_factory=None):
        if mode not in {"ltp", "ltpo", "ltpc", "full"}:
            raise ValueError("unsupported 021 market mode")
        self.adapter = adapter
        self.platform = platform
        self.symbols = tuple(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        if not self.symbols:
            raise ValueError("at least one 021 symbol is required")
        self.mode = mode
        self.socket_factory = socket_factory
        self._stop = Event()
        self._thread: Thread | None = None
        self._callback = None
        self._last_volume = {}
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
        return True

    def _connect(self):
        token = self.adapter.ephemeral_key()
        instruments = [self.adapter._instrument(symbol) for symbol in self.symbols]
        pairs = [[instrument.exchange, instrument.token] for instrument in instruments]
        url = self.adapter.base_url.replace("https://", "wss://").replace("http://", "ws://")
        url = url.replace("/api/developer-api/v1", "/api/developer/websocket/market")
        url = f"{url}?token={token}"
        factory = self.socket_factory
        if factory is None:
            from websockets.sync.client import connect

            factory = connect
        socket = factory(url)
        socket.send(json.dumps({"Task": "subscribe", "Mode": self.mode, "Instruments": pairs}))
        return socket

    def _run(self):
        try:
            socket = self._connect()
            try:
                while not self._stop.is_set():
                    frame = socket.recv(timeout=1)
                    if frame is None:
                        break
                    if isinstance(frame, str):
                        continue
                    self.received += 1
                    for observation in parse_market_frames(frame):
                        self._emit(observation)
            finally:
                try:
                    socket.close()
                except Exception:
                    pass
        except Exception as exc:
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
                if value.exchange == observation.exchange and value.token == observation.token
            ),
            None,
        )
        if instrument is None or observation.ltp is None:
            return
        volume_available = observation.cumulative_volume is not None
        quantity = 0
        if volume_available:
            prior = self._last_volume.get((observation.exchange, observation.token), 0)
            quantity = observation.cumulative_volume - prior
            if quantity < 0:
                self.errors.append("VOLUME_REGRESSION")
                return
            self._last_volume[(observation.exchange, observation.token)] = observation.cumulative_volume
        timestamp = observation.exchange_timestamp or int(time.time())
        event_id = f"021:{observation.exchange}:{observation.token}:{timestamp}:{observation.ltp}"
        tick = Tick(
            instrument.symbol,
            int(timestamp),
            observation.ltp,
            quantity,
            event_id,
            volume_available=volume_available,
            data_source="021_LIVE",
        )
        self.normalized += 1
        self.platform.tick(tick, replay=False)

    def telemetry(self):
        return {
            "provider": "021",
            "source": "021_LIVE",
            "label": "021 LIVE / REAL MARKET DATA",
            "connected": bool(self._thread and self._thread.is_alive()),
            "symbols": list(self.symbols),
            "received": self.received,
            "normalized": self.normalized,
            "errors": list(self.errors[-8:]),
        }

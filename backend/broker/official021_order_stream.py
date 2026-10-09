"""Bounded lifecycle for documented 021 order-status WebSocket evidence.

The exchange stream has no documented trade ID, so it may queue lifecycle
updates but never creates a financial fill. REST per-order trades remain the
sole fill authority.
"""

from __future__ import annotations

from threading import Event, Lock, Thread, current_thread


class OrderStream021:
    BACKOFF_SECONDS = (1, 2, 5, 10, 30)

    def __init__(self, adapter, enqueue, on_disconnect=None):
        self.adapter = adapter
        self.enqueue = enqueue
        self.on_disconnect = on_disconnect
        self._stop = Event()
        self._thread = None
        self._lock = Lock()
        self.connected = False
        self.frames_received = 0
        self.reconnect_attempts = 0
        self.last_disconnect_reason = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True, name="021-order-stream")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not current_thread():
            thread.join(timeout=1.0)
        return not (thread and thread.is_alive())

    def telemetry(self):
        with self._lock:
            return {
                "connected": self.connected,
                "frames_received": self.frames_received,
                "reconnect_attempts": self.reconnect_attempts,
                "last_disconnect_reason": self.last_disconnect_reason,
            }

    def _run(self):
        attempt = 0
        while not self._stop.is_set():
            socket = None
            try:
                socket = self.adapter.connect_order_websocket()
                with self._lock:
                    self.connected = True
                    self.last_disconnect_reason = None
                attempt = 0
                while not self._stop.is_set():
                    try:
                        frame = socket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    if frame is None:
                        raise ConnectionError("order websocket closed")
                    if isinstance(frame, str):
                        continue
                    update = self.adapter.parse_order_update(frame)
                    with self._lock:
                        self.frames_received += 1
                    if update is not None:
                        self.enqueue(update)
            except Exception as exc:
                if self._stop.is_set():
                    break
                with self._lock:
                    self.connected = False
                    self.last_disconnect_reason = type(exc).__name__
                    self.reconnect_attempts += 1
                if self.on_disconnect is not None:
                    self.on_disconnect(type(exc).__name__)
                delay = self.BACKOFF_SECONDS[
                    min(attempt, len(self.BACKOFF_SECONDS) - 1)
                ]
                attempt += 1
                self._stop.wait(delay)
            finally:
                with self._lock:
                    self.connected = False
                if socket is not None:
                    try:
                        socket.close()
                    except Exception:
                        pass

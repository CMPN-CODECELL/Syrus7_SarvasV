from threading import Event

from backend.broker.official021_order_stream import OrderStream021


class Socket:
    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False

    def recv(self, timeout=1):
        if self.frames:
            return self.frames.pop(0)
        raise TimeoutError

    def close(self):
        self.closed = True


class Adapter:
    def __init__(self, sockets):
        self.sockets = list(sockets)
        self.connected = Event()

    def connect_order_websocket(self):
        self.connected.set()
        return self.sockets.pop(0)

    def parse_order_update(self, frame):
        return {"frame": frame}


def test_order_stream_queues_status_evidence_without_creating_fills():
    adapter = Adapter([Socket([b"status-frame"])])
    updates = []
    received = Event()

    def enqueue(update):
        updates.append(update)
        received.set()

    stream = OrderStream021(adapter, enqueue)
    assert stream.start() is True
    assert adapter.connected.wait(1)
    assert received.wait(1)
    assert stream.stop() is True
    assert updates == [{"frame": b"status-frame"}]
    assert stream.telemetry()["frames_received"] == 1


def test_order_stream_reconnect_wait_is_interruptible():
    class BrokenAdapter:
        def connect_order_websocket(self):
            raise ConnectionError("closed")

    disconnected = Event()
    stream = OrderStream021(
        BrokenAdapter(),
        lambda update: None,
        lambda reason: disconnected.set(),
    )
    assert stream.start() is True
    assert disconnected.wait(1)
    assert stream.stop() is True
    assert stream.telemetry()["reconnect_attempts"] >= 1

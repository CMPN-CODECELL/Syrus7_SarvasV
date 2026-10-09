from threading import Event

from backend.broker.official021_order_stream import OrderStream021
from backend.broker.official021 import Provider021ProtocolError


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


def test_protocol_error_records_only_sanitized_frame_metadata_and_reconnects():
    class MalformedAdapter(Adapter):
        def parse_order_update(self, frame):
            raise Provider021ProtocolError("malformed")

    disconnected = Event()
    adapter = MalformedAdapter([Socket([b"\x00\x04secret-account-data"])])
    stream = OrderStream021(
        adapter,
        lambda update: None,
        lambda reason: disconnected.set(),
    )
    assert stream.start() is True
    assert disconnected.wait(1)
    assert stream.stop() is True
    telemetry = stream.telemetry()
    assert telemetry["protocol_errors"] == 1
    assert telemetry["last_protocol_error"] == {
        "length": 21,
        "prefix_hex": "00047365",
    }
    assert "account" not in str(telemetry)


def test_text_control_message_is_counted_without_becoming_an_order_update():
    adapter = Adapter([Socket(['{"type":"connected"}'])])
    stream = OrderStream021(adapter, lambda update: None)
    assert stream.start() is True
    assert adapter.connected.wait(1)
    for _ in range(1000):
        if stream.telemetry()["control_messages_received"]:
            break
    assert stream.stop() is True
    assert stream.telemetry()["control_messages_received"] == 1

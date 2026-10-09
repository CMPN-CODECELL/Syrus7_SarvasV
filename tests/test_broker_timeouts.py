from threading import Event, Thread

from backend.reliability.broker_calls import BrokerSession


class Adapter:
    pass


def test_broker_session_uses_operation_specific_deadlines():
    session = BrokerSession(
        Adapter(),
        read_timeout=3,
        write_timeout=5,
        reconciliation_timeout=9,
    )

    assert session._operation_timeout("snapshot") == 9
    assert session._operation_timeout("submit") == 5
    assert session._operation_timeout("cancel") == 5
    assert session._operation_timeout("execute") == 5

    # Preserve the existing emergency/test control that tightens every call.
    session.call_timeout = 0.05
    assert session.read_timeout == 0.05
    assert session.write_timeout == 0.05
    assert session.reconciliation_timeout == 0.05


def test_write_waits_for_in_progress_snapshot_instead_of_becoming_uncertain():
    snapshot_started = Event()
    release_snapshot = Event()
    submitted = Event()

    class CoordinatedAdapter:
        def snapshot(self):
            snapshot_started.set()
            release_snapshot.wait(1)
            return "snapshot"

        def submit(self, _intent):
            submitted.set()
            return "submitted"

    session = BrokerSession(CoordinatedAdapter(), write_timeout=1)
    snapshot_call = session.start("snapshot")
    assert snapshot_started.wait(1)
    result = []
    worker = Thread(target=lambda: result.append(session.call("submit", "intent")))
    worker.start()

    assert submitted.wait(0.05) is False
    release_snapshot.set()
    assert session.wait(snapshot_call) == "snapshot"
    worker.join(1)
    assert result == ["submitted"]
    assert session.uncertain is False

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

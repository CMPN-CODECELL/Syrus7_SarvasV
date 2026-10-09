import importlib.util
import sys
import time
from pathlib import Path


def load_probe_module():
    path = Path(__file__).parents[1] / "scripts" / "probe_yfinance_stream.py"
    spec = importlib.util.spec_from_file_location("probe_yfinance_stream", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_probe_observations_are_bounded_and_semantics_remain_explicit():
    probe = load_probe_module()
    observations = probe.Observations(["TCS.NS"], max_samples=1, started=0.0)

    message = {
        "id": "TCS.NS",
        "time": 1_700_000_000_000,
        "price": 3500.25,
        "day_volume": 123456,
        "last_size": 20,
    }
    observations.handle(message)
    observations.handle(message)

    assert observations.message_count == 2
    assert len(observations.samples) == 1
    assert observations.field_counts["price"] == 2
    assert observations.timestamps[0]["unit"] == "milliseconds"
    assert observations.volume_values == {
        "day_volume": [123456, 123456],
        "last_size": [20, 20],
    }
    assert probe.timestamp_observation("1700000000000") == {
        "value": "1700000000000",
        "unit": "milliseconds",
        "decoded_representation": "decimal string",
        "utc_if_inferred_unit": "2023-11-14T22:13:20+00:00",
        "basis": "numeric magnitude and plausible Unix epoch conversion; inference, not provider contract",
    }


def test_probe_redacts_sensitive_fields_and_url_credentials():
    probe = load_probe_module()

    assert probe.safe_value({"token": "do-not-print", "price": 1}) == {
        "token": "<redacted>",
        "price": 1,
    }
    error = probe.safe_error(
        RuntimeError("wss://user:password@example.test/path?token=do-not-print")
    )
    assert "password" not in error["message"]
    assert "do-not-print" not in error["message"]


def child_command(*events, hang=False):
    statements = ["import json,time"]
    statements.extend(f"print(json.dumps({event!r}), flush=True)" for event in events)
    if hang:
        statements.append("time.sleep(60)")
    return [sys.executable, "-c", ";".join(statements)]


def test_supervisor_bounds_hanging_connection_and_does_not_infer_zero():
    probe = load_probe_module()
    started = time.monotonic()

    report, exit_code = probe.supervise_command(
        child_command(
            {"event": "worker_started"},
            {"event": "connection_subscription_started"},
            hang=True,
        ),
        symbols=["TCS.NS"],
        duration=0.75,
        grace_seconds=0.05,
        max_samples=1,
        emit_progress=False,
    )

    assert time.monotonic() - started < 2
    assert exit_code == 2
    assert report["observed_facts"]["classification"] == "FAILED"
    assert report["observed_facts"]["message_count"] is None
    assert report["observed_facts"]["message_count_exact"] is False
    assert report["supervision"]["deadline_terminated"] is True
    assert report["supervision"]["child_reaped"] is True
    assert report["supervision"]["child_exit_code"] is not None


def test_supervisor_preserves_messages_when_cleanup_hangs():
    probe = load_probe_module()
    sample = {
        "received_offset_seconds": 0.02,
        "message": {"id": "BTC-USD", "price": 60000.25, "time": 1_700_000_000},
    }
    facts = {
        "message_count": 1,
        "message_count_exact": True,
        "symbol_counts": {"BTC-USD": 1},
        "retained_samples": [sample],
    }

    report, exit_code = probe.supervise_command(
        child_command(
            {"event": "subscribe_returned"},
            {"event": "listening_started"},
            {"event": "sample", "sample": sample},
            {
                "event": "message_progress",
                "message_count_lower_bound": 1,
                "symbol_counts": {"BTC-USD": 1},
            },
            {"event": "observation_summary", "observed_facts": facts},
            {"event": "cleanup_started"},
            hang=True,
        ),
        symbols=["BTC-USD"],
        duration=0.75,
        grace_seconds=0.05,
        max_samples=2,
        emit_progress=False,
    )

    assert exit_code == 2
    assert report["observed_facts"]["classification"] == "STREAM_CONFIRMED"
    assert (
        report["observed_facts"]["outcome"]
        == "stream_confirmed_worker_deadline_terminated"
    )
    assert report["observed_facts"]["message_count"] == 1
    assert report["observed_facts"]["message_count_exact"] is True
    assert report["observed_facts"]["retained_samples"] == [sample]
    assert report["supervision"]["deadline_terminated"] is True
    assert report["supervision"]["child_reaped"] is True


def test_supervisor_accepts_normal_bounded_completion():
    probe = load_probe_module()
    facts = {
        "message_count": 0,
        "message_count_exact": True,
        "symbol_counts": {},
        "retained_samples": [],
    }

    report, exit_code = probe.supervise_command(
        child_command(
            {"event": "subscribe_returned"},
            {"event": "listening_started"},
            {"event": "observation_summary", "observed_facts": facts},
            {"event": "cleanup_complete"},
            {"event": "worker_complete"},
        ),
        symbols=["TCS.NS"],
        duration=1,
        grace_seconds=0.1,
        max_samples=1,
        emit_progress=False,
    )

    assert exit_code == 0
    assert report["observed_facts"]["classification"] == "INCONCLUSIVE"
    assert report["observed_facts"]["message_count"] == 0
    assert report["observed_facts"]["message_count_exact"] is True
    assert report["supervision"]["deadline_terminated"] is False
    assert report["supervision"]["child_reaped"] is True
    assert report["supervision"]["child_exit_code"] == 0

import importlib.util
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

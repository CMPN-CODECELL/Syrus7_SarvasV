import sys
import pytest
from pathlib import Path

repo_root = Path(__file__).resolve().parent
tests_dir = repo_root / "tests"

if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

try:
    import tests

    if hasattr(tests, "__path__") and str(tests_dir) not in tests.__path__:
        tests.__path__.insert(0, str(tests_dir))
except ImportError:
    pass


@pytest.fixture(autouse=True)
def trusted_browser_test_client(monkeypatch):
    """Existing HTTP/WS workflows model a trusted browser, not missing Origin.

    Security negatives explicitly override Origin with an empty/untrusted value.
    This changes test transport only, never the application's authorization.
    """
    from fastapi.testclient import TestClient

    original = TestClient.__init__

    def initialize(self, *args, **kwargs):
        kwargs["headers"] = {
            "Origin": "http://localhost:8000",
            **(kwargs.get("headers") or {}),
        }
        original(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", initialize)

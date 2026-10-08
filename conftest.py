import sys
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

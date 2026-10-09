"""Local browser boundary and bounded single-worker authentication throttling."""

import time
from collections import OrderedDict, deque
from threading import RLock

DEFAULT_ORIGINS = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def origin_allowed(headers, trusted_origins, *, bearer=False):
    origin = headers.get("origin")
    if origin:
        return origin in trusted_origins
    # Nonbrowser explicit credentials are not ambient browser cookies.
    return bearer


class LoginLimiter:
    def __init__(self, *, clock=time.monotonic, capacity=1024, limit=5, window=60):
        self.clock, self.capacity, self.limit, self.window = (
            clock,
            capacity,
            limit,
            window,
        )
        self.entries = OrderedDict()
        self.lock = RLock()

    def acquire(self, key):
        """Reserve an attempt before KDF work, including concurrent attempts."""
        with self.lock:
            now = self.clock()
            for ip, times in list(self.entries.items()):
                while times and times[0][0] <= now - self.window:
                    times.popleft()
                if not times:
                    del self.entries[ip]
            times = self.entries.get(key)
            if times is None:
                # Never evict active failures to let address churn bypass limits.
                if len(self.entries) >= self.capacity:
                    return False
                times = self.entries[key] = deque()
            if len(times) >= self.limit:
                return False
            ticket = object()
            times.append((now, ticket))
            return ticket

    def succeeded(self, key, ticket):
        # Remove only this success; retain other failed/in-flight attempts.
        with self.lock:
            times = self.entries.get(key)
            if times is not None:
                for entry in list(times):
                    if entry[1] is ticket:
                        times.remove(entry)
                if not times:
                    del self.entries[key]

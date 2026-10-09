"""Market session management and trading hours coordination."""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


class MarketSession:
    """Manages trading session state, market hours, and halt states.

    Hours Policy:
    - Default trading hours: 09:15:00 to 15:30:00 Asia/Kolkata (IST).
    - Hours Boundary: Half-open interval [open_time_seconds, close_time_seconds).
      A timestamp exactly at open_time_seconds (09:15:00) is OPEN.
      A timestamp at or after close_time_seconds (15:30:00) is CLOSED.
    - Timezone: Timestamps are accepted as epoch seconds (UTC) and converted
      to Asia/Kolkata before calculating the time of day.
    - Default enforcement: enforce_hours defaults to False to permit mock replay.
    - Fail-Closed: When enforce_hours is True, a missing timestamp (None)
      fails closed and evaluates to False (CLOSED).
    - Session Status:
      - HALTED: Circuit breaker or manual halt (overrides hours and manual status).
      - Manual CLOSED: Explicit administrative closure.
      - Manual OPEN: Enables admission only inside scheduled hours when hours
        are enforced; it remains a full override for explicit offline replay.
      - AUTO: Automatically determined by trading hours when enforce_hours is True,
        or OPEN when enforce_hours is False.
    """

    def __init__(
        self,
        *,
        open_time_seconds: int = 9 * 3600 + 15 * 60,  # 09:15
        close_time_seconds: int = 15 * 3600 + 30 * 60,  # 15:30
        enforce_hours: bool = False,
        clock: Callable[[], float] | None = None,
    ):
        if (
            open_time_seconds < 0
            or close_time_seconds <= open_time_seconds
            or close_time_seconds > 86400
        ):
            raise ValueError("invalid session hours boundaries")
        self.open_time_seconds = open_time_seconds
        self.close_time_seconds = close_time_seconds
        self.enforce_hours = enforce_hours
        self.clock = clock
        self._halted = False
        self._halt_reason: str = ""
        self._manual_status: str | None = None

    @staticmethod
    def _seconds_in_kolkata_day(timestamp: int | float) -> float:
        dt = datetime.fromtimestamp(timestamp, tz=KOLKATA_TZ)
        return dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1_000_000

    def is_open(self, timestamp: int | float | None = None) -> bool:
        """Return True if market is currently open for trading, else False."""
        if self._halted:
            return False
        if self._manual_status == "CLOSED":
            return False
        if self._manual_status == "OPEN" and not self.enforce_hours:
            return True
        if not self.enforce_hours:
            return True
        if timestamp is None:
            if self.clock is not None:
                timestamp = self.clock()
            else:
                return False
        if timestamp is None:
            return False

        sec = self._seconds_in_kolkata_day(timestamp)
        return self.open_time_seconds <= sec < self.close_time_seconds

    def status_at(self, timestamp: int | float | None = None) -> str:
        """Return current session status string: HALTED, OPEN, or CLOSED."""
        if self._halted:
            return "HALTED"
        if self._manual_status == "CLOSED":
            return "CLOSED"
        if self._manual_status == "OPEN" and not self.enforce_hours:
            return "OPEN"
        if not self.enforce_hours:
            return "OPEN"
        if timestamp is None and self.clock is not None:
            timestamp = self.clock()
        if timestamp is None:
            return "CLOSED"
        return "OPEN" if self.is_open(timestamp) else "CLOSED"

    @property
    def status(self) -> str:
        current_time = self.clock() if self.clock is not None else None
        return self.status_at(current_time)

    def halt(self, reason: str = ""):
        self._halted = True
        self._halt_reason = reason

    def resume(self):
        self._halted = False
        self._halt_reason = ""

    def set_status(self, status: str):
        status = status.upper().strip()
        if status not in {"OPEN", "CLOSED", "HALTED", "AUTO"}:
            raise ValueError("status must be OPEN, CLOSED, HALTED, or AUTO")
        if status == "HALTED":
            self._halted = True
        elif status == "AUTO":
            self._halted = False
            self._halt_reason = ""
            self._manual_status = None
        else:
            self._halted = False
            self._halt_reason = ""
            self._manual_status = status

    def to_dict(self, timestamp: int | float | None = None) -> dict:
        current_status = self.status_at(timestamp)
        open_flag = self.is_open(timestamp)
        return {
            "status": current_status,
            "is_open": open_flag,
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            "manual_status": self._manual_status,
            "enforce_hours": self.enforce_hours,
            "open_time_seconds": self.open_time_seconds,
            "close_time_seconds": self.close_time_seconds,
            "timezone": "Asia/Kolkata",
        }

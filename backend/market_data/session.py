"""Market session management and trading hours coordination."""


class MarketSession:
    """Manages trading session state, market hours, and halt states."""

    def __init__(
        self,
        *,
        open_time_seconds: int = 9 * 3600 + 15 * 60,  # 09:15
        close_time_seconds: int = 15 * 3600 + 30 * 60,  # 15:30
        enforce_hours: bool = False,
    ):
        self.open_time_seconds = open_time_seconds
        self.close_time_seconds = close_time_seconds
        self.enforce_hours = enforce_hours
        self._halted = False
        self._manual_status = None

    def is_open(self, timestamp: int | float | None = None) -> bool:
        if self._halted:
            return False
        if self._manual_status is not None:
            return self._manual_status == "OPEN"
        if not self.enforce_hours:
            return True
        if timestamp is None:
            return True
        seconds_in_day = int(timestamp) % 86400
        return self.open_time_seconds <= seconds_in_day <= self.close_time_seconds

    @property
    def status(self) -> str:
        if self._halted:
            return "HALTED"
        if self._manual_status is not None:
            return self._manual_status
        return "OPEN"

    def halt(self, reason: str = ""):
        self._halted = True

    def resume(self):
        self._halted = False

    def set_status(self, status: str):
        status = status.upper().strip()
        if status not in {"OPEN", "CLOSED", "HALTED", "AUTO"}:
            raise ValueError("status must be OPEN, CLOSED, HALTED, or AUTO")
        if status == "HALTED":
            self._halted = True
        elif status == "AUTO":
            self._halted = False
            self._manual_status = None
        else:
            self._halted = False
            self._manual_status = status

    def to_dict(self, timestamp: int | float | None = None) -> dict:
        current_status = (
            self.status
            if not self.enforce_hours
            else ("OPEN" if self.is_open(timestamp) else "CLOSED")
        )
        return {
            "status": current_status,
            "is_open": self.is_open(timestamp),
            "halted": self._halted,
            "enforce_hours": self.enforce_hours,
            "open_time_seconds": self.open_time_seconds,
            "close_time_seconds": self.close_time_seconds,
        }

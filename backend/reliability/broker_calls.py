"""Bound latency without assuming that timed-out broker work was cancelled."""

import time
from dataclasses import dataclass, field
from threading import Event, Lock, Thread


class BrokerCallError(RuntimeError):
    pass


class BrokerCallTimeout(BrokerCallError):
    pass


class BrokerCallUnsettled(BrokerCallError):
    pass


@dataclass
class PendingCall:
    operation: str
    done: Event = field(default_factory=Event)
    result: object = None
    error: BaseException | None = None


class BrokerSession:
    """At most one daemon broker call; the worker never writes platform DB state."""

    def __init__(self, adapter, call_timeout=1.0):
        self.adapter, self.call_timeout = adapter, call_timeout
        self.lock = Lock()
        self.active = None
        self.uncertain = False

    @property
    def unsettled(self):
        with self.lock:
            return self.active is not None and not self.active.done.is_set()

    def start(self, operation, *args):
        if operation not in {"submit", "cancel", "snapshot", "execute"}:
            raise ValueError("unsupported broker operation")
        with self.lock:
            if self.active is not None and not self.active.done.is_set():
                raise BrokerCallUnsettled("BROKER_CALL_UNSETTLED")
            if self.uncertain and operation != "snapshot":
                raise BrokerCallUnsettled("BROKER_RECONCILIATION_REQUIRED")
            call = PendingCall(operation)
            self.active = call

            def invoke():
                try:
                    call.result = getattr(self.adapter, operation)(*args)
                except BaseException as exc:
                    call.error = exc
                finally:
                    call.done.set()

            Thread(target=invoke, daemon=True, name=f"broker-{operation}").start()
            return call

    def wait(self, call, timeout=None):
        limit = (
            self.call_timeout
            if timeout is None
            else min(self.call_timeout, max(0, timeout))
        )
        if not call.done.wait(limit):
            with self.lock:
                self.uncertain = True
            raise BrokerCallTimeout("BROKER_CALL_TIMEOUT")
        if call.error is not None:
            with self.lock:
                self.uncertain = True
            raise BrokerCallError(
                "BROKER_"
                + call.operation.upper()
                + "_"
                + type(call.error).__name__.upper()
            ) from None
        return call.result

    def call(self, operation, *args, timeout=None):
        if timeout is not None and timeout <= 0:
            raise BrokerCallTimeout("BROKER_DEADLINE_EXPIRED")
        return self.wait(self.start(operation, *args), timeout)

    def snapshot(self, timeout=None):
        return self.call("snapshot", timeout=timeout)

    def cancel(self, order_id, timeout=None):
        return self.call("cancel", order_id, timeout=timeout)

    def acknowledge_verified(self):
        with self.lock:
            if self.active is not None and not self.active.done.is_set():
                raise BrokerCallUnsettled("BROKER_CALL_UNSETTLED")
            self.uncertain = False

    def drain_updates(self):
        if hasattr(self.adapter, "drain_updates"):
            return self.adapter.drain_updates()
        return []


class Deadline:
    def __init__(self, seconds, clock=time.monotonic):
        if not 0 < seconds <= 30:
            raise ValueError("deadline must be positive and at most 30 seconds")
        self.clock, self.seconds, self.started = clock, seconds, clock()

    @property
    def elapsed(self):
        return max(0, self.clock() - self.started)

    @property
    def remaining(self):
        return max(0, self.seconds - self.elapsed)

from collections import defaultdict, deque
from statistics import fmean
from threading import Lock
import time


class MetricsRegistry:
    COUNTERS = (
        "risk_bypass_count",
        "duplicate_fill_ignored_count",
        "conflicting_fill_count",
        "unattributed_fill_count",
        "safety_restriction_count",
        "reconciliation_failure_count",
        "failure_lab_runs",
        "failure_lab_passes",
        "failure_lab_failures",
        "risk_decisions_total",
        "orders_admitted_total",
        "fills_processed_total",
        "ticks_processed_total",
    )
    LATENCIES = (
        "risk_decision_latency_ms",
        "reconciliation_latency_ms",
        "kill_gate_close_latency_ms",
        "kill_verified_flat_latency_ms",
        "fill_processing_latency_ms",
        "tick_processing_latency_ms",
    )

    def __init__(self, max_samples_per_metric=10_000, clock=time.time):
        if type(max_samples_per_metric) is not int or max_samples_per_metric < 1:
            raise ValueError("max_samples_per_metric must be positive")
        self.max_samples = max_samples_per_metric
        self.clock = clock
        self._lock = Lock()
        self._counters = defaultdict(int)
        self._samples = defaultdict(lambda: deque(maxlen=self.max_samples))
        for name in self.COUNTERS:
            self._counters[name] = 0
        for name in self.LATENCIES:
            self._samples[name]

    def counter(self, name, amount=1):
        with self._lock:
            self._counters[name] += amount

    def observe(self, name, value):
        with self._lock:
            self._samples[name].append(float(value))

    def snapshot(self):
        with self._lock:
            counters = dict(self._counters)
            samples = {name: tuple(values) for name, values in self._samples.items()}
        return {
            "counters": counters,
            "latencies": {
                name: self._summary(values) for name, values in samples.items()
            },
            "generated_at": self.clock(),
        }

    def reset_demo_metrics(self):
        with self._lock:
            self._counters.clear()
            self._samples.clear()
            for name in self.COUNTERS:
                self._counters[name] = 0
            for name in self.LATENCIES:
                self._samples[name]

    @staticmethod
    def _summary(values):
        ordered = sorted(values)
        if not ordered:
            return {
                "count": 0,
                "min": None,
                "p50": None,
                "p95": None,
                "p99": None,
                "max": None,
                "mean": None,
            }

        def percentile(percent):
            index = max(
                0, min(len(ordered) - 1, (len(ordered) * percent + 99) // 100 - 1)
            )
            return ordered[index]

        return {
            "count": len(ordered),
            "min": ordered[0],
            "p50": percentile(50),
            "p95": percentile(95),
            "p99": percentile(99),
            "max": ordered[-1],
            "mean": fmean(ordered),
        }

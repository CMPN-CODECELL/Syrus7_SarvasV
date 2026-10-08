from backend.observability.metrics import MetricsRegistry
from backend.platform import Platform


def test_metrics_are_bounded_and_percentiles_deterministic():
    metrics = MetricsRegistry(max_samples_per_metric=3, clock=lambda: 1)
    for value in (1, 2, 3, 4):
        metrics.observe("latency", value)
    metrics.counter("events", 2)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["events"] == 2
    assert snapshot["latencies"]["latency"] == {
        "count": 3,
        "min": 2.0,
        "p50": 3.0,
        "p95": 4.0,
        "p99": 4.0,
        "max": 4.0,
        "mean": 3.0,
    }
    assert snapshot["counters"]["risk_bypass_count"] == 0
    assert snapshot["latencies"]["reconciliation_latency_ms"]["count"] == 0


def test_metrics_failure_cannot_change_safety_logic():
    class BrokenMetrics:
        def counter(self, *args):
            raise RuntimeError("metrics unavailable")

        def observe(self, *args):
            raise RuntimeError("metrics unavailable")

    platform = Platform()
    platform.metrics = BrokenMetrics()
    platform.risk.metrics = platform.metrics
    platform.reliability.metrics = platform.metrics
    assert platform.reliability.reconcile() is True
    platform.close()

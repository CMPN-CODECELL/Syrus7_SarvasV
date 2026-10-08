from dataclasses import asdict, dataclass
from time import perf_counter
from uuid import uuid4
import json


@dataclass
class BenchCaseResult:
    name: str
    passed: bool
    duration_ms: float
    evidence: dict
    failure_reason: str = ""


class SafetyBench:
    CASES = (
        "partial",
        "duplicate_fill",
        "conflicting_fill",
        "missed_fill",
        "unknown_submission",
        "disconnect",
        "stale_feed",
        "drift",
        "spam",
        "concurrent_position_race",
        "account_risk",
        "opposing_gross_exposure",
        "limit_lowered_below_position",
        "daily_loss_mark_breach",
        "restart_fail_closed",
        "kill_partial",
        "kill_late_fill",
        "broker_failure_during_kill",
        "invalid_price",
    )

    def __init__(self, store, clock):
        self.store = store
        self.clock = clock

    def run(self, iterations=1):
        if type(iterations) is not int or not 1 <= iterations <= 100:
            raise ValueError("iterations must be between 1 and 100")
        from backend.platform import Platform
        from backend.reliability.failure_lab import FailureLab

        run_id = str(uuid4())
        started_at = self.clock()
        results = []
        for _ in range(iterations):
            for name in self.CASES:
                case_started = perf_counter()
                platform = Platform(":memory:")
                try:
                    result = FailureLab(platform).run(name)
                    proof = result["invariants"]
                    forbidden = [
                        item["id"]
                        for item in proof["invariants"]
                        if item["id"] in {"I1", "I2"} and item["status"] == "FAILED"
                    ]
                    passed = result["status"] == "PASS" and not forbidden
                    results.append(
                        BenchCaseResult(
                            name,
                            passed,
                            (perf_counter() - case_started) * 1000,
                            {"verdict": proof["verdict"], "forbidden": forbidden},
                            ""
                            if passed
                            else "scenario assertion or forbidden invariant failed",
                        )
                    )
                except Exception as exc:
                    results.append(
                        BenchCaseResult(
                            name,
                            False,
                            (perf_counter() - case_started) * 1000,
                            {},
                            type(exc).__name__,
                        )
                    )
                finally:
                    platform.close()
        completed_at = self.clock()
        passed = sum(case.passed for case in results)
        payload = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "cases": [asdict(case) for case in results],
            "summary": {
                "scenario_count": len(results),
                "passed": passed,
                "failed": len(results) - passed,
                "duration_ms": sum(case.duration_ms for case in results),
            },
        }
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO benchmark_runs VALUES (?,?,?,?,?,?,?)",
                (
                    run_id,
                    started_at,
                    completed_at,
                    len(results),
                    passed,
                    len(results) - passed,
                    json.dumps(payload, default=str),
                ),
            )
            self.store.audit("SAFETY_BENCH_COMPLETED", payload["summary"])
        return payload

    def latest(self):
        rows = self.store.rows(
            "SELECT payload_json FROM benchmark_runs ORDER BY completed_at DESC LIMIT 1"
        )
        return json.loads(rows[0]["payload_json"]) if rows else None

from backend.platform import Platform


def test_safety_bench_runs_isolated_suite_and_persists_completed_summary():
    platform = Platform()
    result = platform.safety_bench.run()
    assert result["summary"]["scenario_count"] == 19
    assert result["summary"]["passed"] == 19
    assert result["summary"]["failed"] == 0
    assert platform.safety_bench.latest()["run_id"] == result["run_id"]
    assert platform.store.rows("SELECT COUNT(*) AS n FROM benchmark_runs")[0]["n"] == 1
    platform.close()

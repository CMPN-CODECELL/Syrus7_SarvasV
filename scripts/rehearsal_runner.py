#!/usr/bin/env python3
"""AlgoShield Rehearsal Runner: Deterministic Mock Demo Scenarios & Verification.

Usage:
    python scripts/rehearsal_runner.py [--scenario all|candles|partial|risk|recovery|restart|kill|drift]
    python scripts/rehearsal_runner.py --serve [--port 8000]
"""

import argparse
import sys

from backend.api import create_app
from backend.demo_scenarios import RehearsalRunner


def print_banner():
    print("=" * 76)
    print("  AlgoShield â€” Deterministic Mock Demo & Rehearsal Runner (Task 7)")
    print("=" * 76)


def run_rehearsal(
    scenario_name: str = "all", db_path: str | None = None, keep_db: bool = False
):
    print_banner()
    print(
        f"Initializing rehearsal runner (isolated DB: {db_path or 'temporary SQLite'})..."
    )
    runner = RehearsalRunner(db_path=db_path)
    print(
        f"Demo user created: username='{runner.username}', account='{runner.account_id}'"
    )
    print(f"Isolated SQLite: {runner.db_path}")
    print("-" * 76)

    try:
        if scenario_name == "all":
            results = runner.run_all()
        elif scenario_name in {"candles", "opposing"}:
            results = [runner.run_candles_and_opposing_strategies()]
        elif scenario_name == "partial":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_partial_rejection_duplicate()]
        elif scenario_name == "risk":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_risk_limit_rejection()]
        elif scenario_name == "recovery":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_missed_fill_recovery()]
        elif scenario_name == "restart":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_restart_recovery()]
        elif scenario_name == "kill":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_kill_switch_with_exposure()]
        elif scenario_name == "drift":
            runner.run_candles_and_opposing_strategies()
            results = [runner.run_unexplained_drift_blocked()]
        else:
            print(f"Unknown scenario: {scenario_name}")
            sys.exit(1)

        print("\nRehearsal Results Summary:")
        print("-" * 76)
        all_passed = True
        for i, r in enumerate(results, 1):
            tag = "[PASS]" if r.passed else "[FAIL]"
            print(f"  {tag} Scenario {i}: {r.scenario}")
            print(f"         Summary: {r.summary}")
            if not r.passed:
                all_passed = False

        print("-" * 76)
        if all_passed:
            print("âœ” ALL REHEARSAL SCENARIOS PASSED WITH ZERO ERRORS")
        else:
            print("âœ– SOME SCENARIOS FAILED")
            sys.exit(1)

        return runner

    finally:
        if not keep_db and scenario_name == "all":
            # runner.run_all() automatically cleans up
            pass


def serve_runner(port: int = 8000, db_path: str | None = None):
    import uvicorn

    print_banner()
    print("Preparing populated rehearsal database...")
    runner = RehearsalRunner(db_path=db_path)
    # Run scenarios up to kill or pre-kill so user can view live state
    runner.run_candles_and_opposing_strategies()
    runner.run_partial_rejection_duplicate()
    runner.run_risk_limit_rejection()
    runner.run_missed_fill_recovery()

    app = create_app(runner.platform)
    print("\nStarting local HTTP server for interactive dashboard rehearsal...")
    print(f"  Dashboard: http://127.0.0.1:{port}")
    print(f"  API Docs:  http://127.0.0.1:{port}/docs")
    print(f"  Demo User: username='{runner.username}', password='{runner.password}'")
    print(f"  Token:     {runner.token}")
    print("\nPress Ctrl+C to terminate.")
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    finally:
        runner.close()


def main():
    parser = argparse.ArgumentParser(
        description="AlgoShield deterministic demo scenarios and rehearsal runner."
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=[
            "all",
            "candles",
            "partial",
            "risk",
            "recovery",
            "restart",
            "kill",
            "drift",
        ],
        help="Scenario to execute (default: all)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Custom SQLite DB path (default: temporary isolated DB)",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the temporary database file after execution",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start local uvicorn web server with populated rehearsal state",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port when running with --serve (default: 8000)",
    )

    args = parser.parse_args()

    if args.serve:
        serve_runner(port=args.port, db_path=args.db)
    else:
        run_rehearsal(
            scenario_name=args.scenario,
            db_path=args.db,
            keep_db=args.keep_db,
        )


if __name__ == "__main__":
    main()

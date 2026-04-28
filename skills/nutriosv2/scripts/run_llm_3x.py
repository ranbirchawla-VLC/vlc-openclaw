"""3x require-all-pass LLM test harness for NutriOS.

Runs every LLM test three times at temperature=0 with the pinned model.
A single failure in any run is a gate failure: flaky tests do not clear
the gate.

Usage (via Makefile):
    make test-nutriosv2      # runs Python tests then this script
    make test-nutriosv2-llm-3x  # runs this script directly

Prints per-test per-run results and exits non-zero if any test failed in
any run.
"""

from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

RUNS: int = 3
WORKSPACE: Path = Path(__file__).parent.parent.parent.parent
LLM_TESTS: str = str(
    WORKSPACE / "skills" / "nutriosv2" / "scripts" / "tests" / "llm"
)
PYTHON: str = str(WORKSPACE / ".venv" / "bin" / "python")

# Matches verbose pytest output: "path::test_name PASSED [ 9%]"
_RESULT_RE: re.Pattern[str] = re.compile(
    r"^(.+?::.+?)\s+(PASSED|FAILED)\s+\[",
)


def run_once(run_n: int) -> dict[str, str]:
    """Run the LLM test suite once; return {test_id: 'PASSED'|'FAILED'}."""
    result = subprocess.run(
        [
            PYTHON, "-m", "pytest", LLM_TESTS,
            "-v", "--tb=short", "--no-header",
        ],
        capture_output=True,
        text=True,
        cwd=str(WORKSPACE),
    )

    results: dict[str, str] = {}
    for line in result.stdout.splitlines():
        m = _RESULT_RE.match(line.strip())
        if m:
            results[m.group(1)] = m.group(2)

    if result.returncode != 0 and not results:
        # Pytest exited non-zero but we couldn't parse per-test lines
        # (collection error, import error, etc.). Treat as total failure.
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-1000:] if result.stderr else "")
        results["__collection_error__"] = "FAILED"

    return results


def main() -> None:
    all_failures: dict[str, list[int]] = {}
    all_results: list[dict[str, str]] = []

    for run_n in range(1, RUNS + 1):
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"LLM TEST RUN {run_n}/{RUNS}  (model pinned, temperature=0)")
        print(f"{sep}")

        results = run_once(run_n)
        all_results.append(results)

        for test_id, status in sorted(results.items()):
            marker = "PASS" if status == "PASSED" else "FAIL"
            print(f"  [{marker}] {test_id}")
            if status == "FAILED":
                all_failures.setdefault(test_id, []).append(run_n)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    if not all_failures:
        total = sum(len(r) for r in all_results)
        print(f"All {total} test-runs passed ({len(all_results[0])} tests x {RUNS} runs).")
        sys.exit(0)
    else:
        print(f"FLAKE DETECTED: {len(all_failures)} test(s) failed in at least one run:")
        for test_id in sorted(all_failures):
            failed_runs = all_failures[test_id]
            rate = len(failed_runs) / RUNS
            print(
                f"  {test_id.split('::')[-1]}: "
                f"failed runs {failed_runs} ({rate:.0%} failure rate)"
            )
        sys.exit(1)


if __name__ == "__main__":
    main()

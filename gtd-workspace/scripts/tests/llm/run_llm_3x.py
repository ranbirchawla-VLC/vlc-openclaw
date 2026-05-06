"""3x require-all-pass harness for GTD LLM tests.

Runs pytest -m llm three times. All three runs must pass (zero failures).
Exits nonzero if any run has a failure or error.

Usage: python gtd-workspace/scripts/tests/llm/run_llm_3x.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEST_DIR = Path(__file__).parent
_PYTHON = str(_REPO_ROOT / ".venv" / "bin" / "python")

RUNS = 3


def main() -> int:
    results: list[int] = []
    for run in range(1, RUNS + 1):
        print(f"\n--- LLM test run {run}/{RUNS} ---")
        result = subprocess.run(
            [_PYTHON, "-m", "pytest", "-m", "llm", str(_TEST_DIR), "-v"],
            cwd=str(_REPO_ROOT),
        )
        results.append(result.returncode)
        if result.returncode != 0:
            print(f"Run {run} FAILED (exit {result.returncode})")
        else:
            print(f"Run {run} PASSED")

    failures = sum(1 for r in results if r != 0)
    print(f"\n--- 3x require-all-pass: {RUNS - failures}/{RUNS} passed ---")
    if failures > 0:
        print(f"FAIL: {failures} run(s) failed -- flaky at temperature=0")
        return 1
    print("PASS: all 3 runs green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

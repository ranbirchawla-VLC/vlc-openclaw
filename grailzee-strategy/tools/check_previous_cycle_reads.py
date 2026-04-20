#!/usr/bin/env python3
"""Fail if SKILL.md or strategy-framework.md doesn't instruct the LLM
to read cycle_outcome_previous.{meta.,}json or handle the null case.

Phase A.7 wired the cowork bundle to include these two files. The
strategist side is prose-driven — its "state loading" is a numbered
read list in SKILL.md and strategy-framework.md, not Python. This
check is the markdown-content equivalent of a unit test: assert that
both files mention the filenames, the `source_cycle_id` field, and
the null-case handling that the framework requires.

Run this before every commit that touches either strategist markdown
file. Exits 0 when every assertion holds, non-zero on drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

SKILL_MD = HERE / "SKILL.md"
FRAMEWORK_MD = HERE / "references" / "strategy-framework.md"

# Required tokens per file. Each tuple: (token, human-readable failure hint).
REQUIRED_IN_SKILL = [
    ("cycle_outcome_previous.meta.json", "read-list must cite the meta file"),
    ("cycle_outcome_previous.json", "read-list must cite the outcome file"),
    ("source_cycle_id", "SKILL.md must mention the source_cycle_id field"),
    ("null", "SKILL.md must mention the null / first-session case"),
]

REQUIRED_IN_FRAMEWORK = [
    ("cycle_outcome_previous.meta.json", "framework must name the meta file"),
    ("cycle_outcome_previous.json", "framework must name the outcome file"),
    ("source_cycle_id", "framework must explain the source_cycle_id field"),
    ("skipped_cycles", "framework must explain skipped_cycles"),
    ("resolution_note", "framework must explain resolution_note"),
    ("no prior cycle outcome", "framework must give the null-case briefing phrase"),
    ("PERFORMANCE", "framework must tie the outcome to the PERFORMANCE brief section"),
    ("WHAT WE ACTUALLY BOUGHT", "framework must tie trades[] to the WHAT WE ACTUALLY BOUGHT section"),
    ("in_focus", "framework must reference the in_focus flag on trades[]"),
]


def _check(path: Path, required: list[tuple[str, str]]) -> list[str]:
    """Return a list of failure messages for tokens not found in path."""
    if not path.exists():
        return [f"MISSING FILE: {path}"]
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for token, hint in required:
        if token not in text:
            failures.append(
                f"{path.name}: missing {token!r} — {hint}"
            )
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(_check(SKILL_MD, REQUIRED_IN_SKILL))
    failures.extend(_check(FRAMEWORK_MD, REQUIRED_IN_FRAMEWORK))

    if failures:
        print("DRIFT: strategist markdown missing required A.7 content:",
              file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nThe bundle now includes cycle_outcome_previous.{meta.,}json; "
            "the skill's read list must name them and the framework must "
            "explain how to incorporate them (including the null case).",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: SKILL.md and strategy-framework.md both reference the previous "
        "cycle outcome reads, source_cycle_id field, and null-case guidance."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

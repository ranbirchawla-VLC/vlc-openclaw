#!/usr/bin/env python3
"""Fail if SKILL.md or strategy-framework.md drifts from the contract
for Stage 0 state loading.

Two concerns are guarded by this lint (a markdown-content equivalent
of a unit test), one per phase that introduced it:

Phase A.7 — cycle_outcome_previous.{meta.,}json reads. The bundle
includes the pre-computed previous-cycle rollup (and null-case meta);
both markdown files must name the filenames, the `source_cycle_id`
field, `skipped_cycles`, `resolution_note`, the null-case briefing
phrase, and the brief sections they feed.

Phase A.8 — full ledger bundling. The bundled ledger is no longer a
current-cycle snippet. Both markdown files must name `trade_ledger.csv`
(the new arc-name) and characterise the file as full history, not a
snippet. Guards against regression into the old name.

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
    # Phase A.7 — previous cycle outcome reads
    ("cycle_outcome_previous.meta.json", "read-list must cite the meta file"),
    ("cycle_outcome_previous.json", "read-list must cite the outcome file"),
    ("source_cycle_id", "SKILL.md must mention the source_cycle_id field"),
    ("null", "SKILL.md must mention the null / first-session case"),
    # Phase A.8 — full ledger bundling
    ("trade_ledger.csv", "read-list must cite the full ledger by its new arc-name"),
    ("full trade ledger", "SKILL.md must characterise trade_ledger.csv as the full ledger (not a snippet)"),
]

# Tokens that must NOT appear (regression guards).
FORBIDDEN_IN_SKILL = [
    ("trade_ledger_snippet.csv", "Phase A.8 renamed the bundled ledger — remove the snippet reference"),
]

REQUIRED_IN_FRAMEWORK = [
    # Phase A.7 — previous cycle outcome reads
    ("cycle_outcome_previous.meta.json", "framework must name the meta file"),
    ("cycle_outcome_previous.json", "framework must name the outcome file"),
    ("source_cycle_id", "framework must explain the source_cycle_id field"),
    ("skipped_cycles", "framework must explain skipped_cycles"),
    ("resolution_note", "framework must explain resolution_note"),
    ("no prior cycle outcome", "framework must give the null-case briefing phrase"),
    ("PERFORMANCE", "framework must tie the outcome to the PERFORMANCE brief section"),
    ("WHAT WE ACTUALLY BOUGHT", "framework must tie trades[] to the WHAT WE ACTUALLY BOUGHT section"),
    ("in_focus", "framework must reference the in_focus flag on trades[]"),
    # Phase A.8 — full ledger bundling
    ("trade_ledger.csv", "framework must cite the ledger by its new arc-name"),
    ("full trade ledger", "framework must characterise trade_ledger.csv as the full ledger (not a snippet)"),
    ("all historical cycles", "framework must make clear the ledger spans all cycles, not just the current one"),
]

FORBIDDEN_IN_FRAMEWORK = [
    ("trade_ledger_snippet.csv", "Phase A.8 renamed the bundled ledger — remove the snippet reference"),
]


def _check(
    path: Path,
    required: list[tuple[str, str]],
    forbidden: list[tuple[str, str]],
) -> list[str]:
    """Return a list of failure messages for the path.

    A failure is either (a) a required token missing, or (b) a
    forbidden token present.
    """
    if not path.exists():
        return [f"MISSING FILE: {path}"]
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for token, hint in required:
        if token not in text:
            failures.append(
                f"{path.name}: missing {token!r} — {hint}"
            )
    for token, hint in forbidden:
        if token in text:
            failures.append(
                f"{path.name}: forbidden token {token!r} present — {hint}"
            )
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(_check(SKILL_MD, REQUIRED_IN_SKILL, FORBIDDEN_IN_SKILL))
    failures.extend(_check(FRAMEWORK_MD, REQUIRED_IN_FRAMEWORK, FORBIDDEN_IN_FRAMEWORK))

    if failures:
        print("DRIFT: strategist markdown out of contract with the bundle builder:",
              file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nThe bundle includes cycle_outcome_previous.{meta.,}json "
            "(Phase A.7) and the FULL trade_ledger.csv (Phase A.8). Both "
            "markdown files must reflect those filenames, describe the "
            "ledger as full history (not a snippet), and keep the A.7 "
            "null-case + skipped-cycles handling.",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: SKILL.md and strategy-framework.md reference the previous "
        "cycle outcome reads, source_cycle_id field, null-case guidance, "
        "and the full trade_ledger.csv (no lingering snippet reference)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

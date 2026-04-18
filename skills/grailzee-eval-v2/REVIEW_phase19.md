# REVIEW_phase19.md — Capability Files

**Verdict:** Phase 19 complete. Four capability files written, all within 200-line cap.

## Per-file Summary

| File | Lines | Statuses Covered | Notes |
|------|-------|-----------------|-------|
| report.md | 110 | success, error | Two-step workflow (ingest + analyze); name resolution loop; 4000-char chunking |
| deal.md | 139 | ok, not_found, error | Three response templates; comp_search_hint path; cycle alignment states |
| targets.md | 158 | gate, ok, ok_override, error | Override phrase allowlist; filter table; targets_not_in_cache handling |
| ledger.md | 184 | ok, error (per subcommand) | Two sub-modes; confirmation flow with rejection branch; 4 subcommand mappings |

## Decisions Surfaced and Resolved

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| 1. Confirmation flow | (c) Recommended template + behavioral constraint | Write ops need guardrail (present, wait, write on yes); wording flexes with voice |
| 2. Template specificity | (c) Hybrid | Verbatim data lines, composed framing; preserves Vardalux voice on context |
| 3. Cross-capability handoffs | (a) SKILL.md handles dispatch | Capabilities assume single-intent; multi-intent is Phase 20 |

## Required Fixes Applied

| Fix | What | How |
|-----|------|-----|
| 1. Two-step report orchestration | Inlined multi-step workflow | report.md specifies: ls reports/, ingest_report.py, ls reports_csv/, run_analysis.py. Wrapper flagged for backlog. |
| 2. Confirmation rejection branch | (b) Abort on "no" | ledger.md: "Trade not logged. Re-send with corrections." No re-parse, no follow-up. |
| 3. Override phrase allowlist | Explicit 6-phrase list | targets.md dedicated subsection; anything else defaults to gated + ask |

## Inconsistencies Between Spec and v2 Python

| Item | Spec (Section 10) | Actual v2 | Resolution |
|------|-------------------|-----------|-----------|
| Report orchestration | Single run_analysis.py call | ingest_report.py + glob + run_analysis.py | Documented as multi-step in report.md; wrapper flagged |
| Deal response keys | "Trade History" / "Cycle Focus" strings | confidence dict / cycle_focus dict with structured fields | Capability file uses actual response keys |
| Gate message | Hardcoded in spec | Dynamic from query_targets.py response | Capability file formats from response fields |

## Scope Creep Flags

| Flag | Target | Status |
|------|--------|--------|
| report_pipeline.py wrapper | Post-Phase 22 / Phase 24 | Consolidate ingest+glob+analyze into one CLI call |
| Vardalux voice in MNEMO | Phase 24 | Phase 18 did not seed voice principles; capability files reference SOUL.md instead |

## Voice Reference

All four files end with: "Voice and tone follow Vardalux conventions per SOUL.md." MNEMO does not currently carry voice principles (Phase 18 seed was business model + operational only). Backlog flag added for Phase 24 MNEMO voice seeding.

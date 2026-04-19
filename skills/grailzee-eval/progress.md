# progress.md — Grailzee Eval v2 build

**Purpose:** Session-restart doc. Read this first in a fresh session to pick up where the last one ended.

---

## Status at a glance

- **Branch:** `feature/grailzee-eval-v2`
- **Head:** `9ad9333 [phase24b] grailzee-strategy — review pass, self-check + mirror guard`
- **Ahead of `origin/feature/grailzee-eval-v2`:** 0 commits (pushed at Session 4 close — Phase 25 transport only, not completion)
- **Tests:** 698 passing from repo root (`python3 -m pytest` at `/Users/ranbirchawla/ai-code/vlc-openclaw`). Skill-only: 542 passing (`python3 -m pytest tests/ -q` from this dir). Cowork: 156 passing (`python3 -m pytest tests/ -q` from `grailzee-cowork/`).
- **Phase complete:** Phase 24b (cowork INBOUND dual-input + grailzee-strategy Chat skill)
- **Phase next:** Phase 25 proper — end-to-end dry-run on Mac Studio, then merge `feature/grailzee-eval-v2` → `main`

---

## Shipped (phases 1–24b)

| Phase | What | Key artifact |
|---|---|---|
| 1 | `grailzee_common.py` + scaffolding | `scripts/grailzee_common.py` |
| 2 | Seed `name_cache.json` | `scripts/seed_name_cache.py` |
| 3 | Ledger read + manager | `scripts/read_ledger.py`, `scripts/ledger_manager.py` |
| 4 | Backfill historical trades | `scripts/backfill_ledger.py` |
| 5 | Excel → CSV ingest | `scripts/ingest_report.py` |
| 6 | Reference analyzer | `scripts/analyze_references.py` |
| 7 | Trend/momentum scoring | `scripts/analyze_trends.py` |
| 8 | Emerged/shifted/faded | `scripts/analyze_changes.py` |
| 9 | Breakout detection | `scripts/analyze_breakouts.py` |
| 10 | Watchlist detection | `scripts/analyze_watchlist.py` |
| 11 | Brand rollups | `scripts/analyze_brands.py` |
| 12 | Cycle outcome rollup | `scripts/roll_cycle.py` |
| 13 | Output builders | `scripts/build_spreadsheet.py`, `build_summary.py`, `build_brief.py` |
| 14 | Cache writer v2 | `scripts/write_cache.py` |
| 15 | Orchestrator | `scripts/run_analysis.py` |
| 16 | Deal evaluator v2 | `scripts/evaluate_deal.py` |
| 17 | Targets v2 (later rewritten in Phase 19) | *replaced in Phase 19* |
| 18 | MNEMO seeding | *deferred* |
| 19 | Capability files + `query_targets.py` rewrite | `capabilities/*.md`, `scripts/query_targets.py` |
| 19.5 | Pipeline wrapper | `scripts/report_pipeline.py` |
| 20 | Top-level dispatcher | `SKILL.md` |
| 21 | Pre-deletion audit — 3 tests deleted (v1/v2 equivalence harness) | `REVIEW_phase21.md` |
| 22/23 | Migration — v2 renamed into production slot; v1 deleted | commit `1bb8119` |
| 24a | Cowork plugin — OUTBOUND + INBOUND bundle handoff (sibling dir; does not import from this skill at runtime) | `grailzee-cowork/` |
| 24b A | Cowork INBOUND extended to accept `strategy_output.json` alongside `.zip`. Hand-rolled validator, 5-sheet XLSX builder, best-effort archive to `output/briefs/`, atomic state commit preserved | `grailzee-cowork/grailzee_bundle/strategy_schema.py`, `build_strategy_xlsx.py`, extended `unpack_bundle.py`; `REVIEW_phase24b_cowork.md` |
| 24b B | Chat strategy skill — four session modes (`cycle_planning`, `monthly_review`, `quarterly_allocation`, `config_tuning`) producing validated `strategy_output.json`. Byte-identical schema mirror with cowork, enforced by guard script | `grailzee-strategy/` (sibling dir); `REVIEW_phase24b_strategy.md` |

Batch B1 hygiene session and OTel retrofit shipped between Phase 17 and Phase 19 (see `REVIEW_batchB1.md`, `REVIEW_otel_retrofit.md`).

---

## Remaining (Phase 25)

Per §14 of `Grailzee_Eval_v2_Implementation.md` (plus the cowork-split that came out of Session 4):

- **Phase 25 proper** — End-to-end dry-run on the Mac Studio against a real `GrailzeeData/` tree, then merge `feature/grailzee-eval-v2` → `main` once the operator loop validates. The push at Session 4 close was transport only; it made the branch available on the Mac Studio. Merge does not happen until a live cycle_planning session produces a valid `strategy_output.json` and cowork's `unpack_bundle.py` applies it cleanly against real state.

Integration test on the clean final tree (originally labelled Phase 23) folded into the Phase 22/23 migration commit. Phase 24b's round-trip integration test (`grailzee-cowork/tests/test_round_trip.py::test_strategy_output_full_round_trip`) covers the JSON leg of the dual-input contract — the Mac Studio dry-run exercises the same path against non-fixture data.

---

## Session 3 decisions (D1–D5)

From `DECISIONS_session3_kickoff.md`, binding on Phases 19+:

- **D1** — `report_pipeline.py` wrapper is the single invocation for report processing. Capabilities do not thread state paths.
- **D2** — Ledger rejection = abort with `"re-send with corrections"` (no corrective round-trip in SKILL).
- **D3** — No cycle gate on targets or deal. Deal Branch B (`status: "not_found"`) = market context only, no forced recommendation.
- **D4** — `query_targets.py` emits a two-section Strong/Normal block, MAX BUY (NR) DESC. One-tier-empty preserves header; both-tiers-empty collapses to a single fallback line.
- **D5** — Config-driven analyzer thresholds. **Deferred to a later phase.** Not active yet.

---

## Skill inventory

**Root:**
- `SKILL.md` (top-level dispatcher, name-gate + 5 paths)
- `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md` (scaffolding)
- `Grailzee_Eval_v2_Implementation.md` (THE SPEC — §14 has the phase table)
- `DECISIONS_session3_kickoff.md` (D1–D5)
- REVIEW_phase{1–21}.md + REVIEW_batchB1.md + REVIEW_otel_retrofit.md (Phase 22/23 folded into commit message; Phase 24a review at `grailzee-cowork/REVIEW_phase24a.md`; Phase 24b reviews at `grailzee-cowork/REVIEW_phase24b_cowork.md` and `grailzee-strategy/REVIEW_phase24b_strategy.md`)

**`capabilities/` (4 files, all aligned with D1–D4):**
- `ledger.md` — trade logging + performance queries (untouched in P19 by design)
- `deal.md` — single-watch deal evaluation (Branches A and B per D3)
- `report.md` — report pipeline wrapper invocation (D1)
- `targets.md` — Strong/Normal hunting list (D4)

**`scripts/` (23 files):**
All in list form — see `ls scripts/`. Entry points relevant to SKILL.md:
- `report_pipeline.py` — report capability
- `evaluate_deal.py` — deal capability
- `query_targets.py` — targets capability
- `ledger_manager.py`, `read_ledger.py` — ledger capability

**`tests/` (21 test files):** 542 passing. `test_query_targets.py` is the Phase 19 replacement; no stale Phase 17 suite remains. Phase 21 removed the v1/v2 equivalence harness (`TestV1V2Equivalence` classes in `test_analyze_references.py` and `test_analyze_trends.py`) — impossible to run post-migration since v1 disappears.

**Sibling plugin (not part of this skill):**
- `grailzee-cowork/` — self-contained Claude Code plugin. OUTBOUND builds a `.zip` bundle from local state; INBOUND now accepts either a `.zip` OR a `strategy_output.json` (dual-input dispatch added in Phase 24b). 156 tests after Phase 24b (was 70 after 24a). Does not import from `skills/grailzee-eval/` at runtime; runs alongside via the repo-root `pytest.ini`.
- `grailzee-strategy/` — Chat-side skill (sibling of cowork, not a Claude Code plugin). Four session modes, one output contract (`strategy_output.json` v1). Schema is byte-identical to cowork's; `tools/check_schema_mirror.py` guards the invariant. Four mode fixtures under `references/mode_fixtures/` all validate against cowork's `validate_strategy_output`. No pytest suite — manual test playbook at `TESTING.md` covers operator-loop scenarios; schema/archive/state semantics are automated on the cowork side.

---

## Open scope-creep flags (deferred — do not ship in current phases)

From `REVIEW_phase20.md`:

- **Flag A — Path 2a state-carrying.** Priceless deal query is stateless; operator re-sends brand + ref + price on the next turn. If friction accumulates, a future phase could teach SKILL.md to hold state across turns.
- **Flag B — Sell-side queries.** "What can I sell X for?" is partially handled by Path 2a (asks for an ask price). A genuine sell-side capability would invoke comp research without requiring a purchase price. Future capability candidate.

From `DECISIONS_session3_kickoff.md`:

- **D5 (config-driven thresholds)** — deferred. Analyzer thresholds are still hardcoded.

From Phase 22/23:

- **analysis_cache_sample.json fixture key-shape hygiene** — deferred; noted during migration, not blocking.

---

## How to restart

1. `cd /Users/ranbirchawla/ai-code/vlc-openclaw/skills/grailzee-eval`
2. `git status` — confirm clean
3. `git log --oneline -5` — confirm head is `9ad9333`
4. `python3 -m pytest tests/ -q` — confirm 542 passing (skill-only)
5. From repo root `/Users/ranbirchawla/ai-code/vlc-openclaw`: `python3 -m pytest` — confirm 698 passing (skill + cowork)
6. `python3 /Users/ranbirchawla/ai-code/vlc-openclaw/grailzee-strategy/tools/check_schema_mirror.py` — confirm schema byte-identity holds across both plugins
7. Read these in order:
   - `progress.md` (this file)
   - `DECISIONS_session3_kickoff.md` (D1–D5)
   - `../../grailzee-cowork/REVIEW_phase24b_cowork.md` (most recent phase, Deliverable A)
   - `../../grailzee-strategy/REVIEW_phase24b_strategy.md` (Deliverable B)
   - `Grailzee_Eval_v2_Implementation.md` §14–15 (remaining phase roadmap)
8. Ready for Phase 25 (Mac Studio dry-run → merge to main). The push at Session 4 close already delivered `9ad9333` to origin, so the Mac Studio can pull directly.

---

## Operating pattern (applies to all phases)

- User plans and gates. Claude executes.
- Hard stop at phase boundaries. No drifting into the next phase without a new prompt.
- Opening moves → state summary → **STOP** → plan → **STOP** → execute.
- Every completed module gets a code-review pass before commit.
- One phase = one (or at most two) commits, with a `REVIEW_phase{N}.md` capturing the work. Phase 24 reviews live with their respective plugins as siblings: `grailzee-cowork/REVIEW_phase24a.md`, `grailzee-cowork/REVIEW_phase24b_cowork.md`, `grailzee-strategy/REVIEW_phase24b_strategy.md`. Phase 24b was large enough to split into two deliverables (A = cowork INBOUND extension, B = Chat skill) with a supervisor gate between them; future multi-deliverable phases can follow the same pattern.

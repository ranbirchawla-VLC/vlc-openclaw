# ADR: Mesocycle Tool Surface — Phase 1 of mesocycle_setup Rewrite

**Status:** Locked
**Date:** 2026-05-02
**Branch:** `feature/nutriosv2-v2`
**Predecessors:**
- `architecture-decision-capability-shape.md` (governs prompt shape; this ADR governs tool surface that supports it)
- `architecture-decision-v2-meal-log-path.md` (predecessor pattern: tool-surface decision before capability rewrite)

**Carves exception to:** `capability-shape-execution-plan.md` §5 (no Python tool changes in this rollout). Exception is scoped to mesocycle_setup tool surface only; plan §5 still governs `today_view` and future capabilities.

---

## 1. The problem this fixes

The capability-shape ADR (`architecture-decision-capability-shape.md`) locked that NutriOS capability files are coaching posture, not flowcharts. The first capability rewrite under that decision, `meal_log.md`, validated cleanly. The second, `mesocycle_setup.md`, surfaces a problem the capability ADR did not anticipate: the existing Python tool surface forces the LLM to do exactly the arithmetic the capability rules forbid.

Three forcing functions today:

**The LLM composes the 7-row macro grid.** `compute_candidate_macros` returns one base daily row. `lock_mesocycle.macro_table` requires an array of exactly seven rows. Nothing between them assembles the grid. The LLM is currently expected to replicate the base row into a seven-element array before persisting. This is calculator work in translator territory — small in isolation, structurally identical to the v1 failure pattern the capability ADR exists to remove.

**Override keys carry positional offsets.** `recompute_macros_with_overrides` keys overrides by string `"0".."6"`, where `"0"` is dose day and other keys are days-after-dose. When the user says "make Saturday lower" and dose day is Sunday, the LLM has to compute Saturday's offset from Sunday and stuff that integer into the override key. The capability rules say "never expose offset indexing in any form." The tool surface forces the offset to live in the LLM's working memory. The capability prompt can hide it from the user; it cannot remove it from the LLM's loop.

**Floors and ceilings are cycle-level only.** `lock_mesocycle.intent` carries one `protein_floor_g` and one `fat_ceiling_g` for the whole cycle. The user's actual mental model is per-day: protein floor is 135g across the cycle, but on dose days they will go as low as 110g; fat ceiling is 70g normally, but on a rest day after long training they will allow 90g. The current schema cannot express this. The LLM either flattens the user's intent into a cycle-wide constraint that doesn't match what they said, or holds per-day deviations in conversation state and silently accepts violations against the cycle constant — both failure modes.

A fourth, smaller forcing function: `lock_mesocycle.intent.rationale` is required. The locked input shape from the capability framing burns in that the cycle holds "what," not "why." A required rationale field forces the LLM to invent text every cycle write.

The capability rewrite cannot fix any of this from the prompt side. A coach posture written on top of a tool surface that requires offset arithmetic and 7-row replication will leak under load. The capability prompt and the tool surface have to agree on what is calculator territory and what is translator territory before the capability rewrite is meaningful.

This ADR makes them agree. The Python tool surface for mesocycle setup gets the changes the capability rules already imply: a single tool that builds the full grid from intent, override keys by weekday name not offset, per-day floors and ceilings as a first-class concept, and rationale dropped from the required intent fields.

This is a carved exception to capability-shape execution plan §5 ("no Python tool changes in this rollout"). The exception is named here so it does not propagate. Tool changes in service of mesocycle_setup are in scope for this ADR; tool changes for `today_view` or future capabilities are not.

---

## 2. The decision

Four changes to the mesocycle Python tool surface. Each is named, scoped, and justified against the capability rules.

### 2.1 New tool: `build_macro_grid`

A pure function that takes the cycle intent plus optional per-weekday targets and returns the full 7-row macro grid. One call, no LLM-side assembly, no offset arithmetic.

**Inputs:**
- `estimated_tdee_kcal: int`
- `target_deficit_kcal: int`
- `deficit_unit: "weekly_kcal" | "daily_kcal"`
- `protein_floor_g: int` — cycle baseline
- `fat_ceiling_g: int` — cycle baseline
- `dose_weekday: "monday" | ... | "sunday"`
- `per_weekday_targets: object` — sparse, keyed by weekday name. Each entry is an object that may contain any of: `calories`, `protein_g`, `fat_g`, `protein_floor_g`, `fat_ceiling_g`. Empty object or absent map both mean "all days follow baseline."

**Output:**

```
{
  rows: [
    {
      weekday: "monday",
      calories: <int>,
      protein_g: <int>,
      fat_g: <int>,
      carbs_g: <int>,
      protein_floor_g: <int>,
      fat_ceiling_g: <int>
    },
    ... (7 rows, ordered monday → sunday)
  ],
  weekly_kcal_target: <int>
}
```

**Behavior:**
- Days present in `per_weekday_targets` use the values given, with cycle baseline filling any field not specified on that day's entry.
- Days absent from `per_weekday_targets` use the baseline computation: cycle daily kcal = TDEE − (deficit normalized to daily); protein at floor; fat at ceiling; carbs as remainder.
- Per-day `protein_floor_g` or `fat_ceiling_g` in a target entry override the cycle baseline for that day's row.
- Validation runs after grid construction. Each row checked against its effective floors and ceilings. Sum of row calories across the week must equal `weekly_kcal_target` within a rounding tolerance defined by the implementation. Constraint errors surface as the same shape `recompute_macros_with_overrides` returns today.
- A user-given target on a specific day that violates the cycle baseline floor or ceiling — without an explicit per-day floor/ceiling override — returns a constraint error naming the day, the value, the violated baseline, and the suggested resolution paths (state a per-day floor/ceiling, raise the target, or change the cycle baseline).

**Out of scope for this tool:** persistence, cycle ID assignment, prior-cycle ending. Those remain in `lock_mesocycle`.

### 2.2 `recompute_macros_with_overrides` — override keys re-keyed by weekday name

The tool's redistribution math is unchanged. Two surface changes:

**Override key shape.** Today: `{"0": {...}, "3": {...}}` where `"0"` is dose day. After: `{"monday": {...}, "thursday": {...}}` keyed by weekday name. Internal mapping (`dose_offset_to_weekday` and friends) stays; the tool does the offset math internally. The LLM never sees an integer offset.

**Per-day floor/ceiling on overrides.** Each override entry can carry `protein_floor_g` and/or `fat_ceiling_g` in addition to the existing `calories`, `protein_g`, `fat_g`. Validation enforces against the override's floor/ceiling if given, falls back to cycle baseline if not. The same baseline-violation rule from §2.1 applies: an override that violates the cycle baseline without an explicit per-day floor/ceiling returns a constraint error.

### 2.3 `lock_mesocycle.macro_table` — array of weekday-named rows

Today: array of 7 positional rows. Position implied dose-day-relative offset. After: array of 7 rows, ordered Monday through Sunday, each row carrying its own `weekday` name and the floors and ceilings that applied to it.

**Row shape:**

```
{
  weekday: "monday" | ... | "sunday",
  calories: <int>,
  protein_g: <int>,
  fat_g: <int>,
  carbs_g: <int>,
  protein_floor_g: <int>,
  fat_ceiling_g: <int>
}
```

The LLM never assembles this array by position. It hands `build_macro_grid`'s output rows directly to `lock_mesocycle`. Downstream consumers (meal_log, today_view, future reminders) read today's row by matching weekday name against the current date's weekday — not by offset arithmetic from the dose day.

### 2.4 `lock_mesocycle.intent.rationale` — optional

Required → optional. The cycle holds "what," not "why." If a future use case proves rationale is load-bearing for some downstream behavior, it earns its way back to required in a separate ADR.

The remaining intent fields (`target_deficit_kcal`, `protein_floor_g`, `fat_ceiling_g`) stay required. These are the cycle baseline that downstream consumers need.

### 2.5 What this ADR does not change

- `compute_candidate_macros` survives unchanged. It is the "show me the baseline" exploration tool — useful when the user wants to see what a given TDEE/deficit shape produces before committing to a cycle. It is not in the cycle-build path.
- `get_active_mesocycle` unchanged.
- `dose_offset_to_weekday` and the underlying offset-mapping helpers stay. They are now strictly internal — used by `recompute_macros_with_overrides` to translate weekday-keyed overrides into the redistribution math, and by `build_macro_grid` to identify dose day. The LLM never calls them.
- The Python compute path inside the tools is unchanged in its math. Only the input/output shapes change.
- Cycle persistence format, atomicity, prior-cycle ending — all unchanged.

### 2.6 What "single call" means

The capability rewrite under §2.1 of the capability-shape ADR will define the conversational shape. This ADR does not. But the tool surface is shaped to support a flow where: the coach gathers intent in conversation, calls `build_macro_grid` once with everything it has heard, reads back the resulting grid, accepts adjustments via `recompute_macros_with_overrides`, and persists via `lock_mesocycle`. The LLM never composes a row, never replicates a row, never computes an offset.

If the capability rewrite surfaces a need for the tool surface to expose something this ADR did not anticipate, that is a signal to revise this ADR — not to leak calculator work back into the LLM.

---

## 3. Consequences

### 3.1 The capability rewrite becomes structurally cleaner

The "never expose offset indexing in any form" hard rule in `mesocycle_setup.md` becomes truthful. Today the rule is half-fictional: the prompt says don't show offsets, but the tool surface requires the LLM to hold them in working memory to populate override keys. After §2.2, weekday names go in and weekday names come out; the offset never enters the LLM's loop. The capability prompt and the tool surface agree.

The "never compute macros yourself" rule similarly becomes structurally enforced. Today the LLM replicates a single base row into a 7-element array — small but real arithmetic. After §2.1, the LLM hands intent to one tool and receives the full grid. There is no row replication step for the prompt to forbid in narration but tolerate in mechanism.

The capability rewrite under ADR §2.1 (`architecture-decision-capability-shape.md`) reduces to coaching posture, hard rules grounded in real boundaries, and conversational examples. The hard rules become enforceable rather than aspirational.

### 3.2 Per-day floors and ceilings reshape the meal_log read path

Today, meal_log compares the day's consumed protein against `intent.protein_floor_g` — one value for the whole cycle. After §2.3, each row in `macro_table` carries its own `protein_floor_g` and `fat_ceiling_g`. Meal_log reads today's row by weekday name and checks against that row's floor and ceiling.

The downstream meal_log code change is small (read row.protein_floor_g instead of intent.protein_floor_g) but real. It is in scope for the meal_log update that follows this ADR's implementation. Today_view follows the same pattern.

This is the right model. The user's mental model was per-day from the start. The cycle-level constant was an artifact of the old schema, not a feature.

### 3.3 The test surface shifts deliberately

`test_mesocycle.py`'s coverage of `lock_mesocycle` changes shape: tests that asserted positional `macro_table` ordering update to weekday-keyed assertions. Atomic-write tests, prior-cycle-ending tests, end-date math — all unchanged.

`test_recompute_macros.py` updates to weekday-keyed override inputs. Redistribution math tests carry over with renamed keys.

A new test file covers `build_macro_grid`. The matrix is the union of: existing `compute_candidate_macros` cases (TDEE/deficit/floor/ceiling permutations), per-weekday-target cases (sparse maps with various coverage), per-day floor/ceiling override cases, and constraint violation cases (target violates baseline without explicit per-day override).

The LLM test suite in `llm/test_mesocycle_setup_llm.py` is frozen for Phase 1. Phase 1 is tool-surface only; Phase 2 (capability rewrite) updates these tests to assert against the new tool calls. The current LLM tests assert positional `macro_table` and integer override keys; they will fail against the new surface and that is correct — they are written against the old contract.

### 3.4 Migration cost is zero

No live cycles in production. Test fixtures update with the schema change. No backfill, no compatibility shim, no deprecation window.

If this ADR landed against a populated cycle store, §2.3's `macro_table` shape change would require a migration step (read positional rows, label by weekday using the recorded `dose_weekday`, rewrite). That cost does not exist today. Locking the new shape now is structurally cheaper than locking it after live data accumulates.

### 3.5 The capability ADR is not revised

Nothing in this ADR overrides anything in `architecture-decision-capability-shape.md`. The capability ADR governs prompt shape; this ADR governs tool surface. Both stay in effect. The relationship is: the tool surface changes here let the capability ADR's hard rules be true rather than aspirational. That is a strengthening, not a revision.

The execution plan (`capability-shape-execution-plan.md`) §5 is carved for this ADR's scope. Plan §5 still governs `today_view` and any future capability work. Future tool changes outside the scope of this ADR follow plan §5 — surface, address as separate decision, do not silently extend the rollout.

### 3.6 Phase 2 (capability rewrite) becomes drafting work, not architecture work

After Phase 1 lands, Phase 2's open questions collapse:

- Q1 (customer outcome) — already framed.
- Q2 (numeric correctness / NB-18) — collapses into coach discretion. The deficit-unit confirmation NB-18 was protecting is conversational, not procedural. The tool's `deficit_unit` parameter accepts what the LLM passes; the LLM clarifies in conversation when ambiguous. No procedural step in the prompt.
- Q3 (offset indexing) — fully dead. Tool surface no longer carries offsets at the LLM boundary.
- Q4 (read-back and adjustment) — read-back stays as a hard rule (no `lock_mesocycle` call until user confirms read-back). Adjustment collapses into coach discretion (call `recompute_macros_with_overrides` or `build_macro_grid` again as needed; conversation decides which).
- Q5 (`_shared/confirm_macros.md` retirement) — happens during the Phase 2 commit.

Phase 2 becomes section-by-section drafting against a clean slate. The hard work is done in Phase 1.

---

## 4. Out of scope

This ADR governs four tool surface changes named in §2. It does not decide:

**The capability prompt.** `mesocycle_setup.md` rewrite is Phase 2, drafted under the capability-shape ADR §2.1, after Phase 1 lands. Section-by-section drafting in chat per execution plan §2.

**Voice and tone.** `SOUL.md` governs voice across the agent. Unchanged.

**`today_view` or future capabilities.** Their tool surfaces are not addressed here. If they need changes, they get their own ADR.

**`compute_candidate_macros` deprecation.** Survives as the "show me the baseline" exploration tool. If it proves redundant after Phase 2 ships, retirement is a separate decision.

**Pre-existing schema inconsistency on `_Input.intent.fat_ceiling_g`** — pydantic model marks optional, tool schema marks required. This ADR does not fix it. Carry-forward item, addressed when convenient.

**Plan §6 status tracker update for meal_log scenarios-passed.** Documentation hygiene; not blocking. Update when convenient.

**MNEMO Bug 2 / inner-skill routing.** Unrelated. Inner skills stay on direct API at `05f8165` until the maintainer fix lands; three-line revert when it does.

If any of these surface as blockers during Phase 1 implementation, that is a signal to pause and address as separate decisions, not to silently extend Phase 1 scope.

---

## 5. Build sequence

This is the order Phase 1 implementation runs. Section feeds directly into the build-chat handoff.

### 5.1 Step 1: `lock_mesocycle.intent.rationale` → optional

Smallest, lowest risk, no downstream coupling. Change the pydantic model and tool schema; update one test that asserts rationale presence; verify nothing else breaks.

**Files:** `skills/nutriosv2/scripts/lock_mesocycle.py`, `plugins/nutriosv2-tools/tool-schemas.js`, `plugins/nutriosv2-tools/tools.schema.json`, `skills/nutriosv2/scripts/tests/test_mesocycle.py`.

**Gate:** existing 378 tests still pass; rationale-required test updated to rationale-optional.

### 5.2 Step 2: `lock_mesocycle.macro_table` → weekday-named rows

Schema change with test fixture impact. Update the row model to require `weekday`, `protein_floor_g`, `fat_ceiling_g` per row. Update validators to enforce ordering Monday → Sunday and uniqueness of weekday names. Update existing tests to construct rows with weekday names.

**Files:** same as Step 1 plus model definitions wherever `MacroRow` lives.

**Gate:** all `test_mesocycle.py` tests pass against new shape; `test_models.py` updated for new row schema.

### 5.3 Step 3: `recompute_macros_with_overrides` re-keyed by weekday name

Override key shape change plus per-day floor/ceiling support. Internal redistribution math unchanged. Existing tests in `test_recompute_macros.py` rewrite their override inputs from `"0".."6"` to weekday names and add per-day floor/ceiling cases.

**Files:** `skills/nutriosv2/scripts/recompute_macros_with_overrides.py`, the two schema files, `skills/nutriosv2/scripts/tests/test_recompute_macros.py`.

**Gate:** all `test_recompute_macros.py` tests pass; new per-day floor/ceiling test cases pass; constraint-violation cases return correctly shaped errors.

### 5.4 Step 4: `build_macro_grid` — new tool

The largest piece. Implementation plus full unit test coverage. Pure function, no I/O.

**Implementation order:**
1. Pydantic input model with sparse `per_weekday_targets` map.
2. Pydantic output model (rows + weekly_kcal_target).
3. Baseline computation (port the relevant math from `compute_candidate_macros`).
4. Per-weekday application (target overrides, floor/ceiling resolution).
5. Constraint validation (baseline violation without explicit per-day override returns named error).
6. Tool schema registration.
7. Unit tests covering: all-baseline grid (no per-weekday targets), single-day target, multi-day target, per-day floor override, per-day ceiling override, baseline-violation rejection (with named day in error), weekly-kcal-target reconciliation.

**Files:** new `skills/nutriosv2/scripts/build_macro_grid.py`, the two schema files, new `skills/nutriosv2/scripts/tests/test_build_macro_grid.py`.

**Gate:** new tool's unit tests pass; existing 378 (post-step-3) tests still pass.

### 5.5 Step 5: LLM test suite freeze acknowledgment

`llm/test_mesocycle_setup_llm.py` will fail against the new tool surface. This is expected. The Phase 1 close-out documents which tests are expected to fail and confirms they fail for the right reasons (referencing positional `macro_table` or integer override keys). They are not fixed in Phase 1; they get refactored at Phase 2 capability rewrite.

**Gate:** the LLM test failures match the predicted set; no surprise failures.

### 5.6 Two-commit pattern

Per plan §2.4 and `CLAUDE.md`. Each step:
1. Pre-review commit (implementation + tests).
2. Code-reviewer subagent in fresh context with sample-record requirement per `Vardalux_Postmortem_Spec_Reality_Gap_2026-04-29.md` §5.
3. Address review findings as a second commit.

For Step 4 specifically (the new tool), the build prompt must include: actual sample input shapes for `per_weekday_targets`, actual sample output rows, and explicit constraint-violation examples. The postmortem rule applies.

### 5.7 Out-of-band cleanup

Two items not in the gated build sequence but landed in the same branch:

- Plan §6 status tracker update — mark meal_log scenarios-passed.
- `_Input.intent.fat_ceiling_g` pydantic/schema mismatch — carry-forward item, address if encountered during Step 2 work; defer otherwise.

These are documentation/hygiene; do not block any Phase 1 gate.

---

*End of ADR.*

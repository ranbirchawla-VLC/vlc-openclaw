# Capability Shape — Execution Plan

**Status:** Active
**Created:** 2026-05-01
**Branch:** `feature/nutriosv2-v2`
**Implements:** `architecture-decision-capability-shape.md`

This document is the working plan for rolling out the capability shape decision across the three NutriOS capabilities. It is time-bound and gets updated as work progresses. The ADR it implements is permanent; this plan is not.

---

## 1. Order of work

1. **`capabilities/meal_log.md`** — first rewrite. Highest-pressure surface, most exposed to the v1 failure mode, immediate target of the operator's day-to-day use.
2. **Conversational scenario validation against the running agent** before moving on. The acceptance criterion for the new shape is whether the coach handles realistic dictated and typed inputs across clean, ambiguous, partial, and scenario-planning turns. If it does not, the shape is wrong and gets revised before the next capability is touched.
3. **`capabilities/mesocycle_setup.md`** — second. The most procedural capability today (offset indexing, NB-18 numeric confirmation, adjustment flow, read-back flow). Largest reshape. Worth landing meal_log first to learn what the shape produces under load.
4. **`capabilities/today_view.md`** — third. Read-only, smallest surface. Easiest to bring into shape once the pattern is locked from the first two.

Each capability gets its own session and its own operator review.

---

## 2. Drafting protocol per capability

1. Read the ADR. Re-anchor on §2 every time.
2. Draft the capability file section by section in chat.
3. Operator redlines section by section. No silent edits, no batch-and-submit.
4. When all sections are locked, the capability file is written to disk and committed via Code with the two-commit gate per `CLAUDE.md` (TDD-first or review-first depending on what the change requires; code-reviewer subagent in fresh context).
5. Existing tests run. Any procedural-pattern tests that fail because the capability is no longer procedural are reviewed and either rewritten as behavioral assertions or removed.

---

## 3. Conversational acceptance scenarios

Before any capability is considered shipped, it passes a set of conversational scenarios run against the live agent. The scenarios are not unit tests. They are dictated or typed inputs that exercise the realistic surface of the capability.

**For `meal_log`:**

- **Clean.** "Two eggs, toast, and a coffee with milk." Single message, all items resolvable, expected behavior: log without ceremony, surface what it means for the day.
- **Ambiguous-but-resolvable.** "Had my usual shake." Recipe lookup returns a likely match. Expected behavior: surface the macros for confirmation rather than logging silently.
- **Partial information.** "I had a bunch of stuff for breakfast, like a sandwich and some fruit, not sure on portions." Expected behavior: estimate, surface confidence, ask for confirmation, log on yes.
- **Scenario-planning.** After logging breakfast, "what should I aim for at dinner to hit my targets?" Expected behavior: stay inside the meal_log capability, surface the day's remaining, suggest plausible options without inventing macros.

**For `mesocycle_setup`** and **`today_view`**: scenarios authored when their respective sessions begin.

---

## 4. Pass criteria

A capability is considered passing when, across its conversational scenarios:

- No fabricated dates, macros, totals, or log IDs appear in any response.
- The coach responds in conversation, not in procedure narration.
- The right tools are called and the right data is persisted.
- Scenario-planning turns are handled without leaving the capability.
- The conversation feels like a coach, not a form.

A capability that fails any of these gets its draft revised. Tools are not changed unless the failure proves a tool gap.

---

## 5. Out of scope for this rollout

- Any change to the Python compute path (`log_meal_items`, inner skills, `turn_state`, `write_meal_log`, `get_daily_reconciled_view`). The tool surface is in good shape.
- Voice and tone changes (governed by `SOUL.md`).
- New tools or new capabilities beyond the three named above.
- Routing or `turn_state` logic changes.

If any of the above prove necessary during the rollout, that is a signal to pause the rollout and address the underlying issue separately.

### Logged exception, 2026-05-01

During the `meal_log.md` rewrite, the code-reviewer subagent surfaced a tool-surface gap: `log_meal_items` output exposed `recipe_match` (the recipe name) but no `recipe_id`, leaving the SKILL unable to construct valid recipe-source `write_meal_log` calls. The validator on `write_meal_log` rejects `source="recipe"` without a `recipe_id`, which would have forced the SKILL to either always write `source="ad_hoc"` (losing recipe provenance) or carry an unspecified silence the LLM could trip on at runtime.

We chose to fix the interface (commit `1dc2cf7`) rather than work around it in the SKILL prompt. Reasoning: building LLM discipline around a known-bad interface is exactly the failure mode this rollout exists to prevent. The fix was small and additive — a new `recipe_id` field on `ResolvedItem`, populated for recipe-match items, `null` for estimation items. Spec §3.1 updated; tests updated; 376 tests still passing; subagent clean.

This is the only Python compute-path change made under this rollout. The §5 rule otherwise stands. Future rollout work should treat tool-surface gaps the same way: if the SKILL has to work around a bad interface to land, fix the interface instead, but only after the gap is surfaced and the operator agrees the fix is in scope.

---

## 6. Status tracker

Updated as work progresses.

| Capability | Draft started | Draft locked | Committed | Scenarios passed |
|---|---|---|---|---|
| meal_log | 2026-05-01 | 2026-05-01 | 2026-05-01 | — |
| mesocycle_setup | — | — | — | — |
| today_view | — | — | — | — |

---

## 7. Carry-forward items

These are known cleanup or follow-on tasks that depend on future capability work landing. Each entry names what to do, when to do it, and why it can't be done now. New chats read this section to pick up tracked work without the operator having to remember it.

- **Retire `capabilities/_shared/confirm_macros.md`.** The file is orphaned after the `meal_log.md` rewrite — `meal_log.md` no longer embeds the sub-flow because confirmation is now coach discretion, not a shared procedural gate. The file is still referenced by inclusion-convention comments in `capabilities/mesocycle_setup.md`. Delete the file and any remaining references when `mesocycle_setup.md` is rewritten under this plan. Doing it earlier creates stale comments in a file we're going to rewrite anyway.

- **Audit `intent_classifier.py` for capability-shape implications.** The classifier currently routes on intent labels (`meal_log`, `mesocycle_setup`, etc.). After all three capabilities are coach-shaped, revisit whether the classifier still makes sense as a discrete dispatcher or whether intent recognition should fold into the capabilities themselves. Defer until all three rewrites land; until then the classifier works as-is.

- **Eventual `turn_state` deprecation.** Operator intent: `turn_state` goes away over time. New capabilities anchor to `get_today_date` directly rather than `turn_state.today_date`. When the second and third capabilities are rewritten, evaluate whether `turn_state` still has a non-date job, and plan its retirement separately.

---

## 8. Related documents

- `architecture-decision-capability-shape.md` — the decision this plan implements.
- `architecture-decision-v2-meal-log-path.md` — Python tool surface decision (predecessor).
- `log_meal_items_spec.md` — Python contract (predecessor).
- `SOUL.md` — voice and tone (governs alongside this plan).
- `CLAUDE.md` — repo-level commit and review protocol.

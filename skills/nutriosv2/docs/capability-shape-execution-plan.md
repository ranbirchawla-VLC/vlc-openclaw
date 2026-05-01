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

---

## 6. Status tracker

Updated as work progresses.

| Capability | Draft started | Draft locked | Committed | Scenarios passed |
|---|---|---|---|---|
| meal_log | — | — | — | — |
| mesocycle_setup | — | — | — | — |
| today_view | — | — | — | — |

---

## 7. Related documents

- `architecture-decision-capability-shape.md` — the decision this plan implements.
- `architecture-decision-v2-meal-log-path.md` — Python tool surface decision (predecessor).
- `log_meal_items_spec.md` — Python contract (predecessor).
- `SOUL.md` — voice and tone (governs alongside this plan).
- `CLAUDE.md` — repo-level commit and review protocol.

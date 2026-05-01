# ADR: NutriOS Capability Shape — Coach, not Flowchart

**Status:** Proposed for operator review
**Date:** 2026-05-01
**Branch:** `feature/nutriosv2-v2`
**Predecessors:**
- `architecture-decision-v2-meal-log-path.md` (Python tool surface, `log_meal_items`)
- `log_meal_items_spec.md` (Python contract, locked)

**Supersedes:** No prior ADR exists. The implicit shape from v1 capability files (`capabilities/meal_log.md`, `capabilities/mesocycle_setup.md`, `capabilities/today_view.md`) is what this decision corrects.

---

## 1. The problem this fixes

v1 NutriOS produced a procedural app that could not think. The capability files were flowcharts. The LLM was instructed step by step what to do, in what order, with which tool, what to say, when to stop. The outcome on the floor: an app indistinguishable from MyFitnessPal with a bad chat interface. Track-only, no judgment, no scenario planning, no awareness that yesterday's under-eat changes today's deficit math.

The product being built is a thinking partner. A coach who tracks. The v1 shape made that impossible regardless of how good the underlying tools were.

The Python compute path (`log_meal_items`, the inner skills, `turn_state`) is in good shape and stays. The fix is upstream of that. The SKILL prompt shape itself is the failure surface.

---

## 2. The decision

### 2.1 Capability files are coaching posture, not flowcharts

Every `capabilities/*.md` file follows this shape:

1. **Posture statement.** Who the agent is to the user in this capability. Not "follow these steps." Closer to "you are the user's nutrition coach handling their meal log."
2. **Tools and what they exist for.** Each tool, one line, what it's for. Not when to call it. The coach decides timing from conversation context.
3. **Hard rules, no-fabrication boundary.** What the LLM cannot invent. These values always come from tools.
4. **OpenClaw plumbing rules.** Mechanical, not coaching. Text/tool separation, the NO_REPLY pattern, single `message` tool call per turn. These are bot-platform constraints.
5. **What good looks like.** Examples of conversational handling across the realistic surface of user inputs. Representative coverage, not exhaustive scenarios.
6. **What good does not look like.** Explicit failure modes. Procedural narration, ceremonial confirmation, balance-sheet readback when the user came for a coach, fabricated dates.

Numbered procedural steps of the form "Step 1: Call X. Step 2: Call Y" are removed.

### 2.2 The HARD RULES that survive

Two categories only.

**No-fabrication rules.** The LLM cannot invent dates, macros, totals, log IDs, or any other tool-returned value. These come from tools, every time. This is the protection against the v1 failure mode where the bot told the operator it was Monday on a Tuesday.

**OpenClaw plumbing rules.** Text blocks and tool calls do not share a response. When `message` is called with buttons, the text block is exactly `NO_REPLY`. These are platform constraints, not coaching.

Procedural rules of the form "call X exactly once," "stop after Step 2b," "confirm before Step 3" are removed. The coach decides based on the conversation.

### 2.3 The agent is one coach across all capabilities

A coach for meals and a form-filler for cycle setup, sharing one bot, is incoherent. All three capabilities (`meal_log`, `mesocycle_setup`, `today_view`) end up in the same shape. They share posture, no-fabrication rules, and OpenClaw plumbing. They differ in their tool surface and in their good/bad examples.

### 2.4 Scenario planning is in scope inside the capability

A coach who tracks must be able to handle "what should I have for dinner given what I've eaten" and "if I add X, where am I" without leaving the meal-log capability. Routing scenario questions to a separate intent fragments the coaching. The same capability handles the log plus the immediate scenario question.

Cross-capability handoffs still route through `turn_state` (e.g., user is in meal_log and asks to modify their cycle). Intra-capability conversation does not.

---

## 3. What this does NOT decide

- **The specific examples in each capability's "what good looks like" section.** Authored per capability at draft time.
- **Voice and tone specifics.** `SOUL.md` governs voice across the agent. This ADR governs structural shape only.
- **The exact phrasing of no-fabrication rules.** Specific wording authored per capability at draft time.

---

## 4. Consequences

### 4.1 LLM behavior is more variable

The procedural shape was also predictable. The same flow every time. The coach shape produces a wider range of outputs. The no-fabrication rules are the floor that prevents variability from drifting into commodity-tracker error (wrong macros, wrong dates).

### 4.2 Test surface shifts

LLM-level tests against capabilities shift from "did it call the estimation tool exactly once" to "given conversation X, did the coach respond sensibly, call the right tools, persist the right data." Python-level tool tests are unaffected. New LLM tests are coach-shaped: scenario inputs, behavioral assertions.

### 4.3 Capability files get longer but more durable

Procedural capability files are short and brittle. Coach-shaped capability files carry examples, so they are longer, but more durable. Review burden shifts from "is this flow correct" to "do these examples cover the surface."

### 4.4 The shape is validated by conversational scenarios, not unit tests

A coach-shaped capability cannot be validated by asserting tool-call sequences in isolation. The shape is validated by realistic dictated or typed conversations against the running agent: clean inputs, ambiguous inputs, partial information, scenario-planning turns. If the coach handles those well, the shape is working. If it cannot, the shape is wrong before the tools are.

---

## 5. This is the anchor

This ADR governs all NutriOS capability work going forward. When a future session asks whether a capability should use numbered steps or coaching posture, the answer is §2.1. When a future session asks what HARD RULES belong in a capability, the answer is §2.2. When a future session asks whether the agent is one coach or many, the answer is §2.3.

A future decision that needs to override anything here gets its own ADR. Until then, this is the shape.

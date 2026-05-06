# 2b.3 Negative-Path Reply Shape

**Date:** 2026-05-04
**Phase:** Design (Layer 3.4 closure)
**Status:** Locked
**Version:** v2 (supersedes v1)
**Inputs:** Layer 1 outcomes; soul anchor v2; target architecture v1; classifier spec v1 (3.1); capability shape v1 (3.2); span contract v1 (3.3)
**Roll-up:** Component of Layer 3 (API design) closure artifact at Layer 3 close.

**Changes from v1.** One em-dash in the "What this spec does not lock" section converted to semicolons per project no-em-dash rule. No design content changes.

---

## Architectural reshape

`unknown` is promoted to a first-class capability with its own capability file at `capabilities/unknown.md`. The earlier framing (empty `capability_prompt` governed by AGENTS.md plus SOUL.md) needed real reply instructions anyway; making the content first-class is cleaner than smuggling it into AGENTS.md.

### Reshape impact on prior locks

- **Classifier spec decision 4 unchanged.** Classifier returns `unknown` when signal is weak.
- **Tech outcome 4 rephrased.** "When classifier returns `unknown`, no tool call is produced." Mechanism: capability prompt instruction at temperature=0 plus test discipline. Gate 1 corpus must be airtight.
- **turn_state span attribute renamed.** `capability_loaded` becomes `capability_dispatched` (true if a tool capability was loaded; false if `unknown.md` was loaded). Always-true confusion avoided; cleaner Honeycomb queries.

---

## Eight locked decisions

### 1. Capability file structure

`capabilities/unknown.md` follows the same template as the other capabilities (Purpose, Voice Register, Verbatim Render Rule, Workflow, Branches, Composition Guardrails, LLM Responsibilities, What the LLM Does NOT Do). Difference: workflow does not call any tool; the response is the workflow.

### 2. Four branches inside the unknown capability

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Greeting / check-in | "hi Trina"; "morning"; "you there"; "you up?" | Light acknowledgment in inward voice; soft prompt if it reads as a check-in |
| B. Out-of-scope | "what's the weather"; "tell me a joke"; topics outside her surface | Honest acknowledgment that's not what she does; soft pointer to what she does, expressed contextually |
| C. Truly ambiguous in-scope | "the thing from yesterday"; "that idea I had" | Ask the one question that resolves; treat as pre-capture clarification; continuation flows back through turn_state |
| D. Mid-flow stuck | "yes" / "no" / "Friday" with no prior continuation context | Acknowledge plainly; ask what they meant |

### 3. Discovery surface is contextual, not enumerative

When users probe what she does, Trina describes herself in soul-anchor voice. Not a feature list.

- Allowed: "I track tasks, ideas, parking lot, and the calendar; weather isn't my thing."
- Allowed: "I'm here for the GTD stuff and the calendar; tell me what you're trying to land."
- Not allowed: bullet list of capabilities, command syntax, slash-command-style enumeration.

### 4. Hard prohibitions

What Trina never says on the negative path:

- "I don't understand."
- "Please rephrase."
- Any literal command list.
- "I'm just an AI assistant."
- Any process narration about classification ("I'm not sure how to route that").
- Any apology framing ("Sorry, I can't help with that").

### 5. Voice register

Inward Trina; warmth of shared context. Familiarity honored, not performed. Greetings get warmth without ceremony; out-of-scope gets honest dryness, not robotic deflection. Reply length short by default; one or two sentences. Longer only when branch C clarification needs context.

### 6. Span attributes for the unknown capability span

| Attribute | Type | Notes |
|---|---|---|
| `branch` | string | `greeting` / `out_of_scope` / `ambiguous_in_scope` / `mid_flow_stuck` |
| `tool_called` | boolean | Always false; regression check that tech outcome 4 holds |

### 7. Test corpus shape

Comprehensive negative-path corpus, every entry asserting:

- No tool calls (assert `tool_called=false` on capability span).
- No prohibited phrases from decision 4 (regex check on response text).
- Branch attribution matches expected branch.
- Response style matches branch register.

Inputs covering: greetings ("hi Trina", "morning", "you up?"); out-of-scope ("what's the weather", "tell me a joke", "what time in Tokyo"); ambiguous in-scope ("the thing from yesterday"); mid-flow stuck ("yes" with no prior turn, "Friday" with no prior turn). Each tested at temp=0, 3x require-all-pass.

### 8. Continuity-turn handoff from unknown.md

When branch C asks a clarifying question and the user replies, the continuation flows through turn_state. Classifier sees prior-turn context; routes to the actual intent (most often `capture`). The unknown capability does not hold state across turns; turn_state's continuity-turn handling does.

---

## Outcomes ties

- User outcome 4 (negative path conversational, not robotic): direct service surface.
- User outcome 5 (familiarity honored): warmth without performance in greeting branch.
- Tech outcome 4 (negative-path safety mechanically guaranteed): test discipline plus `tool_called` regression attribute.
- Soul anchor "explains herself through behavior, not menu enumeration": decision 3.

---

## What this spec does not lock

Exact reply prose per branch; prose lands at build with TDD against the test corpus. Threshold for branch attribution edge cases (e.g., "hi, what's on my plate?", which is greeting plus query; recommendation: classifier routes to `query_tasks` since the substantive intent dominates and greeting is incidental). Build refines branch attribution through corpus.

---

_Layer 3.4 locked. Layer 3 (API design) is now fully locked across 3.1, 3.2, 3.3, 3.4. Design phase closure opens._

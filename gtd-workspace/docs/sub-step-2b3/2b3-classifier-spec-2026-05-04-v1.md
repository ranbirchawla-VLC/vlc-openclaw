# 2b.3 Classifier Specification

**Date:** 2026-05-04
**Phase:** Design (Layer 3.1 closure)
**Status:** Locked
**Inputs:** Layer 1 outcomes; soul anchor v2; target architecture v1
**Roll-up:** Component of Layer 3 (API design) closure artifact at Layer 3 close.

---

## Eight locked decisions

### 1. Output shape: intent only

Classifier returns `{intent, confidence, rationale}`. No parameter extraction. Slot filling (record_type, due date, priority, time window, context) is the capability's job, not the classifier's. Cleaner separation; classifier prompt stays lean; capabilities stay self-contained.

### 2. Bounded vocabulary: seven values

`capture`, `query_tasks`, `query_ideas`, `query_parking_lot`, `review`, `calendar_read`, `unknown`. JSON schema validation post-call; out-of-vocabulary collapses to `unknown`.

### 3. Continuity turns flow through turn_state

Every turn passes through turn_state per pattern 1; that includes single-word continuations ("yes," "task," "Friday") after a capability asked a clarifying question. Classifier sees the most recent 1-2 turns of context and routes the continuation to the same intent. Capability handles resumption from there.

### 4. Classifier always commits

No internal ambiguity escape. If signal is weak, return `unknown`. Negative-path reply handles clarification through Trina's voice. No "low-confidence ambiguous-result" branch inside the classifier.

### 5. Python signal philosophy: high precision, narrow patterns

Deterministic layer catches direct command patterns ("add a task," "weekly review," "show me tasks") with confidence. False positive worse than false negative because false positive produces confident wrong dispatch; false negative falls through to LLM fallback. Realistic catch rate: 30-50% deterministic, 50-70% LLM fallback.

### 6. Edge case routing rules

- "What's on my plate today" and similar route to `query_tasks`. Commitment-biased reading.
- "Park this in ideas: …" and similar route to `capture`. Verb wins over target.
- "How do I X" / "What can you do" route to `unknown`. Trina explains herself through behavior, not menu enumeration.

### 7. turn_state span attributes

- `intent` (one of seven vocabulary values)
- `capability_file` (path to the capability file read, or empty for `unknown`)
- `capability_loaded` (boolean)
- `classifier_strategy` ∈ {`deterministic`, `llm`, `unknown`}
- `classifier_latency_ms`

### 8. Inner LLM classifier prompt shape

~40-60 lines. Sections: purpose; the seven intents in one or two lines each; 2-3 examples per intent including correct/incorrect pattern from deal.md; JSON output schema; vocabulary-bound enforcement; explicit prohibition on parameter extraction. Pinned to `mnemo/claude-sonnet-4-6` at temperature=0; tested 3x require-all-pass.

## Outcomes ties

- Tech outcome 3 (dispatch determinism): temp=0 plus 3x require-all-pass test discipline.
- Tech outcome 4 (negative-path safety): `unknown` returns empty `capability_prompt`; capability never invoked.
- Tech outcome 6 (span attribute coverage): classifier surface attributes locked.
- User outcome 4 (negative path conversational): classifier hands off cleanly to negative-path reply.
- User outcome 5 (familiarity honored): continuity-turn handling preserves conversation thread.

## Deferred to build

- Exact deterministic signal patterns line-by-line (regex set; per intent).
- Exact classifier prompt prose.
- Latency budget measured against `openclaw-latency-playbook.md`.
- LLM test corpus authoring (per-intent positive cases, negative-path corpus, edge cases from decision 6).

---

_Layer 3.1 locked. Layer 3.2 (per-capability prompt shape) opens against this._

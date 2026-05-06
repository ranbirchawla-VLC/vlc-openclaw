# 2b.3 Outcomes Lock

**Date:** 2026-05-04
**Phase:** Design (Layer 1 closure; formal lock document)
**Status:** Locked
**Inputs:** Soul anchor v2; chat-approved outcomes from 2026-05-04 design session.

This document formalizes the seven user outcomes and seven tech outcomes already chat-locked. Captures language for downstream reference; freezes the outcome set against which 2b.3 success is measured.

---

## User outcomes

### 1. Capture without ceremony
Voice or text in. Fields extracted, validated, persisted, conversational confirmation. The user keeps the thought; Trina takes the burden of remembering it.

**Soul anchor tie:** Capture mode 1; reason for being.

### 2. Surface without overwhelm
Three queries (tasks, ideas, parking lot). Right tool picked by intent; clean projection; lists shaped to support action, not flood it.

**Soul anchor tie:** Surface mode; "no flood; the slice the user can act on."

### 3. Stamp without ritual
Review walks the pass. Atomic per-file stamp. Surfaces `storage_unavailable` with failing path on partial. Re-runnable safely.

**Soul anchor tie:** Stamp mode; weekly review is real human work; Trina removes file-juggling.

### 4. Negative path is conversational, not robotic
When intent is ambiguous, off-topic, or out of scope, the reply feels like Trina. Not an error message. No tool dispatched, no fake confirmation, no command enumeration.

**Soul anchor tie:** "Explains herself through behavior, not menu enumeration"; warmth of shared context.

### 5. Joy and trust through honored familiarity
Conversational. No process narration. No schema leak. No fake confirmations. Familiarity earned through history; honored without performance.

**Soul anchor tie:** "Familiarity honored, not performed"; voice rules.

### 6. Honest pushback when input is sloppy
Tasks without next actions, ideas without domains, ambiguous record_type get named and fixed in place with the user. Capture is dialogic when input is sloppy; quiet when input is clean.

**Soul anchor tie:** "Honest pushback is friendship"; "Have opinions" rule from existing SOUL.md.

### 7. Pack defense (future surface, out of 2b.3 build)
Non-pack interlocutors received professionally and warmly. The pack's attention budget is what she protects. Soul and AGENTS.md anticipate so the surface lands clean later.

**Soul anchor tie:** Outward mode; "Ultimate Assistant calibration standard."

---

## Tech outcomes

### 1. Trace tree completeness
Every dispatch produces a parent-child trace from gateway through `turn_state` through capability tool through Python script. No orphan spans.

### 2. Audit cleanliness
Zero forbidden calls and zero exec bypasses across any session.

### 3. Dispatch determinism
Same natural-language input maps to the same intent at temperature=0, 3x require-all-pass.

### 4. Negative-path safety
When classifier returns `unknown`, no tool call is produced. Mechanically guaranteed by capability prompt instruction at temp=0 plus test discipline.

### 5. Capability hot-reload
Editing `capabilities/<intent>.md` takes effect on the next turn with no gateway restart.

### 6. Span attribute coverage
Every `turn_state` span carries `intent`, `capability_dispatched`, `capability_file`, `classifier_strategy`, `classifier_latency_ms`, `capability_file_mtime`, `continuity_turn`. Per-capability spans carry locked attribute sets per span contract v1.

### 7. Verbatim label fidelity
Capture, query, review, and calendar_read confirmations use only labels and values returned by the tool. The LLM never recomposes user input as confirmation. Tested via LLM tests asserting tool-returned labels appear and LLM-generated paraphrase does not.

---

## Outcome-to-capability traceability

| Outcome | Primary surface |
|---|---|
| User 1 (capture without ceremony) | `capabilities/capture.md` |
| User 2 (surface without overwhelm) | `capabilities/query_tasks.md`, `capabilities/query_ideas.md`, `capabilities/query_parking_lot.md` |
| User 3 (stamp without ritual) | `capabilities/review.md` |
| User 4 (negative path conversational) | `capabilities/unknown.md` |
| User 5 (joy through honored familiarity) | All capabilities; voice register from soul anchor |
| User 6 (honest pushback when sloppy) | `capabilities/capture.md` branches B-D; query branches C |
| User 7 (pack defense, future) | AGENTS.md outward guardrails (inert); calendar_read framing today |
| Tech 1 (trace tree completeness) | Plugin `index.js` retrofit; turn_state and capability scripts |
| Tech 2 (audit cleanliness) | `tools.deny` plus capability prompts; runtime verification at Gate 3 |
| Tech 3 (dispatch determinism) | Classifier; LLM tests at temp=0 3x |
| Tech 4 (negative-path safety) | `capabilities/unknown.md`; `tool_called=false` regression attribute |
| Tech 5 (capability hot-reload) | turn_state fresh-read pattern; `capability_file_mtime` attribute |
| Tech 6 (span attribute coverage) | Span contract v1 across all surfaces |
| Tech 7 (verbatim label fidelity) | Per-capability composition guardrails; LLM tests |

---

_Outcomes locked. No further reshaping in design phase. Build phase verifies against these outcomes at Gate 3._

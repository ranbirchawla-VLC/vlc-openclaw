# 2b.3 Decision-Reasoning

**Date:** 2026-05-04
**Phase:** Design (closure)
**Status:** Locked
**Purpose:** Captures every load-bearing design decision and the reasoning behind it. Becomes the lock reference for build phase. When build surfaces a question that touches a locked decision, this document is the canonical answer; reopening requires explicit "unlock" and a fresh decision-reasoning doc.
**Inputs:** All Layer closure docs; chat record from 2026-05-03 to 2026-05-04 supervisor session.

---

## Phase shift: from gap-fix to refactor

**Decision.** 2b.3 is reframed from "wiring missing" to "v1-to-v2 conversion of the entire agent surface."

**Reasoning.** Audit revealed three layered problems, not one: tools registered but not in `tools.allow` (Gate 3 root cause); AGENTS.md still v1-legacy (`pipeline.md`, exec/read/write); SKILL.md not at workspace root (gateway never loads it); plus OTEL pattern 2 violations across plugin and Python surfaces. Fixing tools.allow alone would expose tools to a v1 AGENTS.md that contradicts locked patterns 3 and 4; trades silent narration for confused dispatch. The right framing is target architecture first; walk back from target to current state; sequence the moves. Single coordinated diff; one set of gates.

**Locked at:** Phase shift accepted by operator after gap analysis review.

---

## Soul anchor

### v1 → v2 reshape: calendar framing

**Decision.** Trina is the conversational surface to the pack's calendar; today she reads (existing tools), plausibly tomorrow she writes (event creation, time-blocking). She is not the calendar itself; the calendar lives in Google Calendar.

**Reasoning.** v1 had calendar listed under "what Trina is not" as separate tools. Wrong. Calendar awareness ties to GTD's engage step ("do the work, confident about what you are not doing because it is held by other commitments"). Calendar is workflow integration, not adjacent feature. Existing tools (`list_events`, `get_event`) survive untouched; framing reshape only.

**Locked at:** Soul anchor v2 (`2b3-soul-anchor-2026-05-04-v2.md`).

### Friendship-and-team frame

**Decision.** Trina's relationship to the pack is friendship + teammate aiming at shared outcomes. Honest pushback is friendship; familiarity is earned through history and honored without performance.

**Reasoning.** Pure substrate framing was too passive. Operator surfaced: "we're friends and we care and know a lot about each other and we try to remember that, but in the end we are team trying to get to shared outcomes." Re-anchors voice register on real relationship dynamics; reinforces the existing "have opinions" rule from SOUL.md.

### Pack-defense outward surface

**Decision.** Trina has two interaction modes: inward (pack: friend, teammate) and outward (non-pack: friendly pro; representative voice; defender of pack attention). Outward surface deferred to future sub-step; framing locked now so AGENTS.md outward guardrails section lands in 2b.3.

**Reasoning.** Calendar invite handling, meeting facilitation, the tactful no all need a coherent framing for Trina-as-representative. Naming it now prevents rewriting AGENTS.md when the surface opens. "Ultimate Assistant" as calibration standard; not the label she carries.

---

## Layer 2: Target architecture

### Decision A1: Classifier with inner LLM fallback

**Decision.** Three-layer classifier in `turn_state`: Python signal + keyword first; inner LLM classification on miss; empty-equivalent (`unknown.md`) on second miss.

**Reasoning.** No slash commands per operator constraint. Voice transcription noise plus natural-language input means deterministic classification alone produces silent narration when intent is clear but signals do not match (the exact bug 2b.3 closes). LLM fallback catches the long tail with one extra Sonnet call on classifier-miss turns; latency cost acceptable against the dropped-capture cost. Promotes "Inner LLM role-based routing" from TRIAL to LOCKED for Trina; doc-level promotion is separate sub-step decision.

**Rejected alternative:** Python-only classifier. Rejected because brittle natural-language detection produces exactly the failure mode 2b.3 closes.

### Decision A2: Multi-user data architecture

**Decision.** USER.md becomes thin schema-and-template at workspace root (cached prefix). Per-user profile lives at `agent_data/gtd/<user.id>/profile.json`. `user_context` Python helper reads profile on demand.

**Reasoning.** Family deployment is implicit in user outcomes 1-6. Today's USER.md hardcodes Ranbir; cannot scale. Pattern 7 already locks runtime data path; profile sits in that path. Schema-vs-data split keeps cached prefix uniform across users while allowing per-user truth.

### Decision A3: Negative-path enforcement via prompt + tests, not runtime structural

**Decision.** PREFLIGHT block plus `unknown.md` capability prompt prohibit tool calls. LLM tests assert zero tool calls across negative-path corpus at temp=0 3x.

**Reasoning.** Structural enforcement (dynamic `tools.deny` on empty intent) considered; rejected. Runtime cost exceeds determinism win at temp=0; if determinism breaks, structural enforcement does not save the agent because broken determinism is itself the bug. Mechanical guarantee comes from determinism plus comprehensive coverage.

### Smaller decisions

| Decision | Resolution | Reasoning |
|---|---|---|
| Tool naming | `capture_gtd` → `capture`; `review_gtd` → `review` | Aligns plugin to locks ledger; suffixing only two of five was inconsistent namespace avoidance |
| Delegation | Remove from registration; delete script | D-D pulled it; tool present in registration is tool dispatcher might pick under ambiguity; absence is cleanest fence |
| Outward guardrails | Section header in AGENTS.md, inert | Frame locked now; outward surface lands later without rewriting AGENTS.md |
| Capability file layout | Six files at `capabilities/<intent>.md` | Pattern 1 layout; capabilities match user-visible surfaces per pattern 5 |

**Locked at:** Target architecture v1 (`2b3-target-architecture-2026-05-04-v1.md`).

---

## Layer 3.1: Classifier specification

| Decision | Reasoning |
|---|---|
| Output is intent only (no parameter extraction) | Separation of concerns; classifier stays lean; capabilities own slot filling |
| Bounded vocabulary (seven values) | Schema enforcement post-call; out-of-vocabulary collapses to `unknown` |
| Continuity turns flow through turn_state | Pattern 1 says every turn calls turn_state; continuations included |
| Classifier always commits | Internal ambiguity escape breaks dispatch determinism (tech outcome 3) |
| Python signal philosophy: high precision | False positive worse than false negative; false positive produces confident wrong dispatch; false negative falls through to LLM |
| Edge case routing locked at design | Documented for build; future cousin handling has anchor patterns |
| Span attributes on turn_state | Observability for outcome 6; classifier strategy queryable |
| Inner LLM prompt shape (~40-60 lines, correct/incorrect pattern from deal.md) | deal.md proved high-leverage for closing variant space |

**Locked at:** Classifier spec v1 (`2b3-classifier-spec-2026-05-04-v1.md`).

---

## Layer 3.2: Capability prompt shape

### Meta-decisions

| Decision | Reasoning |
|---|---|
| Template adopts deal.md sections; drops Trigger; adds Voice Register | Capability is invoked by turn_state, not triggered; voice register inherits from soul anchor without restatement |
| Voice register references soul anchor by name | CLAUDE.md "cross-cutting voice rules live in this section; do not restate" applied to capability files |
| Cross-cutting rule placement is audience-aware | Runtime voice rules in SOUL.md (cached prefix); runtime structural rules in AGENTS.md; build-time consistency in CLAUDE.md (Code reads). Runtime Trina cannot resolve a CLAUDE.md reference. |
| Per-capability sketch level locks workflow + branches + composition guardrails; defers prose to build | Build-time TDD against LLM tests refines prose; design locks shape |

**Critical correction during 3.2:** Initial framing referenced CLAUDE.md from capability files. Corrected when operator surfaced the audience question. Runtime files only reference what runtime Trina can read.

### Per-capability decisions

| Capability | Key decisions | Reasoning |
|---|---|---|
| capture | Dialogic when sloppy; quiet when clean; one-question-at-a-time clarification flow; no inner LLM call needed (rule-based branches sufficient) | Soul anchor "honest pushback is friendship"; multi-turn through turn_state continuity |
| queries | Verbatim Z3 read projection; no editorial framing; length-cap with narrowing offer | Locks ledger Z3 read projection; user outcome 2 "surface without overwhelm" |
| review | Counts and outcomes, no record-by-record narration; partial failure named not buried; no GTD coaching | Soul anchor opinions about input not about how user does reviews; user outcome 3 "stamp without ritual" |
| calendar_read | LLM observes structure (conflicts, gaps, day shape); no Python extension to `list_events` | Empirical evidence (LLM caught conflicts in earlier testing) outranks rule-application; tests validate at temp=0 3x |

**Critical correction during 3.2:** Initial calendar_read guardrail prohibited surfacing busy-day characterization. Wrong; the rule was inverted. Correction: decision-helping framing (per deal.md) allowed; decision-making not allowed. Pack defense surfaces conflicts and tight stretches.

**Locked at:** Capability shape v1 (`2b3-capability-shape-2026-05-04-v1.md`).

---

## Layer 3.3: Span contract and error span discipline

| Decision | Reasoning |
|---|---|
| Plugin span: `tool.name`, `agent.id`, `plugin.name` | Identifies plugin and tool; per-capability extension at capability span, not plugin |
| turn_state span: full attribute set including `capability_file_mtime` | Honeycomb verifies hot-reload pattern in production |
| `continuity_turn` boolean on turn_state | Multi-turn debugging without reconstructing from session logs |
| Per-capability spans: locked attribute sets per capability | Outcome verification queryable in Honeycomb |
| Review per-record-type breakdown (`records_stamped.task` etc.) | Surfaces silent skip if review misses one record_type |
| Internal Python module spans: minimal attributes | Z3 lock; existing pattern; trace structure sufficient |
| `get_today_date` span | Pattern 6 lock; per-call observability |
| Error spans carry `error.type`, `error.code`, `error.location`, `error.context` | Debuggable detail for production incident response |
| Error spans omit `exception.message`, `exception.stacktrace` | Stack frames and raw messages can leak user content; bounded codes in `error.code` cover the diagnosis need |
| PII discipline (success path): no user content in span attributes | Family deployment hardening; observability infrastructure should not hold PII |
| Error span discipline (error path): full structural detail; user content still excluded | Two rules together: clean success surface + debuggable error surface; PII never |

**Critical addition during 3.3:** Initial framing focused only on success-path PII. Operator surfaced the error path: "make sure to not however if there is an Error anywhere we have a detailed Error span." Error span discipline added; both paths locked.

**Locked at:** Span contract v1 (`2b3-span-contract-2026-05-04-v1.md`).

---

## Layer 3.4: Negative-path reply shape

### Architectural reshape

**Decision.** `unknown` is promoted to a first-class capability with `capabilities/unknown.md`. turn_state span attribute renamed `capability_loaded` → `capability_dispatched`.

**Reasoning.** Negative path needs real instructions (branches, voice, boundaries, prohibitions). Empty `capability_prompt` would push that content into AGENTS.md; better to keep AGENTS.md focused on structural rules and let `unknown.md` carry the negative-path instructions in the same template family as other capabilities. TDD discipline applies uniformly.

### Negative-path decisions

| Decision | Reasoning |
|---|---|
| Four branches (greeting, out_of_scope, ambiguous_in_scope, mid_flow_stuck) | Comprehensive coverage of non-dispatch cases |
| Discovery contextual, not enumerative | Soul anchor "explains herself through behavior, not menu enumeration" |
| Hard prohibition list (six phrases) | Voice register bounded; common LLM defaults excluded |
| Span attributes `branch`, `tool_called=false` | Branch attribution observable; regression check on tech outcome 4 |
| Test corpus per branch at temp=0 3x | Mechanical guarantee on tech outcome 4; per-branch register correctness |
| Continuity handoff via turn_state | turn_state owns multi-turn state; `unknown.md` does not |

**Locked at:** Negative path v1 (`2b3-negative-path-2026-05-04-v1.md`).

---

## Customer review cadence

| Decision | Reasoning |
|---|---|
| Gate 3 as first customer review | Build phase verification; live Telegram round-trip across full corpus |
| Gate 3 splits into two steps (one capability + Honeycomb verify; then full sweep) | Catch OTEL breakage on one transaction instead of six; cheaper diagnosis |
| Weekly check pattern post-2b.3 (noting practice, not meeting) | Captures voice-fit and edge-case misses; feeds capability prompt refinement |
| Per-user check before family activation | Soul anchor "familiarity earned through history"; first turns matter |

**Locked at:** Success criteria + cadence v1 (`2b3-success-criteria-cadence-2026-05-04-v1.md`).

---

## What this document does not do

Does not enumerate full capability prompt prose; build authors against the Layer 3.2 sketches. Does not specify exact classifier signal patterns; build-time per-intent work. Does not draft the build prompt; build phase work. Does not promote TRIAL patterns at AGENT_ARCHITECTURE doc level; sub-step close decision.

---

## Lock status

All decisions in this document are locked. Reopening any requires explicit "unlock" from the operator and a fresh decision-reasoning document per supervisor-session skill. Build phase carries the locks forward; surgical mid-build adjustments within locked design are allowed; structural reopening returns the session to design phase per phase-transition authority rules.

---

_Decision-reasoning locked. Build sequence opens against this._

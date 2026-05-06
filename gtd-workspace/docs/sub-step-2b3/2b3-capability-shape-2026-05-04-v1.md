# 2b.3 Capability Prompt Shape

**Date:** 2026-05-04
**Phase:** Design (Layer 3.2 closure)
**Status:** Locked
**Inputs:** Layer 1 outcomes; soul anchor v2; target architecture v1; classifier spec v1 (3.1); deal.md as structural template
**Roll-up:** Component of Layer 3 (API design) closure artifact at Layer 3 close.

---

## Meta-decisions across all capabilities

### A. Template contract

Adopt deal.md sections with two adaptations:

- Drop "Trigger." Capability is invoked by turn_state, not triggered by message inspection.
- Add "Voice Register." One-line reference to soul anchor; no restatement.

Final section list per capability file: **Purpose, Voice Register, Verbatim Render Rule, Workflow, Branches, Composition Guardrails, LLM Responsibilities, What the LLM Does NOT Do.**

### B. Voice register reference pattern

Capability files reference the soul anchor by name, not by quotation. Capabilities customize register only where the capability differs from the default (capture is dialogic when input is sloppy; queries are quiet and clean; review names completion without drama; calendar_read is pack-defense observational).

### C. Cross-cutting rule placement (audience-aware)

Three layers, each placed where the audience can read it:

- **Runtime voice rules.** Live in **SOUL.md** (cached prefix; loaded every turn). Capability files reference SOUL.md by name.
- **Runtime structural rules.** Live in **AGENTS.md Hard Rules** (cached prefix). Capability files reference AGENTS.md.
- **Build-time consistency rules.** Live in CLAUDE.md. Code reads CLAUDE.md when authoring capability files; runtime Trina never sees it.

Capability files never reference CLAUDE.md because runtime Trina cannot resolve the reference.

### D. Per-capability sketch level at design

Lock at sketch level: Purpose, Workflow, Branches, capability-specific composition guardrails, span attributes. Defer prose to build with TDD on LLM tests.

---

## Capture

**Purpose.** Capture without ceremony. Voice or text in; record_type detected; fields extracted; Pydantic submission contract met; persisted; conversational confirmation.

**Voice Register.** Soul anchor inward voice. Dialogic when input is sloppy; quiet and clean when input is well-formed.

**Workflow.**

1. Read user message; extract candidate fields (title, record_type signal, due hint, priority hint, area hint, context hint).
2. If record_type ambiguous and no signal, ask one question; capability ends turn.
3. Call `capture` tool with extracted fields.
4. Tool returns ValidationResult per Z3 D-F vocabulary.
5. Render confirmation per render rules.

**Branches.**

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Successful capture | Tool returns success with stored record | Verbatim confirmation label; what was captured surfaced in inward voice |
| B. Ambiguous record_type | User said "remember this" or similar without verb signal | One question to disambiguate; capability ends turn |
| C. `missing_required_field` | Validation returned missing field | Name the missing field plainly; ask for it; one question |
| D. `submission_invalid` | Validation returned other error | Name the issue from D-F translation; ask for correction; one question |
| E. `storage_unavailable` | Tool returned storage failure with path | Name the failure plainly; offer to try again; do not pretend captured |

**Composition guardrails.**

1. Sloppy input gets named, not silently corrected. Honest pushback is friendship per soul anchor.
2. Verbatim label rendering. Confirmation uses tool-returned record summary; LLM does not recompose user input. Voice rule from SOUL.md applied to capture.
3. One question at a time. Multi-question flows resume through turn_state.
4. No persistence narration. Surface the fact of capture, not the writing to disk.
5. Length-bounded. Confirmation is one short sentence plus the record summary; clarification is one question, no preamble.

**Span attributes.** `record_type`, `validate_outcome`.

**Date sourcing.** `get_today_date` required for due-date language ("Friday," "tomorrow").

**What this sketch does not lock.** Exact clarification prose per branch; exact confirmation render shape; whether inner LLM call ever needed within capture (current read: no).

---

## Queries (shared sketch + per-capability deltas)

Three files: `capabilities/query_tasks.md`, `capabilities/query_ideas.md`, `capabilities/query_parking_lot.md`. Shared template; per-capability deltas at the end.

**Purpose.** Surface without overwhelm. Read user filter intent; call the tool; render results in inward voice without recomposition.

**Voice Register.** Soul anchor inward voice. Quiet and clean; not editorial. Lists shaped to support action, not flood.

**Workflow.**

1. Read user message; extract filter parameters (varies per capability; deltas below).
2. If filter ambiguous and the ambiguity changes the result set materially, ask one question.
3. Call the matching query tool with parsed filters.
4. Tool returns records via Z3 read projection (13 / 9 / 8 fields per record_type; channel fields and record_type excluded).
5. Render the list; surface count plainly; offer to narrow if list is long.

**Branches.**

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Results returned | Tool returns non-empty list | Render verbatim; surface count; if long, offer to narrow |
| B. Empty results | Tool returns empty | Name plainly; if filters applied, surface filter so user can adjust |
| C. Filter ambiguous | "Show me important things"; ambiguity not classifier-resolvable | One question; capability ends turn |

**Composition guardrails.**

1. Verbatim record rendering per Z3 read projection; LLM does not recompose, summarize across records, or invent fields.
2. No editorial framing. Counts and lists; not "looks like you're falling behind."
3. Length-bounded. Lists over 8-10 records get a short surface plus an offer to narrow. Threshold refined at build.
4. No filter recomposition. The result list is the confirmation; Trina does not paraphrase filters back.

**Span attributes.** `result_count`, `projection_clean`.

**Per-capability deltas.**

- `query_tasks`. Filter parameters: priority, context, area, status (open/completed), overdue. Overdue requires `get_today_date`. Most likely to overflow length cap; build's narrowing prompt matters most here.
- `query_ideas`. Filter parameters: domain, area, status (open/completed). Stale filter possible but lower priority; defer to build / 2c.
- `query_parking_lot`. Filter parameters: area only. Status is `Literal["open"]` until 2d (locks ledger); no completed parking-lot records exist. If user asks for completed parking-lot items, capability surfaces plainly that the field is not tracked yet; does not invent.

---

## Review

**Purpose.** Stamp without ritual. The user does the reflecting; the capability removes the file-juggling.

**Voice Register.** Soul anchor inward voice. Mechanical, calm; names completion without drama; names partial failures plainly.

**Workflow.**

1. Read user message; extract review window if specified (today, weekly, custom dates).
2. Default window if not specified (build refines: today / since-last-review).
3. Call `review` tool.
4. Tool returns count stamped per record_type; on partial failure, returns `storage_unavailable` with the failing path (Z3: per-file atomic, no cross-file rollback).
5. Render confirmation (success) or partial failure surface.

**Branches.**

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Successful pass | Tool returns clean stamp counts | Conversational completion; counts surfaced plainly |
| B. Empty pass | Nothing to stamp in window | Clean acknowledgment; no drama |
| C. Partial failure | Tool returned `storage_unavailable` with path | Name the failure plainly; surface what was stamped before failure; offer to retry; do not pretend success |

**Composition guardrails.**

1. No record-by-record narration. Counts and outcomes; not a play-by-play. Length-bounded.
2. Partial failure named, not buried. Failure is the headline; partial success is secondary. User can re-run safely (Z3 atomic-per-file lock).
3. No GTD coaching during review. Surface the count; do not lecture about review discipline.

**Span attributes.** `records_stamped` (per-record-type breakdown to be finalized at 3.3), `partial_failure_path` (string; null on success).

**Date sourcing.** `get_today_date` required for window calculation.

**What this sketch does not lock.** Default window definition; per-record-type breakdown shape in span attribute; retry prose for partial failures.

---

## Calendar_read

**Purpose.** Pack-calendar awareness as conversational surface. Read-only today; write surface deferred to a future sub-step.

**Voice Register.** Soul anchor inward voice; pack-defense framing. The calendar tools return verbatim event data; Trina selects what to surface and observes structure on top of it without composing the data itself.

**Workflow.**

1. Read user message; extract date intent (today by default; this week, specific date, range).
2. Decide tool: `list_events` for ranges, `get_event` for specific event detail.
3. Call tool with parsed parameters.
4. Render events verbatim; observe structural patterns (conflicts, no-gap stretches, day shape) and surface in inward voice.

**Branches.**

| Branch | Trigger | Trina behavior |
|---|---|---|
| A. Events returned, clean structure | Tool returns events; no conflicts, no notable gaps | Render verbatim; chronological; concise |
| B. Empty range | No events in range | Clean acknowledgment ("Nothing on the calendar Friday") |
| C. Specific event detail | User asked about a named event | `get_event`; render verbatim with full detail |
| D. Date ambiguous | "Next week" without anchor; "Friday" past or future unclear | One question; capability ends turn |
| E. Notable structure | Conflicts present, or significant no-gap stretch, or other notable pattern | Surface alongside event list; integrated, not separate response |

**Composition guardrails.**

1. **Decision-helping, not decision-making.** Surface conflicts, gaps, day shape; do not tell the user to reschedule, skip, or move events. The user owns the call. ("The 2pm overlaps with the 2:30 client call" allowed; "you should reschedule the 2pm" not allowed.)
2. **Verbatim event rendering.** Titles, times, attendees as the tool returns them. Structural observations sit alongside this data, not in place of it.
3. **No invented numerical claims beyond what the tool returns.** Naming a conflict or qualitatively naming a tight stretch is recognition; emitting derived durations or counts is computation. The LLM may name the conflict, may name a stretch as tight; does not emit derived minutes / hours / counts.
4. **Honest uncertainty on edge cases.** Events that touch exactly (10:00-11:00 and 11:00-12:00); ambiguous all-day events; timezone-boundary cases. If recognition is uncertain, surface the events plainly and let the user read it. Do not force a conflict call.

**Span attributes.** `event_count`, `date_range` (start / end ISO).

**Date sourcing.** `get_today_date` required for default and relative date resolution.

**Test discipline does the empirical work.** The LLM-driven approach to conflict and gap recognition is validated through LLM tests at temperature=0, 3x require-all-pass, against a corpus that includes: clean day; two clearly overlapping events; three overlapping events; back-to-back morning; mixed conflict plus wide gap; edge case of events touching exactly. If the corpus passes 3x, the approach holds. If it does not, fallback (Python conflict detection in `list_events`) lands as a deferred sub-step.

**What this sketch does not lock.** Render shape (chronological list vs. blocked-out time view); date-disambiguation prose; per-event detail level for `get_event`; "significant no-gap stretch" qualitative threshold (build refines via test corpus).

---

## Date sourcing summary across all six capabilities

| Capability | Needs `get_today_date` | Why |
|---|---|---|
| capture | yes | Due-date language ("Friday," "tomorrow") |
| query_tasks | yes | Overdue filter |
| query_ideas | possibly | Stale filter; defer to build / 2c |
| query_parking_lot | no | No date-relative filters in 2b scope |
| review | yes | Review window default |
| calendar_read | yes | Default today; relative date resolution |

`get_today_date` plugin tool needs to land in 2b.3 (pattern 6 lock). Capabilities import via standard plugin tool dispatch; turn_state does not call it.

---

## Tied-to outcomes check

| Outcome | Capability surfaces |
|---|---|
| User outcome 1 (capture without ceremony) | capture |
| User outcome 2 (surface without overwhelm) | three queries |
| User outcome 3 (stamp without ritual) | review |
| User outcome 4 (negative path conversational) | classifier returns `unknown`; no capability invoked |
| User outcome 5 (joy and trust) | all six; voice register inheritance from soul anchor |
| User outcome 6 (honest pushback when input sloppy) | capture branches B-D; queries branch C |
| User outcome 7 (pack defense, future) | calendar_read framing today; outward surface deferred |
| Tech outcome 7 (verbatim label fidelity) | every capability composition guardrail |

---

_Layer 3.2 locked. Layer 3.3 (span attribute contract finalized across all surfaces; date sourcing scope confirmed) opens against this._

# 2b.3 Build Sequence

**Date:** 2026-05-04
**Phase:** Design (closure)
**Status:** Locked
**Purpose:** Ordered task list for the 2b.3 build sub-step. Input to the build prompt drafted at build phase open.
**Inputs:** All design phase closure docs (outcomes lock, soul anchor v2, target architecture v1, classifier spec v1, capability shape v1, span contract v1, negative path v1, success criteria + cadence v1, decision-reasoning v1, gap analysis v1).

One sub-step: 2b.3. One coordinated diff across all phases below. Three gates. Two-commit pattern (pre-review, post-review). Squash on green per AA section 4.11.

---

## Pre-flight

1. Branch creation: `feature/sub-step-2b3-capability-wiring` off main at `4cc1f58`.
2. Required reading by Code at session open (in order):
   - `CLAUDE.md`
   - `AGENT_ARCHITECTURE.md`
   - `agent_api_integration_pattern.md`
   - `openclaw-latency-playbook.md`
   - All design closure docs (listed above)
3. Confirm reading of canon and closure docs in build session log.
4. Operator confirms branch and pre-flight before phase 1 opens.

---

## Phase 1: Class A infrastructure (OTEL plumbing + setup)

Independent of LLM design; mechanical fixes against `agent_api_integration_pattern.md`.

1. Add `@opentelemetry/api ^1.9.0` dependency to `plugins/gtd-tools/package.json`.
2. Retrofit `plugins/gtd-tools/index.js`:
   - `SPAWN_ENV` constant with `OTEL_SERVICE_NAME` per pattern.
   - `startActiveSpan` wrapping per `execute()`.
   - `TRACEPARENT` injection into subprocess via `SPAWN_ENV`.
   - Plugin span attributes per span contract v1: `tool.name`, `agent.id`, `plugin.name`.
   - Error path: span status `ERROR` with full error attribute set on subprocess failure.
3. Confirm Python scripts use `attach_parent_trace_context` per locked pattern 2 (Z3 baseline; verify still in place after refactors).
4. Create `~/.openclaw/agents/gtd/agent/auth-profiles.json` with `{"version":1,"profiles":{}}`.
5. **Tests (Gate 1 surface):**
   - JS unit tests with `InMemorySpanExporter` assert `startActiveSpan` per `execute()`, `SPAWN_ENV` shape, TRACEPARENT injection.
   - Python integration test: drive plugin spawn against stub Python target; capture spans from both processes; assert trace ID matches and child carries plugin span as parent.
   - Error span tests per surface.

---

## Phase 2: turn_state plugin (the dispatcher)

The architectural anchor of 2b.3.

1. Author `scripts/turn_state.py`:
   - Python signal + keyword classifier (deterministic first pass per classifier spec v1 decision 5).
   - Inner LLM classifier fallback (structured JSON return; bounded vocabulary; temp=0; pinned to `mnemo/claude-sonnet-4-6`).
   - Capability file fresh-read per turn (no caching; `capability_file_mtime` captured for span).
   - Returns `{intent, capability_prompt}`.
   - Span attributes per span contract v1: `intent`, `capability_dispatched`, `capability_file`, `classifier_strategy`, `classifier_latency_ms`, `capability_file_mtime`, `continuity_turn`.
   - Error path per error span discipline.
2. Author Python signal patterns per intent (build-time work; high precision per decision 5).
3. Author inner LLM classifier prompt (~40-60 lines; correct/incorrect pattern from deal.md; bounded vocabulary; explicit prohibition on parameter extraction).
4. Register `turn_state` in `plugins/gtd-tools/tool-schemas.js`.
5. Add `turn_state` to `tools.allow` in agent entry.
6. **Tests (Gate 1 surface):**
   - Per-vocabulary classification at temp=0 3x require-all-pass.
   - Continuity-turn handling (single-word continuations after clarification questions).
   - LLM fallback on signal miss.
   - Edge case routing per classifier spec v1 decision 6.
   - Span emission tests for all attributes.

---

## Phase 3: get_today_date plugin

Pattern 6 lock; required by capture, query_tasks, review, calendar_read.

1. Author `scripts/get_today_date.py` returning today's date in user's timezone.
2. Read user timezone from `agent_data/gtd/<user.id>/profile.json`.
3. Span attributes per span contract v1: `tool.name`, `agent.id`, `tz`.
4. Register in `tool-schemas.js`.
5. Add to `tools.allow`.
6. **Tests:**
   - Timezone correctness across user profiles.
   - Per-user profile path resolution.
   - Span emission.

---

## Phase 4: Capability files

Author seven capability files per Layer 3.2 sketches plus Layer 3.4 negative path. Each file follows the template (Purpose, Voice Register, Verbatim Render Rule, Workflow, Branches, Composition Guardrails, LLM Responsibilities, What the LLM Does NOT Do).

1. `capabilities/capture.md` per 3.2 capture sketch.
2. `capabilities/query_tasks.md` per 3.2 query sketch + delta.
3. `capabilities/query_ideas.md` per 3.2 query sketch + delta.
4. `capabilities/query_parking_lot.md` per 3.2 query sketch + delta.
5. `capabilities/review.md` per 3.2 review sketch.
6. `capabilities/calendar_read.md` per 3.2 calendar_read sketch (LLM observes structure).
7. `capabilities/unknown.md` per 3.4 negative-path sketch.

**TDD discipline:** LLM tests authored before capability prompts finalized. Per-capability per-branch test corpus. Standing scenarios per CLAUDE.md ("Standing scenarios every capability gets tested against") plus capability-specific corpus.

**Voice rules:** capability files reference SOUL.md and AGENTS.md by name; do not restate cross-cutting rules. CLAUDE.md never referenced from capability files (runtime Trina cannot resolve).

---

## Phase 5: Workspace files

Replace v1 content; bring in alignment with AGENT_ARCHITECTURE skeleton and soul anchor v2.

1. **AGENTS.md** at workspace root: full replacement.
   - Skeleton from AGENT_ARCHITECTURE Reference section.
   - PREFLIGHT block per pattern 1 (multi-mode dispatcher).
   - Hard Rules block: no exec/read/write/edit/browser; three response types only; NO_REPLY for inline buttons.
   - Tools Available list: `turn_state`, `capture`, `query_tasks`, `query_ideas`, `query_parking_lot`, `review`, `calendar_read` (note: `calendar_read` is the capability; tools called are `list_events`, `get_event`), `list_events`, `get_event`, `get_today_date`, `message`.
   - Outward guardrails section header (inert; carries soul anchor v2 outward framing for future activation).
2. **SKILL.md** at workspace root: new file (currently absent; gateway requires at this path).
   - Capabilities index per turn_state.
   - Reference to soul anchor and capability files.
3. **USER.md** at workspace root: thin schema-and-template per decision A2.
   - Schema: name, call_them, pronouns, timezone, gtd_maturity, areas, delegation contacts.
   - Template form; per-user truth lives at `agent_data/gtd/<user.id>/profile.json`.
4. **SOUL.md** at workspace root: existing content retained with three additions.
   - Add friendship-and-team frame paragraph.
   - Add pack-defense outward surface section (inert today; framing locked).
   - Add Voice Rules section (no process narration; verbatim labels through; no paraphrase faking understanding; familiarity honored not performed; ambiguity is one question; completion without drama).
   - Fix v1 tool reference: `gtd_write.py` → `capture` (or remove the specific tool reference and use general "her tools" framing).
   - Fix one em-dash to semicolon ("isn't a task — it's anxiety" → "isn't a task; it's anxiety").
5. **TOOLS.md** at workspace root: full content rewrite for v2 tool surface.
   - Skeleton survives; v1 content (`needs_llm: true` gate; v1 tool names; LLM skill index) deleted.
   - New content: tool descriptions per registered tool; inheritance from capability files for invocation context; calendar tools described alongside GTD tools.
6. Delete `gtd-workspace/skills/gtd/SKILL.md` (mislocated v1 file; unsalvageable).
7. Remove `BOOTSTRAP.md` from gateway injection list (`injectedWorkspaceFiles` in sessions.json or equivalent gateway config). Keep file on disk for future setup reference.

---

## Phase 6: Naming and surface alignment

Mechanical alignments per Q2/Q3 resolution.

1. Rename `capture_gtd` → `capture` in `tool-schemas.js` and any references.
2. Rename `review_gtd` → `review` in `tool-schemas.js` and any references.
3. Remove `delegation` from `tool-schemas.js`.
4. Delete `scripts/gtd/delegation.py`.
5. Update agent `tools.allow` to:
   - `list_events`, `get_event` (already present)
   - `message` (already present)
   - `turn_state` (new from phase 2)
   - `get_today_date` (new from phase 3)
   - `capture`, `query_tasks`, `query_ideas`, `query_parking_lot`, `review` (renamed/exposed)

---

## Phase 7: Per-user profile architecture

Multi-user data path; first user is Ranbir.

1. Author `scripts/user_context.py` helper: reads `agent_data/gtd/<user.id>/profile.json` on demand.
2. Create `agent_data/gtd/<ranbir-user-id>/profile.json` from current USER.md content (name, call_them, timezone America/Denver, areas of focus, delegation contacts).
3. Capabilities import `user_context` where they need profile fields (timezone for `get_today_date`; pronouns for voice register; areas for query filtering context).

---

## Phase 8: Carry-forwards (opportunistic)

Fold in if the diff is already open against the relevant files.

- N-3: shared `projections.py` module to deduplicate the five `_*_KEYS` frozensets; do if query files touched in 2b.3.
- N-6, N-7: missing OTEL span regression tests for `validate_submission` and `validate_storage`; add since OTEL work is happening anyway.
- O-2: misleading comment in `review.py:212-214`; one-line edit if review.py touched.
- N-1, N-2, N-5: trivial cleanup (unused imports, missing utf-8 encoding); fold if diff is already open.
- O-5: priority and energy enum constraints; not in 2b.3 scope (revisit at 2c or 2d).

---

## Gate 1: Automated tests pass

All Python and LLM tests green before pre-review commit.

- `make test-gtd`: full Python suite green.
- `make test-gtd-llm`: full LLM suite green at temp=0 3x require-all-pass.
- Per-capability per-branch test corpus green.
- Span emission regression tests green per span contract v1.
- Error case unit tests green per Gate 1 error discipline (span status ERROR; required attributes; no PII; no exception.message; no stacktrace).
- Cross-process integration test green (Python child receives plugin parent context).
- Negative-path corpus green (`tool_called=false`; no prohibited phrases; branch attribution correct).

**Gate report extension** per CLAUDE.md test conditions section: every gate report explicitly answers "Does this test reproduce the production failure?"; "Did this test fail against unfixed code?"; "What model and temperature were used?"

---

## Pre-review commit

- All Phase 1-8 work landed.
- Gate 1 green.
- Subject line: `2b.3: capability wiring and v1-to-v2 dispatcher conversion [pre-review]`.

---

## Gate 2: Code-reviewer subagent

- Invoke via "run the code-reviewer subagent" in fresh context.
- Subagent reads diff; applies `Review.md` plus any project Review-delta plus AGENT_ARCHITECTURE patterns 1-10 plus this build sequence.
- Output printed to CLI for operator review.
- Findings triaged: blockers fixed in-pass; non-blockers to `KNOWN_ISSUES.md` with priority and target sub-step; observations surfaced.
- Operator approves fix list before any further code change.

---

## Post-review commit

- Review-driven changes only.
- Subject line: `2b.3: address review findings`.

---

## Gate 3: Release check (Telegram round-trip)

Two-step pattern.

### Gate 3 step 1: Single-capability OTEL verification

- Operator runs one capture turn from Telegram.
- Pull trace in Honeycomb.
- Confirm parent-child tree connected from gateway through plugin span through `turn_state` child through capability child through Python script grandchild.
- Confirm all required span attributes present.
- **Halt if broken.** Do not proceed to step 2 if step 1 fails.

### Gate 3 step 2: Full corpus

- Capture across record types (task, idea, parking_lot).
- Each query (open tasks, ideas, parking lot).
- Review pass (with at least one record to stamp).
- Calendar read (today; this week; specific date).
- Negative-path probes: greeting ("hi Trina"); out-of-scope ("what's the weather"); ambiguous in-scope ("the thing from yesterday"); mid-flow stuck ("yes" with no prior).
- Deliberate error provocation: malformed capture; invalid query filter; malformed date intent in calendar_read.
- **Audit checks:**
  - Zero forbidden calls; zero exec bypasses.
  - Honeycomb traces complete with full attribute coverage.
  - Error spans clean (status ERROR; bounded `error.code`; no PII).
  - Spot-check span attributes for any user content (PII discipline regression).

### Gate 3 success criteria per success criteria + cadence v1

Every locked outcome verified per its evidence requirement.

---

## Sub-step closure

1. Squash 2b.3 commits into single commit on main per AA section 4.11.
2. Update `progress.md` with sub-step closure entry.
3. KNOWN_ISSUES updates: any non-blockers from Gate 2; any deferred items.
4. AGENT_ARCHITECTURE update at sub-step close:
   - "Inner LLM role-based routing" promotes from TRIAL to LOCKED for Trina; doc-level promotion is operator decision.
   - Capability file content shape pattern (deal.md template family) added as reference.
   - Negative-path capability file pattern added as reference.
5. Closeout report (operator-reporting structure):
   - **What this means from the user POV:** Trina now captures, queries, stamps, reads the calendar, and handles negative paths conversationally. The agent that narrated through capture is gone; the wired agent dispatches reliably.
   - **What was verified:** all seven user outcomes plus seven tech outcomes; full audit clean; full Honeycomb trace tree.
   - **What carries forward:** any KNOWN_ISSUES entries with target sub-steps.
   - **Sub-step reference:** 2b.3 (available if operator asks for technical detail).

---

## What this build sequence does not lock

Does not author exact prose for capability prompts; build authors against sketches with TDD. Does not author exact Python signal patterns; build authors against high-precision philosophy. Does not author exact LLM test corpora; build authors per CLAUDE.md standing scenarios plus per-capability per-branch sets. Does not specify exact `error.code` vocabulary on classifier and dispatcher surfaces; build-time work as raise sites are written.

---

_Build sequence locked. Design phase ready to close._

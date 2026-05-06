# 2b.3 Success Criteria and Customer Review Cadence

**Date:** 2026-05-04
**Phase:** Design (closure)
**Status:** Locked
**Inputs:** Outcomes lock v1; soul anchor v2; gate definitions per CLAUDE.md.

This document bridges outcomes to verification surfaces. For every locked outcome, what evidence counts as success; how that evidence is captured; when it is reviewed by the customer (the pack).

---

## Per-outcome success criteria

### User outcome 1: capture without ceremony

**Evidence:**
- LLM test corpus per record_type (task, idea, parking_lot) at temp=0 3x. Each input asserts: correct tool dispatched; correct fields extracted; verbatim label confirmation in response.
- Voice transcription corpus (sample N8N transcriptions including word-soup, run-on phrasing, transcription artifacts) asserts capture still works under realistic noise.
- Gate 3: live Telegram captures by Ranbir across record types; behavior matches spec.

**Surface:** `make test-gtd-llm` plus Gate 3 smoke.

### User outcome 2: surface without overwhelm

**Evidence:**
- LLM tests per query intent assert: correct tool; verbatim record render; no LLM recomposition; clean Z3 read projection (no `record_type`, `source`, `telegram_chat_id` leak).
- Length-cap behavior verified against a corpus including >10 record results; assert narrowing offer present, not raw flood.
- Gate 3: live queries by Ranbir across all three flavors with at-scale data.

**Surface:** `make test-gtd-llm` plus Gate 3 smoke.

### User outcome 3: stamp without ritual

**Evidence:**
- LLM tests assert: review tool dispatched; clean confirmation on success; partial-failure surfaced plainly with failing path; no record-by-record narration.
- Python tests assert per-record-type stamp counts; per-file atomic via temp+fsync+rename (Z3 lock); `storage_unavailable` returned with path on partial.
- Gate 3: live review pass by Ranbir; partial-failure scenario simulated by deliberately permission-locking one storage path.

**Surface:** `make test-gtd` plus `make test-gtd-llm` plus Gate 3 smoke.

### User outcome 4: negative path conversational, not robotic

**Evidence:**
- Comprehensive negative-path test corpus per `2b3-negative-path-2026-05-04-v1` decision 7. Asserts per branch: no tool calls; no prohibited phrases; branch attribution correct; voice register matches branch.
- Gate 3: live negative-path probes by Ranbir (greeting, out-of-scope, ambiguous, mid-flow stuck).

**Surface:** `make test-gtd-llm` plus Gate 3 smoke.

### User outcome 5: joy through honored familiarity

**Evidence:**
- LLM tests assert: no process narration phrases; no paraphrase that fakes understanding; verbatim labels through; familiarity register holds across multi-turn.
- Voice rule regression suite per CLAUDE.md `assert_no_process_narration` helper, applied to every capability.
- Gate 3: subjective check by Ranbir across multi-turn flows.

**Surface:** `make test-gtd-llm` plus Gate 3 subjective evaluation.

### User outcome 6: honest pushback when input is sloppy

**Evidence:**
- LLM tests for capture branches B-D assert: gap named (not silently corrected); one clarification question; clarification continuation flows through turn_state.
- Test corpus includes deliberately sloppy inputs (task with no verb; idea with no domain; ambiguous record_type) per branch.
- Gate 3: live sloppy inputs by Ranbir verify behavior.

**Surface:** `make test-gtd-llm` plus Gate 3 smoke.

### User outcome 7: pack defense (future surface)

**Evidence at 2b.3 close:**
- AGENTS.md contains outward guardrails section (inert; ready for activation when outward surface opens).
- SOUL.md contains pack-defense framing (out_of_scope branch in `unknown.md` already enforces honest acknowledgment).
- No live verification today; surface deferred.

**Surface:** Doc-state verification at sub-step close; live verification at future sub-step.

### Tech outcome 1: trace tree completeness

**Evidence:**
- Cross-process integration test (Python child process receives plugin parent context) at Gate 1.
- Honeycomb verification at Gate 3 step 1: complete parent-child tree from gateway through plugin span through turn_state child through capability child through Python script grandchild.

**Surface:** Gate 1 integration test plus Gate 3 step 1.

### Tech outcome 2: audit cleanliness

**Evidence:**
- Forensic audit on Gate 3 sessions: zero forbidden calls; zero exec bypasses.
- `tools.deny: ["exec", "group:runtime"]` enforced at agent entry.

**Surface:** Audit log review at Gate 3.

### Tech outcome 3: dispatch determinism

**Evidence:**
- LLM tests per intent at temp=0, 3x require-all-pass.
- Test failure (passes once, fails another at temp=0) blocks gate clear; per CLAUDE.md.

**Surface:** `make test-gtd-llm` Gate 1.

### Tech outcome 4: negative-path safety

**Evidence:**
- `tool_called=false` regression attribute on every `unknown.md` capability span across the test corpus.
- LLM tests assert no tool calls across negative-path inputs.

**Surface:** `make test-gtd-llm` plus span emission tests Gate 1.

### Tech outcome 5: capability hot-reload

**Evidence:**
- Manual verification at Gate 3: edit a capability file mid-session; next turn reflects change without gateway restart.
- Honeycomb verification: `capability_file_mtime` attribute changes when capability files are edited.

**Surface:** Gate 3 manual; ongoing Honeycomb production observation.

### Tech outcome 6: span attribute coverage

**Evidence:**
- Per-attribute regression tests at Gate 1 (`InMemorySpanExporter`) per span contract v1.
- Honeycomb verification at Gate 3: spot-check every capability's span set.

**Surface:** `make test-gtd` plus Gate 3.

### Tech outcome 7: verbatim label fidelity

**Evidence:**
- LLM tests assert tool-returned labels appear in response; LLM-generated paraphrase patterns (regex) do not.
- Per CLAUDE.md NB-18 lexical assertion (extended for label rendering).

**Surface:** `make test-gtd-llm` Gate 1.

---

## Customer review cadence

The customer is the pack. Three review surfaces, each tied to a phase or trigger.

### Build phase: Gate 3 as first customer review

When 2b.3 reaches Gate 3, Ranbir runs the smoke test corpus across all six capabilities plus negative path. Behavior measured against this success criteria document. Gate 3 is the first customer review and the first concrete verification that the build matches the design.

Gate 3 splits into two steps per OTEL discipline: first a single capability through end-to-end with Honeycomb verification; halt if broken. Then the full corpus.

If Gate 3 surfaces an outcome miss, two responses possible:
- Surgical fix in 2b.3 if the gap is small and the diff already open.
- KNOWN_ISSUES carry-forward if the gap is larger; resolves in 2c or later.

### Post-2b.3 ongoing: weekly check during family use

Cadence pattern (not a meeting; a noting practice):

- Each user notes captures that felt off (wrong record_type, missed field, awkward clarification).
- Each user notes queries that returned wrong-shape results.
- Each user notes review passes with surprising counts or partial failures.
- Each user notes any voice register that felt cold, performed, or not-Trina.

Notes accumulate; supervisor session reviews monthly; capability prompt refinements land as small sub-steps. Test corpus extends with each noted miss (per CLAUDE.md "new cousin equals new test row" pattern).

### Family deployment readiness: per-user check before activation

Before adding a family member beyond Ranbir to Trina's bot, one-on-one check:

- What does the user expect to capture (vocabulary, record types, voice patterns)?
- What times of day do they expect to use her?
- What contexts and areas are theirs?
- One soul-anchor framing: "Trina's a teammate; she'll learn you over time. The first turns matter."

Per-user profile.json populated from the check. First captures observed for voice-fit; refinements as needed.

This cadence honors the soul anchor's "familiarity earned through history": the trust starts with intentional onboarding, not a generic activation.

---

_Success criteria and cadence locked. Build phase verifies against this document at Gate 3 and beyond._

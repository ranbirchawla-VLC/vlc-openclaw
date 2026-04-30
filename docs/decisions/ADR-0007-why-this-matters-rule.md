# ADR-0007: Build prompts must contain a "why this matters" business-framing section

**Status:** Accepted
**Decided:** 2026-04-29
**Origin:** `Vardalux_Postmortem_Spec_Reality_Gap_2026-04-29.md` §5
**Implemented in:** SUPERVISOR_ROLE.md v2 — "Code prompt shape" and "Pre-emit audit" sections

---

## Context

During Phase 1, the build agent made structurally correct implementation decisions
that turned out to be wrong for the business. The clearest example: the validity boundary
on `services=[]` Grailzee Sales. The spec (design v1 §11) stated that validity belongs to
the extraction agent. The sub-step 1.2 test list in design v1 §13.1 named
`ERPBatchInvalid` on three "ambiguous-services" cases — a direct contradiction the build
agent could not resolve without understanding the business stakes.

The build agent cannot make good judgment calls about trade-offs if it does not understand
why a sub-step matters. Without that framing, it resolves ambiguity by optimizing for
completeness and coverage rather than outcome fidelity. It adds validation that should be
upstream, adds fallbacks that should not exist, and leaves unhandled the failure modes
that matter most.

The problem is not ambition; it is that the build agent interprets spec conflicts as
technical problems rather than business questions. The "why this matters" framing routes
those questions back to the supervisor.

---

## Decision

Every code prompt delivered to the build agent must contain a section named
**"Why this matters"** (or an equivalent heading) that:

1. **Names the business outcome this sub-step enables.** Not the technical output — the
   downstream business behavior that depends on this sub-step working correctly.
2. **Identifies the silent-failure mode.** What breaks without surfacing an error if this
   sub-step fails silently? Silent failures are the highest-risk failure class because they
   produce plausible-looking wrong output that passes Gate 1 and Gate 2.
3. **Names upstream and downstream dependencies.** What does this sub-step read from?
   What reads from it? This anchors the build agent's scope judgment and prevents scope
   drift in both directions.

The section should be 3–6 sentences. It is not a freeform narrative; it is a structured
gate that the supervisor runs before emitting the prompt.

---

## What this rule is not

**Not a project-motivation paragraph.** The build agent has full context on the project.
"Why this matters" is sub-step-specific, not project-wide.

**Not a substitute for a locked spec.** The framing supplements the technical spec; it
does not replace constraints, schema definitions, or test requirements.

**Not optional for small sub-steps.** The framing is cheapest to write when the sub-step
is small. It is most needed when it is small, because small sub-steps have the most
ambiguous scope boundaries.

---

## Scope

**Applies to:** every code prompt for every sub-step in every build cycle. No exception
for "simple" or "mechanical" sub-steps.

**Does not apply to:** chore commits, documentation updates, config tweaks that contain
no decision-making surface.

---

## Rejected alternatives

**Trust the build agent to infer business context from prior conversation.** This is the
default behavior. It produces structurally correct sub-steps that fail spec audits because
the build agent optimized for the wrong objective. The clearest symptom: a sub-step that
passes all tests, passes code review, and is wrong.

**Add business framing to the design doc only.** Design docs are read once at spec-lock;
the build agent reads the prompt, not the design doc, during implementation. The framing
must be present in the prompt that triggers the implementation.

---

## Consequences

- The supervisor's pre-emit audit (SUPERVISOR_ROLE.md v2) checks for this section before
  any code prompt is sent.
- The principle underlying this rule: **judgment calls in implementation are business
  questions, not technical ones. The build agent cannot route them correctly without
  business framing. Spec text alone does not supply the framing.**
- Correlates with the rule-class principle in CLAUDE.md: name the behavior class, not
  the instance. ADR-0007 names the class ("why does this sub-step matter") rather than
  an instance ("make sure the validity boundary is in the prompt").

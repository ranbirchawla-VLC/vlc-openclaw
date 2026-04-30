# SUPERVISOR_ROLE.md v2: Vardalux / OpenClaw Build Supervisor

Operating contract for the supervisor role in all NutriOS and OpenClaw agent builds.
The supervisor is Principal Engineer + Product Manager + Architect. The build agent
is the executor; the supervisor owns decisions, gates, and direction changes.

v2 changes: Code prompt shape section added; pre-emit audit added; methodology rules
section added; two failure modes added from Phase 1 corrective pass post-mortem.

---

## Role and authority

The supervisor locks decisions. Once locked, a decision is not relitigated unless
new information changes the constraint that motivated it. The build agent surfaces
conflicts and ambiguities; the supervisor resolves them.

The supervisor clears gates. Gate 1 (automated tests) is automated; supervisor
confirms the count and any skips. Gate 2 (code-reviewer subagent) runs in fresh
context; supervisor reads findings and triages. Gate 3 (release check) runs in
production; supervisor declares pass or fail.

---

## Operating mode

When the build agent reports a problem, the first ask is for diagnostic data,
not a fix proposal. The agent does not propose a fix until the data is in. This
separates "what is happening" from "what to do about it" and routes the second
question correctly.

---

## Code prompt shape

Every code prompt must contain:

1. **"Why this matters" section.** Names the business outcome this sub-step enables,
   the silent-failure mode if it fails, and the upstream/downstream dependencies.
   3–6 sentences, sub-step-specific. See ADR-0007 for full rule.

2. **Real data samples** (for data-shape sub-steps). At minimum three verbatim records
   from the external system embedded in the prompt. Fields confirmed by real observation,
   not spec text. See ADR-0006 for full rule.

3. **Locked constraints section.** Decisions that are not to be relitigated, stated
   explicitly so the build agent does not surface them as open questions.

4. **Stop conditions.** Scenarios where the build agent must surface to supervisor
   rather than resolve autonomously.

---

## Pre-emit audit

Before emitting a code prompt, the supervisor runs this checklist:

- [ ] "Why this matters" section present and sub-step-specific?
- [ ] If the sub-step parses or transforms external-system data: real records embedded?
- [ ] Data-shape fields drawn from embedded records, not from spec prose or field tables?
- [ ] Locked constraints named explicitly?
- [ ] Stop conditions defined?

If any box is unchecked, the prompt is not emitted. Draft it until the checklist passes.

---

## Failure modes the supervisor catches

**Test passing without production parity is a yellow flag, not a green one.**
When a sub-step's tests pass, the supervisor asks: are the test conditions actually
as messy as production? If not, the gate does not clear on tests alone.

**Spec without real data samples produces hallucinated schemas.**
When a build prompt names transaction IDs or references field names without embedding
real records, the build agent invents the data shape from spec prose. The resulting
implementation and tests are internally consistent but wrong against production data.
The failure surfaces at Gate 3. The fix is ADR-0006: embed real records before
authoring any data-shape spec. Phase 1 cost: 7 sub-steps rebuilt, 308 tests discarded.

**Missing "why this matters" produces structurally correct but business-wrong sub-steps.**
The build agent resolves spec conflicts by optimizing for technical completeness when
it lacks business framing. It adds validation that should be upstream, misplaces
validity boundaries, and leaves the highest-value failure modes underspecified. ADR-0007
closes this by requiring business framing in every code prompt.

**In-context drift overrides system-prompt rules in long sessions.** When a session
history contains many demonstrations of prohibited behavior, the model follows the
demonstrations, not the rules. Session scope and rule placement both matter; fixing
the rule text without addressing session scope does not fix the bug.

**Rule instances don't generalize to cousins.** A rule scoped to one concrete
failure mode (e.g., macro arithmetic) will leak to related behaviors (date
arithmetic, offset language, script narration, intermediate values) that the rule
did not name. Supervisor asks: is this rule written at the class level or the
instance level?

**Capability prompt iterations have a deploy step that is currently invisible.**
A fix that passes tests may still fail in production if the capability prompt is
cached from a prior session load. Supervisor confirms session reset or prompt
reload before declaring gate 3 open.

---

## Gate discipline

Gate 3 is the production-parity check. Tests can pass and the code-reviewer can
clear and the sub-step can still be broken in production. Gate 3 closes only when
production behavior matches the spec. No sub-step ships without Gate 3 passing.

Sub-step Z is the model for "stop and fix the foundation" sub-steps. When a gate
review surfaces architectural debt that blocks closure, the next sub-step is named
Z (or Z2, Z3) and lands the fix as two commits before the blocked work resumes.

---

## Scope enforcement

Scope is defined at sub-step open. The build agent flags any drift into adjacent
work before taking action. The supervisor confirms scope changes explicitly; silent
expansion is not permitted.

Carry-forwards go to KNOWN_ISSUES.md with priority and a target sub-step.
They are not silently dropped and not fixed out-of-turn without supervisor approval.

---

## Methodology rules

Two methodology rules locked in this version. Both are binding on all future build
cycles. Read the ADRs for full rationale.

**ADR-0006 — real-data sample-records rule.**
`docs/decisions/ADR-0006-real-data-sample-records-rule.md`
Any sub-step that parses or transforms external-system data requires embedded real
records in the build prompt. Spec prose and field tables are not a substitute.

**ADR-0007 — why-this-matters rule.**
`docs/decisions/ADR-0007-why-this-matters-rule.md`
Every code prompt must contain a business-framing section that names the outcome,
the silent-failure mode, and the upstream/downstream dependencies.

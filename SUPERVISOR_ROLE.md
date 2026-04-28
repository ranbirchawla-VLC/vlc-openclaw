# SUPERVISOR_ROLE.md: Vardalux / OpenClaw Build Supervisor

Operating contract for the supervisor role in all NutriOS and OpenClaw agent builds.
The supervisor is Principal Engineer + Product Manager + Architect. The build agent
is the executor; the supervisor owns decisions, gates, and direction changes.

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

## Failure modes the supervisor catches

**Test passing without production parity is a yellow flag, not a green one.**
When a sub-step's tests pass, the supervisor asks: are the test conditions actually
as messy as production? If not, the gate does not clear on tests alone.

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

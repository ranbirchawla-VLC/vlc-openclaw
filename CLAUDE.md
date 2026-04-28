# CLAUDE.md — vlc-openclaw

## Project Overview
Vardalux Collections OpenClaw workspace. Multi-agent system for running our luxury business and some personal time management skills.

This document governs the whole repo. Workspace-specific rules (build order, pipeline definitions, agent-local conventions) live in that workspace's own CLAUDE.md or local doc.


## Core Principle
LLM = synthesis + human judgment. Python = everything deterministic.
If it's math, formatting, templating, or substitutions → Python.
If it's writing, visual assessment, or strategic decisions → micro-skill.

The LLM is a translator, never a calculator. It reads numbers back, it does not derive them. When a user supplies a value, the LLM passes it through verbatim — no inference from names, context, or convention.

**LLM emits zero arithmetic.** Every numeric value in user-facing LLM output must trace to a Python tool return. The LLM does not compute, redistribute, sum, average, or restate-with-recomputed-totals. If a number appears in output, a tool produced it. This rule applies to every capability across every agent in this project. Per-capability prompts may restate this rule for emphasis; they may not weaken or scope-limit it.


## LLM voice rules

**The LLM does not narrate its own process.** Every user-facing turn is
conversational, not procedural.

**Mechanism.** Every user-facing number, date, and structural fact comes
from a tool result. The LLM reads tool-returned values verbatim and never
produces values, dates, or structural facts in its own composition.

**Forbidden patterns and rewrites.**

| Forbidden | Preferred |
|---|---|
| "Today plus 10 weeks is July 5..." | "Your cycle ends July 5." (date returned by tool) |
| "The script takes a single JSON string. One call covers all rows." | (no narration; produce the user-facing result) |
| "Dose day is Sunday (weekday 6), so offset 0 = Sunday, offset 1 = Monday." | "Sunday is dose day. Monday is the day after." |
| "The baseline row is: 1,729 cal, 175g protein..." (then a different tool-returned number) | (suppress the intermediate; show only the final tool-returned value) |
| "Let me compute that for you..." | (call the tool; produce the result) |
| "Your weekly deficit divided by 7 is..." | (call the tool; produce the daily target) |

The list extends when a new cousin surfaces in production. New cousin
equals: new row in the table, plus regression test in the LLM-test suite,
plus capability-prompt patch only if the cousin is capability-specific
(default: no capability-prompt change; the rule lives here).

**For capability-prompt authors.** Capability prompts carry per-capability
phrasing only: output shape, clarification flows, intent-specific framing.
Cross-cutting LLM voice rules live in this section. Capability prompts
reference this section by name and do not restate the forbidden patterns.
The standing instruction the capability prompt must carry: read
tool-returned values verbatim and produce no values, dates, or structural
facts in your own composition.

**Test enforcement.** `assert_no_process_narration` helper in the LLM test
utilities checks every assistant turn against the forbidden patterns
above. Called from every LLM test fixture. Today's seed: zero-arithmetic,
plus the four cousins logged today (date arithmetic in prose, script
description, offset language, intermediate values). Helper extends in
lock-step with the table.

**Missing numeric input: ask, do not infer.** When a metric input is absent
where one is expected, the bot asks for it; never substitutes a default or
inferred value.

### NB-18: Numeric-input unit/scope disambiguation

**Locked behavior: read-back with Yes/No/Change buttons.** Fires on metric
inputs only (cycle plan and check-in: weekly deficit, weight, TDEE, protein
floor, fat ceiling, target calories). Does not fire on food descriptions; the
meal-log path parses naturally and routes corrections through sub-step 5.

When a user supplies a numeric value where unit or scope could be read more
than one way, the bot reads back its assumption in plain language ("Got it,
1850 calorie weekly deficit. Yes?") and shows three buttons:

- **Yes:** value commits, flow advances.
- **No:** bot asks what the user meant in conversation.
- **Change:** bot opens edit on the value or unit.

**Enforcement:** lexical assertion in the LLM-test utility checks that metric
inputs trigger a confirmation turn before the value lands in any tool call.
New ambiguity class found in production: new pattern row plus regression test.


## Test conditions match production conditions

Test fixtures must demonstrate they reproduce the production failure mode they
claim to cover. A new test that closes a production bug is confirmed to fail
against unfixed code before the fix is applied. Test conditions match
production conditions or the test is decorative.

**Specific failure modes (non-exhaustive).**

1. Single-shot LLM tests do not exercise multi-turn state carryover. Multi-turn
   harness required for rules that depend on in-context state.
2. Test fixtures load capability prompts fresh per run; production caches in
   JSONL. Tests must run against the same loading mechanism production uses
   (Decision 1 pattern closes this by construction).
3. Clean fixture arcs do not reproduce messy production arcs (intent bundling,
   embedded constraints, continuity turns, locked-then-changed offers). Multi-turn
   fixtures must reproduce the actual failure shape, not a sanitized version.
4. Intent classification ambiguity: tests assume clean transitions; production
   hands ambiguous turns. Fixtures include the ambiguous case.

5. LLM tests do not pin model or temperature. Tests that run against a different
   model version or with non-zero temperature do not reproduce production conditions.
   LLM tests must pin the model string to the production runtime model (verified at
   session start) and set temperature=0 for determinism. Each LLM test runs 3x
   with require-all-pass: a test that passes in one run but fails in another is
   flaky at temperature=0 and the gate does not clear until all 3 runs pass. Flaky
   tests at temperature=0 indicate an undertested capability or an assertion that
   does not match what the model reliably produces.
6. **Cross-cutting assertion scope.** Cross-cutting LLM rules (voice, narration)
   are enforced via dedicated fixtures, not layered on every per-capability test.
   Per-capability tests assert per-capability behavior (argument correctness,
   tool-call shape, output structure). Layering cross-cutting assertions on every
   test produces cascading failures when the assertion catches a real cousin in
   unrelated code paths. The cross-cutting rule still fires; it fires in its own
   fixture series.

**Gate report extension.** Every sub-step gate report explicitly answers three
questions: "Does this test reproduce the production failure?"; "Did this test
fail against unfixed code before the fix was applied?"; "What model and
temperature were used, and do they match the production agent config?" If any
answer is "no," the gate does not clear.


## Testing Requirements

### TDD is the default
- Test first. Write the failing test, then the implementation. No exceptions for "trivial" code — that's where bugs hide.
- Applies to Python tool logic AND to LLM behavior (see LLM tests below).
- Every Python tool MUST have tests before it is considered complete.
- Do NOT present code as complete until tests pass.
- Run tests after every edit to a test file.
- A test passing is not the same as a test asserting the right thing. When writing or reviewing a test, name the specific behavior under test and verify the assertion would fail if that behavior broke. If you can't construct a failing case the test would catch, the test isn't testing what its name claims.


### Test invocation goes through Make
- First run on a new machine: `make setup` (creates `.venv` and installs workspace dev deps).
- LLM tests require `ANTHROPIC_API_KEY` in the environment, or `~/.openclaw/openclaw.json` present (legacy).
- Always use `make test-*` targets (not raw pytest) to run tests.
- It is always safe to run any `make test-*` target without asking.
- For TDD, prefer the most specific target available.

Standard target naming, portfolio-wide:
- `make test`                            — full suite across all workspaces
- `make test-fast`                       — Python tests only across all workspaces, skip LLM tests
- `make test-<workspace>`                — full suite for one workspace (e.g. `test-nutrios`, `test-watch-listing`)
- `make test-<workspace>-llm`            — LLM tests only for one workspace
- `make test-<workspace>-<scope>`        — narrowest target for TDD (e.g. `test-nutrios-time`)
- `make lint`                            — linter (or no-op for now)

When extending a Makefile, read it first. Add only what's missing. Keep target names and conventions consistent with what's there. If a target name conflicts with current usage, surface — do not rename silently.

Every tool must also be runnable standalone: `python tool_name.py /path/to/_draft.json`. Every tool validates its input against the relevant schema before operating.

### LLM tests are mandatory
LLM behavior is product surface. Bugs there are not caught by Python unit tests.

LLM tests live in `tests/llm/` at each workspace root (separate from `tests/` for Python unit tests, and never nested under `scripts/`). Each LLM test:
- Spins up the actual LLM with the actual capability prompt loaded.
- Sends a scripted conversation turn.
- Asserts on the tool calls made (args + values) AND on the response text (regex / substring / structured assertion).

Standing scenarios every capability gets tested against:
- User supplies all required numeric inputs → tool call args match user input verbatim. Response reads numbers back within ±1 of Python output.
- User omits a required input → LLM asks for it. Does NOT substitute a default, infer from context, or fabricate a value.
- User-chosen names (e.g., "maintenance", "cut") are not treated as constraints. Constraints come from explicit intent fields.
- Response does not describe the script, the JSON arg, or the algorithm.

LLM tests are slow and cost tokens. Run via the workspace's `make test-<workspace>-llm` target, not on every edit. Run before each gate.


## Sub-step Gate Definition

Every sub-step gate has THREE checks. All three required, in order:

### Gate 1: Automated tests pass — Python AND LLM

The gate is automated tests, not a human demo.

- Python unit tests for any logic introduced or modified — `make test-<workspace>` green.
- LLM tests for any capability prompt introduced or modified — `make test-<workspace>-llm` green.
- LLM tests assert on tool-call args and on response text. They are written before the capability prompt is finalized (TDD applies to prompt engineering as much as to Python).

A human running the conversation in Telegram or any chat client is NOT gate 1. That is a smoke test or release check — useful, but not what decides whether work is done.

This rule is a correction from the v3 sub-step 1 build, where Telegram-demo-as-gate let an LLM fabrication bug ship through commit 1. The LLM test that would have caught it (asserting `target_deficit_kcal == 1850` regardless of cycle name) became part of the post-bug fix. Going forward, those tests are written first.

### Gate 2: Code-reviewer subagent in fresh context

Invoke via "run the code-reviewer subagent." Subagent runs in fresh context, reads the diff, applies `Review.md`, returns findings. Output PRINTED TO CLI for the operator to read, not just written to a file.

The operator triages findings: blockers fixed in-pass, non-blockers go to `KNOWN_ISSUES.md` with priority and a target sub-step.

Self-review by the build agent is insufficient. Same model, same blind spots.

### Gate 3: Release check (smoke test)

Operator runs the new capability end-to-end in the real client (Telegram, CLI, whatever the agent's interface is). One pass. Confirms the integrated system behaves as the LLM tests said it would.

If gate 3 surfaces something the LLM tests missed, that's a new LLM test to add — not a reason to relax the gate definition.

Gate 3 is the production-parity check. Tests can pass and the subagent can
clear and the sub-step can still be broken in production. Gate 3 closes only
when production behavior matches the spec. No sub-step ships without Gate 3
passing.


## Commit Discipline

### Two-commit gate pattern
Sub-step gates require TWO commits, not one:

**Commit 1 (pre-review):** all sub-step work landed and gate 1 green (`make test-<workspace>` + `make test-<workspace>-llm`).
Subject line format: `<sub-step>: <summary> [pre-review]`.

**Then invoke the code-reviewer subagent (gate 2).** Operator approves the fix list before any further code change.

**Commit 2 (post-review):** review-driven changes only.
Subject line format: `<sub-step>: address review findings`.

After commit 2, gate 3 (release check). Then squash both commits into one for the long-lived branch per AA §4.11.

The two-commit pattern preserves the review trail; the squash preserves clean history. Both serve different audiences.

### Commit messages
- `[build] tool_name — what was built/fixed` for general work.
- Sub-step gate commits use the `<sub-step>: ...` format above.


## Code Standards
- Python 3.10+
- Minimize external deps. Workspaces declare their own dependencies in their own `pyproject.toml`.
- Error messages to stdout (OpenClaw captures for Slack/Telegram).
- `references/` folders are read-only at runtime.
- Shared data travels through state files (e.g. `_draft.json`, JSON state per agent), not through context.
- Prefer `match/case` over `if/elif` chains when branching on a known value.


## Repo Structure
- `skills/` — OpenClaw skills shared across the workspace.
- `<workspace>/` — agent or pipeline workspaces (e.g. `nutriosv2/`, `watch-listing-workspace/`). Each has its own CLAUDE.md for local rules and its own build order.
- `memory/` — OpenClaw memory files.
- `pipelines/` — pipeline definitions.

Workspace-specific build orders, pipeline specs, and decomposition documents live inside the workspace, not at the repo root.


## Git Workflow

- Never commit directly to main.
- Use feature branches: `feature/<workspace>-<description>` or `feature/step-N-<description>` for pipeline work.
- Long-lived branches squash on green per AA §4.11.
- See Commit Discipline above for the two-commit gate pattern.


## Session Tracking

Maintain a `progress.md` at each workspace root. Append-only log per sub-step. Each entry contains:

- Sub-step number and name (heading).
- Started: ISO timestamp.
- Pre-review commit: sha and test count (Python + LLM).
- Review findings: count of blockers and non-blockers.
- Post-review commit: sha.
- Squash commit on the long-lived feature branch: sha.
- Release check: one-line summary of the operator's smoke test.
- KNOWN_ISSUES added: list, or "none".
- Notes: anything the operator should know in the next session.

Update at gate clear, not mid-sub-step. The operator clears or archives `progress.md` at session boundaries.


## What NOT to Do
- Do not gate sub-steps on a human demo. Gate 1 is automated tests. Human demo is gate 3, the release check.
- Do not rebuild existing assets without explicit instruction.
- Do not delete or modify a monolith skill while a decomposed replacement is in flight.
- Do not combine multiple build steps without confirmation.
- Do not let the LLM substitute a value the user did not supply.
- Do not let the LLM describe Python tools, their inputs, or their algorithms to the user.
- Do not run the code-reviewer subagent against the build agent's own context. Always fresh context.
- Do not skip LLM tests for capabilities that take user-supplied numeric input.
- Do not run raw `pytest`. Always go through a `make test-*` target.
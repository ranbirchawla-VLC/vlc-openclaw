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
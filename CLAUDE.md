# CLAUDE.md — vlc-openclaw

> **Status: interim.** This file describes existing practice across the OpenClaw
> workspace as of May 9, 2026. It is not the designed end-state. The agent-architect
> subagent (Item 5 of the personal-substrate arc) will own OpenClaw runtime canon;
> once it ships, the operator defines the final structure against ADRs and
> accumulated learnings, this file is rewritten, and the existing OpenClaw agents
> get refactored to fit.
>
> The "OpenClaw-Specialty" section below is the migration target: its content
> moves to agent-architect's CANON.md when Item 5 ships.

## Project Overview

Vardalux Collections OpenClaw workspace. Multi-agent system running luxury business operations and personal time management.

## Repo Structure

- `skills/` — OpenClaw skills; do not modify without naming the active commission
- `plugins/` — OpenClaw plugin tools (one plugin per agent)
- `memory/` — OpenClaw memory files
- `pipelines/` — pipeline definitions
- `state/` — runtime state (config files, cache, ledger, cycle outcomes)

## Session-Open Protocol

Each workspace has its own progress file at `<workspace>/progress.md`. Read the file for the workspace the session targets. Do not update `.claude/progress.md`; it is the workspace index only.

## Testing Requirements

- Test runner is `make test-*` targets; per cross-arc structured-runner principle
- `make test` and workspace-scoped targets are always safe to run without asking

## Git Workflow

- Feature branches per task, named for the workstream and step
- Commit after each tool passes tests
- Commit messages: `[build] tool_name — what was built/fixed`

## Code Standards

- Python 3.10+
- `references/` folders are read-only at runtime

---

## OpenClaw-Specialty

> Migration target. Moves to agent-architect's CANON.md when Item 5 ships.
> Content here reflects existing practice; the agent-architect rewrite formalizes
> it against ADRs and locked design.

### Core Principle

LLM does synthesis and human judgment. Python does everything deterministic.

- Math, formatting, templating, substitutions: Python
- Writing, visual assessment, strategic decisions: micro-skill

### OTEL Instrumentation

Top-level functions in any tool or script wrap in spans. Span attributes are consistent within a subproject; per-subproject attribute schemas live with the subproject. Honeycomb exporter wired at the runtime layer; instrumentation is present from day one of any new tool or skill.

### Schema and Config Files

Config files (any file written by strategy and read by automation) follow these rules:

- **No-nulls.** Every field has a concrete factory default at file creation. Fields at default land in a top-level `defaulted_fields` array of dotted paths. Strategy writes remove paths from the array.
- **Per-file `schema_version`.** Required. Consumers read the version, route to the appropriate parser, and fail loud on a newer-than-self version.
- **Audit fields.** `last_updated` (ISO timestamp) and `updated_by` (session id or script name) on every write.

### Tool Conventions

- Every tool runnable standalone: `python tool_name.py /path/to/_draft.json`
- Every tool validates `_draft.json` against the schema before operating

### Inter-Tool Communication

Shared data travels through `_draft.json`, not through context.

### Error Reporting

Error messages go to stdout. OpenClaw runtime captures stdout for Slack and Telegram delivery.
